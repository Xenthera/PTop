"""
Color system for ANSI terminal rendering.

Provides ANSI color codes, RGB conversion, and color interpolation utilities.
"""

import os
from typing import Tuple, List, Union


class ANSIColors:
    """ANSI color and style escape sequences."""
    # Reset
    RESET = '\033[0m'
    
    # Text colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    # Text styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    
    """
    Apply color/style to text.
    
    Args:
        text: Text to colorize
        color: ANSI color/style code
    
    Returns:
        Colored text string
    """
    @staticmethod
    def colorize(text: str, color: str) -> str:
        return f"{color}{text}{ANSIColors.RESET}"


"""
Convert ANSI color code to RGB values.

Maps common ANSI colors to their RGB equivalents.

Args:
    ansi_code: ANSI color code (e.g., ANSIColors.BRIGHT_GREEN)

Returns:
    Tuple of (R, G, B) values (0-255)
"""
def ansi_to_rgb(ansi_code: str) -> Tuple[int, int, int]:
    # Map ANSI colors to RGB
    color_map = {
        ANSIColors.BRIGHT_GREEN: (60, 180, 120),    # Winter green
        ANSIColors.BRIGHT_YELLOW: (255, 240, 100),  # Saturated yellow
        ANSIColors.BRIGHT_RED: (255, 100, 100),     # Saturated red
        ANSIColors.BRIGHT_BLACK: (64, 64, 64),     # Gray
        ANSIColors.BRIGHT_BLUE: (100, 150, 255),   # Bright blue
        ANSIColors.BRIGHT_MAGENTA: (255, 100, 255), # Bright magenta/purple
        ANSIColors.BRIGHT_WHITE: (255, 255, 255),  # White
        ANSIColors.GREEN: (0, 200, 0),
        ANSIColors.YELLOW: (200, 200, 0),
        ANSIColors.RED: (200, 0, 0),
        ANSIColors.BLACK: (0, 0, 0),
    }
    
    return color_map.get(ansi_code, (128, 128, 128))  # Default to gray


"""
Convert RGB values to 256-color ANSI code.

Uses the 256-color palette (xterm-256color) with improved quantization
for smoother gradients.

Args:
    r: Red component (0-255)
    g: Green component (0-255)
    b: Blue component (0-255)

Returns:
    ANSI escape sequence for 256-color mode
"""
def rgb_to_ansi256(r: int, g: int, b: int) -> str:
    # Clamp values
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    # Convert to 256-color ANSI code
    # Formula: 16 + 36*r + 6*g + b (for RGB cube)
    # Map 0-255 to 0-5 for each component
    r6 = round(r / 51.0)
    g6 = round(g / 51.0)
    b6 = round(b / 51.0)
    
    # Clamp to 0-5
    r6 = max(0, min(5, r6))
    g6 = max(0, min(5, g6))
    b6 = max(0, min(5, b6))
    
    # Calculate color code (16-231 for RGB cube)
    color_code = 16 + 36 * r6 + 6 * g6 + b6
    
    return f'\033[38;5;{color_code}m'


"""
Convert RGB values to truecolor (24-bit) ANSI code.

Uses truecolor ANSI codes for perfectly smooth gradients.
Format: \033[38;2;R;G;Bm

Args:
    r: Red component (0-255)
    g: Green component (0-255)
    b: Blue component (0-255)

Returns:
    ANSI escape sequence for truecolor mode
"""
# Cache for rgb_to_ansitruecolor (256^3 = 16M possible values, but we'll use LRU cache)
_rgb_cache = {}
_rgb_cache_size = 65536  # Cache up to 64K most recent colors

def rgb_to_ansitruecolor(r: int, g: int, b: int) -> str:
    # Clamp values
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    # Use cache key
    cache_key = (r, g, b)
    if cache_key in _rgb_cache:
        return _rgb_cache[cache_key]
    
    # Generate ANSI code (use % formatting which is slightly faster than f-strings for this)
    result = f'\033[38;2;{r};{g};{b}m'
    
    # Simple cache: if cache is full, clear it (simple but effective for repeated colors)
    if len(_rgb_cache) >= _rgb_cache_size:
        _rgb_cache.clear()
    
    _rgb_cache[cache_key] = result
    return result


"""
Interpolate between two RGB colors with smooth linear interpolation.

Args:
    rgb1: First RGB color (R, G, B)
    rgb2: Second RGB color (R, G, B)
    ratio: Interpolation ratio (0.0 = rgb1, 1.0 = rgb2)

Returns:
    Interpolated RGB color
"""
def interpolate_rgb(rgb1: Tuple[int, int, int], rgb2: Tuple[int, int, int], ratio: float) -> Tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    r = round(rgb1[0] + (rgb2[0] - rgb1[0]) * ratio)
    g = round(rgb1[1] + (rgb2[1] - rgb1[1]) * ratio)
    b = round(rgb1[2] + (rgb2[2] - rgb1[2]) * ratio)
    # Clamp to valid RGB range
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return (r, g, b)


"""
Interpolate between colors in a list based on percentage.

This function provides a common way to interpolate colors across multiple stops,
used by graphs, progress bars, and other gradient color features.

Args:
    rgb_colors: List of RGB tuples representing color stops
    percent: Percentage value (0-100) to map to color stops
    
Returns:
    Interpolated RGB tuple

Example:
    colors = [(0, 255, 0), (191, 255, 0), (255, 255, 255)]  # green -> lime -> white
    color_at_25_percent = interpolate_color_list(colors, 25.0)  # Between green and lime
    color_at_75_percent = interpolate_color_list(colors, 75.0)  # Between lime and white
"""
def interpolate_color_list(rgb_colors: list, percent: float) -> Tuple[int, int, int]:
    if len(rgb_colors) == 0:
        return (128, 128, 128)  # Default gray
    if len(rgb_colors) == 1:
        return rgb_colors[0]
    
    # Map percent (0-100) to position in color list (0 to len-1)
    max_index = len(rgb_colors) - 1
    position = (percent / 100.0) * max_index
    
    # Find the two colors to interpolate between
    lower_index = int(position)
    upper_index = min(lower_index + 1, max_index)
    
    # If we're exactly at a color stop, return it
    if lower_index == upper_index:
        return rgb_colors[lower_index]
    
    # Calculate interpolation ratio between the two colors
    ratio = position - lower_index
    
    # Interpolate between the two colors
    return interpolate_rgb(rgb_colors[lower_index], rgb_colors[upper_index], ratio)


"""
Get ANSI color code for a value using color interpolation.

Converts a list of colors (ANSI codes or RGB tuples) to RGB, interpolates based on
value percentage (0-100), and returns the appropriate ANSI color code.

Args:
    colors: List of color stops (ANSI codes or RGB tuples)
    value_percent: Value as percentage (0-100)
    truecolor_support: If True, use truecolor; if False, use 256-color mode
    
Returns:
    ANSI color code string
"""
def get_gradient_color(colors: list, value_percent: float, truecolor_support: bool = True) -> str:
    # Convert colors to RGB (handle both ANSI codes and RGB tuples)
    rgb_colors = []
    for color in colors:
        if isinstance(color, tuple):
            rgb_colors.append(color)
        else:
            rgb_colors.append(ansi_to_rgb(color))
    
    # Interpolate color
    rgb = interpolate_color_list(rgb_colors, value_percent)
    
    # Convert to ANSI
    if truecolor_support:
        return rgb_to_ansitruecolor(*rgb)
    else:
        return rgb_to_ansi256(*rgb)


"""
Check if terminal supports truecolor (24-bit RGB).

Returns:
    True if truecolor is supported, False otherwise
"""
def _supports_truecolor() -> bool:
    # Check COLORTERM environment variable (common indicator)
    colorterm = os.environ.get('COLORTERM', '').lower()
    if 'truecolor' in colorterm or '24bit' in colorterm:
        return True
    
    # Check TERM variable for common truecolor terminals
    term = os.environ.get('TERM', '').lower()
    truecolor_terms = ['xterm-256color', 'screen-256color', 'tmux-256color', 
                       'rxvt-unicode-256color', 'alacritty', 'kitty', 'wezterm']
    if any(t in term for t in truecolor_terms):
        return True
    
    # Default to truecolor for modern terminals (most support it)
    return True
