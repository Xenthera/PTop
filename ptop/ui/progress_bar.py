"""
Progress bar UI element for displaying percentage values with gradient colors.
"""

from .colors import (
    ANSIColors,
    ansi_to_rgb,
    interpolate_rgb,
    rgb_to_ansi256,
    rgb_to_ansitruecolor,
)


"""
Create a horizontal progress bar with smooth RGB gradient colors.

Each filled cell gets its own interpolated RGB color for a smooth gradient
from green (0%) -> yellow (50%) -> red (100%).

Args:
    value: Value percentage (0-100)
    width: Bar width in characters
    low_color: ANSI color for low values (0-50%) - will be converted to RGB
    mid_color: ANSI color for mid values (50%) - will be converted to RGB
    high_color: ANSI color for high values (50-100%) - will be converted to RGB
    empty_color: ANSI color for unfilled portion (gray)
    truecolor_support: If True, use truecolor; if False, use 256-color mode

Returns:
    Formatted bar string with per-cell RGB gradient
"""
def draw_bar_gradient(
    value: float,
    width: int,
    low_color: str = ANSIColors.BRIGHT_GREEN,
    mid_color: str = ANSIColors.BRIGHT_YELLOW,
    high_color: str = ANSIColors.BRIGHT_RED,
    empty_color: str = ANSIColors.BRIGHT_BLACK,
    truecolor_support: bool = True
) -> str:
    # Clamp value
    value = max(0, min(100, value))
    
    # Calculate filled portion
    filled = int((value / 100.0) * width)
    empty = width - filled
    
    # Unicode square character (like btop uses)
    bar_char = '■'
    
    # Convert ANSI colors to RGB
    rgb_low = ansi_to_rgb(low_color)
    rgb_mid = ansi_to_rgb(mid_color)
    rgb_high = ansi_to_rgb(high_color)
    rgb_empty = ansi_to_rgb(empty_color)
    
    # Convert empty color to ANSI (use truecolor if available)
    if truecolor_support:
        empty_ansi = rgb_to_ansitruecolor(*rgb_empty)
    else:
        empty_ansi = rgb_to_ansi256(*rgb_empty)
    
    # Build bar with per-cell RGB interpolation
    bar_parts = []
    
    for i in range(filled):
        # Calculate position as percentage (0-100) based on cell position in bar
        cell_percent = (i / max(1, width - 1)) * 100.0 if width > 1 else 0.0
        
        # Clamp to ensure we hit the endpoints
        if i == 0:
            cell_percent = 0.0
        elif i == filled - 1 and filled == width:
            cell_percent = 100.0
        
        # Interpolate RGB based on cell position
        if cell_percent <= 50.0:
            ratio = cell_percent / 50.0
            rgb = interpolate_rgb(rgb_low, rgb_mid, ratio)
        else:
            ratio = (cell_percent - 50.0) / 50.0
            rgb = interpolate_rgb(rgb_mid, rgb_high, ratio)
        
        # Convert interpolated RGB to ANSI
        if truecolor_support:
            color_ansi = rgb_to_ansitruecolor(*rgb)
        else:
            color_ansi = rgb_to_ansi256(*rgb)
        bar_parts.append(color_ansi + bar_char)
    
    # Add empty cells with gray color
    for i in range(empty):
        bar_parts.append(empty_ansi + bar_char)
    
    return ''.join(bar_parts) + ANSIColors.RESET


"""
Create a status bar with standard gradient colors.

Uses the default color scheme: winter green -> yellow -> red.
This is the standard bar type for all UI components.

Args:
    value: Value percentage (0-100)
    width: Bar width in characters
    truecolor_support: If True, use truecolor; if False, use 256-color mode

Returns:
    Formatted bar string with per-cell RGB gradient
"""
def draw_status_bar(value: float, width: int, truecolor_support: bool = True) -> str:
    return draw_bar_gradient(
        value, width,
        ANSIColors.BRIGHT_GREEN,
        ANSIColors.BRIGHT_YELLOW,
        ANSIColors.BRIGHT_RED,
        ANSIColors.BRIGHT_BLACK,
        truecolor_support
    )
