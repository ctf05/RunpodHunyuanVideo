import runpod
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
from PIL import Image
from io import BytesIO

# Constants for ComfyUI interaction
COMFY_API_AVAILABLE_INTERVAL_MS = 100
COMFY_API_AVAILABLE_MAX_RETRIES = 1000
COMFY_POLLING_INTERVAL_MS = 250
COMFY_POLLING_MAX_RETRIES = 50000
COMFY_HOST = "127.0.0.1:8188"
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"
MIN_GENERATION_PIXELS = 512 * 320
MAX_GENERATION_TOTAL = 500 * 500 * 100

def resize_and_compress_image(image_bytes, target_width, target_height):
    """Resize and compress the preview image"""
    # Open the image from bytes
    img = Image.open(BytesIO(image_bytes))

    # Resize the image
    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Save the compressed image to bytes
    output_buffer = BytesIO()
    img.save(output_buffer, format='JPEG', quality=85, optimize=True)
    return output_buffer.getvalue()

def calculate_generation_dimensions(target_width, target_height):
    target_ratio = target_width / target_height
    width = 8
    height = 8

    while width * height < MIN_GENERATION_PIXELS:
        current_ratio = width / height

        if current_ratio < target_ratio:
            width += 8
        else:
            height += 8

    return width, height

class HunyuanGenerator:
    def __init__(self):
        self.workflow_path = '/comfyui/workflows/workflow.json'
        self.load_default_workflow()

    def load_default_workflow(self):
        """Load the default workflow template"""
        with open(self.workflow_path, 'r') as f:
            self.workflow_template = f.read()

    def update_workflow(self, params: dict) -> dict:
        """Update workflow template with new parameters using string replacement"""
        workflow_str = self.workflow_template

        # Replace all placeholders
        replacements = {
            '|prompt|': str(params.get('prompt')),
            '|base_width|': str(params.get('base_width')),
            '|base_height|': str(params.get('base_height')),
            '|target_width|': str(params.get('target_width')),
            '|target_height|': str(params.get('target_height')),
            '|num_frames|': str(params.get('num_frames')),
            '|num_inference_steps|': str(params.get('num_inference_steps')),
            '|fps|': str(params.get('fps')),
            '|guidance_scale|': str(params.get('guidance_scale')),
            '|flow_shift|': str(params.get('flow_shift'))
        }

        for placeholder, value in replacements.items():
            workflow_str = workflow_str.replace(placeholder, value)

        return json.loads(workflow_str)

def check_server(url, retries=500, delay=50):
    """Check if ComfyUI server is reachable"""
    for i in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"runpod-worker-comfy - API is reachable")
                return True
        except requests.RequestException:
            pass
        time.sleep(delay / 1000)

    print(f"runpod-worker-comfy - Failed to connect to server at {url} after {retries} attempts.")
    return False

def queue_workflow(workflow):
    """Queue a workflow to be processed by ComfyUI"""
    data = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_history(prompt_id):
    """Get workflow execution history"""
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as response:
        return json.loads(response.read())

def process_output_video(outputs, job_id, target_width, target_height, video_index=None):
    """Process video outputs from ComfyUI"""
    # Find gif outputs which contain video and workflow preview
    video_info = None
    for node_id, node_output in outputs.items():
        if "gifs" in node_output:
            video_info = node_output["gifs"][0]
            break

    if not video_info:
        print(f"runpod-worker-comfy - Available outputs: {outputs}")
        return {"status": "error", "message": "No video found in outputs"}

    # Construct paths directly to known locations
    video_path = f"/comfyui/output/{video_info['filename']}"
    workflow_path = f"/comfyui/output/{video_info['workflow']}"

    print(f"runpod-worker-comfy - Looking for files:")
    print(f"Video: {video_path}")
    print(f"Workflow: {workflow_path}")

    if os.path.exists(video_path) and os.path.exists(workflow_path):
        # Encode video and workflow preview
        with open(video_path, 'rb') as f:
            video_bytes = f.read()
        with open(workflow_path, 'rb') as f:
            workflow_bytes = f.read()

        # Resize and compress the workflow preview
        if video_index == 0:
            workflow_bytes = resize_and_compress_image(workflow_bytes, target_width, target_height)

        video_b64 = base64.b64encode(video_bytes).decode('utf-8')
        workflow_b64 = base64.b64encode(workflow_bytes).decode('utf-8')

        print("runpod-worker-comfy - Video and workflow preview processed successfully")
        return {
            "status": "success",
            "video": video_b64,
            "workflow_preview": workflow_b64
        }
    else:
        missing = []
        if not os.path.exists(video_path):
            missing.append("video")
        if not os.path.exists(workflow_path):
            missing.append("workflow preview")
        print(f"runpod-worker-comfy - Could not find: {', '.join(missing)}")
        return {
            "status": "error",
            "message": f"Could not find files: {', '.join(missing)}"
        }

def validate_frame_count(num_frames):
    """Ensure frame count follows HunyuanVideo requirements"""
    if (num_frames - 1) % 4 != 0:
        # Round up to next valid frame count
        num_frames = ((num_frames - 1) // 4 * 4) + 5
    return num_frames

def handler(job):
    """Main handler function"""
    try:
        job_input = job["input"]
        if not job_input or "prompt" not in job_input:
            return {"error": "Missing required parameter: prompt"}

        # Extract parameters
        prompt = job_input.get("prompt", "high quality nature video of a red panda balancing on a bamboo stick while a bird lands on the panda's head, there's a waterfall in the background")
        target_width = job_input.get("target_width", 512)
        target_height = job_input.get("target_height", 288)

        prompt = prompt + ". really fast motion"

        # Calculate optimal generation dimensions
        try:
            base_width, base_height = calculate_generation_dimensions(target_width, target_height)
        except ValueError as e:
            return {"error": str(e)}

        num_frames = validate_frame_count(job_input.get("num_frames", 17))
        fps = job_input.get("fps", 24) / 2 # We double the fps in the workflow
        num_inference_steps = job_input.get("num_inference_steps", 25)
        guidance_scale = job_input.get("guidance_scale", 6)
        flow_shift = job_input.get("flow_shift", 2)
        video_index = job_input.get("video_index", None)

        # Validate total size
        if base_width * base_height * num_frames > MAX_GENERATION_TOTAL:
            print(f"runpod-worker-comfy - Total size exceeds maximum allowed: {base_width}x{base_height}x{num_frames}")
            return {"error": "Width * height * num_frames exceeds maximum allowed"}

        # Check if ComfyUI is available
        if not check_server(f"http://{COMFY_HOST}"):
            return {"error": "ComfyUI server not available"}

        # Clear history
        requests.post(f"http://{COMFY_HOST}/history", json={"clear": True})

        # Prepare and update workflow
        generator = HunyuanGenerator()
        workflow = generator.update_workflow({
            "prompt": prompt,
            "base_width": base_width,
            "base_height": base_height,
            "target_width": target_width,
            "target_height": target_height,
            "num_frames": num_frames,
            "fps": fps,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "flow_shift": flow_shift
        })

        # Queue workflow
        try:
            queued = queue_workflow(workflow)
            prompt_id = queued["prompt_id"]
            print(f"runpod-worker-comfy - queued workflow with ID {prompt_id}")
        except Exception as e:
            return {"error": f"Error queuing workflow: {str(e)}"}

        # Poll for completion
        print("runpod-worker-comfy - waiting for video generation")
        retries = 0
        while retries < COMFY_POLLING_MAX_RETRIES:
            history = get_history(prompt_id)

            if prompt_id in history and history[prompt_id].get("outputs"):
                # Process output video with target dimensions
                result = process_output_video(history[prompt_id]["outputs"], job["id"], target_width, target_height, video_index)
                if result["status"] == "success":
                    if video_index == 0:
                        return {
                            "base64_video": result["video"],
                            "base64_preview": result["workflow_preview"]
                        }
                    else:
                        return {"base64_video": result["video"]}
                else:
                    return {"error": result["message"]}

            time.sleep(COMFY_POLLING_INTERVAL_MS / 1000)
            retries += 1

        return {"error": "Timeout waiting for video generation"}

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})