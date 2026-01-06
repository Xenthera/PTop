"""
Panel class for UI layout and rendering.

This module provides the Panel class for creating bordered UI elements in the terminal.
"""

import re
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..ansi_renderer import ANSIRendererBase

from .container import Container
from ..utils import visible_length
from ..colors import ANSIColors

# Constants
LABEL_SEPARATOR_SPACING = 2  # Horizontal lines between labels
ELLIPSIS_LENGTH = 3  # Length of "..." truncation indicator


class Panel(Container):
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
        borderless: If True, render without borders (default: False)
        z: Z-order for rendering (lower values render first, default: 0)
        max_width: Optional maximum width (for HLayout constraints, default: None)
        max_height: Optional maximum height (for VLayout constraints, default: None)
    """
    def __init__(self, row: int, col: int, width: int, height: int, title: str = "", 
                 rounded: bool = False, border_color: Optional[str] = None, borderless: bool = False,
                 z: int = 0, max_width: Optional[int] = None, max_height: Optional[int] = None):
        super().__init__(row, col, width, height, z)
        self.title = title
        self.rounded = rounded
        self.border_color = border_color
        self.borderless = borderless
        self.max_width = max_width
        self.max_height = max_height
        self.left_labels: List[str] = []
        self.right_labels: List[str] = []
        self.center_labels: List[str] = []
        self.bottom_left_labels: List[str] = []
        self.bottom_right_labels: List[str] = []
        self.bottom_center_labels: List[str] = []
        # Title is always the first left-aligned label (only if not borderless)
        if title and not borderless:
            self.left_labels.append(title)
        self.content_lines: List[str] = []
        self._last_content_hash: Optional[int] = None
        self._last_labels_hash: Optional[int] = None
        self._last_rendered_lines: List[str] = []
        self._last_rendered_dimensions: Optional[Tuple[int, int, int, int]] = None  # (row, col, width, height)
    
    """Add a left-aligned label to the top border."""
    def add_left_label(self, label: str) -> None:
        if label:
            self.left_labels.append(label)
    
    """Add a right-aligned label to the top border."""
    def add_right_label(self, label: str) -> None:
        if label:
            self.right_labels.append(label)
    
    """Add a center-aligned label to the top border."""
    def add_center_label(self, label: str) -> None:
        if label:
            self.center_labels.append(label)
    
    """Add a left-aligned label to the bottom border."""
    def add_bottom_left_label(self, label: str) -> None:
        if label:
            self.bottom_left_labels.append(label)
    
    """Add a right-aligned label to the bottom border."""
    def add_bottom_right_label(self, label: str) -> None:
        if label:
            self.bottom_right_labels.append(label)
    
    """Add a center-aligned label to the bottom border."""
    def add_bottom_center_label(self, label: str) -> None:
        if label:
            self.bottom_center_labels.append(label)
    
    """Clear all labels, keeping only the title as first left label."""
    def clear_labels(self) -> None:
        self.left_labels = []
        self.right_labels = []
        self.center_labels = []
        self.bottom_left_labels = []
        self.bottom_right_labels = []
        self.bottom_center_labels = []
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
        max_width = self.width if self.borderless else self.width - 2
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
    Add an inline-composed line to panel content.
    
    Composes multiple inline elements (text, bars, graphs) into a single line.
    Automatically sizes resizable elements (bars, graphs) to fit panel width.
    Text elements get priority and use their natural width.
    Remaining space is divided evenly among resizable components.
    
    Args:
        *elements: Variable number of inline elements (InlineText, InlineBar, InlineGraph, InlineSpacer, or strings)
        separator: Optional separator string between elements (default: single space)
        renderer: Optional ANSIRendererBase instance (needed for resizable graphs)
    """
    def add_inline(self, *elements, separator: str = " ", renderer=None) -> None:
        # Set renderer for resizable graphs if provided (before composition)
        from .inline import InlineGraph, InlineBar
        if renderer:
            for elem in elements:
                if isinstance(elem, InlineGraph) and elem._is_resizable:
                    elem.set_renderer(renderer)
                elif isinstance(elem, InlineBar) and elem._is_resizable:
                    elem.renderer = renderer
        
        # Use panel width minus borders for available width
        available_width = self.width if self.borderless else self.width - 2
        from .inline import compose_inline_width
        line = compose_inline_width(available_width, *elements, separator=separator)
        
        # Re-render all resizable elements after composition to ensure they're updated
        if renderer:
            for elem in elements:
                if isinstance(elem, InlineGraph) and elem._is_resizable:
                    elem._render()
                elif isinstance(elem, InlineBar) and elem._is_resizable:
                    elem._render()
        
        self.add_line(line)
    
    """
    Get the content area of this panel.
    
    For bordered panels, returns area inside borders.
    For borderless panels, returns full bounds.
    
    Returns:
        Tuple of (content_row, content_col, content_width, content_height)
    """
    def get_content_area(self) -> Tuple[int, int, int, int]:
        if self.borderless:
            return (self.row, self.col, self.width, self.height)
        else:
            # Content area is inside borders: row+1, col+1, width-2, height-2
            return (self.row + 1, self.col + 1, self.width - 2, self.height - 2)
    
    """
    Check if panel content or dimensions have changed since last render.
    
    Returns:
        True if content or dimensions have changed, False otherwise
    """
    def has_changed(self) -> bool:
        # Check if dimensions or position have changed
        current_dimensions = (self.row, self.col, self.width, self.height)
        if self._last_rendered_dimensions != current_dimensions:
            self._last_rendered_dimensions = current_dimensions
            return True
        
        # Check if labels have changed
        current_labels_hash = hash((
            tuple(self.left_labels),
            tuple(self.right_labels),
            tuple(self.center_labels),
            tuple(self.bottom_left_labels),
            tuple(self.bottom_right_labels),
            tuple(self.bottom_center_labels)
        ))
        if current_labels_hash != self._last_labels_hash:
            self._last_labels_hash = current_labels_hash
            return True
        
        # Check if content has changed
        current_hash = hash(tuple(self.content_lines))
        if current_hash != self._last_content_hash:
            self._last_content_hash = current_hash
            return True
        return False
    
    # Border and rendering helper methods
    
    """Get border characters based on rounded flag."""
    def _get_border_chars(self) -> Tuple[str, str, str, str, str, str]:
        if self.rounded:
            return ('╭', '╮', '╰', '╯', '─', '│')
        else:
            return ('┌', '┐', '└', '┘', '─', '│')
    
    """Apply border color to text if border_color is set."""
    def _apply_border_color(self, text: str) -> str:
        if self.border_color:
            return self.border_color + text + ANSIColors.RESET
        return text
    
    """Apply border color only to border characters, not labels."""
    def _colorize_border_only(self, border_with_labels: str) -> str:
        if not self.border_color or not border_with_labels:
            return border_with_labels
        
        def colorize_match(match):
            return self._apply_border_color(match.group(0))
        
        # Match border characters: ┐, ┌, ┘, └, or sequences of ─
        result = re.sub(r'[┐┌┘└]|─+', colorize_match, border_with_labels)
        return result
    
    """Format labels with separators."""
    def _format_labels(self, labels: List[str], horizontal_char: str, is_bottom: bool = False) -> str:
        if not labels:
            return ""
        
        # Use bottom corners for bottom labels, top corners for top labels
        if is_bottom:
            left_sep = "┘"  # Bottom-right corner
            right_sep = "└"  # Bottom-left corner
        else:
            left_sep = "┐"  # Top-right corner
            right_sep = "┌"  # Top-left corner
        
        formatted = []
        for i, label in enumerate(labels):
            formatted.append(left_sep)
            formatted.append(f" {label} ")
            formatted.append(right_sep)
            # Add horizontal lines between labels (except after last)
            if i < len(labels) - 1:
                formatted.append(horizontal_char * LABEL_SEPARATOR_SPACING)
        
        return ''.join(formatted)
    
    """Build top border with labels."""
    def _build_top_border(self, available_width: int) -> str:
        tl, tr, _, _, h, _ = self._get_border_chars()
        
        # Format labels
        left_text = self._format_labels(self.left_labels, h)
        right_text = self._format_labels(self.right_labels, h)
        center_text = self._format_labels(self.center_labels, h)
        
        left_len = visible_length(left_text)
        right_len = visible_length(right_text)
        center_len = visible_length(center_text)
        total_label_len = left_len + right_len + center_len
        
        # Handle truncation if labels are too long
        if total_label_len >= available_width:
            # Priority: left, right, then center
            if left_text and left_len > available_width // 3:
                left_text = left_text[:available_width // 3]
                left_len = visible_length(left_text)
            if right_text and right_len > available_width // 3:
                right_text = right_text[:available_width // 3]
                right_len = visible_length(right_text)
            remaining = available_width - left_len - right_len
            if center_text and center_len > remaining:
                center_text = center_text[:remaining]
                center_len = visible_length(center_text)
        
        # Build border string with left, center, and right labels
        if not left_text and not right_text and not center_text:
            # No labels - just horizontal line
            top_border = tl + h * available_width + tr
            return ANSIColors.BOLD + self._apply_border_color(top_border) + ANSIColors.RESET
        
        # Calculate spacing: center should be truly centered in the full width
        if center_text:
            # Center label exists: calculate center position in full width
            center_start = (available_width - center_len) // 2
            
            # Calculate how much space we have on each side of center
            # Left side: from start to center_start
            # Right side: from center_end to end
            center_end = center_start + center_len
            
            # Left labels go on the left, but can't overlap center
            left_space_available = max(0, center_start - left_len)
            # Right labels go on the right, but can't overlap center
            right_space_available = max(0, available_width - center_end - right_len)
            
            # Build: [left labels][space][center][space][right labels]
            # If left/right would overlap center, truncate them
            if left_len > center_start:
                # Left overlaps center, truncate left
                left_text = left_text[:max(0, center_start - 1)]
                left_len = visible_length(left_text)
            
            if right_len > (available_width - center_end):
                # Right overlaps center, truncate right
                right_text = right_text[:max(0, available_width - center_end - 1)]
                right_len = visible_length(right_text)
            
            # Recalculate positions
            center_start = (available_width - center_len) // 2
            center_end = center_start + center_len
            
            # Calculate spaces
            left_to_center_space = max(0, center_start - left_len)
            center_to_right_space = max(0, available_width - center_end - right_len)
            
            top_border = tl + left_text + h * left_to_center_space + center_text + h * center_to_right_space + right_text + tr
        else:
            # No center label: left and right with space in between
            middle_space = max(0, available_width - left_len - right_len)
            top_border = tl + left_text + h * middle_space + right_text + tr
        
        # Apply color to border parts only
        colored_tl = self._apply_border_color(tl)
        colored_tr = self._apply_border_color(tr)
        colored_left = self._colorize_border_only(left_text)
        colored_right = self._colorize_border_only(right_text)
        colored_center = self._colorize_border_only(center_text) if center_text else ""
        
        # Rebuild with colored parts
        if center_text:
            center_start = (available_width - center_len) // 2
            center_end = center_start + center_len
            left_to_center_space = max(0, center_start - left_len)
            center_to_right_space = max(0, available_width - center_end - right_len)
            colored_middle_left = self._apply_border_color(h * left_to_center_space) if left_to_center_space > 0 else ""
            colored_middle_right = self._apply_border_color(h * center_to_right_space) if center_to_right_space > 0 else ""
            return ANSIColors.BOLD + colored_tl + colored_left + colored_middle_left + colored_center + colored_middle_right + colored_right + colored_tr + ANSIColors.RESET
        else:
            middle_space = max(0, available_width - left_len - right_len)
            colored_middle = self._apply_border_color(h * middle_space) if middle_space > 0 else ""
            return ANSIColors.BOLD + colored_tl + colored_left + colored_middle + colored_right + colored_tr + ANSIColors.RESET
    
    """Build content area lines with borders."""
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
    
    """Build bottom border with labels."""
    def _build_bottom_border(self) -> str:
        _, _, bl, br, h, _ = self._get_border_chars()
        available_width = self.width - 2  # Account for corner characters
        
        # Format labels
        left_text = self._format_labels(self.bottom_left_labels, h, is_bottom=True)
        right_text = self._format_labels(self.bottom_right_labels, h, is_bottom=True)
        center_text = self._format_labels(self.bottom_center_labels, h, is_bottom=True)
        
        left_len = visible_length(left_text)
        right_len = visible_length(right_text)
        center_len = visible_length(center_text)
        total_label_len = left_len + right_len + center_len
        
        # Handle truncation if labels are too long
        if total_label_len >= available_width:
            # Priority: left, right, then center
            if left_text and left_len > available_width // 3:
                left_text = left_text[:available_width // 3]
                left_len = visible_length(left_text)
            if right_text and right_len > available_width // 3:
                right_text = right_text[:available_width // 3]
                right_len = visible_length(right_text)
            remaining = available_width - left_len - right_len
            if center_text and center_len > remaining:
                center_text = center_text[:remaining]
                center_len = visible_length(center_text)
        
        # Build border string with left, center, and right labels
        if not left_text and not right_text and not center_text:
            # No labels - just horizontal line
            bottom_border = bl + h * available_width + br
            return ANSIColors.BOLD + self._apply_border_color(bottom_border) + ANSIColors.RESET
        
        # Calculate spacing: center should be truly centered in the full width
        if center_text:
            # Center label exists: calculate center position in full width
            center_start = (available_width - center_len) // 2
            
            # Calculate how much space we have on each side of center
            # Left side: from start to center_start
            # Right side: from center_end to end
            center_end = center_start + center_len
            
            # Left labels go on the left, but can't overlap center
            left_space_available = max(0, center_start - left_len)
            # Right labels go on the right, but can't overlap center
            right_space_available = max(0, available_width - center_end - right_len)
            
            # Build: [left labels][space][center][space][right labels]
            # If left/right would overlap center, truncate them
            if left_len > center_start:
                # Left overlaps center, truncate left
                left_text = left_text[:max(0, center_start - 1)]
                left_len = visible_length(left_text)
            
            if right_len > (available_width - center_end):
                # Right overlaps center, truncate right
                right_text = right_text[:max(0, available_width - center_end - 1)]
                right_len = visible_length(right_text)
            
            # Recalculate positions
            center_start = (available_width - center_len) // 2
            center_end = center_start + center_len
            
            # Calculate spaces
            left_to_center_space = max(0, center_start - left_len)
            center_to_right_space = max(0, available_width - center_end - right_len)
            
            bottom_border = bl + left_text + h * left_to_center_space + center_text + h * center_to_right_space + right_text + br
        else:
            # No center label: left and right with space in between
            middle_space = max(0, available_width - left_len - right_len)
            bottom_border = bl + left_text + h * middle_space + right_text + br
        
        # Apply color to border parts only
        colored_bl = self._apply_border_color(bl)
        colored_br = self._apply_border_color(br)
        colored_left = self._colorize_border_only(left_text)
        colored_right = self._colorize_border_only(right_text)
        colored_center = self._colorize_border_only(center_text) if center_text else ""
        
        # Rebuild with colored parts
        if center_text:
            center_start = (available_width - center_len) // 2
            center_end = center_start + center_len
            left_to_center_space = max(0, center_start - left_len)
            center_to_right_space = max(0, available_width - center_end - right_len)
            colored_middle_left = self._apply_border_color(h * left_to_center_space) if left_to_center_space > 0 else ""
            colored_middle_right = self._apply_border_color(h * center_to_right_space) if center_to_right_space > 0 else ""
            return ANSIColors.BOLD + colored_bl + colored_left + colored_middle_left + colored_center + colored_middle_right + colored_right + colored_br + ANSIColors.RESET
        else:
            middle_space = max(0, available_width - left_len - right_len)
            colored_middle = self._apply_border_color(h * middle_space) if middle_space > 0 else ""
            return ANSIColors.BOLD + colored_bl + colored_left + colored_middle + colored_right + colored_br + ANSIColors.RESET
    
    """
    Render the panel as a list of ANSI strings.
    
    This renders only the panel itself (borders and content).
    Children are rendered separately by the renderer.
    
    Args:
        renderer: The ANSI renderer instance (unused, kept for interface compatibility)
        force_redraw: If True, force redraw even if unchanged
    
    Returns:
        List of strings, each representing a line of the panel
    """
    def render(self, renderer: 'ANSIRendererBase' = None, force_redraw: bool = False) -> List[str]:
        if not force_redraw and not self.has_changed():
            return self._last_rendered_lines
        
        lines = []
        
        if self.borderless:
            # Borderless panel: render content directly without borders
            content_height = self.height
            for i in range(content_height):
                if i < len(self.content_lines):
                    content = self.content_lines[i]
                    visible_len = visible_length(content)
                    padding_needed = max(0, (self.width - visible_len))
                    padded = content + ' ' * padding_needed
                else:
                    padded = ' ' * self.width
                lines.append(padded)
        else:
            # Bordered panel: render with borders
            # Ensure minimum height of 3 (top border, content, bottom border)
            if self.height < 3:
                # Panel too small for borders - render as borderless content only
                for i in range(self.height):
                    if i < len(self.content_lines):
                        content = self.content_lines[i]
                        visible_len = visible_length(content)
                        padding_needed = max(0, (self.width - visible_len))
                        padded = content + ' ' * padding_needed
                    else:
                        padded = ' ' * self.width
                    lines.append(padded)
            else:
                # Top border with labels
                available_width = self.width - 2  # Account for corner characters
                lines.append(self._build_top_border(available_width))
                
                # Content lines - if panel has children but no content, skip rendering
                # empty content lines that would clear the children area
                if self.content_lines or not self.children:
                    lines.extend(self._build_content_lines())
                else:
                    # Panel has children but no content - render border structure only
                    # Children will render in the content area, so we don't want to clear it
                    _, _, _, _, _, v = self._get_border_chars()
                    content_height = self.height - 2
                    for _ in range(content_height):
                        left_border = self._apply_border_color(v)
                        right_border = self._apply_border_color(v)
                        # Render borders only, leave content area empty for children
                        lines.append(left_border + ' ' * (self.width - 2) + right_border)
                
                # Bottom border
                lines.append(self._build_bottom_border())
        
        self._last_rendered_lines = lines
        return lines

