"""
Time utility functions for consistent timestamp formatting across the application.

This module centralizes all time-related utilities to ensure consistency
between subtitle generation, translation, and other time-sensitive operations.
"""

from datetime import timedelta


def format_timestamp(seconds: float) -> str:
    """
    Convert seconds to SRT/VTT timestamp format (HH:MM:SS,mmm).
    
    Args:
        seconds: Time in seconds (can be fractional)
        
    Returns:
        Formatted timestamp string like "00:01:23,456"
        
    Example:
        >>> format_timestamp(83.456)
        '00:01:23,456'
    """
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - int(seconds)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_timestamp(timestamp: str) -> float:
    """
    Parse SRT/VTT timestamp format to seconds.
    
    Args:
        timestamp: Timestamp string like "00:01:23,456" or "00:01:23.456"
        
    Returns:
        Time in seconds as float
        
    Example:
        >>> parse_timestamp("00:01:23,456")
        83.456
    """
    # Replace comma with dot for consistent parsing
    normalized = timestamp.replace(",", ".")
    
    parts = normalized.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = "0"
        minutes, seconds = parts
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")
    
    try:
        secs = float(seconds)
        mins = int(minutes)
        hrs = int(hours)
    except ValueError:
        raise ValueError(f"Invalid timestamp format: {timestamp}")
    
    return hrs * 3600 + mins * 60 + secs
