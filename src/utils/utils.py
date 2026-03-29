import re

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