"""
History graph UI elements for scrolling data visualization.

Contains both single-line and multi-line graph implementations using Unicode braille characters (btop-style).
"""

import math
from typing import List, Optional, Union, Tuple, TYPE_CHECKING

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


class SingleLineGraph:
    """
    Single-line scrolling history graph using Unicode braille characters (btop-style).
    
    Uses a virtual raster grid approach where each braille character represents a 2×4 tile.
    Virtual width = character_width * 2 (each character packs 2 virtual columns)
    Virtual height = 4 (each character has 4 vertical units)
    
    Data is stored at virtual-column resolution and quantized to 0-4 vertical units.
    Each braille character packs two adjacent virtual columns:
    - Left virtual column → dots {1, 2, 3, 7}
    - Right virtual column → dots {4, 5, 6, 8}
    
    Braille dot layout (Unicode standard):
    (1) (4)  <- Left column uses 1,2,3,7 | Right column uses 4,5,6,8
    (2) (5)
    (3) (6)
    (7) (8)
    """
    
    # Braille base codepoint (U+2800)
    BRAILLE_BASE = 0x2800
    
    # Virtual column height quantization: 0-4 vertical units
    VIRTUAL_HEIGHT = 4
    
    # Fallback block characters for terminals without braille support
    FALLBACK_BLOCKS = [' ', '▁', '▂', '▃', '▄']
    
    """
    Initialize a history graph.
    
    Args:
        width: Width of the graph in characters (not virtual columns)
        min_value: Minimum value for scaling (default: 0.0)
        max_value: Maximum value for scaling (default: 100.0)
        use_braille: If True, use braille characters; if False, use fallback blocks
        colors: List of ANSI color codes or RGB tuples (r, g, b) for gradient stops.
                Colors are evenly distributed from 0% to 100%.
                Defaults to [green, yellow, red] if None.
                Supports any number of colors (e.g., 2 colors for simple gradient,
                4+ colors for multi-stop gradients).
    """
    def __init__(self, width: int, min_value: float = 0.0, max_value: float = 100.0, use_braille: bool = True,
                 colors: Optional[List[Union[str, Tuple[int, int, int]]]] = None):
        self._width = width  # Character width (use property to recalculate virtual_width)
        self.min_value = min_value
        self.max_value = max_value
        # Store history at virtual-column resolution, quantized to 0-4
        # Store both quantized height and original value for color calculation
        # Prefill history with zeros (height 1 dot, value min_value) to fill the graph width
        # Height 1 ensures dots are visible (rendered as gray for min_value)
        virtual_width = width * 2  # 2 virtual columns per character
        self.history: List[Tuple[int, float]] = [(1, min_value)] * virtual_width
        self.use_braille = use_braille
        self.colors = colors
    
    @property
    def width(self) -> int:
        """Get the character width."""
        return self._width
    
    @width.setter
    def width(self, value: int) -> None:
        """Set the character width and adjust history if needed."""
        old_virtual_width = self.virtual_width
        self._width = value
        new_virtual_width = self.virtual_width
        
        # Trim history if it exceeds the new virtual width
        if len(self.history) > new_virtual_width:
            # Keep only the most recent values (newest data on the right)
            # Remove oldest data from the left
            self.history = self.history[-new_virtual_width:]
        # Pad history with zeros if it's shorter than the new virtual width
        elif len(self.history) < new_virtual_width:
            # Fill with gray dots (height 1, value min_value) on the left
            padding_needed = new_virtual_width - len(self.history)
            self.history = [(1, self.min_value)] * padding_needed + self.history
    
    @property
    def virtual_width(self) -> int:
        """Calculate virtual column width (2 columns per character)."""
        return self._width * 2
    
    """
    Add a new value to the history graph.
    
    New values are added to the right, old values scroll left.
    Values are quantized to 0-4 vertical units and stored at virtual-column resolution.
    If buffer is full, oldest value is removed.
    
    Args:
        value: New value to add (will be clamped to min_value-max_value and quantized to 0-4)
    """
    def add_value(self, value: float) -> None:
        # Clamp value to range
        value = max(self.min_value, min(self.max_value, value))
        
        # Normalize to 0.0-1.0
        value_range = self.max_value - self.min_value
        if value_range == 0:
            normalized = 0.5
        else:
            normalized = (value - self.min_value) / value_range
        
        # Quantize to 0-4 vertical units (virtual column height)
        quantized = int(math.floor(normalized * self.VIRTUAL_HEIGHT + FLOOR_EPSILON))
        quantized = max(0, min(self.VIRTUAL_HEIGHT, quantized))
        
        # Always show at least 1 dot high (even when value is 0 or very small)
        if quantized == 0:
            quantized = 1
        
        # Add to history at virtual-column resolution (store both quantized height and original value)
        self.history.append((quantized, value))
        
        # Keep only the last 'virtual_width' values (scroll left by virtual column)
        # Recalculate virtual_width in case width changed
        current_virtual_width = self.virtual_width
        if len(self.history) > current_virtual_width:
            self.history.pop(0)
    
    """Clear the history buffer."""
    def clear(self) -> None:
        self.history = []
    
    """
    Pack two virtual columns into a single braille character.
    
    Each braille character represents a 2×4 tile:
    - Left virtual column (height 0-4) → dots {1, 2, 3, 7}
    - Right virtual column (height 0-4) → dots {4, 5, 6, 8}
    
    Args:
        left_height: Height of left virtual column (0-4)
        right_height: Height of right virtual column (0-4)
    
    Returns:
        Unicode braille character for the 2×4 tile
    """
    def _pack_virtual_columns(self, left_height: int, right_height: int) -> str:
        left_height = max(0, min(self.VIRTUAL_HEIGHT, left_height))
        right_height = max(0, min(self.VIRTUAL_HEIGHT, right_height))
        
        if not self.use_braille:
            # Fallback: use average height
            avg_height = (left_height + right_height) // 2
            return self.FALLBACK_BLOCKS[avg_height]
        
        # Build bitmask for left column (dots 1, 2, 3, 7)
        # Fill from bottom to top: 7 (bottom), then 3, 2, 1 (top)
        bitmask = 0
        if left_height >= 1:
            bitmask |= (1 << (7 - 1))  # Dot 7 (bottom)
        if left_height >= 2:
            bitmask |= (1 << (3 - 1))  # Dot 3
        if left_height >= 3:
            bitmask |= (1 << (2 - 1))  # Dot 2
        if left_height >= 4:
            bitmask |= (1 << (1 - 1))  # Dot 1 (top)
        
        # Build bitmask for right column (dots 4, 5, 6, 8)
        # Fill from bottom to top: 8 (bottom), then 6, 5, 4 (top)
        if right_height >= 1:
            bitmask |= (1 << (8 - 1))  # Dot 8 (bottom)
        if right_height >= 2:
            bitmask |= (1 << (6 - 1))  # Dot 6
        if right_height >= 3:
            bitmask |= (1 << (5 - 1))  # Dot 5
        if right_height >= 4:
            bitmask |= (1 << (4 - 1))  # Dot 4 (top)
        
        # Convert to braille character
        codepoint = self.BRAILLE_BASE + bitmask
        return chr(codepoint)
    
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
            normalized_percent = 50.0
        else:
            normalized_percent = ((value - self.min_value) / value_range) * 100.0
        
        # Get color list (default or custom)
        if self.colors is None or len(self.colors) == 0:
            colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
        else:
            colors = self.colors
        
        # Convert colors to RGB (handle both ANSI codes and RGB tuples)
        rgb_colors = []
        for color in colors:
            if isinstance(color, tuple):
                rgb_colors.append(color)
            else:
                rgb_colors.append(ansi_to_rgb(color))
        
        # Interpolate color using the same logic as progress bars
        rgb = self._interpolate_color_list(rgb_colors, normalized_percent)
        
        # Convert to ANSI
        if renderer._truecolor_support:
            return rgb_to_ansitruecolor(*rgb)
        else:
            return rgb_to_ansi256(*rgb)
    
    """
    Interpolate between colors in a list based on percentage.
    
    Args:
        rgb_colors: List of RGB tuples
        percent: Percentage value (0-100)
    
    Returns:
        Interpolated RGB tuple
    """
    def _interpolate_color_list(self, rgb_colors: List[Tuple[int, int, int]], percent: float) -> Tuple[int, int, int]:
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
    Get the graph as a formatted string with colors using braille characters.
    
    Args:
        renderer: ANSIRendererBase instance for color conversion
    
    Returns:
        Formatted string with colored braille characters representing the history
    """
    def get_graph_string(self, renderer: 'ANSIRendererBase') -> str:
        if not self.history:
            empty_glyph = self._pack_virtual_columns(0, 0)
            return empty_glyph * self.width
        
        graph_parts = []
        
        # Pad left if history is shorter than virtual_width
        if len(self.history) < self.virtual_width:
            padding_virtual = self.virtual_width - len(self.history)
            # Pad with empty virtual columns (height 0, value min_value)
            padded_history = [(0, self.min_value)] * padding_virtual + self.history
        else:
            # Take only the last virtual_width values
            padded_history = self.history[-self.virtual_width:]
        
        # Get color list (default or custom)
        if self.colors is None or len(self.colors) == 0:
            colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
        else:
            colors = self.colors
        
        # Convert colors to RGB (handle both ANSI codes and RGB tuples)
        rgb_colors = []
        for color in colors:
            if isinstance(color, tuple):
                rgb_colors.append(color)
            else:
                rgb_colors.append(ansi_to_rgb(color))
        
        # Render characters: each character packs 2 adjacent virtual columns
        for char_idx in range(self.width):
            left_virtual_idx = char_idx * 2
            right_virtual_idx = left_virtual_idx + 1
            
            # Get heights and original values for left and right virtual columns
            if left_virtual_idx < len(padded_history):
                left_height, left_original = padded_history[left_virtual_idx]
            else:
                left_height, left_original = 0, self.min_value
            
            if right_virtual_idx < len(padded_history):
                right_height, right_original = padded_history[right_virtual_idx]
            else:
                right_height, right_original = 0, self.min_value
            
            # Pack into braille character
            glyph = self._pack_virtual_columns(left_height, right_height)
            
            # Get color based on the maximum original value of the two columns
            max_original = max(left_original, right_original)
            # Normalize original value to percentage (0-100) for color mapping
            value_range = self.max_value - self.min_value
            if value_range == 0:
                height_percent = 50.0
            else:
                height_percent = ((max_original - self.min_value) / value_range) * 100.0
            
            # Use gray color when value is about 0 (within 1% of range from min_value)
            if height_percent <= 1.0:
                # Use gray color for near-zero values
                if renderer._truecolor_support:
                    color_code = rgb_to_ansitruecolor(128, 128, 128)
                else:
                    color_code = ANSIColors.BRIGHT_BLACK
            else:
                # Interpolate color using the same logic as progress bars
                rgb = self._interpolate_color_list(rgb_colors, height_percent)
                
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
        
        # Find maximum original value from history
        max_value = max(original for _, original in self.history)
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
        
        # Get original value from the last entry
        _, current_value = self.history[-1]
        return self._get_value_color(current_value, renderer)


# Backward compatibility alias
HistoryGraph = SingleLineGraph


class MultiLineGraph:
    """
    Multi-line scrolling history graph using Unicode braille characters (btop-style).
    
    Supports multiple character rows, equivalent to btop's large graphs.
    Uses a virtual raster grid where each braille character represents a 2×4 tile.
    
    Viewport: width_chars × height_chars
    Virtual grid: width_chars * 2 × height_chars * 4
    
    Data is stored as virtual column heights [0, virtual_height].
    Data scrolls horizontally by one virtual column per sample.
    Virtual Y = 0 is the bottom of the graph.
    """
    
    # Braille base codepoint (U+2800)
    BRAILLE_BASE = 0x2800
    
    """
    Initialize a multi-line history graph.
    
    Args:
        width_chars: Width of the graph in characters
        height_chars: Height of the graph in character rows
        min_value: Minimum value for scaling (default: 0.0)
        max_value: Maximum value for scaling (default: 100.0)
        use_braille: If True, use braille characters; if False, use fallback blocks
        top_to_bottom: If True, render from top to bottom (virtual Y=0 at top);
                       If False, render from bottom to top (virtual Y=0 at bottom, default)
        colors: List of ANSI color codes or RGB tuples (r, g, b) for gradient stops.
                Colors are evenly distributed from 0% to 100%.
                Defaults to [green, yellow, red] if None.
    """
    def __init__(self, width_chars: int, height_chars: int, min_value: float = 0.0, 
                 max_value: float = 100.0, use_braille: bool = True,
                 top_to_bottom: bool = False,
                 colors: Optional[List[Union[str, Tuple[int, int, int]]]] = None):
        self._width_chars = width_chars
        self._height_chars = height_chars
        self.min_value = min_value
        self.max_value = max_value
        # Virtual grid dimensions
        self.virtual_width = width_chars * 2  # 2 virtual columns per character
        self.virtual_height = height_chars * 4  # 4 virtual rows per character
        # Store history as virtual column heights [0, virtual_height]
        # Circular buffer sized to virtual_width
        self.history: List[Tuple[int, float]] = []  # List of (quantized_height, original_value)
        self.use_braille = use_braille
        self.top_to_bottom = top_to_bottom  # If True, virtual Y=0 is at top; if False, at bottom
        self.colors = colors
    
    @property
    def width_chars(self) -> int:
        """Get the character width."""
        return self._width_chars
    
    @width_chars.setter
    def width_chars(self, value: int) -> None:
        """Set the character width and trim history if needed."""
        self._width_chars = value
        self.virtual_width = value * 2
        # Trim history to keep only newest data
        if len(self.history) > self.virtual_width:
            self.history = self.history[-self.virtual_width:]
    
    @property
    def height_chars(self) -> int:
        """Get the character height."""
        return self._height_chars
    
    @height_chars.setter
    def height_chars(self, value: int) -> None:
        """Set the character height."""
        self._height_chars = value
        self.virtual_height = value * 4
    
    """
    Add a new value to the history graph.
    
    New values are added to the right, old values scroll left.
    Values are quantized to 0-virtual_height and stored at virtual-column resolution.
    If buffer is full, oldest value is removed.
    
    Args:
        value: New value to add (will be clamped to min_value-max_value and quantized)
    """
    def add_value(self, value: float) -> None:
        # Clamp value to range
        value = max(self.min_value, min(self.max_value, value))
        
        # Normalize to 0.0-1.0
        value_range = self.max_value - self.min_value
        if value_range == 0:
            normalized = 0.5
        else:
            normalized = (value - self.min_value) / value_range
        
        # Quantize to 0-virtual_height vertical units (virtual column height)
        quantized = int(math.floor(normalized * self.virtual_height + FLOOR_EPSILON))
        quantized = max(0, min(self.virtual_height, quantized))
        
        # Add to history at virtual-column resolution (store both quantized height and original value)
        self.history.append((quantized, value))
        
        # Keep only the last 'virtual_width' values (circular buffer, scroll left by virtual column)
        if len(self.history) > self.virtual_width:
            self.history.pop(0)
    
    """Clear the history buffer."""
    def clear(self) -> None:
        self.history = []
    
    """
    Pack a 2×4 virtual tile into a single braille character.
    
    Each braille character represents a 2×4 tile:
    - Left virtual column (4 rows) → dots {1, 2, 3, 7}
    - Right virtual column (4 rows) → dots {4, 5, 6, 8}
    
    This method has two completely separate logic paths:
    - When top_to_bottom=False: heights[0] = bottom row, heights[3] = top row
    - When top_to_bottom=True: heights[0] = top row, heights[3] = bottom row
    
    Args:
        left_heights: List of 4 heights for left column
        right_heights: List of 4 heights for right column
        When top_to_bottom=False: [row0=bottom, row1, row2, row3=top]
        When top_to_bottom=True: [row0=top, row1, row2, row3=bottom]
    
    Returns:
        Unicode braille character for the 2×4 tile
    """
    def _pack_tile(self, left_heights: List[int], right_heights: List[int]) -> str:
        if not self.use_braille:
            # Fallback: use average
            avg_left = sum(left_heights) // len(left_heights) if left_heights else 0
            avg_right = sum(right_heights) // len(right_heights) if right_heights else 0
            avg = (avg_left + avg_right) // 2
            # Use simple block character
            blocks = [' ', '▁', '▂', '▃', '▄']
            return blocks[min(avg, len(blocks) - 1)]
        
        bitmask = 0
        
        if self.top_to_bottom:
            # TOP TO BOTTOM RENDERING - Separate logic path
            # left_heights[0] = top row, left_heights[3] = bottom row
            # Left column: dots {1, 2, 3, 7}
            # Map: top row (heights[0]) → dot 1, second row (heights[1]) → dot 2,
            #      third row (heights[2]) → dot 3, bottom row (heights[3]) → dot 7
            if left_heights[0] > 0:  # Top row
                bitmask |= (1 << (1 - 1))  # Dot 1 (top-left)
            if left_heights[1] > 0:  # Second row from top
                bitmask |= (1 << (2 - 1))  # Dot 2
            if left_heights[2] > 0:  # Third row from top
                bitmask |= (1 << (3 - 1))  # Dot 3
            if left_heights[3] > 0:  # Bottom row
                bitmask |= (1 << (7 - 1))  # Dot 7 (bottom-left)
            
            # Right column: dots {4, 5, 6, 8}
            # Map: top row (heights[0]) → dot 4, second row (heights[1]) → dot 5,
            #      third row (heights[2]) → dot 6, bottom row (heights[3]) → dot 8
            if right_heights[0] > 0:  # Top row
                bitmask |= (1 << (4 - 1))  # Dot 4 (top-right)
            if right_heights[1] > 0:  # Second row from top
                bitmask |= (1 << (5 - 1))  # Dot 5
            if right_heights[2] > 0:  # Third row from top
                bitmask |= (1 << (6 - 1))  # Dot 6
            if right_heights[3] > 0:  # Bottom row
                bitmask |= (1 << (8 - 1))  # Dot 8 (bottom-right)
        else:
            # BOTTOM TO TOP RENDERING (default) - Separate logic path
            # left_heights[0] = bottom row, left_heights[3] = top row
            # Left column: dots {1, 2, 3, 7}
            # Map: bottom row (heights[0]) → dot 7, second row (heights[1]) → dot 3,
            #      third row (heights[2]) → dot 2, top row (heights[3]) → dot 1
            if left_heights[0] > 0:  # Bottom row
                bitmask |= (1 << (7 - 1))  # Dot 7 (bottom-left)
            if left_heights[1] > 0:  # Second row from bottom
                bitmask |= (1 << (3 - 1))  # Dot 3
            if left_heights[2] > 0:  # Third row from bottom
                bitmask |= (1 << (2 - 1))  # Dot 2
            if left_heights[3] > 0:  # Top row
                bitmask |= (1 << (1 - 1))  # Dot 1 (top-left)
            
            # Right column: dots {4, 5, 6, 8}
            # Map: bottom row (heights[0]) → dot 8, second row (heights[1]) → dot 6,
            #      third row (heights[2]) → dot 5, top row (heights[3]) → dot 4
            if right_heights[0] > 0:  # Bottom row
                bitmask |= (1 << (8 - 1))  # Dot 8 (bottom-right)
            if right_heights[1] > 0:  # Second row from bottom
                bitmask |= (1 << (6 - 1))  # Dot 6
            if right_heights[2] > 0:  # Third row from bottom
                bitmask |= (1 << (5 - 1))  # Dot 5
            if right_heights[3] > 0:  # Top row
                bitmask |= (1 << (4 - 1))  # Dot 4 (top-right)
        
        # Convert to braille character
        codepoint = self.BRAILLE_BASE + bitmask
        return chr(codepoint)
    
    """
    Get the graph as a formatted string with colors using braille characters.
    
    Renders from top character row to bottom.
    Each character packs a 2×4 virtual tile.
    
    Args:
        renderer: ANSIRendererBase instance for color conversion
    
    Returns:
        Formatted string with colored braille characters representing the history
        (multiple lines, one per character row)
    """
    def get_graph_string(self, renderer: 'ANSIRendererBase') -> str:
        if not self.history:
            empty_glyph = self._pack_tile([0, 0, 0, 0], [0, 0, 0, 0])
            return (empty_glyph * self.width_chars + '\n') * self.height_chars
        
        # Pad history if needed
        if len(self.history) < self.virtual_width:
            padding_virtual = self.virtual_width - len(self.history)
            padded_history = [(0, self.min_value)] * padding_virtual + self.history
        else:
            # Take only the last virtual_width values
            padded_history = self.history[-self.virtual_width:]
        
        # Get color list (default or custom)
        if self.colors is None or len(self.colors) == 0:
            colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
        else:
            colors = self.colors
        
        # Convert colors to RGB (handle both ANSI codes and RGB tuples)
        rgb_colors = []
        for color in colors:
            if isinstance(color, tuple):
                rgb_colors.append(color)
            else:
                rgb_colors.append(ansi_to_rgb(color))
        
        # Build a virtual raster grid
        # virtual_grid[virtual_y][virtual_x] = 1 if filled, 0 if empty
        if self.top_to_bottom:
            # virtual_y = 0 is top, virtual_y = virtual_height-1 is bottom
            virtual_grid = [[0 for _ in range(self.virtual_width)] for _ in range(self.virtual_height)]
            
            # Fill the grid from history data (fill from top downward)
            for virtual_x, (height, _) in enumerate(padded_history):
                # Fill from top (virtual_y = 0) down to height
                for virtual_y in range(height):
                    if virtual_y < self.virtual_height:
                        virtual_grid[virtual_y][virtual_x] = 1
        else:
            # virtual_y = 0 is bottom, virtual_y = virtual_height-1 is top (default)
            virtual_grid = [[0 for _ in range(self.virtual_width)] for _ in range(self.virtual_height)]
            
            # Fill the grid from history data (fill from bottom upward)
            for virtual_x, (height, _) in enumerate(padded_history):
                # Fill from bottom (virtual_y = 0) up to height
                for virtual_y in range(height):
                    if virtual_y < self.virtual_height:
                        virtual_grid[virtual_y][virtual_x] = 1
        
        # Render character rows from top to bottom
        graph_lines = []
        for char_row in range(self.height_chars):
            line_parts = []
            if self.top_to_bottom:
                # Top to bottom: top character row maps to virtual_y = 0
                virtual_row_base = char_row * 4
            else:
                # Bottom to top: top character row maps to highest virtual_y
                virtual_row_base = (self.height_chars - 1 - char_row) * 4
            
            # Render each character in this row
            for char_col in range(self.width_chars):
                virtual_col_base = char_col * 2
                
                # Get the 2×4 tile for this character
                left_heights = []
                right_heights = []
                
                if self.top_to_bottom:
                    # TOP TO BOTTOM: virtual_y=0 is at top of grid
                    # virtual_row_base = char_row * 4, so for char_row=0, virtual_row_base=0 (top)
                    # We iterate tile_row from 0 to 3, which gives virtual_y from virtual_row_base to virtual_row_base+3
                    # This means we're going from top to bottom of the tile
                    # We want left_heights[0] = top row of tile, left_heights[3] = bottom row of tile
                    for tile_row in range(4):
                        virtual_y = virtual_row_base + tile_row
                        if 0 <= virtual_y < self.virtual_height:
                            # Left column
                            left_heights.append(virtual_grid[virtual_y][virtual_col_base])
                            # Right column
                            right_heights.append(virtual_grid[virtual_y][virtual_col_base + 1])
                        else:
                            left_heights.append(0)
                            right_heights.append(0)
                    # left_heights[0] = top row of tile, left_heights[3] = bottom row of tile
                    # This is the correct order for top_to_bottom=True
                else:
                    # BOTTOM TO TOP: Iterate from bottom to top of the tile
                    # virtual_row_base is at the bottom, so we go from virtual_row_base up
                    # We want left_heights[0] = bottom row, left_heights[3] = top row
                    for tile_row in range(4):
                        virtual_y = virtual_row_base + tile_row
                        if virtual_y < self.virtual_height:
                            # Left column
                            left_heights.append(virtual_grid[virtual_y][virtual_col_base])
                            # Right column
                            right_heights.append(virtual_grid[virtual_y][virtual_col_base + 1])
                        else:
                            left_heights.append(0)
                            right_heights.append(0)
                    # left_heights[0] = bottom row, left_heights[3] = top row (correct order)
                
                # Pack into braille character
                glyph = self._pack_tile(left_heights, right_heights)
                
                # Color based on vertical position (row position) rather than value
                # For normal orientation (top_to_bottom=False): bottom = 0%, top = 100%
                # For flipped orientation (top_to_bottom=True): top = 0%, bottom = 100%
                if self.top_to_bottom:
                    # Top to bottom: char_row 0 is top, so position increases downward
                    # Top row (char_row=0) should map to first color (0%), bottom to last color (100%)
                    position_percent = (char_row / (self.height_chars - 1)) * 100.0 if self.height_chars > 1 else 0.0
                else:
                    # Bottom to top: char_row 0 is top row visually, but represents highest virtual_y
                    # Bottom should map to first color (0%), top to last color (100%)
                    # So we reverse: char_row 0 (top visual) = 100%, char_row height_chars-1 (bottom visual) = 0%
                    position_percent = ((self.height_chars - 1 - char_row) / (self.height_chars - 1)) * 100.0 if self.height_chars > 1 else 0.0
                
                # Interpolate color based on position
                rgb = self._interpolate_color_list(rgb_colors, position_percent)
                
                # Convert to ANSI color
                if renderer._truecolor_support:
                    color_code = rgb_to_ansitruecolor(*rgb)
                else:
                    color_code = rgb_to_ansi256(*rgb)
                
                line_parts.append(color_code + glyph)
            
            graph_lines.append(''.join(line_parts) + ANSIColors.RESET)
        
        return '\n'.join(graph_lines)
    
    """
    Interpolate between colors in a list based on percentage.
    
    Args:
        rgb_colors: List of RGB tuples
        percent: Percentage value (0-100)
    
    Returns:
        Interpolated RGB tuple
    """
    def _interpolate_color_list(self, rgb_colors: List[Tuple[int, int, int]], percent: float) -> Tuple[int, int, int]:
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
