"""
ANSI-based base renderer for terminal system monitor.

This module provides a generic ANSI renderer base class that handles only drawing.
All application-specific formatting, thresholds, and metric logic should be
handled by external controllers that use this renderer.
"""

import os
import sys
import shutil
import re
import math
from typing import Dict, Any, List, Tuple, Optional
from .renderer import BaseRenderer


# ============================================================================
# Constants
# ============================================================================

DEFAULT_TERMINAL_COLS = 80
DEFAULT_TERMINAL_ROWS = 24
HEADER_LINES = 2
FLOOR_EPSILON = 1e-6
LABEL_SEPARATOR_SPACING = 2  # Horizontal lines between labels
ELLIPSIS_LENGTH = 3  # Length of "..." truncation indicator


# ============================================================================
# Utility Functions
# ============================================================================

"""
Remove ANSI escape sequences from text.

Args:
    text: Text that may contain ANSI codes

Returns:
    Text with ANSI codes removed
"""
def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


"""
Get the visible length of text (excluding ANSI codes).

Args:
    text: Text that may contain ANSI codes

Returns:
    Visible character count
"""
def visible_length(text: str) -> int:
    return len(strip_ansi(text))


# ============================================================================
# Color System
# ============================================================================

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
def rgb_to_ansitruecolor(r: int, g: int, b: int) -> str:
    # Clamp values
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    return f'\033[38;2;{r};{g};{b}m'


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


# ============================================================================
# Panel Class
# ============================================================================

class Panel:
    """
    Represents a panel/viewport in the terminal.
    
    A panel is a bordered box that can display content.
    The panel handles only layout and rendering - content formatting
    is the responsibility of the caller.
    """
    
    """
    Initialize a panel.
    
    Args:
        row: Top row position (1-based)
        col: Left column position (1-based)
        width: Panel width in characters
        height: Panel height in lines
        title: Optional panel title (displayed as first left-aligned label in top border)
        rounded: If True, use rounded corners; if False, use square corners (default)
        border_color: Optional ANSI color code for borders (e.g., ANSIColors.BRIGHT_CYAN)
                     If None, borders use default color (no ANSI codes)
    """
    def __init__(self, row: int, col: int, width: int, height: int, title: str = "", 
                 rounded: bool = False, border_color: Optional[str] = None):
        self.row = row
        self.col = col
        self.width = width
        self.height = height
        self.title = title
        self.rounded = rounded
        self.border_color = border_color
        self.left_labels: List[str] = []
        self.right_labels: List[str] = []
        # Title is always the first left-aligned label
        if title:
            self.left_labels.append(title)
        self.content_lines: List[str] = []
        self._last_content_hash: Optional[int] = None
        self._last_rendered_lines: List[str] = []
    
    """
    Add a left-aligned label to the top border.
    
    Labels are packed to the left side of the border.
    The title (if set) is always the first left label.
    
    Args:
        label: Label text to add (will be formatted with spaces)
    """
    def add_left_label(self, label: str) -> None:
        if label:
            self.left_labels.append(label)
    
    """
    Add a right-aligned label to the top border.
    
    Labels are packed to the right side of the border.
    
    Args:
        label: Label text to add (will be formatted with spaces)
    """
    def add_right_label(self, label: str) -> None:
        if label:
            self.right_labels.append(label)
    
    """Clear all labels, keeping only the title as first left label."""
    def clear_labels(self) -> None:
        self.left_labels = []
        self.right_labels = []
        if self.title:
            self.left_labels.append(self.title)
    
    """Clear panel content."""
    def clear(self) -> None:
        self.content_lines = []
        self._last_content_hash = None
    
    """
    Add a line to panel content.
    
    Line is automatically truncated to fit panel width.
    Caller should format and color the line before adding.
    
    Args:
        line: Formatted line (may include ANSI codes)
    """
    def add_line(self, line: str) -> None:
        # Truncate to fit panel width (accounting for borders)
        max_width = self.width - 2
        visible_len = visible_length(line)
        
        if visible_len > max_width:
            # Need to truncate, but preserve ANSI codes
            visible_chars = max_width - ELLIPSIS_LENGTH
            result = ''
            visible_count = 0
            i = 0
            while i < len(line) and visible_count < visible_chars:
                # Check if we're at an ANSI escape sequence
                if line[i] == '\x1B' or (i < len(line) - 1 and line[i:i+2] == '\033'):
                    # Find the end of the ANSI sequence
                    j = i + 1
                    while j < len(line) and line[j] not in 'ABCDEFGHJKSTfmnsulh':
                        j += 1
                    if j < len(line):
                        j += 1
                    result += line[i:j]
                    i = j
                else:
                    result += line[i]
                    visible_count += 1
                    i += 1
            
            # Add ellipsis (with reset to ensure clean ending)
            result += ANSIColors.RESET + '...'
            line = result
        
        self.content_lines.append(line)
    
    """
    Check if panel content has changed since last render.
    
    Returns:
        True if content has changed, False otherwise
    """
    def has_changed(self) -> bool:
        current_hash = hash(tuple(self.content_lines))
        if current_hash != self._last_content_hash:
            self._last_content_hash = current_hash
            return True
        return False
    
    # Border and rendering helper methods
    
    """
    Get border characters based on rounded flag.
    
    Returns:
        Tuple of (top_left, top_right, bottom_left, bottom_right, horizontal, vertical)
    """
    def _get_border_chars(self) -> Tuple[str, str, str, str, str, str]:
        if self.rounded:
            return ('╭', '╮', '╰', '╯', '─', '│')
        else:
            return ('┌', '┐', '└', '┘', '─', '│')
    
    """
    Apply border color to text if border_color is set.
    
    Args:
        text: Text to colorize
    
    Returns:
        Text with border color applied (or unchanged if no border_color)
    """
    def _apply_border_color(self, text: str) -> str:
        if self.border_color:
            return self.border_color + text + ANSIColors.RESET
        return text
    
    """
    Apply border color only to border characters (┐, ┌, ─), not labels.
    
    Args:
        border_with_labels: Border string with labels and separators
    
    Returns:
        Border string with only border characters colored, labels remain uncolored
    """
    def _colorize_border_only(self, border_with_labels: str) -> str:
        if not self.border_color or not border_with_labels:
            return border_with_labels
        
        """Colorize a matched border character."""
        def colorize_match(match):
            return self._apply_border_color(match.group(0))
        
        # Match border characters: ┐, ┌, or sequences of ─
        result = re.sub(r'[┐┌]|─+', colorize_match, border_with_labels)
        return result
    
    """
    Format labels with separators (┐ label ┌).
    
    Args:
        labels: List of label strings
        horizontal_char: Horizontal line character for spacing
    
    Returns:
        Formatted label string with separators
    """
    def _format_labels(self, labels: List[str], horizontal_char: str) -> str:
        if not labels:
            return ""
        
        formatted = []
        for i, label in enumerate(labels):
            formatted.append("┐")
            formatted.append(f" {label} ")
            formatted.append("┌")
            # Add horizontal lines between labels (except after last)
            if i < len(labels) - 1:
                formatted.append(horizontal_char * LABEL_SEPARATOR_SPACING)
        
        return ''.join(formatted)
    
    """
    Build top border with labels.
    
    Args:
        available_width: Available width for border (excluding corners)
    
    Returns:
        Formatted top border string
    """
    def _build_top_border(self, available_width: int) -> str:
        tl, tr, _, _, h, _ = self._get_border_chars()
        
        # Format labels
        left_text = self._format_labels(self.left_labels, h)
        right_text = self._format_labels(self.right_labels, h)
        
        left_len = visible_length(left_text)
        right_len = visible_length(right_text)
        total_label_len = left_len + right_len
        
        # Handle truncation if labels are too long
        if total_label_len >= available_width:
            if left_text and right_text:
                max_left = min(left_len, available_width - 1)
                if left_len > max_left:
                    left_text = left_text[:max_left]
                    left_len = max_left
                remaining = available_width - left_len
                if right_len > remaining:
                    right_text = right_text[:remaining]
            elif left_text and left_len > available_width:
                left_text = left_text[:available_width]
            elif right_text and right_len > available_width:
                right_text = right_text[:available_width]
        
        # Build border string
        if not left_text and not right_text:
            # No labels - just horizontal line
            top_border = tl + h * available_width + tr
            return ANSIColors.BOLD + self._apply_border_color(top_border) + ANSIColors.RESET
        
        # Labels exist - pack left and right with horizontal lines in between
        middle_space = max(0, available_width - left_len - right_len)
        top_border = tl + left_text + h * middle_space + right_text + tr
        
        # Apply color to border parts only
        colored_tl = self._apply_border_color(tl)
        colored_tr = self._apply_border_color(tr)
        colored_left = self._colorize_border_only(left_text)
        colored_right = self._colorize_border_only(right_text)
        colored_middle = self._apply_border_color(h * middle_space) if middle_space > 0 else ""
        
        return ANSIColors.BOLD + colored_tl + colored_left + colored_middle + colored_right + colored_tr + ANSIColors.RESET
    
    """
    Build content area lines with borders.
    
    Returns:
        List of formatted content lines
    """
    def _build_content_lines(self) -> List[str]:
        _, _, _, _, _, v = self._get_border_chars()
        content_height = self.height - 2  # Account for top and bottom borders
        lines = []
        
        for i in range(content_height):
            if i < len(self.content_lines):
                content = self.content_lines[i]
                visible_len = visible_length(content)
                padding_needed = max(0, (self.width - 2 - visible_len))
                padded = content + ' ' * padding_needed
            else:
                padded = ' ' * (self.width - 2)
            
            left_border = self._apply_border_color(v)
            right_border = self._apply_border_color(v)
            lines.append(left_border + padded + right_border)
        
        return lines
    
    """
    Build bottom border.
    
    Returns:
        Formatted bottom border string
    """
    def _build_bottom_border(self) -> str:
        _, _, bl, br, h, _ = self._get_border_chars()
        bottom_border = bl + h * (self.width - 2) + br
        return ANSIColors.BOLD + self._apply_border_color(bottom_border) + ANSIColors.RESET
    
    """
    Render the panel as a list of ANSI strings.
    
    Returns:
        List of strings, each representing a line of the panel
    """
    def render(self) -> List[str]:
        lines = []
        
        # Top border with labels
        available_width = self.width - 2  # Account for corner characters
        lines.append(self._build_top_border(available_width))
        
        # Content lines
        lines.extend(self._build_content_lines())
        
        # Bottom border
        lines.append(self._build_bottom_border())
        
        self._last_rendered_lines = lines
        return lines


# ============================================================================
# Layout System
# ============================================================================

class BaseLayout:
    """
    Base class for layout managers.
    
    Layouts manage panel positioning and sizing based on terminal dimensions.
    Supports both panels and nested layouts.
    """
    
    """
    Initialize a layout.
    
    Args:
        margin: Margin around the layout (default: 0)
        spacing: Spacing between items (default: 1)
    """
    def __init__(self, margin: int = 0, spacing: int = 1):
        self.margin = margin
        self.spacing = spacing
        self.items: List[Any] = []  # Can contain both Panel and BaseLayout objects
    
    """
    Add a panel to this layout.
    
    Args:
        panel: Panel to add
    """
    def add_panel(self, panel: Panel) -> None:
        self.items.append(panel)
    
    """
    Add a nested layout to this layout.
    
    Args:
        layout: Layout to nest (HLayout or VLayout)
    """
    def add_layout(self, layout: 'BaseLayout') -> None:
        self.items.append(layout)
    
    """
    Update panel positions and sizes based on layout constraints.
    
    Args:
        start_row: Starting row position (1-based)
        start_col: Starting column position (1-based)
        width: Available width
        height: Available height
    """
    def update_layout(self, start_row: int, start_col: int, width: int, height: int) -> None:
        raise NotImplementedError("Subclasses must implement update_layout")


class HLayout(BaseLayout):
    """
    Horizontal layout - arranges panels side by side.
    
    Panels are distributed equally across the available width.
    """
    
    """
    Update panel/layout positions and sizes for horizontal layout.
    
    Args:
        start_row: Starting row position (1-based)
        start_col: Starting column position (1-based)
        width: Available width
        height: Available height
    """
    def update_layout(self, start_row: int, start_col: int, width: int, height: int) -> None:
        if not self.items:
            return
        
        available_width = width - (2 * self.margin)
        available_height = height - (2 * self.margin)
        
        num_items = len(self.items)
        if num_items == 0:
            return
        
        total_spacing = self.spacing * (num_items - 1)
        item_width = (available_width - total_spacing) // num_items
        
        # Position items horizontally
        current_col = start_col + self.margin
        for item in self.items:
            if isinstance(item, Panel):
                item.row = start_row + self.margin
                item.col = current_col
                item.width = item_width
                item.height = available_height
            elif isinstance(item, BaseLayout):
                item.update_layout(start_row + self.margin, current_col, item_width, available_height)
            current_col += item_width + self.spacing


class VLayout(BaseLayout):
    """
    Vertical layout - arranges panels stacked vertically.
    
    Panels are distributed equally across the available height.
    """
    
    """
    Update panel/layout positions and sizes for vertical layout.
    
    Args:
        start_row: Starting row position (1-based)
        start_col: Starting column position (1-based)
        width: Available width
        height: Available height
    """
    def update_layout(self, start_row: int, start_col: int, width: int, height: int) -> None:
        if not self.items:
            return
        
        available_width = width - (2 * self.margin)
        available_height = height - (2 * self.margin)
        
        num_items = len(self.items)
        if num_items == 0:
            return
        
        total_spacing = self.spacing * (num_items - 1)
        item_height = (available_height - total_spacing) // num_items
        
        # Position items vertically
        current_row = start_row + self.margin
        for item in self.items:
            if isinstance(item, Panel):
                item.row = current_row
                item.col = start_col + self.margin
                item.width = available_width
                item.height = item_height
            elif isinstance(item, BaseLayout):
                item.update_layout(current_row, start_col + self.margin, available_width, item_height)
            current_row += item_height + self.spacing


# ============================================================================
# History Graph
# ============================================================================

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


# ============================================================================
# ANSI Renderer Base
# ============================================================================

class ANSIRendererBase(BaseRenderer):
    """
    Base ANSI renderer that handles only drawing operations.
    
    This renderer provides:
    - Terminal setup and cleanup
    - Panel drawing with borders and titles
    - Generic progress bars
    - Cursor-based efficient updates
    - ANSI color utilities
    - Truecolor (24-bit RGB) support for smooth gradients
    - History graphs for scrolling data visualization
    
    It does NOT:
    - Decide colors based on thresholds
    - Format metric data
    - Calculate or interpret metrics
    - Make application-specific decisions
    
    All formatting, coloring, and metric logic should be handled
    by external controllers that use this renderer.
    """
    
    """Initialize the base ANSI renderer."""
    def __init__(self):
        self.terminal_size: Tuple[int, int] = (DEFAULT_TERMINAL_COLS, DEFAULT_TERMINAL_ROWS)
        self.panels: Dict[str, Panel] = {}
        self.layouts: List[BaseLayout] = []
        self._initialized = False
        self._header_lines = HEADER_LINES
        self._truecolor_support = _supports_truecolor()
    
    """Initialize the renderer and terminal."""
    def setup(self) -> None:
        self.terminal_size = self.get_terminal_size()
        
        # Hide cursor
        sys.stdout.write('\033[?25l')
        
        # Clear screen
        sys.stdout.write('\033[2J')
        sys.stdout.write('\033[H')
        
        # Enable alternative buffer (if supported)
        sys.stdout.write('\033[?1049h')
        
        sys.stdout.flush()
        self._initialized = True
    
    """
    Get current terminal size.
    
    Returns:
        Tuple of (columns, rows)
    """
    def get_terminal_size(self) -> Tuple[int, int]:
        try:
            cols, rows = shutil.get_terminal_size()
            return (cols, rows)
        except (OSError, AttributeError, ValueError):
            return (DEFAULT_TERMINAL_COLS, DEFAULT_TERMINAL_ROWS)
    
    """
    Create a new panel.
    
    Args:
        panel_id: Unique identifier for the panel
        row: Top row position (1-based)
        col: Left column position (1-based)
        width: Panel width in characters
        height: Panel height in lines
        title: Optional panel title
        rounded: If True, use rounded corners; if False, use square corners (default)
        border_color: Optional ANSI color code for borders
    
    Returns:
        Created Panel object
    """
    def create_panel(self, panel_id: str, row: int, col: int, width: int, height: int, 
                     title: str = "", rounded: bool = False, border_color: Optional[str] = None) -> Panel:
        panel = Panel(row, col, width, height, title, rounded=rounded, border_color=border_color)
        self.panels[panel_id] = panel
        return panel
    
    """
    Get an existing panel by ID.
    
    Args:
        panel_id: Panel identifier
    
    Returns:
        Panel object or None if not found
    """
    def get_panel(self, panel_id: str) -> Optional[Panel]:
        return self.panels.get(panel_id)
    
    """
    Create a new history graph.
    
    Args:
        width: Width of the graph in characters
        min_value: Minimum value for scaling (default: 0.0)
        max_value: Maximum value for scaling (default: 100.0)
    
    Returns:
        HistoryGraph instance
    """
    def create_history_graph(self, width: int, min_value: float = 0.0, max_value: float = 100.0) -> HistoryGraph:
        return HistoryGraph(width, min_value, max_value)
    
    """
    Add a layout to be managed by the renderer.
    
    Layouts are updated automatically when terminal resizes.
    
    Args:
        layout: Layout object (HLayout or VLayout)
    """
    def add_layout(self, layout: BaseLayout) -> None:
        self.layouts.append(layout)
    
    """
    Update all layouts based on current terminal size.
    
    This should be called after terminal resize or when layouts change.
    """
    def update_layouts(self) -> None:
        cols, rows = self.terminal_size
        content_start_row = self._header_lines + 1
        content_start_col = 1
        content_width = cols
        content_height = rows - self._header_lines
        
        for layout in self.layouts:
            layout.update_layout(content_start_row, content_start_col, content_width, content_height)
    
    """
    Create a horizontal progress bar with gradient colors.
    
    Uses draw_bar_gradient for smooth per-cell gradient.
    This method is kept for backward compatibility.
    
    Args:
        value: Value percentage (0-100)
        width: Bar width in characters
        low_color: Color for low values (0-50%)
        mid_color: Color for mid values (50%)
        high_color: Color for high values (50-100%)
        empty_color: Color for unfilled portion (gray)
    
    Returns:
        Formatted bar string with gradient colors
    """
    def draw_bar(self, value: float, width: int, 
                 low_color: str = ANSIColors.BRIGHT_GREEN,
                 mid_color: str = ANSIColors.BRIGHT_YELLOW,
                 high_color: str = ANSIColors.BRIGHT_RED,
                 empty_color: str = ANSIColors.BRIGHT_BLACK) -> str:
        return self.draw_bar_gradient(value, width, low_color, mid_color, high_color, empty_color)
    
    """
    Create a status bar with standard gradient colors.
    
    Uses the default color scheme: winter green -> yellow -> red.
    This is the standard bar type for all UI components.
    
    Args:
        value: Value percentage (0-100)
        width: Bar width in characters
    
    Returns:
        Formatted bar string with per-cell RGB gradient
    """
    def draw_status_bar(self, value: float, width: int) -> str:
        return self.draw_bar_gradient(
            value, width,
            ANSIColors.BRIGHT_GREEN,
            ANSIColors.BRIGHT_YELLOW,
            ANSIColors.BRIGHT_RED,
            ANSIColors.BRIGHT_BLACK
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
    
    Returns:
        Formatted bar string with per-cell RGB gradient
    """
    def draw_bar_gradient(self, value: float, width: int,
                          low_color: str = ANSIColors.BRIGHT_GREEN,
                          mid_color: str = ANSIColors.BRIGHT_YELLOW,
                          high_color: str = ANSIColors.BRIGHT_RED,
                          empty_color: str = ANSIColors.BRIGHT_BLACK) -> str:
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
        if self._truecolor_support:
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
            if self._truecolor_support:
                color_ansi = rgb_to_ansitruecolor(*rgb)
            else:
                color_ansi = rgb_to_ansi256(*rgb)
            bar_parts.append(color_ansi + bar_char)
        
        # Add empty cells with gray color
        for i in range(empty):
            bar_parts.append(empty_ansi + bar_char)
        
        return ''.join(bar_parts) + ANSIColors.RESET
    
    """
    Move cursor to specified position.
    
    Args:
        row: Row position (1-based)
        col: Column position (1-based)
    """
    def move_cursor(self, row: int, col: int) -> None:
        sys.stdout.write(f'\033[{row};{col}H')
    
    """
    Render a panel at its position.
    
    Args:
        panel: Panel to render
        force_redraw: If True, redraw even if content unchanged
    """
    def render_panel(self, panel: Panel, force_redraw: bool = False) -> None:
        if not force_redraw and not panel.has_changed():
            return
        
        panel_lines = panel.render()
        for i, line in enumerate(panel_lines):
            self.move_cursor(panel.row + i, panel.col)
            sys.stdout.write(line)
    
    """
    Render a header line.
    
    Args:
        text: Header text (may contain ANSI codes)
        style: ANSI style/color for header
    """
    def render_header(self, text: str, style: str = ANSIColors.BOLD + ANSIColors.BRIGHT_CYAN) -> None:
        width = self.terminal_size[0]
        padding = (width - visible_length(text)) // 2
        header = ' ' * padding + style + text + ANSIColors.RESET
        sys.stdout.write(header + '\n')
        sys.stdout.write('─' * width + '\n')
    
    """
    Render metrics data.
    
    This is a placeholder - subclasses or external controllers
    should override or use the panel methods to render content.
    
    Args:
        data: Dictionary with collector data
    """
    def render(self, data: Dict[str, Any]) -> None:
        if not self._initialized:
            self.setup()
        
        # Update terminal size
        self.terminal_size = self.get_terminal_size()
        
        # Move cursor to top
        sys.stdout.write('\033[H')
        
        # Default: render all panels
        for panel in self.panels.values():
            self.render_panel(panel)
        
        sys.stdout.flush()
    
    """Clear the display."""
    def clear(self) -> None:
        sys.stdout.write('\033[2J')
        sys.stdout.write('\033[H')
        sys.stdout.flush()
    
    """Clean up on exit."""
    def cleanup(self) -> None:
        # Show cursor
        sys.stdout.write('\033[?25h')
        
        # Disable alternative buffer
        sys.stdout.write('\033[?1049l')
        
        # Clear screen
        sys.stdout.write('\033[2J')
        sys.stdout.write('\033[H')
        
        # Reset colors
        sys.stdout.write(ANSIColors.RESET)
        
        sys.stdout.write("\nMonitor stopped.\n")
        sys.stdout.flush()


# ============================================================================
# Module Exports
# ============================================================================

# Alias for backward compatibility
ANSIRenderer = ANSIRendererBase
