"""
Inline composition system for mixing text, progress bars, and graphs on the same line.
"""

from typing import List, Union, Optional, TYPE_CHECKING
from ..utils import visible_length
from ..colors import ANSIColors

if TYPE_CHECKING:
    from .history_graph import SingleLineGraph
    from .progress_bar import ProgressBar


class InlineElement:
    """
    Base class for inline elements (text, bars, graphs).
    
    All inline elements must provide a string representation.
    """
    
    def __str__(self) -> str:
        """Return the string representation of this element."""
        raise NotImplementedError


class InlineText(InlineElement):
    """Text element for inline composition."""
    
    def __init__(self, text: str):
        """
        Initialize text element.
        
        Args:
            text: Text string (may contain ANSI codes)
        """
        self.text = text
    
    def __str__(self) -> str:
        return self.text


class InlineBar(InlineElement):
    """Progress bar element for inline composition."""
    
    def __init__(self, bar: 'ProgressBar', max_size: Optional[int] = None):
        """
        Initialize bar element from a ProgressBar object.
        
        Args:
            bar: ProgressBar object (knows its own colors and value)
            max_size: Maximum width in characters (None = no limit)
        """
        self.bar = bar
        self.width = 20  # Default width, will be resized
        self.max_size = max_size
        self._is_resizable = True
        self.bar_string = None
        # Render initial bar
        self._render()
    
    def _render(self) -> None:
        """Render the bar with current width."""
        if self.bar is not None:
            self.bar_string = self.bar.render(self.width)
    
    def resize(self, new_width: int) -> None:
        """
        Resize the bar to a new width.
        
        Args:
            new_width: New width in characters (will be clamped to max_size if set)
        """
        if self._is_resizable:
            if self.max_size is not None:
                self.width = min(new_width, self.max_size)
            else:
                self.width = new_width
            self._render()
    
    def get_actual_width(self) -> int:
        """Get the actual width used (may be less than requested if max_size is set)."""
        return self.width if self._is_resizable else visible_length(str(self))
    
    def __str__(self) -> str:
        if self.bar_string is not None:
            return self.bar_string
        return ""


class InlineGraph(InlineElement):
    """History graph element for inline composition."""
    
    def __init__(self, graph: 'SingleLineGraph', renderer, max_size: Optional[int] = None):
        """
        Initialize graph element from a SingleLineGraph object.
        
        Args:
            graph: SingleLineGraph object (knows its own colors)
            renderer: ANSIRendererBase instance for rendering
            max_size: Maximum width in characters (None = no limit)
        """
        self.graph = graph
        self.width = graph.width if graph else 20
        self.renderer = renderer
        self.max_size = max_size
        self._is_resizable = True
        self.graph_string = None
        # Render initial graph
        self._render()
    
    def _render(self) -> None:
        """Render the graph with current width."""
        if self.graph is not None and self.renderer is not None:
            # Update graph width
            self.graph.width = self.width
            self.graph_string = self.graph.get_graph_string(self.renderer)
    
    def set_renderer(self, renderer) -> None:
        """
        Set the renderer for graph rendering.
        
        Args:
            renderer: ANSIRendererBase instance
        """
        self.renderer = renderer
        if self._is_resizable:
            self._render()
    
    def resize(self, new_width: int) -> None:
        """
        Resize the graph to a new width.
        
        Args:
            new_width: New width in characters (will be clamped to max_size if set)
        """
        if self._is_resizable:
            if self.max_size is not None:
                self.width = min(new_width, self.max_size)
            else:
                self.width = new_width
            # Update graph width immediately before rendering
            if self.graph is not None:
                self.graph.width = self.width
            self._render()
    
    def get_actual_width(self) -> int:
        """Get the actual width used (may be less than requested if max_size is set)."""
        return self.width if self._is_resizable else visible_length(str(self))
    
    def __str__(self) -> str:
        if self.graph_string is not None:
            return self.graph_string
        return ""


class InlineSpacer(InlineElement):
    """Spacer element for inline composition."""
    
    def __init__(self, width: int = 1):
        """
        Initialize spacer element.
        
        Args:
            width: Number of spaces
        """
        self.width = width
    
    def __str__(self) -> str:
        return ' ' * self.width


"""
Compose multiple inline elements into a single line string.

Elements are concatenated in order. Spacing can be controlled with InlineSpacer.

Args:
    *elements: Variable number of inline elements (InlineText, InlineBar, InlineGraph, InlineSpacer, or strings)
    separator: Optional separator string between elements (default: single space)

Returns:
    Composed string with all elements concatenated

Example:
    line = compose_inline(
        InlineText("CPU:"),
        InlineSpacer(2),
        InlineText(f"{usage:.1f}%"),
        InlineBar(bar_string),
        InlineGraph(graph_string)
    )
"""
def compose_inline(*elements: Union[InlineElement, str], separator: str = " ") -> str:
    # Convert strings to InlineText automatically
    converted = []
    for elem in elements:
        if isinstance(elem, str):
            converted.append(InlineText(elem))
        elif isinstance(elem, InlineElement):
            converted.append(elem)
        else:
            # Try to convert to string
            converted.append(InlineText(str(elem)))
    
    # Join all elements
    parts = [str(elem) for elem in converted]
    return separator.join(parts)


"""
Compose inline elements with automatic width distribution.

Distributes available width among flexible elements (bars, graphs).
Text elements use their natural width (priority).
Remaining space is divided evenly among resizable components.

Args:
    available_width: Total available width for the line
    *elements: Variable number of inline elements
    separator: Optional separator string between elements (default: single space)

Returns:
    Composed string with elements distributed across available width

Example:
    # Text takes natural width, bar and graph share remaining space
    line = compose_inline_width(
        panel.width - 2,
        InlineText("CPU:"),
        InlineText(f"{usage:.1f}%"),
        InlineBar(value=usage, renderer=renderer),  # Resizable
        InlineGraph(graph=graph, renderer=renderer)  # Resizable
    )
"""
def compose_inline_width(
    available_width: int,
    *elements: Union[InlineElement, str],
    separator: str = " "
) -> str:
    # Convert strings to InlineText automatically
    converted = []
    for elem in elements:
        if isinstance(elem, str):
            converted.append(InlineText(elem))
        elif isinstance(elem, InlineElement):
            converted.append(elem)
        else:
            converted.append(InlineText(str(elem)))
    
    # Calculate natural widths for fixed elements (text, spacers)
    # Identify resizable elements (bars, graphs that can be resized)
    fixed_widths = []
    resizable_elements = []
    resizable_indices = []
    
    for i, elem in enumerate(converted):
        if isinstance(elem, InlineBar) and elem._is_resizable:
            # Resizable bar - will be sized later
            fixed_widths.append(0)
            resizable_elements.append(elem)
            resizable_indices.append(i)
        elif isinstance(elem, InlineGraph) and elem._is_resizable:
            # Resizable graph - will be sized later
            fixed_widths.append(0)
            resizable_elements.append(elem)
            resizable_indices.append(i)
        else:
            # Fixed element (text, spacer, or pre-rendered bar/graph)
            fixed_widths.append(visible_length(str(elem)))
    
    # Calculate total fixed width
    total_fixed = sum(fixed_widths)
    separator_width = len(separator) * (len(converted) - 1) if len(converted) > 1 else 0
    total_fixed_with_separators = total_fixed + separator_width
    
    # Calculate available width for resizable elements
    available_for_resizable = available_width - total_fixed_with_separators
    
    # Distribute available width among resizable elements
    # Elements with max_size get their max_size, remaining space goes to elements without max_size
    if resizable_elements and available_for_resizable > 0:
        # Separate elements with and without max_size
        elements_with_max = [e for e in resizable_elements if e.max_size is not None]
        elements_without_max = [e for e in resizable_elements if e.max_size is None]
        
        # First, give max_size to elements that have it
        space_used_by_max = 0
        for elem in elements_with_max:
            elem.resize(elem.max_size)
            space_used_by_max += elem.get_actual_width()
        
        # Remaining space goes to elements without max_size
        remaining_space = available_for_resizable - space_used_by_max
        
        if elements_without_max and remaining_space > 0:
            # Distribute remaining space evenly among elements without max_size
            width_per_element = remaining_space // len(elements_without_max)
            for elem in elements_without_max:
                elem.resize(width_per_element)
            
            # Give any leftover space to the first element without max_size
            leftover = remaining_space - (width_per_element * len(elements_without_max))
            if leftover > 0 and elements_without_max:
                first_elem = elements_without_max[0]
                first_elem.resize(first_elem.get_actual_width() + leftover)
        
        elif not elements_without_max:
            # All elements have max_size, distribute remaining space evenly
            if remaining_space > 0:
                width_per_element = remaining_space // len(elements_with_max)
                for elem in elements_with_max:
                    # Only add if element hasn't reached max_size yet
                    if elem.get_actual_width() < elem.max_size:
                        new_width = min(elem.get_actual_width() + width_per_element, elem.max_size)
                        elem.resize(new_width)
    elif resizable_elements:
        # Not enough space - give minimum width (1 char)
        for elem in resizable_elements:
            elem.resize(1)
    
    # Build final string with all elements
    parts = [str(elem) for elem in converted]
    return separator.join(parts)
