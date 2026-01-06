"""
Container base class for UI layout and rendering.

This module provides the base Container class that all UI elements inherit from.
"""

from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..ansi_renderer import ANSIRendererBase


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

