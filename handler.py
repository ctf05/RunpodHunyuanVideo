import runpod
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64

# Constants for ComfyUI interaction
COMFY_API_AVAILABLE_INTERVAL_MS = 50
COMFY_API_AVAILABLE_MAX_RETRIES = 500
COMFY_POLLING_INTERVAL_MS = int(os.environ.get("COMFY_POLLING_INTERVAL_MS", 250))
COMFY_POLLING_MAX_RETRIES = int(os.environ.get("COMFY_POLLING_MAX_RETRIES", 500))
COMFY_HOST = "127.0.0.1:8188"
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

class HunyuanGenerator:
    def __init__(self):
        # Updated to use /comfyui path
        self.workflow_path = '/comfyui/workflows/hyvideo_t2v_example_01.json'
        self.load_default_workflow()

    def load_default_workflow(self):
        """Load the default workflow template"""
        with open(self.workflow_path, 'r') as f:
            self.workflow_template = json.load(f)

    def update_workflow(self, params: dict) -> dict:
        """Update workflow template with new parameters"""
        workflow = self.workflow_template.copy()
        nodes_dict = workflow['nodes']

        # Update text encode node
        text_node = next(node for node in nodes_dict if node['type'] == 'HyVideoTextEncode')
        if text_node:
            text_node['widgets_values'][0] = params.get('prompt', text_node['widgets_values'][0])
            text_node['widgets_values'][1] = params.get('negative_prompt', text_node['widgets_values'][1])

        # Update sampler node
        sampler_node = next(node for node in nodes_dict if node['type'] == 'HyVideoSampler')
        if sampler_node:
            sampler_node['widgets_values'][0] = params.get('width', sampler_node['widgets_values'][0])
            sampler_node['widgets_values'][1] = params.get('height', sampler_node['widgets_values'][1])
            sampler_node['widgets_values'][2] = params.get('num_frames', sampler_node['widgets_values'][2])
            sampler_node['widgets_values'][3] = params.get('num_inference_steps', sampler_node['widgets_values'][3])

        # Update video combine node
        video_node = next(node for node in nodes_dict if node['type'] == 'VHS_VideoCombine')
        if video_node:
            video_node['widgets_values']['frame_rate'] = params.get('fps', video_node['widgets_values']['frame_rate'])

        return workflow

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
    # Updated to use /comfyui path
    COMFY_OUTPUT_PATH = os.environ.get("COMFY_OUTPUT_PATH", "/comfyui/output")

    # Find video in outputs
    video_info = None
    for node_id, node_output in outputs.items():
        if "videos" in node_output:
            video_info = node_output["videos"][0]
            break

    if not video_info:
        return {"status": "error", "message": "No video found in outputs"}

    # Construct video path
    video_path = os.path.join(COMFY_OUTPUT_PATH, video_info.get("subfolder", ""), video_info["filename"])
    print(f"runpod-worker-comfy - Looking for video at: {video_path}")

    if os.path.exists(video_path):
        # Encode video
        with open(video_path, 'rb') as f:
            video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode('utf-8')

        print("runpod-worker-comfy - Video processed successfully")
        return {
            "status": "success",
            "video": video_b64
        }
    else:
        print("runpod-worker-comfy - Video file not found")
        return {
            "status": "error",
            "message": f"Video file not found at: {video_path}"
        }

def handler(job):
    """Main handler function"""
    try:
        job_input = job["input"]
        if not job_input or "prompt" not in job_input:
            return {"error": "Missing required parameter: prompt"}

        # Extract parameters
        prompt = job_input["prompt"]
        negative_prompt = job_input.get("negative_prompt", "")
        width = job_input.get("width", 512)
        height = job_input.get("height", 512)
        num_frames = job_input.get("num_frames", 16)
        fps = job_input.get("fps", 8)
        num_inference_steps = job_input.get("num_inference_steps", 30)

        # Validate parameters
        if width % 8 != 0 or height % 8 != 0:
            return {"error": "Width and height must be divisible by 8"}
        if width * height > 1024 * 1024:
            return {"error": "Resolution too high"}
        if num_frames > 120:
            return {"error": "Too many frames requested"}

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
            "num_inference_steps": num_inference_steps
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