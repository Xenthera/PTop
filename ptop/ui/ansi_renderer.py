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
from typing import Dict, Any, List, Tuple, Optional
from abc import ABC, abstractmethod
from .history_graph import HistoryGraph
from .progress_bar import draw_status_bar, draw_bar_gradient


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
# Color System (imported from colors module)
# ============================================================================

from .colors import (
    ANSIColors,
    ansi_to_rgb,
    rgb_to_ansi256,
    rgb_to_ansitruecolor,
    interpolate_rgb,
    _supports_truecolor,
)


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
# Base Renderer Interface
# ============================================================================

class BaseRenderer(ABC):
    """
    Abstract base class for all renderers.
    
    This defines the interface that all renderers must implement,
    allowing the UI layer to be swapped without changing other modules.
    """
    
    @abstractmethod
    def setup(self) -> None:
        """Initialize the renderer (e.g., set up terminal)."""
        pass
    
    @abstractmethod
    def render(self, data: Dict[str, Any]) -> None:
        """
        Render the collected metrics data.
        
        Args:
            data: Dictionary containing metrics from all collectors,
                  keyed by collector name (e.g., {'cpu': {...}})
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear the display area."""
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources on exit."""
        pass


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
        return draw_bar_gradient(
            value, width, low_color, mid_color, high_color, empty_color,
            self._truecolor_support
        )
    
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
        return draw_status_bar(value, width, self._truecolor_support)
    
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
