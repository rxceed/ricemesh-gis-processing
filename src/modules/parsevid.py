import cv2
import os
from pathlib import Path

def video_to_frames(video_path: Path, output_dir: Path, start_sec: float=0.0, end_sec:float=None):
    """
    Extracts frames from a specific section of a video and saves them as PNGs.
    
    Args:
        video_path (str): The path to the input MP4 video file.
        output_dir (str): The directory where the PNG frames will be saved.
        start_sec (float): The time in seconds to start extracting. Defaults to 0.0.
        end_sec (float): The time in seconds to stop extracting. 
        If None, processes until the end of the video.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Open the video using OpenCV
    if video_path.exists():
        cap = cv2.VideoCapture(video_path)
    else:
        vidPathStr = str(video_path)
        pathSplit = vidPathStr.split(".")
        if pathSplit[1] == "mp4":
            newPath = Path(pathSplit[0]+".MP4")
        elif pathSplit[1] == "MP4":
            newPath = Path(pathSplit[0]+".mp4")
        else:
            print(f"Error: File is not in mp4 format")
        cap = cv2.VideoCapture(newPath)

    # Check if the video was opened successfully
    if not cap.isOpened():
        print(f"Error: Could not open video at {video_path}")
        return

    # Get the frames per second (FPS) of the video
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        print("Error: Could not determine FPS of the video.")
        cap.release()
        return

    # Convert seconds to specific frame numbers
    start_frame = int(start_sec * fps)
    end_frame = int(end_sec * fps) if end_sec is not None else float('inf')

    # Jump directly to the starting frame (efficient seeking)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    
    # Keep track of the absolute frame position in the video
    current_frame = start_frame
    saved_count = 0

    print(f"Processing '{video_path}' from {start_sec}s to {end_sec if end_sec else 'end'}s...")
    
    while current_frame < end_frame:
        ret, frame = cap.read()

        if not ret:
            break # Reached the end of the video

        # You can use 'saved_count' to start filenames at 0000, 
        # or 'current_frame' to keep the original video frame index. 
        # Using saved_count here for a clean 0-indexed sequence.
        filename = f"frame_{saved_count:04d}.png"
        filepath = os.path.join(output_dir, filename)

        cv2.imwrite(filepath, frame)

        current_frame += 180
        saved_count += 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

    cap.release()
    print(f"Success! Extracted {saved_count} frames to the '{output_dir}' directory.")

# --- Example Usage ---
if __name__ == "__main__":
    # Replace these with your actual file path and desired output folder
    input_video = Path.joinpath(Path.cwd(), "dataset/DJI_20260415164716_0081_D.mp4").resolve()
    output_folder = Path.joinpath(Path.cwd(), "dataset/parsed/DJI_20260415164716_0081_D").resolve()
    
    # Example: Start at 5.5 seconds and stop at 12 seconds
    start_time = 0
    stop_time = None
    
    video_to_frames(input_video, output_folder, start_sec=start_time, end_sec=stop_time)