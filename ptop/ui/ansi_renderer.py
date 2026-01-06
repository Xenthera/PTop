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
from .history_graph import SingleLineGraph, MultiLineGraph
from .progress_bar import draw_status_bar, draw_bar_gradient
from .inline import compose_inline, compose_inline_width, InlineText, InlineBar, InlineGraph, InlineSpacer


# ============================================================================
# Constants
# ============================================================================

DEFAULT_TERMINAL_COLS = 80
DEFAULT_TERMINAL_ROWS = 24
FLOOR_EPSILON = 1e-6
LABEL_SEPARATOR_SPACING = 2  # Horizontal lines between labels
ELLIPSIS_LENGTH = 3  # Length of "..." truncation indicator


# ============================================================================
# Utility Functions
# ============================================================================

# Import utility functions
from .utils import strip_ansi, visible_length


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
# Container Base Class
# ============================================================================

class Container:
    """
    Base class for all UI containers (panels and layouts).
    
    Containers have bounds, can contain other containers, and automatically
    clip children to their content area.
    """
    
    """
    Initialize a container.
    
    Args:
        row: Top row position (1-based)
        col: Left column position (1-based)
        width: Container width in characters
        height: Container height in lines
        z: Z-order for rendering (lower values render first, default: 0)
    """
    def __init__(self, row: int, col: int, width: int, height: int, z: int = 0):
        self.row = row
        self.col = col
        self.width = width
        self.height = height
        self.z = z
        self.children: List['Container'] = []
        self.parent: Optional['Container'] = None
    
    """Get the content area (full bounds by default, overridden by Panel)."""
    def get_content_area(self) -> Tuple[int, int, int, int]:
        # Default implementation: full bounds (overridden by Panel for bordered)
        return (self.row, self.col, self.width, self.height)
    
    """Add a child container."""
    def add_child(self, child: 'Container') -> None:
        if child.parent is not None:
            child.parent.remove_child(child)
        self.children.append(child)
        child.parent = self
    
    """Remove a child container."""
    def remove_child(self, child: 'Container') -> None:
        if child in self.children:
            self.children.remove(child)
            child.parent = None
    
    """Set the bounds of this container."""
    def set_bounds(self, row: int, col: int, width: int, height: int) -> None:
        self.row = row
        self.col = col
        self.width = width
        self.height = height
    
    """
    Render this container and its children.
    
    This is called by the renderer. Containers should render themselves,
    then render their children (clipped to content area).
    
    Args:
        renderer: The ANSI renderer instance
        force_redraw: If True, force redraw even if unchanged
    
    Returns:
        List of strings representing rendered lines
    """
    def render(self, renderer: 'ANSIRendererBase', force_redraw: bool = False) -> List[str]:
        raise NotImplementedError("Subclasses must implement render()")
    
    """
    Render children of this container, clipped to content area.
    
    Args:
        renderer: The ANSI renderer instance
        force_redraw: If True, force redraw even if unchanged
        clip_row: Optional external clipping region (intersects with content area)
        clip_col: Optional external clipping region
        clip_width: Optional external clipping region
        clip_height: Optional external clipping region
    """
    def render_children(self, renderer: 'ANSIRendererBase', force_redraw: bool = False,
                       clip_row: Optional[int] = None, clip_col: Optional[int] = None,
                       clip_width: Optional[int] = None, clip_height: Optional[int] = None) -> None:
        content_row, content_col, content_width, content_height = self.get_content_area()
        
        # Calculate effective clipping region (intersection of content area and external clip)
        if clip_row is not None and clip_col is not None and clip_width is not None and clip_height is not None:
            # Intersect external clip with content area
            clip_left = max(clip_col, content_col)
            clip_top = max(clip_row, content_row)
            clip_right = min(clip_col + clip_width - 1, content_col + content_width - 1)
            clip_bottom = min(clip_row + clip_height - 1, content_row + content_height - 1)
            
            if clip_left > clip_right or clip_top > clip_bottom:
                return  # No intersection, nothing to render
            
            effective_clip_row = clip_top
            effective_clip_col = clip_left
            effective_clip_width = clip_right - clip_left + 1
            effective_clip_height = clip_bottom - clip_top + 1
        else:
            # No external clipping, use content area
            effective_clip_row = content_row
            effective_clip_col = content_col
            effective_clip_width = content_width
            effective_clip_height = content_height
        
        # Sort children by z-order (lower z renders first)
        sorted_children = sorted(self.children, key=lambda c: c.z)
        
        for child in sorted_children:
            # Calculate child bounds
            child_bottom = child.row + child.height - 1
            child_right = child.col + child.width - 1
            
            # Skip if child is completely outside effective clipping region
            if (child_bottom < effective_clip_row or child.row > effective_clip_row + effective_clip_height - 1 or
                child_right < effective_clip_col or child.col > effective_clip_col + effective_clip_width - 1):
                continue
            
            # Pass the effective clipping region to child
            renderer._render_container(child, force_redraw=force_redraw,
                                      clip_row=effective_clip_row, clip_col=effective_clip_col,
                                      clip_width=effective_clip_width, clip_height=effective_clip_height)
    
    """Render children into a frame buffer (for double buffering)."""
    def render_children_to_buffer(self, renderer: 'ANSIRendererBase', buffer: List[str], 
                                 force_redraw: bool = False,
                                 clip_row: Optional[int] = None, clip_col: Optional[int] = None,
                                 clip_width: Optional[int] = None, clip_height: Optional[int] = None) -> None:
        content_row, content_col, content_width, content_height = self.get_content_area()
        
        # Calculate effective clipping region (intersection of content area and external clip)
        if clip_row is not None and clip_col is not None and clip_width is not None and clip_height is not None:
            # Intersect external clip with content area
            clip_left = max(clip_col, content_col)
            clip_top = max(clip_row, content_row)
            clip_right = min(clip_col + clip_width - 1, content_col + content_width - 1)
            clip_bottom = min(clip_row + clip_height - 1, content_row + content_height - 1)
            
            if clip_left > clip_right or clip_top > clip_bottom:
                return  # No intersection, nothing to render
            
            effective_clip_row = clip_top
            effective_clip_col = clip_left
            effective_clip_width = clip_right - clip_left + 1
            effective_clip_height = clip_bottom - clip_top + 1
        else:
            # No external clipping, use content area
            effective_clip_row = content_row
            effective_clip_col = content_col
            effective_clip_width = content_width
            effective_clip_height = content_height
        
        # Sort children by z-order (lower z renders first)
        sorted_children = sorted(self.children, key=lambda c: c.z)
        
        for child in sorted_children:
            # Calculate child bounds
            child_bottom = child.row + child.height - 1
            child_right = child.col + child.width - 1
            
            # Skip if child is completely outside effective clipping region
            if (child_bottom < effective_clip_row or child.row > effective_clip_row + effective_clip_height - 1 or
                child_right < effective_clip_col or child.col > effective_clip_col + effective_clip_width - 1):
                continue
            
            # Pass the effective clipping region to child
            renderer._render_container_to_buffer(child, buffer, force_redraw=force_redraw,
                                                clip_row=effective_clip_row, clip_col=effective_clip_col,
                                                clip_width=effective_clip_width, clip_height=effective_clip_height)


# ============================================================================
# Panel Class
# ============================================================================

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


# ============================================================================
# Layout System
# ============================================================================

class BaseLayout(Container):
    """
    Base class for layout managers.
    
    Layouts manage panel positioning and sizing based on terminal dimensions.
    Supports both panels and nested layouts.
    """
    
    """
    Initialize a layout.
    
    Args:
        row: Top row position (1-based)
        col: Left column position (1-based)
        width: Layout width in characters
        height: Layout height in lines
        margin: Margin around the layout (default: 0)
        spacing: Spacing between items (default: 1)
        z: Z-order for rendering (default: 0)
    """
    def __init__(self, row: int = 1, col: int = 1, width: int = 80, height: int = 24,
                 margin: int = 0, spacing: int = 1, z: int = 0):
        super().__init__(row, col, width, height, z)
        self.margin = margin
        self.spacing = spacing
    
    """Get the content area (accounts for margins)."""
    def get_content_area(self) -> Tuple[int, int, int, int]:
        return (self.row + self.margin, self.col + self.margin,
                self.width - (2 * self.margin), self.height - (2 * self.margin))
    
    def add_child(self, child: Container) -> None:
        super().add_child(child)
    
    """Add a panel to this layout (convenience for add_child)."""
    def add_panel(self, panel: Panel) -> None:
        self.add_child(panel)
    
    """Add a nested layout (convenience for add_child)."""
    def add_layout(self, layout: 'BaseLayout') -> None:
        self.add_child(layout)
    
    """Update layout: arrange children within content area (must be implemented by subclasses)."""
    def update(self) -> None:
        raise NotImplementedError("Subclasses must implement update()")
    
    """Render this layout (returns empty list, layouts don't render themselves)."""
    def render(self, renderer: 'ANSIRendererBase' = None, force_redraw: bool = False) -> List[str]:
        # Layouts don't render themselves, only arrange children
        # Children are rendered by the renderer
        return []


class HLayout(BaseLayout):
    """
    Horizontal layout - arranges panels side by side.
    
    Panels are distributed equally across the available width.
    """
    
    """Update layout: arrange children horizontally."""
    def update(self) -> None:
        if not self.children:
            return
        
        content_row, content_col, content_width, content_height = self.get_content_area()
        
        num_items = len(self.children)
        if num_items == 0:
            return
        
        # Calculate base item width
        total_spacing = self.spacing * (num_items - 1)
        base_item_width = (content_width - total_spacing) // num_items
        
        # Apply max_width constraints and redistribute space
        # First pass: calculate actual widths considering max_width
        actual_widths = []
        total_used_width = 0
        flexible_items = []
        
        for child in self.children:
            if isinstance(child, Panel) and child.max_width is not None:
                actual_width = min(base_item_width, child.max_width)
                actual_widths.append(actual_width)
                total_used_width += actual_width
            else:
                actual_widths.append(base_item_width)
                total_used_width += base_item_width
                flexible_items.append(len(actual_widths) - 1)
        
        # Redistribute remaining space to flexible items
        remaining_width = content_width - total_spacing - total_used_width
        if remaining_width > 0 and flexible_items:
            extra_per_item = remaining_width // len(flexible_items)
            for idx in flexible_items:
                actual_widths[idx] += extra_per_item
            # Distribute any remainder
            remainder = remaining_width % len(flexible_items)
            for i, idx in enumerate(flexible_items):
                if i < remainder:
                    actual_widths[idx] += 1
        
        # Position items horizontally
        current_col = content_col
        for i, child in enumerate(self.children):
            item_width = actual_widths[i]
            child.set_bounds(content_row, current_col, item_width, content_height)
            if isinstance(child, BaseLayout):
                child.update()  # Recursively update nested layouts
            current_col += item_width + self.spacing


class VLayout(BaseLayout):
    """
    Vertical layout - arranges panels stacked vertically.
    
    Panels are distributed equally across the available height.
    """
    
    """Update layout: arrange children vertically."""
    def update(self) -> None:
        if not self.children:
            return
        
        content_row, content_col, content_width, content_height = self.get_content_area()
        
        num_items = len(self.children)
        if num_items == 0:
            return
        
        # Calculate base item height
        total_spacing = self.spacing * (num_items - 1)
        base_item_height = (content_height - total_spacing) // num_items
        
        # Apply max_height constraints and redistribute space
        # First pass: calculate actual heights considering max_height
        actual_heights = []
        total_used_height = 0
        flexible_items = []
        
        for child in self.children:
            if isinstance(child, Panel) and child.max_height is not None:
                actual_height = min(base_item_height, child.max_height)
                actual_heights.append(actual_height)
                total_used_height += actual_height
            else:
                actual_heights.append(base_item_height)
                total_used_height += base_item_height
                flexible_items.append(len(actual_heights) - 1)
        
        # Redistribute remaining space to flexible items
        remaining_height = content_height - total_spacing - total_used_height
        if remaining_height > 0 and flexible_items:
            extra_per_item = remaining_height // len(flexible_items)
            for idx in flexible_items:
                actual_heights[idx] += extra_per_item
            # Distribute any remainder
            remainder = remaining_height % len(flexible_items)
            for i, idx in enumerate(flexible_items):
                if i < remainder:
                    actual_heights[idx] += 1
        
        # Ensure total height doesn't exceed available space
        total_actual_height = sum(actual_heights) + total_spacing
        if total_actual_height > content_height:
            # Reduce heights to fit, but respect max_height constraints
            # Items with max_height constraints should not be scaled below their max_height
            # Only scale down flexible items (those without max_height constraints)
            excess_height = total_actual_height - content_height
            
            # Build a list of which items have max_height constraints
            constrained_items = []
            for i, child in enumerate(self.children):
                if isinstance(child, Panel) and child.max_height is not None:
                    constrained_items.append(i)
            
            # Try to reduce only flexible items first
            if flexible_items:
                # Calculate how much we can reduce from flexible items
                reduction_per_flexible = excess_height // len(flexible_items)
                for idx in flexible_items:
                    new_height = max(1, actual_heights[idx] - reduction_per_flexible)
                    actual_heights[idx] = new_height
                
                # Distribute any remaining excess
                remaining_excess = excess_height - (reduction_per_flexible * len(flexible_items))
                for idx in flexible_items:
                    if remaining_excess <= 0:
                        break
                    if actual_heights[idx] > 1:
                        reduction = min(remaining_excess, actual_heights[idx] - 1)
                        actual_heights[idx] -= reduction
                        remaining_excess -= reduction
            
            # Recalculate total
            total_actual_height = sum(actual_heights) + total_spacing
            
            # If still too large, we need to scale constrained items proportionally
            # but ensure they don't go below their max_height
            if total_actual_height > content_height and constrained_items:
                # Scale all items proportionally, but clamp constrained items to their max_height
                scale_factor = content_height / total_actual_height
                for i in range(len(actual_heights)):
                    if i in constrained_items:
                        child = self.children[i]
                        min_allowed = child.max_height if isinstance(child, Panel) and child.max_height is not None else 1
                        scaled = int(actual_heights[i] * scale_factor)
                        actual_heights[i] = max(min_allowed, scaled)
                    else:
                        actual_heights[i] = max(1, int(actual_heights[i] * scale_factor))
                
                # Recalculate total after scaling
                total_actual_height = sum(actual_heights) + total_spacing
            
            # Add back any lost space to flexible items if we ended up with too little
            if total_actual_height < content_height:
                diff = content_height - total_actual_height
                for idx in reversed(flexible_items):
                    if diff > 0:
                        actual_heights[idx] += diff
                        diff = 0
                        break
        
        # Position items vertically
        content_end_row = content_row + content_height - 1  # Inclusive
        
        current_row = content_row
        for i, child in enumerate(self.children):
            item_height = actual_heights[i]
            
            # Calculate where this panel would end (inclusive)
            panel_bottom = current_row + item_height - 1
            
            # Clamp panel to fit within available space
            if panel_bottom > content_end_row:
                item_height = max(1, content_end_row - current_row + 1)
                panel_bottom = current_row + item_height - 1
            
            child.set_bounds(current_row, content_col, content_width, item_height)
            if isinstance(child, BaseLayout):
                child.update()  # Recursively update nested layouts
            
            # Move to next position (accounting for spacing)
            current_row = panel_bottom + 1 + self.spacing
            
            # Stop if we've exceeded the available space
            if current_row > content_end_row + 1:
                break




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
        self.panels: Dict[str, Panel] = {}  # Keep for backward compatibility
        self.containers: List[Container] = []  # Unified container registry
        self._initialized = False
        self._truecolor_support = _supports_truecolor()
        # Double buffering: front_buffer is last frame drawn, back_buffer is frame being built
        self.front_buffer: Optional[List[str]] = None  # Previous frame (row-indexed, 0-based)
        self.back_buffer: Optional[List[str]] = None   # Current frame being built
    
    """Initialize the renderer and terminal."""
    def setup(self) -> None:
        # On Windows, configure stdout to use UTF-8 encoding for Unicode box-drawing characters
        if sys.platform == 'win32':
            try:
                # Try to set UTF-8 encoding for stdout
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                elif hasattr(sys.stdout, 'buffer'):
                    # Fallback: wrap stdout with UTF-8 encoding
                    import io
                    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
            except (AttributeError, OSError, ValueError):
                # If reconfiguration fails, continue with default encoding
                # Box-drawing characters may not display correctly, but app won't crash
                pass
        
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
    
    """Get current terminal size."""
    def get_terminal_size(self) -> Tuple[int, int]:
        try:
            cols, rows = shutil.get_terminal_size()
            new_size = (cols, rows)
            # If terminal size changed, invalidate buffers to force full redraw
            if new_size != self.terminal_size:
                self.terminal_size = new_size
                self.front_buffer = None  # Force full redraw on next frame
            return new_size
        except (OSError, AttributeError, ValueError):
            return (DEFAULT_TERMINAL_COLS, DEFAULT_TERMINAL_ROWS)
    
    """Create a new panel."""
    def create_panel(self, panel_id: str, row: int = 1, col: int = 1, width: int = 80, height: int = 24, 
                     title: str = "", rounded: bool = False, border_color: Optional[str] = None,
                     borderless: bool = False, z: int = 0, max_width: Optional[int] = None,
                     max_height: Optional[int] = None) -> Panel:
        panel = Panel(row, col, width, height, title, rounded=rounded, border_color=border_color, 
                     borderless=borderless, z=z, max_width=max_width, max_height=max_height)
        self.panels[panel_id] = panel
        self.containers.append(panel)  # Add to unified registry
        return panel
    
    """Create a new history graph."""
    def create_history_graph(self, width: int, min_value: float = 0.0, max_value: float = 100.0, use_braille: bool = True) -> SingleLineGraph:
        return SingleLineGraph(width, min_value, max_value, use_braille=use_braille)
    
    """Create a new multi-line history graph."""
    def create_multi_line_graph(self, width_chars: int, height_chars: int, min_value: float = 0.0, 
                                 max_value: float = 100.0, use_braille: bool = True,
                                 top_to_bottom: bool = False, show_max_label: bool = False, 
                                 show_min_label: bool = False) -> MultiLineGraph:
        return MultiLineGraph(width_chars, height_chars, min_value, max_value, use_braille=use_braille, top_to_bottom=top_to_bottom, show_max_label=show_max_label, show_min_label=show_min_label)
    
    """Add a layout to be managed by the renderer."""
    def add_layout(self, layout: BaseLayout) -> None:
        self.containers.append(layout)  # Add to unified container registry
    
    """Create a horizontal progress bar with gradient colors (backward compatibility)."""
    def draw_bar(self, value: float, width: int, 
                 low_color: str = ANSIColors.BRIGHT_GREEN,
                 mid_color: str = ANSIColors.BRIGHT_YELLOW,
                 high_color: str = ANSIColors.BRIGHT_RED,
                 empty_color: str = ANSIColors.BRIGHT_BLACK) -> str:
        return draw_bar_gradient(
            value, width, low_color, mid_color, high_color, empty_color,
            self._truecolor_support
        )
    
    """Create a status bar with standard gradient colors (winter green -> yellow -> red)."""
    def draw_status_bar(self, value: float, width: int) -> str:
        return draw_status_bar(value, width, self._truecolor_support)
    
    """Move cursor to specified position (1-based)."""
    def move_cursor(self, row: int, col: int) -> None:
        sys.stdout.write(f'\033[{row};{col}H')
    
    """
    Clip a line to fit within visible width, preserving all ANSI codes.
    
    This method properly handles ANSI codes that may appear anywhere in the line,
    not just at the beginning. It maps visible characters to their positions in
    the original string (accounting for ANSI codes) and clips accordingly.
    
    Args:
        line: Line to clip
        max_visible_width: Maximum visible width (excluding ANSI codes)
        start_offset: Number of visible characters to skip from the start
    
    Returns:
        Clipped line string with all ANSI codes preserved
    """
    def _clip_line(self, line: str, max_visible_width: int, start_offset: int = 0) -> Tuple[str, int]:
        """
        Clip a line to fit within visible width, preserving all ANSI codes.
        Returns (clipped_line, visible_length).
        """
        if max_visible_width <= 0:
            return ("", 0)
        
        # Build a mapping of visible character positions to original string positions
        # This allows us to clip while preserving ANSI codes
        visible_to_original = []
        i = 0
        line_len = len(line)
        while i < line_len:
            if line[i] == '\033' and i + 1 < line_len and line[i + 1] == '[':
                # Found ANSI escape sequence - skip it but don't add to mapping
                j = i + 2
                while j < line_len and line[j] not in 'mH':
                    j += 1
                if j < line_len:
                    j += 1  # Include the terminator
                i = j
            else:
                # Regular character - map it
                visible_to_original.append(i)
                i += 1
        
        visible_len = len(visible_to_original)
        
        # Skip lines that are completely before the start offset
        if start_offset >= visible_len:
            return ("", 0)
        
        # Calculate the range of visible characters we want
        start_visible = start_offset
        end_visible = min(start_offset + max_visible_width, visible_len)
        
        if start_visible >= end_visible:
            return ("", 0)
        
        # Find the corresponding positions in the original string
        start_original = visible_to_original[start_visible]
        end_original = visible_to_original[end_visible - 1] + 1
        
        # Extract the clipped portion, preserving all ANSI codes
        clipped = line[start_original:end_original]
        
        return (clipped, end_visible - start_visible)
    
    """
    Build a complete frame buffer by rendering all containers.
    
    Returns a List[str] where each string is a terminal row (padded to terminal width,
    ends with RESET). Rows are 0-indexed internally but represent 1-based terminal rows.
    """
    def _build_frame_buffer(self, force_redraw: bool = False) -> List[str]:
        cols, rows = self.terminal_size
        
        # Initialize back buffer as blank rows (each row padded to width, ends with RESET)
        buffer = [' ' * cols + ANSIColors.RESET for _ in range(rows)]
        
        # Sort containers by z-order (lower z renders first)
        sorted_containers = sorted(self.containers, key=lambda c: c.z)
        
        # Render only root containers (those without parents)
        # Children will be rendered recursively
        for container in sorted_containers:
            if container.parent is None:
                self._render_container_to_buffer(container, buffer, force_redraw=force_redraw)
        
        return buffer
    
    """
    Extract a substring from a string up to a specific visible position, preserving ANSI codes.
    
    Returns the portion of the string up to (but not including) the specified visible character position.
    """
    def _extract_up_to_visible_pos(self, text: str, visible_pos: int) -> str:
        """Extract text up to visible_pos, preserving all ANSI codes."""
        if visible_pos <= 0:
            return ""
        
        visible_count = 0
        i = 0
        result_parts = []  # Use list for faster concatenation
        text_len = len(text)
        while i < text_len and visible_count < visible_pos:
            if text[i] == '\033' and i + 1 < text_len and text[i + 1] == '[':
                # ANSI escape sequence - include it
                j = i + 2
                while j < text_len and text[j] not in 'mH':
                    j += 1
                if j < text_len:
                    j += 1  # Include the terminator
                result_parts.append(text[i:j])
                i = j
            else:
                result_parts.append(text[i])
                visible_count += 1
                i += 1
        return ''.join(result_parts)
    
    """
    Write a line into a buffer row at a specific visible column position.
    
    This helper function composites a new line into an existing buffer row, preserving
    content before and after the insertion point, and handling ANSI codes correctly.
    """
    def _write_line_to_buffer_row(self, buffer_row: str, line: str, start_col: int, max_width: int, terminal_width: int) -> str:
        """Write a line into a buffer row string at visible position start_col."""
        from .utils import visible_length
        
        # Remove RESET from end if present
        has_reset = buffer_row.endswith(ANSIColors.RESET)
        buffer_content = buffer_row[:-len(ANSIColors.RESET)] if has_reset else buffer_row
        
        # Clip the line to max_width and get visible length from _clip_line (avoids extra visible_length call)
        # Quick check: if line is short, avoid calling _clip_line
        line_visible_len = visible_length(line)
        if line_visible_len > max_width:
            clipped_line, clipped_visible_len = self._clip_line(line, max_width, 0)
        else:
            clipped_line = line
            clipped_visible_len = line_visible_len
        
        # Extract "before" part, find "after" position, and count "after_visible" in a single pass
        after_start_visible = start_col + clipped_visible_len
        if start_col > 0 or after_start_visible < terminal_width:
            visible_count = 0
            i = 0
            buffer_len = len(buffer_content)
            before_parts = []
            after_start_pos = buffer_len  # Default to end if not found
            after_visible = 0
            
            while i < buffer_len:
                if buffer_content[i] == '\033' and i + 1 < buffer_len and buffer_content[i + 1] == '[':
                    # ANSI escape sequence
                    j = i + 2
                    while j < buffer_len and buffer_content[j] not in 'mH':
                        j += 1
                    if j < buffer_len:
                        j += 1
                    
                    if visible_count < start_col:
                        before_parts.append(buffer_content[i:j])
                    elif visible_count >= after_start_visible and after_start_pos == buffer_len:
                        after_start_pos = i
                    
                    i = j
                else:
                    # Regular character
                    if visible_count < start_col:
                        before_parts.append(buffer_content[i])
                    elif visible_count >= after_start_visible:
                        if after_start_pos == buffer_len:
                            after_start_pos = i
                        after_visible += 1
                    
                    visible_count += 1
                    i += 1
            
            before_part = ''.join(before_parts) if start_col > 0 else ""
            after_part = buffer_content[after_start_pos:] if after_start_visible < terminal_width and after_start_pos < buffer_len else ""
            if not after_part:
                after_visible = 0
        else:
            before_part = ""
            after_part = ""
            after_visible = 0
        
        # Build the new row: before_part + clipped_line + after_part
        new_row = before_part + clipped_line + after_part
        
        # Calculate total visible length (we already have all components)
        total_visible = start_col + clipped_visible_len + after_visible
        
        # Ensure exactly terminal_width visible characters (pad with spaces if needed)
        if total_visible < terminal_width:
            new_row += ' ' * (terminal_width - total_visible)
        elif total_visible > terminal_width:
            # Clip if somehow too long (shouldn't happen if clipping worked)
            new_row, _ = self._clip_line(new_row, terminal_width, 0)
        
        return new_row + ANSIColors.RESET
    
    """
    Render a container into the frame buffer at its absolute position.
    
    This replaces the old stdout-writing logic with buffer writing.
    """
    def _render_container_to_buffer(self, container: Container, buffer: List[str], 
                                   force_redraw: bool = False,
                                   clip_row: Optional[int] = None, clip_col: Optional[int] = None,
                                   clip_width: Optional[int] = None, clip_height: Optional[int] = None) -> None:
        # Render the container itself
        container_lines = container.render(self, force_redraw=force_redraw)
        
        # Render container lines into buffer with clipping
        cols, rows = self.terminal_size
        for i, line in enumerate(container_lines):
            render_row = container.row + i - 1  # Convert to 0-based buffer index (container.row is 1-based)
            
            # Skip if outside terminal bounds
            if render_row < 0 or render_row >= rows:
                continue
            
            # Skip if outside clipping region vertically
            if clip_row is not None and clip_height is not None:
                clip_row_0based = clip_row - 1  # Convert to 0-based
                if render_row < clip_row_0based or render_row >= clip_row_0based + clip_height:
                    continue
            
            # Calculate horizontal clipping for this line
            render_col = container.col - 1  # Convert to 0-based (visible column in buffer)
            clipped_line = line
            
            if clip_col is not None and clip_width is not None:
                clip_col_0based = clip_col - 1  # Convert to 0-based
                clip_right = clip_col_0based + clip_width - 1
                
                # Container starts before clip region
                if render_col < clip_col_0based:
                    start_offset = clip_col_0based - render_col
                    max_width = min(clip_width, container.width - start_offset)
                    clipped_line, _ = self._clip_line(line, max_width, start_offset)
                    render_col = clip_col_0based
                # Container extends beyond clip region
                elif render_col + container.width - 1 > clip_right:
                    max_width = clip_width - (render_col - clip_col_0based)
                    if max_width > 0:
                        clipped_line, _ = self._clip_line(line, max_width, 0)
                    else:
                        continue  # Line is completely outside clip region
                # Container is within clip region
                else:
                    clipped_line = line
                    # Clip to container width
                    from .utils import visible_length
                    # Check if clipping is needed using visible_length, then clip if needed
                    from .utils import visible_length
                    if visible_length(clipped_line) > container.width:
                        clipped_line, _ = self._clip_line(line, container.width, 0)
            
            # Determine how much width we can use
            max_line_width = min(cols - render_col, container.width)
            if clip_col is not None and clip_width is not None:
                clip_col_0based = clip_col - 1
                if render_col >= clip_col_0based:
                    max_line_width = min(max_line_width, clip_width - (render_col - clip_col_0based))
            
            # Write the line into the buffer row
            buffer[render_row] = self._write_line_to_buffer_row(
                buffer[render_row], clipped_line, render_col, max_line_width, cols
            )
        
        # Render children recursively (automatically clipped to container's content area)
        container.render_children_to_buffer(self, buffer, force_redraw=force_redraw,
                                          clip_row=clip_row, clip_col=clip_col,
                                          clip_width=clip_width, clip_height=clip_height)
    
    """
    Diff two frame buffers and write only changed rows to stdout.
    
    This eliminates flicker by building the entire frame in memory (back_buffer),
    comparing it row-by-row against the previous frame (front_buffer), and writing
    only changed rows atomically. This ensures the user sees complete, consistent frames
    rather than partial updates, similar to btop's rendering approach.
    """
    def _diff_and_draw(self, front_buffer: Optional[List[str]], back_buffer: List[str]) -> None:
        rows = len(back_buffer)
        
        # If no front buffer, draw everything (first frame or after resize)
        if front_buffer is None or len(front_buffer) != rows:
            # Full redraw
            for row_idx in range(rows):
                # Move cursor to row (1-based in ANSI)
                sys.stdout.write(f'\033[{row_idx + 1};1H')
                sys.stdout.write(back_buffer[row_idx])
            sys.stdout.flush()
            return
        
        # Diff row by row and write only changed rows
        for row_idx in range(rows):
            if front_buffer[row_idx] != back_buffer[row_idx]:
                # Row changed - write it
                # Move cursor to row (1-based in ANSI), column 1
                sys.stdout.write(f'\033[{row_idx + 1};1H')
                sys.stdout.write(back_buffer[row_idx])
        
        # Flush once after all changes
        sys.stdout.flush()
    
    """Render all registered containers using double buffering to eliminate flicker."""
    def render_all_panels(self, force_redraw: bool = False) -> None:
        # Build the new frame in back buffer
        self.back_buffer = self._build_frame_buffer(force_redraw=force_redraw)
        
        # Diff and draw only changed rows
        self._diff_and_draw(self.front_buffer, self.back_buffer)
        
        # Swap buffers
        self.front_buffer = self.back_buffer
    
    """Render a container and its children (internal method that handles clipping)."""
    def _render_container(self, container: Container, force_redraw: bool = False,
                         clip_row: Optional[int] = None, clip_col: Optional[int] = None,
                         clip_width: Optional[int] = None, clip_height: Optional[int] = None) -> None:
        # Render the container itself
        container_lines = container.render(self, force_redraw=force_redraw)
        
        # Render container lines with clipping
        cols, rows = self.terminal_size
        for i, line in enumerate(container_lines):
            render_row = container.row + i
            
            # Skip if outside clipping region vertically
            if clip_row is not None and clip_height is not None:
                if render_row < clip_row or render_row > clip_row + clip_height - 1:
                    continue
            
            # Calculate horizontal clipping for this line
            render_col = container.col
            clipped_line = line
            
            if clip_col is not None and clip_width is not None:
                clip_right = clip_col + clip_width - 1
                
                # Container starts before clip region
                if container.col < clip_col:
                    start_offset = clip_col - container.col
                    max_width = min(clip_width, container.width - start_offset)
                    clipped_line, _ = self._clip_line(line, max_width, start_offset)
                    render_col = clip_col
                # Container extends beyond clip region
                elif container.col + container.width - 1 > clip_right:
                    max_width = clip_width - (container.col - clip_col)
                    if max_width > 0:
                        clipped_line, _ = self._clip_line(line, max_width, 0)
                    else:
                        continue  # Line is completely outside clip region
                # Container is within clip region
                else:
                    clipped_line = line
            
            # Move cursor and render line
            # Use absolute cursor positioning - no need for \n since we position explicitly for each line
            self.move_cursor(render_row, render_col)
            sys.stdout.write(clipped_line)
        
        # Render children (automatically clipped to container's content area and external clip region)
        container.render_children(self, force_redraw=force_redraw,
                                 clip_row=clip_row, clip_col=clip_col,
                                 clip_width=clip_width, clip_height=clip_height)
    
    """Render a panel (backward compatibility, use render_all_panels() for new code)."""
    def render_panel(self, panel: Panel, force_redraw: bool = False, 
                     clip_row: Optional[int] = None, clip_col: Optional[int] = None,
                     clip_width: Optional[int] = None, clip_height: Optional[int] = None) -> None:
        # Delegate to _render_container for consistent rendering logic
        self._render_container(panel, force_redraw=force_redraw,
                             clip_row=clip_row, clip_col=clip_col,
                             clip_width=clip_width, clip_height=clip_height)
    
    """Render a header line."""
    def render_header(self, text: str, style: str = ANSIColors.BOLD + ANSIColors.BRIGHT_CYAN) -> None:
        width = self.terminal_size[0]
        padding = (width - visible_length(text)) // 2
        header = ' ' * padding + style + text + ANSIColors.RESET
        sys.stdout.write(header + '\n')
        sys.stdout.write('─' * width + '\n')
    
    """Render metrics data (required by BaseRenderer, but unused - use render_all_panels() instead)."""
    def render(self, data: Dict[str, Any]) -> None:
        # Minimal implementation for abstract base class requirement
        # Actual rendering uses render_all_panels() instead
        pass
    
    """Clear the display."""
    def clear(self) -> None:
        sys.stdout.write('\033[2J')
        sys.stdout.write('\033[H')
        sys.stdout.flush()
        # Invalidate buffers to force full redraw on next frame
        self.front_buffer = None
    
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
