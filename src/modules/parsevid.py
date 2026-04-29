import cv2
from pathlib import Path
from argparse import ArgumentParser
import time

def video_to_frames(video_path: Path, output_dir: Path, start_sec: float=0.0, end_sec:float=None, frame_interval:int=1, compression:int=0) -> tuple[int, Path]:
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
            raise Exception(f"Error: File is not in mp4 format")
        cap = cv2.VideoCapture(newPath)

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
    end_frame = int(end_sec * fps) if end_sec is not None else float('inf')
    # Jump directly to the starting frame (efficient seeking)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    
    # Keep track of the absolute frame position in the video
    current_frame = start_frame
    saved_count = 0

    #print(f"Processing '{video_path}' from {start_sec}s to {end_sec if end_sec else 'end'}s with {interval} frames interval and {compression} PNG compression...")

    while current_frame < end_frame:
        ret, frame = cap.read()

        if not ret:
            break # Reached the end of the video
        
        frame = cv2.resize(frame, (1920, 1080))
        # You can use 'saved_count' to start filenames at 0000, 
        # or 'current_frame' to keep the original video frame index. 
        # Using saved_count here for a clean 0-indexed sequence.
        filename = f"frame_{saved_count:04d}.png"
        filepath = Path.joinpath(output_dir, filename)

        cv2.imwrite(filepath, frame, [cv2.IMWRITE_PNG_COMPRESSION, compression])

        current_frame += frame_interval
        saved_count += 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

    cap.release()
    return saved_count, output_dir

def main(input, start, end, interval, compression):
    t_start = time.perf_counter()
    if input:
        input_path_str = str(args.input)
        input_parent_path = Path(args.input).parent.resolve()
        input_file_name = ((input_path_str.split("/"))[-1].split("."))[0]
        output_path = Path.joinpath(input_parent_path, "parsed_"+input_file_name)
        input_video = Path.joinpath(Path.cwd(), input_path_str).resolve()
        output_folder = Path.joinpath(Path.cwd(), output_path).resolve()
    else:
        print("No input path provided")
        return
    count, output_dir = video_to_frames(input_video, output_folder, start, end, interval, compression)
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
    args = arg_parser.parse_args()

    start_time = 0
    stop_time = None
    interval = None
    input_path_str = None
    compression = None
    
    if args.input:
        input_path_str = str(args.input)
    if args.start_sec:
        start_time = float(args.start_sec)
    if args.end_sec:
        stop_time = float(args.end_sec)
    if args.frame_interval:
        interval = int(args.frame_interval)
    if args.compression:
        if int(args.compression) < 0:
            compression = 0
        elif int(args.compression) > 9:
            compression = 9
        else:
            compression = int(args.compression)
    
    main(input_path_str, start_time, stop_time, interval, compression)