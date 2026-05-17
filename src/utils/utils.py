import re
import math
from pathlib import Path

def dms_to_decimal(dms_str):
    """
    Converts a DMS string (e.g., '7° 27\' 0" S') to a decimal float.
    Also handles plain float strings.
    """
    # If it's already a float/int, just return it
    try:
        return float(dms_str)
    except ValueError:
        pass

    # Regex to capture: degrees, minutes, seconds, and direction
    # Format: 7^ 27' 0" S
    parts = re.search(r'(\d+)o\s*(\d+)\'\s*([\d.]+)"\s*([NSEW])', dms_str, re.IGNORECASE)
    
    if not parts:
        raise ValueError(f"Could not parse coordinate: {dms_str}. Use format like '7o 27\' 0\" S'")

    degrees = float(parts.group(1))
    minutes = float(parts.group(2))
    seconds = float(parts.group(3))
    direction = parts.group(4).upper()

    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)

    if direction in ['S', 'W']:
        decimal *= -1
        
    return decimal

def create_bounding_box(center_lat, center_lon, area_ha):
    """Calculates a square bounding box around decimal coordinates."""
    # Convert hectares to square meters
    side_m = math.sqrt(area_ha * 10000)
    dist_m = side_m / 2
    
    # Earth conversions
    delta_lat = dist_m / 111320.0
    delta_lon = dist_m / (111320.0 * math.cos(math.radians(center_lat)))
    
    return [center_lon - delta_lon, center_lat - delta_lat, 
            center_lon + delta_lon, center_lat + delta_lat]

def read_video_metadata(file_path: Path) -> dict:
    """
    Extract fps, duration, codec, and resolution from a video file on disk.
    Raises RuntimeError if the file has no video track or cannot be parsed.
    """
    from pymediainfo import MediaInfo
    

    info = MediaInfo.parse(file_path)
    if not info or not info.tracks:
        raise RuntimeError(f"MediaInfo returned no tracks for {file_path}")

    video_track = next(
        (t for t in info.tracks if t.track_type == "Video"), None
    )
    if not video_track:
        raise RuntimeError(f"No video track found in {file_path}")

    return {
        "fps":        float(video_track.frame_rate or 0),
        "duration":   float(video_track.duration or 0) / 1000,
        "codec":      video_track.format or "unknown",
        "resolution": {
            "width":  int(video_track.width or 0),
            "height": int(video_track.height or 0),
        },
    }