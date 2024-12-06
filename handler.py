import os
import time
import base64
import runpod
import torch
import asyncio
from typing import Dict, Any, Optional
import json
import sys

# Add ComfyUI to path
comfy_path = os.path.join(os.path.dirname(__file__), 'ComfyUI')
sys.path.append(comfy_path)
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'

# Import ComfyUI components
import nodes
import folder_paths
import server
from execution import PromptExecutor

# Constants
COMFY_PORT = int(os.environ.get('COMFY_PORT', 8188))
MAX_RETRIES = 100
RETRY_DELAY = 0.5

class HunyuanGenerator:
    def __init__(self):
        self.workflow_path = os.path.join(os.path.dirname(__file__), 'workflows/hyvideo_t2v_example_01.json')
        self.initialized = False
        self.executor = None
        self.load_default_workflow()

    def load_default_workflow(self):
        """Load the default workflow template"""
        with open(self.workflow_path, 'r') as f:
            self.workflow_template = json.load(f)

    def initialize(self):
        """Initialize ComfyUI if not already initialized"""
        if not self.initialized:
            # Load custom nodes
            nodes.init_custom_nodes()

            # Initialize server
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            server.PromptServer.instance = server.PromptServer(loop)

            # Initialize executor
            self.executor = PromptExecutor()

            # Start server
            server.PromptServer.instance.start()

            self.initialized = True

    def update_workflow(self, params: Dict[str, Any]) -> Dict:
        """Update workflow template with new parameters"""
        workflow = self.workflow_template.copy()

        # Update nodes dict to match actual workflow
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

    async def execute_workflow(self, workflow: Dict) -> Dict:
        """Execute workflow and return results"""
        prompt_id = await server.PromptServer.instance.prompt_queue.put(workflow)

        # Poll for completion
        retries = 0
        while retries < MAX_RETRIES:
            if prompt_id in server.PromptServer.instance.prompt_queue.history:
                history = server.PromptServer.instance.prompt_queue.history[prompt_id]
                if 'outputs' in history:
                    return history['outputs']

            await asyncio.sleep(RETRY_DELAY)
            retries += 1

        raise RuntimeError("Timeout waiting for workflow execution")

    def generate(
            self,
            prompt: str,
            negative_prompt: str = "",
            width: int = 512,
            height: int = 512,
            num_frames: int = 16,
            fps: int = 8,
            num_inference_steps: int = 30,
            seed: Optional[int] = None,
    ) -> bytes:
        """Generate video based on input parameters"""
        try:
            self.initialize()

            # Set random seed if provided
            if seed is not None:
                torch.manual_seed(seed)

            # Prepare parameters
            params = {
                'prompt': prompt,
                'negative_prompt': negative_prompt,
                'width': width,
                'height': height,
                'num_frames': num_frames,
                'num_inference_steps': num_inference_steps,
                'fps': fps
            }

            # Update workflow with parameters
            workflow = self.update_workflow(params)

            # Create event loop if it doesn't exist
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Execute workflow
            outputs = loop.run_until_complete(self.execute_workflow(workflow))

            # Find the video output
            video_path = None
            for node_id, node_output in outputs.items():
                if 'videos' in node_output:
                    video_path = os.path.join(
                        folder_paths.get_output_directory(),
                        node_output['videos'][0]['filename']
                    )
                    break

            if not video_path or not os.path.exists(video_path):
                raise RuntimeError("Video file not found in outputs")

            # Read video file
            with open(video_path, 'rb') as f:
                video_bytes = f.read()

            return video_bytes

        except Exception as e:
            raise RuntimeError(f"Video generation failed: {str(e)}")

def encode_video_base64(video_bytes: bytes) -> str:
    """Encode video bytes to base64 string"""
    return base64.b64encode(video_bytes).decode('utf-8')

# Initialize generator
generator = HunyuanGenerator()

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """Runpod handler function"""
    try:
        job_input = event["input"]

        if "prompt" not in job_input:
            return {"error": "Missing required parameter: prompt"}

        # Extract parameters
        prompt = job_input["prompt"]
        negative_prompt = job_input.get("negative_prompt", "")
        width = job_input.get("width", 512)
        height = job_input.get("height", 512)
        num_frames = job_input.get("num_frames", 16)
        fps = job_input.get("fps", 8)
        num_inference_steps = job_input.get("num_inference_steps", 30)
        seed = job_input.get("seed", None)

        # Validate parameters
        if width % 8 != 0 or height % 8 != 0:
            return {"error": "Width and height must be divisible by 8"}
        if width * height > 1024 * 1024:  # 1MP limit
            return {"error": "Resolution too high"}
        if num_frames > 120:
            return {"error": "Too many frames requested"}

        start_time = time.time()

        # Generate video
        video_bytes = generator.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_frames=num_frames,
            fps=fps,
            num_inference_steps=num_inference_steps,
            seed=seed
        )

        base64_video = encode_video_base64(video_bytes)
        process_duration = time.time() - start_time

        return {
            "base64_video": base64_video,
            "metadata": {
                "fps": fps,
                "duration": process_duration,
                "resolution": {"height": height, "width": width},
                "num_frames": num_frames
            }
        }

    except Exception as e:
        return {"error": str(e)}

# Start the serverless handler
runpod.serverless.start({"handler": handler})