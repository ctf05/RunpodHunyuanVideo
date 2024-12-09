import runpod
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64

# Constants for ComfyUI interaction
COMFY_API_AVAILABLE_INTERVAL_MS = 100
COMFY_API_AVAILABLE_MAX_RETRIES = 1000
COMFY_POLLING_INTERVAL_MS = 250
COMFY_POLLING_MAX_RETRIES = 50000
COMFY_HOST = "127.0.0.1:8188"
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

class HunyuanGenerator:
    def __init__(self):
        self.workflow_path = '/comfyui/workflows/hyvideo_t2v_example_01.json'
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
            '|prompt|': params.get('prompt'),
            '|negative_prompt|': params.get('negative_prompt'),
            '|width|': str(params.get('width')),
            '|height|': str(params.get('height')),
            '|num_frames|': str(params.get('num_frames')),
            '|steps|': str(params.get('num_inference_steps')),
            '|fps|': str(params.get('fps')),
            '|guidance_scale|': str(params.get('guidance_scale')),
            '|flow_shift|': str(params.get('flow_shift'))
        }

        for placeholder, value in replacements.items():
            workflow_str = workflow_str.replace(placeholder, value)

        return json.loads(workflow_str)

def wait_for_comfyui_ready():
    """Wait for ComfyUI to be fully initialized and ready"""
    for i in range(COMFY_API_AVAILABLE_MAX_RETRIES):
        try:
            # Test prompt endpoint with empty prompt
            data = json.dumps({"prompt": {}}).encode("utf-8")
            req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=data)
            response = urllib.request.urlopen(req)
            print(f"ComfyUI response: {response.read().decode('utf-8')}")
            print(f"ComfyUI response code: {response.getcode()}")

            response_data = json.loads(response.read().decode('utf-8'))
            if isinstance(response_data, dict) and response_data.get('type') == 'prompt_no_outputs':
                print(f"ComfyUI ready after {i+1} attempts")
                return True
        except Exception as e:
            if i == 0:  # Only print on first attempt
                print(f"Waiting for ComfyUI to initialize...")
            time.sleep(COMFY_API_AVAILABLE_INTERVAL_MS / 1000)
            continue
    print("Failed to confirm ComfyUI readiness")
    return False

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

def process_output_video(outputs, job_id):
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
        # Wait for ComfyUI to be fully initialized
        if not wait_for_comfyui_ready():
            return {"error": "ComfyUI not fully initialized after waiting"}

        job_input = job["input"]
        if not job_input or "prompt" not in job_input:
            return {"error": "Missing required parameter: prompt"}

        # Extract parameters
        prompt = job_input.get("prompt", "high quality nature video of a red panda balancing on a bamboo stick while a bird lands on the panda's head, there's a waterfall in the background")
        negative_prompt = job_input.get("negative_prompt", "bad quality video")
        width = job_input.get("width", 512)
        height = job_input.get("height", 288)
        num_frames = validate_frame_count(job_input.get("num_frames", 17))
        fps = job_input.get("fps", 12)
        num_inference_steps = job_input.get("num_inference_steps", 30)
        guidance_scale = job_input.get("guidance_scale", 6)
        flow_shift = job_input.get("flow_shift", 9)

        # Validate parameters
        if width % 8 != 0 or height % 8 != 0:
            return {"error": "Width and height must be divisible by 8"}
        if width * height > 1024 * 592 * 72:
            return {"error": "Resolution * num_frames too high"}

        # Check if ComfyUI is available
        if not check_server(f"http://{COMFY_HOST}"):
            return {"error": "ComfyUI server not available"}

        # Prepare and update workflow
        generator = HunyuanGenerator()
        workflow = generator.update_workflow({
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
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
                # Process output video
                result = process_output_video(history[prompt_id]["outputs"], job["id"])
                if result["status"] == "success":
                    return {
                        "base64_video": result["video"],
                        "base64_preview": result["workflow_preview"],
                        "refresh_worker": REFRESH_WORKER
                    }
                else:
                    return {"error": result["message"]}

            time.sleep(COMFY_POLLING_INTERVAL_MS / 1000)
            retries += 1

        return {"error": "Timeout waiting for video generation"}

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})