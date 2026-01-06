"""
Progress bar UI element for displaying percentage values with gradient colors.
"""

from typing import Optional, Union, Tuple, List
from ..colors import (
    ANSIColors,
    ansi_to_rgb,
    interpolate_rgb,
    rgb_to_ansi256,
    rgb_to_ansitruecolor,
)


"""
Create a horizontal progress bar with smooth RGB gradient colors.

Each filled cell gets its own interpolated RGB color for a smooth gradient
across multiple color stops. Colors are evenly distributed from 0% to 100%.

Args:
    value: Value percentage (0-100)
    width: Bar width in characters
    colors: List of ANSI color codes or RGB tuples (r, g, b) for gradient stops.
            Colors are evenly distributed from 0% to 100%.
            Defaults to [green, yellow, red] if None.
            Supports any number of colors (e.g., 2 colors for simple gradient,
            4+ colors for multi-stop gradients).
    empty_color: ANSI color code or RGB tuple for unfilled portion (gray)
    truecolor_support: If True, use truecolor; if False, use 256-color mode

Returns:
    Formatted bar string with per-cell RGB gradient
"""
def draw_bar_gradient(
    value: float,
    width: int,
    colors: Optional[List[Union[str, Tuple[int, int, int]]]] = None,
    empty_color: Union[str, Tuple[int, int, int]] = ANSIColors.BRIGHT_BLACK,
    truecolor_support: bool = True
) -> str:
    # Clamp value
    value = max(0, min(100, value))
    
    # Calculate filled portion
    filled = int((value / 100.0) * width)
    empty = width - filled
    
    # Unicode square character (like btop uses)
    bar_char = '■'
    
    # Default colors if not provided
    if colors is None or len(colors) == 0:
        colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
    
    # Convert colors to RGB (handle both ANSI codes and RGB tuples)
    rgb_colors = []
    for color in colors:
        if isinstance(color, tuple):
            rgb_colors.append(color)
        else:
            rgb_colors.append(ansi_to_rgb(color))
    
    # Convert empty color to RGB
    if isinstance(empty_color, tuple):
        rgb_empty = empty_color
    else:
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
        
        # Interpolate RGB based on cell position across color stops
        rgb = _interpolate_color_list(rgb_colors, cell_percent)
        
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


def _interpolate_color_list(rgb_colors: List[Tuple[int, int, int]], percent: float) -> Tuple[int, int, int]:
    """
    Interpolate between colors in a list based on percentage.
    
    Args:
        rgb_colors: List of RGB tuples
        percent: Percentage value (0-100)
    
    Returns:
        Interpolated RGB tuple
    """
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
Create a status bar with standard gradient colors.

Uses the default color scheme: green -> yellow -> red.
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
        colors=[ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED],
        empty_color=ANSIColors.BRIGHT_BLACK,
        truecolor_support=truecolor_support
    )


class ProgressBar:
    """
    Progress bar object that knows its own colors and value.
    
    Encapsulates bar rendering with configurable gradient colors.
    Supports both ANSI color codes and RGB tuples, with any number of color stops.
    """
    
    def __init__(self, value: float, 
                 colors: Optional[List[Union[str, Tuple[int, int, int]]]] = None,
                 truecolor_support: bool = True):
        """
        Initialize progress bar.
        
        Args:
            value: Current value percentage (0-100)
            colors: List of ANSI color codes or RGB tuples (r, g, b) for gradient stops.
                    Colors are evenly distributed from 0% to 100%.
                    Defaults to [green, yellow, red] if None.
            truecolor_support: Truecolor support flag
        """
        self.value = value
        self.colors = colors
        self.truecolor_support = truecolor_support
    
    def render(self, width: int) -> str:
        """
        Render the bar at the specified width.
        
        Args:
            width: Bar width in characters
        
        Returns:
            Formatted bar string
        """
        return draw_bar_gradient(
            self.value, width,
            colors=self.colors,
            empty_color=ANSIColors.BRIGHT_BLACK,
            truecolor_support=self.truecolor_support
        )
    
    def update_value(self, value: float) -> None:
        """Update the bar value."""
        self.value = value
