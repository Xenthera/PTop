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
from .ui_elements import draw_status_bar, draw_bar_gradient, Container, Panel, BaseLayout, HLayout, VLayout


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
    _supports_truecolor,
)


# ============================================================================
# Container and Layout classes are now in separate modules:
# - container.py: Container, Panel
# - layout.py: BaseLayout, HLayout, VLayout
# ============================================================================


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
                  keyed by collector name
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear the display area."""
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources (e.g., restore terminal state)."""
        pass




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
    - Windows Console API optimization for extreme performance
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
        self._initialized = False
        self._truecolor_support = _supports_truecolor()
        # Double buffering: front_buffer is last frame drawn, back_buffer is frame being built
        self.front_buffer: Optional[List[str]] = None  # Previous frame (row-indexed, 0-based)
        self.back_buffer: Optional[List[str]] = None   # Current frame being built
        # Windows Console API optimization - cache console handle
        self._win_console_handle = None
        self._win_kernel32 = None
        self._win_WriteConsoleW = None
    
    """Initialize the renderer and terminal."""
    def setup(self) -> None:
        # On Windows, configure stdout to use UTF-8 encoding for Unicode box-drawing characters
        if sys.platform == 'win32':
            try:
                # Initialize Windows Console API for extreme performance
                import ctypes
                from ctypes import wintypes
                self._win_kernel32 = ctypes.windll.kernel32
                STD_OUTPUT_HANDLE = -11
                self._win_console_handle = self._win_kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
                
                if self._win_console_handle and self._win_console_handle != -1:
                    # Setup WriteConsoleW function pointer for fast calls
                    self._win_WriteConsoleW = self._win_kernel32.WriteConsoleW
                    self._win_WriteConsoleW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
                    self._win_WriteConsoleW.restype = wintypes.BOOL
                
                # Try to set UTF-8 encoding for stdout (fallback)
                try:
                    if hasattr(sys.stdout, 'reconfigure'):
                        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                    elif hasattr(sys.stdout, 'buffer'):
                        # Fallback: wrap stdout with UTF-8 encoding
                        # Disable line_buffering for better performance (we flush explicitly)
                        import io
                        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=False)
                except (AttributeError, OSError, ValueError):
                    pass
            except (ImportError, AttributeError, OSError):
                # If Windows API initialization fails, continue with regular stdout
                self._win_console_handle = None
                self._win_kernel32 = None
                self._win_WriteConsoleW = None
        
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
            # On Windows, cache terminal size check to avoid repeated syscalls
            # Only check if we don't have a cached size or if it's been a while
            if sys.platform == 'win32' and hasattr(self, '_cached_terminal_size'):
                import time
                current_time = time.time()
                # Cache for 0.1 seconds to reduce syscalls (terminal size rarely changes)
                if current_time - getattr(self, '_last_terminal_check', 0) < 0.1:
                    return self._cached_terminal_size
                self._last_terminal_check = current_time
            
            cols, rows = shutil.get_terminal_size()
            new_size = (cols, rows)
            # If terminal size changed, invalidate buffers to force full redraw
            if new_size != self.terminal_size:
                self.terminal_size = new_size
                self.front_buffer = None  # Force full redraw on next frame
            
            # Cache on Windows
            if sys.platform == 'win32':
                self._cached_terminal_size = new_size
                if not hasattr(self, '_last_terminal_check'):
                    import time
                    self._last_terminal_check = time.time()
            
            return new_size
        except (OSError, AttributeError, ValueError):
            return (DEFAULT_TERMINAL_COLS, DEFAULT_TERMINAL_ROWS)
    
    
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
    def _build_frame_buffer(self, containers: List[Container], force_redraw: bool = False) -> List[str]:
        cols, rows = self.terminal_size
        
        # Initialize back buffer as blank rows (each row padded to width, ends with RESET)
        buffer = [' ' * cols + ANSIColors.RESET for _ in range(rows)]
        
        # Sort containers by z-order (lower z renders first)
        sorted_containers = sorted(containers, key=lambda c: c.z)
        
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
        
        # On Windows, use cached Windows Console API for extreme performance
        if sys.platform == 'win32' and self._win_console_handle and self._win_WriteConsoleW:
            try:
                from ctypes import wintypes
                import ctypes
                
                # Extreme optimization: build string directly using list with pre-sized estimate
                # This avoids multiple allocations and method lookups
                cols = self.terminal_size[0]
                
                # Count how many rows we'll write
                if front_buffer is None or len(front_buffer) != rows:
                    rows_to_write = rows
                else:
                    rows_to_write = sum(1 for i in range(rows) if front_buffer[i] != back_buffer[i])
                
                if rows_to_write == 0:
                    return
                
                # Pre-allocate with conservative estimate: cursor move (10) + row (cols + ANSI overhead ~50)
                estimated_size = rows_to_write * (10 + cols + 50)
                output_parts = []
                output_parts_append = output_parts.append  # Cache method lookup for speed
                
                if front_buffer is None or len(front_buffer) != rows:
                    # Full redraw - build all at once
                    for row_idx in range(rows):
                        # Move cursor to row (1-based in ANSI), column 1
                        output_parts_append(f'\033[{row_idx + 1};1H')
                        output_parts_append(back_buffer[row_idx])
                else:
                    # Diff row by row and write only changed rows
                    for row_idx in range(rows):
                        if front_buffer[row_idx] != back_buffer[row_idx]:
                            # Row changed - write it
                            output_parts_append(f'\033[{row_idx + 1};1H')
                            output_parts_append(back_buffer[row_idx])
                
                # Join all parts into single string (single allocation, optimized by Python)
                output_str = ''.join(output_parts)
                
                # Write using cached WriteConsoleW function pointer
                # This bypasses Python's stdout wrapper and all encoding overhead
                written = wintypes.DWORD(0)
                char_count = len(output_str)
                result = self._win_WriteConsoleW(
                    self._win_console_handle,
                    output_str,  # ctypes converts Python string to LPCWSTR automatically
                    char_count,
                    ctypes.byref(written),
                    None
                )
                
                if not result:
                    # Fallback to regular stdout if WriteConsoleW fails
                    sys.stdout.write(output_str)
                    sys.stdout.flush()
                return
            except (AttributeError, OSError, TypeError):
                # Fall through to regular implementation if Windows API fails
                pass
        
        # Non-Windows or fallback path (original implementation)
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
    
    """Render containers using double buffering to eliminate flicker."""
    def render_containers(self, containers: List[Container], force_redraw: bool = False) -> None:
        # Build the new frame in back buffer
        self.back_buffer = self._build_frame_buffer(containers, force_redraw=force_redraw)
        
        # Diff and draw only changed rows
        self._diff_and_draw(self.front_buffer, self.back_buffer)
        
        # Swap buffers
        self.front_buffer = self.back_buffer
    
    """Render all registered containers using double buffering (backward compatibility)."""
    def render_all_panels(self, force_redraw: bool = False) -> None:
        # This method is deprecated - use render_containers() instead
        # For backward compatibility, return empty (caller should use render_containers)
        pass
    
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
