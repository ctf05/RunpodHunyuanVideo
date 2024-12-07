import os
import json
import base64
import time
import csv
import requests
import cv2
from datetime import datetime
import tempfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key
API_KEY = os.getenv('RUNPOD_API_KEY')
if not API_KEY:
    raise ValueError("RUNPOD_API_KEY not found in environment variables")

# Headers for all requests
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# Configuration
PROMPT_PATH = "prompts/exec.txt"  # Path to prompt file
COST_PER_SECOND = 0.00053  # Cost per second of generation
RUNPOD_ENDPOINT = "https://api.runpod.ai/v2/lgm5rz8ogoqvgp/run"  # HunyuanVideo endpoint
RUNPOD_STATUS_ENDPOINT = "https://api.runpod.ai/v2/lgm5rz8ogoqvgp/status"  # Status endpoint
INPUT_CONFIG_PATH = "inputs/default.json"  # Path to input configuration
OUTPUT_CSV_PATH = "generation_stats.csv"  # Path to output CSV file
VIDEO_OUTPUT_DIR = "videos"  # Directory to save output videos
PREVIEW_OUTPUT_DIR = "previews"  # Directory to save preview images
POLLING_INTERVAL = 0.5  # Polling interval in seconds

def read_prompt(prompt_path: str) -> str:
    """Read prompt from file."""
    try:
        with open(prompt_path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        raise Exception(f"Prompt file not found at {prompt_path}")

def prepare_input_data(config_path: str, prompt: str) -> [dict, dict]:
    """Prepare input data from config and prompt."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            input = config.copy()
    except FileNotFoundError:
        raise Exception(f"Config file not found at {config_path}")

    # Add prompt to config
    input["prompt"] = prompt

    return input, config

def save_generation_stats(stats: dict):
    """Save generation statistics to CSV."""
    file_exists = os.path.exists(OUTPUT_CSV_PATH)

    with open(OUTPUT_CSV_PATH, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=stats.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(stats)

def display_video(video_data: bytes):
    """Display the video using OpenCV."""
    # Create a temporary file to store the video
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
        temp_file.write(video_data)
        temp_path = temp_file.name

    try:
        # Open the video file
        cap = cv2.VideoCapture(temp_path)

        if not cap.isOpened():
            print("Error: Could not open video.")
            return

        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        frame_time = int(1000/fps)  # Time in milliseconds between frames

        # Create window
        window_name = "Generated Video"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                # If we reach the end, loop back to the beginning
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            cv2.imshow(window_name, frame)

            # Wait between frames and check for 'q' press to quit
            if cv2.waitKey(frame_time) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

    finally:
        # Clean up the temporary file
        os.unlink(temp_path)

def wait_for_completion(job_id: str) -> dict:
    """Poll the status endpoint until job is complete."""
    while True:
        response = requests.get(
            f"{RUNPOD_STATUS_ENDPOINT}/{job_id}",
            headers=HEADERS
        )

        if response.status_code != 200:
            raise Exception(f"Status check failed with code {response.status_code}: {response.text}")

        status_data = response.json()
        status = status_data.get("status")

        if status == "COMPLETED":
            return status_data.get("output", {})
        elif status in ["FAILED", "CANCELLED"]:
            raise Exception(f"Job {job_id} {status.lower()}: {status_data.get('error', 'Unknown error')}")

        time.sleep(POLLING_INTERVAL)

def sanitize_filename(config: dict) -> str:
    """Create a safe filename from config data."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"hunyuan_video_{timestamp}.mp4"

def main():
    try:
        # Create output directories if they don't exist
        os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
        os.makedirs(PREVIEW_OUTPUT_DIR, exist_ok=True)

        # Read prompt
        prompt = read_prompt(PROMPT_PATH)
        print(f"Using prompt: {prompt}")

        # Prepare input data
        input_data, config = prepare_input_data(INPUT_CONFIG_PATH, prompt)
        print("\nInput configuration:")
        print(json.dumps(input_data, indent=2))

        # Record start time
        start_time = time.time()

        # Make request to RunPod endpoint to start the job
        response = requests.post(
            RUNPOD_ENDPOINT,
            json={"input": input_data},
            headers=HEADERS
        )

        # Calculate duration and cost (for initial request)
        duration = time.time() - start_time
        cost = duration * COST_PER_SECOND

        if response.status_code == 200:
            # Get job ID from response
            job_data = response.json()
            job_id = job_data.get("id")

            if not job_id:
                raise Exception("No job ID in response")

            print(f"\nJob started with ID: {job_id}")
            print("Waiting for completion...")

            try:
                # Wait for job completion and get result
                result = wait_for_completion(job_id)
                duration = time.time() - start_time  # Update duration to include polling time
                cost = duration * COST_PER_SECOND  # Update cost

                print("\nGeneration successful!")
                print(f"Generation took {duration:.2f} seconds")
                print(f"Estimated cost: ${cost:.4f}")

                # Save statistics
                stats = {
                    "timestamp": datetime.now().isoformat(),
                    "prompt": prompt,
                    "height": input_data.get("height", "N/A"),
                    "width": input_data.get("width", "N/A"),
                    "num_frames": input_data.get("num_frames", "N/A"),
                    "fps": input_data.get("fps", "N/A"),
                    "num_inference_steps": input_data.get("num_inference_steps", "N/A"),
                    "duration_seconds": f"{duration:.2f}",
                    "cost_usd": f"{cost:.4f}",
                    "status": "success"
                }
                save_generation_stats(stats)

                # Save and display video and preview if they're in the response
                if "base64_video" in result:
                    print("\nDisplaying generated video (press 'q' to close)")
                    video_data = base64.b64decode(result["base64_video"])

                    # Save video
                    output_filename = os.path.join(VIDEO_OUTPUT_DIR, sanitize_filename(config))
                    with open(output_filename, 'wb') as f:
                        f.write(video_data)
                    print(f"Video saved to: {output_filename}")

                    # Display video
                    display_video(video_data)

                    # Save preview if available
                    if "base64_preview" in result:
                        preview_data = base64.b64decode(result["base64_preview"])
                        preview_filename = output_filename.replace('.mp4', '_preview.png')
                        preview_path = os.path.join(PREVIEW_OUTPUT_DIR, os.path.basename(preview_filename))
                        with open(preview_path, 'wb') as f:
                            f.write(preview_data)
                        print(f"Preview saved to: {preview_path}")

            except Exception as e:
                print(f"\nJob failed: {str(e)}")

                # Save error statistics
                stats = {
                    "timestamp": datetime.now().isoformat(),
                    "prompt": prompt,
                    "height": input_data.get("height", "N/A"),
                    "width": input_data.get("width", "N/A"),
                    "num_frames": input_data.get("num_frames", "N/A"),
                    "fps": input_data.get("fps", "N/A"),
                    "num_inference_steps": input_data.get("num_inference_steps", "N/A"),
                    "duration_seconds": f"{duration:.2f}",
                    "cost_usd": f"{cost:.4f}",
                    "status": "error"
                }
                save_generation_stats(stats)

        else:
            print("\nJob submission failed!")
            print(f"Status code: {response.status_code}")
            print(f"Error: {response.text}")

            # Save error statistics
            stats = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "height": input_data.get("height", "N/A"),
                "width": input_data.get("width", "N/A"),
                "num_frames": input_data.get("num_frames", "N/A"),
                "fps": input_data.get("fps", "N/A"),
                "num_inference_steps": input_data.get("num_inference_steps", "N/A"),
                "duration_seconds": f"{duration:.2f}",
                "cost_usd": f"{cost:.4f}",
                "status": "error"
            }
            save_generation_stats(stats)

    except Exception as e:
        print(f"\nError occurred: {str(e)}")

if __name__ == "__main__":
    main()