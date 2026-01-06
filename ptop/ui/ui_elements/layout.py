"""
Layout system for managing panel positioning and sizing.

This module provides layout managers (HLayout, VLayout) that arrange
panels and nested layouts within containers.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container
    from .panel import Panel

from .container import Container
from .panel import Panel


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
    def get_content_area(self) -> tuple:
        return (self.row + self.margin, self.col + self.margin,
                self.width - (2 * self.margin), self.height - (2 * self.margin))
    
    def add_child(self, child: 'Container') -> None:
        super().add_child(child)
    
    """Add a panel to this layout (convenience for add_child)."""
    def add_panel(self, panel: 'Panel') -> None:
        self.add_child(panel)
    
    """Add a nested layout (convenience for add_child)."""
    def add_layout(self, layout: 'BaseLayout') -> None:
        self.add_child(layout)
    
    """Update layout: arrange children within content area (must be implemented by subclasses)."""
    def update(self) -> None:
        raise NotImplementedError("Subclasses must implement update()")
    
    """Render this layout (returns empty list, layouts don't render themselves)."""
    def render(self, renderer=None, force_redraw: bool = False) -> list:
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

