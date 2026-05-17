import cv2
from pathlib import Path
from argparse import ArgumentParser
import time

def video_to_frames(video_path: Path, output_dir: Path, start_sec: float=0.0, end_sec:float=None, frame_interval:int=1, compression:int=0, resize: tuple=None, on_progress=None, save_to_db=None) -> tuple[int, Path]:
    """
    Extracts frames from a specific section of a video and saves them as PNGs.
    
    Args:
        video_path (str): The path to the input MP4 video file.
        output_dir (str): The directory where the PNG frames will be saved.
        start_sec (float): The time in seconds to start extracting. Defaults to 0.0.
        end_sec (float): The time in seconds to stop extracting. 
        If None, processes until the end of the video.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Open the video using OpenCV
    if not video_path.exists():
        raise FileNotFoundError(f"Error: Video file not found at {video_path}")
    
    cap = cv2.VideoCapture(str(video_path))

    # Check if the video was opened successfully
    if not cap.isOpened():
        raise Exception(f"Error: Could not open video at {video_path}")

    # Get the frames per second (FPS) of the video
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        cap.release()
        raise Exception("Could not determine FPS of the video.")

    # Convert seconds to specific frame numbers
    start_frame = int(start_sec * fps)
    
    # Get total video frames to handle None end_sec or out-of-bounds end_sec
    video_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if end_sec is not None:
        end_frame = min(int(end_sec * fps), video_total_frames)
    else:
        end_frame = video_total_frames
        
    # Jump directly to the starting frame (efficient seeking)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    
    # Keep track of the absolute frame position in the video
    current_frame = start_frame
    saved_count = 0

    print(f"Processing '{video_path}' from {start_sec}s to {end_sec if end_sec else 'end'}s with {frame_interval} frames interval and {compression} PNG compression...")
    total_frames = max(1, int((end_frame - start_frame) / frame_interval))
    while current_frame < end_frame:
        ret, frame = cap.read()
        if not ret:
            break # Reached the end of the video
        if resize is not None:
            frame = cv2.resize(frame, resize)
        # You can use 'saved_count' to start filenames at 0000, 
        # or 'current_frame' to keep the original video frame index. 
        # Using saved_count here for a clean 0-indexed sequence.
        filename = f"frame_{saved_count:04d}.png"
        filepath = Path.joinpath(output_dir, filename)

        cv2.imwrite(filepath, frame, [cv2.IMWRITE_PNG_COMPRESSION, compression])

        current_frame += frame_interval
        saved_count += 1
        if on_progress is not None:
            on_progress(saved_count, total_frames)
        if save_to_db is not None:
            save_to_db(filepath, saved_count)
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

    cap.release()
    return saved_count, output_dir

def main(input_val, start, end, interval, compression, resize):
    t_start = time.perf_counter()
    if input_val:
        input_path_str = str(input_val)
        input_video = Path(input_path_str).resolve()
        input_parent_path = input_video.parent
        input_file_name = input_video.stem
        output_folder = input_parent_path / f"parsed_{input_file_name}"
    else:
        print("No input path provided")
        return
    count, output_dir = video_to_frames(input_video, output_folder, start, end, interval, compression, resize)
    t_end = time.perf_counter()
    print(f"Parsing completed in {t_end-t_start} seconds. {count} frames saved to {output_dir}")

# --- Example Usage ---
if __name__ == "__main__":
    arg_parser = ArgumentParser()
    arg_parser.add_argument("input", type=str, help="file path to input video relative to working directory")
    arg_parser.add_argument("-s", "--start-sec", type=float, help="starting point of the video that want to be parsed in seconds")
    arg_parser.add_argument("-e","--end-sec", type=float, help="ending point of the video that want to be parsed in seconds")
    arg_parser.add_argument("-f", "--frame-interval", type=int, help="frame interval of the parser")
    arg_parser.add_argument("-c", "--compression", type=int, help="image PNG compression on a scale from 0 (no compression) to 9 (max compression)")
    arg_parser.add_argument("--resize", type=str, help="resize the frames to the specified dimensions in WxH (e.g., 1920x1080)")
    args = arg_parser.parse_args()

    start_time = 0.0
    stop_time = None
    interval = 1
    compression = 0
    resize_val = None
    
    if args.start_sec:
        start_time = float(args.start_sec)
    if args.end_sec:
        stop_time = float(args.end_sec)
    if args.frame_interval:
        interval = int(args.frame_interval)
    if args.compression:
        compression = max(0, min(9, int(args.compression)))
    if args.resize:
        resize_val = tuple(map(int, args.resize.split('x')))

    main(args.input, start_time, stop_time, interval, compression, resize_val)
