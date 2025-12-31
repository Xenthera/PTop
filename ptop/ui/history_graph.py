"""
History graph UI element for scrolling data visualization.

Single-line scrolling history graph using Unicode braille characters (btop-style).
"""

import math
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .ansi_renderer import ANSIRendererBase

# Import color utilities from colors module
from .colors import (
    ANSIColors,
    ansi_to_rgb,
    interpolate_rgb,
    rgb_to_ansi256,
    rgb_to_ansitruecolor,
)

# Constants
FLOOR_EPSILON = 1e-6


class HistoryGraph:
    """
    Single-line scrolling history graph using Unicode braille characters (btop-style).
    
    Maintains a buffer of values and displays them as a scrolling graph
    that moves left as new data arrives. Uses braille characters (U+2800-U+28FF)
    to represent fill levels in a 2×4 dot grid per character cell.
    
    Braille dot layout (Unicode standard):
    (1) (4)
    (2) (5)
    (3) (6)
    (7) (8)
    
    btop fill order (bottom-up, left column first, then right):
    Level 1 → dot 7
    Level 2 → dots 7, 3
    Level 3 → dots 7, 3, 2
    Level 4 → dots 7, 3, 2, 1
    Level 5 → dots 7, 3, 2, 1, 8
    Level 6 → dots 7, 3, 2, 1, 8, 6
    Level 7 → dots 7, 3, 2, 1, 8, 6, 5
    Level 8 → dots 7, 3, 2, 1, 8, 6, 5, 4
    """
    
    # Braille base codepoint (U+2800)
    BRAILLE_BASE = 0x2800
    
    # Exact btop fill order mapping
    # Each dot corresponds to bit = 1 << (dot_number - 1)
    # Fill sequence: 7, 3, 2, 1, 8, 6, 5, 4
    FILL_DOT_SEQUENCE = [7, 3, 2, 1, 8, 6, 5, 4]
    
    # Mapping from fill level (0-8) to braille bitmask (generated programmatically)
    # This produces: [0x00, 0x40, 0x44, 0x46, 0x47, 0xC7, 0xE7, 0xF7, 0xFF]
    # Which renders as: ⠀⡀⡄⡆⡇⣇⣧⣷⣿
    _FILL_DOT_SEQUENCE = [7, 3, 2, 1, 8, 6, 5, 4]
    _bitmasks_temp = [0x00]  # Level 0: no dots
    _current_mask_temp = 0x00
    for _dot_num in _FILL_DOT_SEQUENCE:
        _bit = 1 << (_dot_num - 1)  # bit = 1 << (dot_number - 1)
        _current_mask_temp |= _bit
        _bitmasks_temp.append(_current_mask_temp)
    FILL_LEVEL_TO_BITMASK = _bitmasks_temp
    del _FILL_DOT_SEQUENCE, _bitmasks_temp, _current_mask_temp, _dot_num, _bit
    
    # Fallback block characters for terminals without braille support
    FALLBACK_BLOCKS = [' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    
    """
    Initialize a history graph.
    
    Args:
        width: Width of the graph in characters
        min_value: Minimum value for scaling (default: 0.0)
        max_value: Maximum value for scaling (default: 100.0)
        use_braille: If True, use braille characters; if False, use fallback blocks
    """
    def __init__(self, width: int, min_value: float = 0.0, max_value: float = 100.0, use_braille: bool = True):
        self.width = width
        self.min_value = min_value
        self.max_value = max_value
        self.history: List[float] = []
        self.use_braille = use_braille
    
    """
    Add a new value to the history graph.
    
    New values are added to the right, old values scroll left.
    If buffer is full, oldest value is removed.
    
    Args:
        value: New value to add (will be clamped to min_value-max_value)
    """
    def add_value(self, value: float) -> None:
        value = max(self.min_value, min(self.max_value, value))
        self.history.append(value)
        
        # Keep only the last 'width' values (scroll left)
        if len(self.history) > self.width:
            self.history.pop(0)
    
    """Clear the history buffer."""
    def clear(self) -> None:
        self.history = []
    
    """
    Convert a normalized value [0.0-1.0] to a fill level [0-8] using btop's method.
    
    Uses floor (not round) to avoid jitter at boundaries.
    
    Args:
        normalized: Normalized value in range [0.0-1.0]
    
    Returns:
        Fill level in range [0-8]
    """
    def _normalized_to_fill_level(self, normalized: float) -> int:
        fill_level = math.floor(normalized * 8.0 + FLOOR_EPSILON)
        return max(0, min(8, int(fill_level)))
    
    """
    Convert a fill level [0-8] to a braille or block character.
    
    Args:
        fill_level: Fill level in range [0-8]
    
    Returns:
        Unicode character for the fill level
    """
    def _fill_level_to_glyph(self, fill_level: int) -> str:
        fill_level = max(0, min(8, fill_level))
        
        if self.use_braille:
            bitmask = self.FILL_LEVEL_TO_BITMASK[fill_level]
            codepoint = self.BRAILLE_BASE + bitmask
            return chr(codepoint)
        else:
            return self.FALLBACK_BLOCKS[fill_level]
    
    """
    Get the ANSI color code for a specific value using the exact same
    RGB interpolation as the graph rendering.
    
    Args:
        value: The value to get color for (in original units, not normalized)
        renderer: ANSIRendererBase instance for color conversion
    
    Returns:
        ANSI color code for the value
    """
    def _get_value_color(self, value: float, renderer: 'ANSIRendererBase') -> str:
        # Normalize to 0-100 for color mapping
        value_range = self.max_value - self.min_value
        if value_range == 0:
            normalized = 50.0
        else:
            normalized = ((value - self.min_value) / value_range) * 100.0
        
        # Use EXACT same RGB interpolation as graph rendering
        rgb_low = ansi_to_rgb(ANSIColors.BRIGHT_GREEN)
        rgb_mid = ansi_to_rgb(ANSIColors.BRIGHT_YELLOW)
        rgb_high = ansi_to_rgb(ANSIColors.BRIGHT_RED)
        
        # Interpolate color
        if normalized <= 50.0:
            ratio = normalized / 50.0
            rgb = interpolate_rgb(rgb_low, rgb_mid, ratio)
        else:
            ratio = (normalized - 50.0) / 50.0
            rgb = interpolate_rgb(rgb_mid, rgb_high, ratio)
        
        # Convert to ANSI
        if renderer._truecolor_support:
            return rgb_to_ansitruecolor(*rgb)
        else:
            return rgb_to_ansi256(*rgb)
    
    """
    Get the graph as a formatted string with colors using braille characters.
    
    Args:
        renderer: ANSIRendererBase instance for color conversion
    
    Returns:
        Formatted string with colored braille characters representing the history
    """
    def get_graph_string(self, renderer: 'ANSIRendererBase') -> str:
        if not self.history:
            empty_glyph = self._fill_level_to_glyph(0)
            return empty_glyph * self.width
        
        # Normalize values to [0.0-1.0]
        value_range = self.max_value - self.min_value
        if value_range == 0:
            normalized = [0.5] * len(self.history)
        else:
            normalized = [((v - self.min_value) / value_range) for v in self.history]
        
        graph_parts = []
        
        # Pad left if history is shorter than width
        if len(self.history) < self.width:
            padding = self.width - len(self.history)
            empty_glyph = self._fill_level_to_glyph(0)
            graph_parts.append(empty_glyph * padding)
        
        # Add colored braille characters for each value
        for norm_value in normalized:
            fill_level = self._normalized_to_fill_level(norm_value)
            glyph = self._fill_level_to_glyph(fill_level)
            
            # Get color based on normalized value
            value_percent = norm_value * 100.0
            rgb_low = ansi_to_rgb(ANSIColors.BRIGHT_GREEN)
            rgb_mid = ansi_to_rgb(ANSIColors.BRIGHT_YELLOW)
            rgb_high = ansi_to_rgb(ANSIColors.BRIGHT_RED)
            
            # Interpolate color (same logic as status bar)
            if value_percent <= 50.0:
                ratio = value_percent / 50.0
                rgb = interpolate_rgb(rgb_low, rgb_mid, ratio)
            else:
                ratio = (value_percent - 50.0) / 50.0
                rgb = interpolate_rgb(rgb_mid, rgb_high, ratio)
            
            # Convert to ANSI color
            if renderer._truecolor_support:
                color_code = rgb_to_ansitruecolor(*rgb)
            else:
                color_code = rgb_to_ansi256(*rgb)
            
            graph_parts.append(color_code + glyph)
        
        return ''.join(graph_parts) + ANSIColors.RESET
    
    """
    Get the ANSI color code for the maximum value in the history.
    
    Args:
        renderer: ANSIRendererBase instance for color conversion
    
    Returns:
        ANSI color code for the maximum value, or default color if history is empty
    """
    def get_max_value_color(self, renderer: 'ANSIRendererBase') -> str:
        if not self.history:
            return self._get_value_color(self.min_value, renderer)
        
        max_value = max(self.history)
        return self._get_value_color(max_value, renderer)
    
    """
    Get the ANSI color code for the current (latest) value in the history.
    
    Args:
        renderer: ANSIRendererBase instance for color conversion
    
    Returns:
        ANSI color code for the current value, or default color if history is empty
    """
    def get_current_value_color(self, renderer: 'ANSIRendererBase') -> str:
        if not self.history:
            return self._get_value_color(self.min_value, renderer)
        
        current_value = self.history[-1]
        return self._get_value_color(current_value, renderer)
