"""
History panel controller.

This module manages the history panel (panel1) which displays:
- CPU usage history graph (top)
- GPU usage history graph (bottom)
- CPU uptime information
"""

from typing import Dict, Any
from ..ui.ansi_renderer import ANSIRendererBase, VLayout
from ..ui.colors import ANSIColors
from ..ui.inline import InlineText


class HistoryPanel:
    """
    Controller for the history panel (panel1).
    
    This panel displays usage history graphs for CPU and GPU.
    """
    
    def __init__(self, renderer: ANSIRendererBase):
        """
        Initialize the history panel.
        
        Args:
            renderer: The ANSI renderer instance
        """
        self.renderer = renderer
        self.panel = None
        self.vlayout = None
        self.graph_top = None
        self.separator = None
        self.graph_bottom = None
        self.uptime = None
        self.graph_top_obj = None
        self.graph_bottom_obj = None
        
        self._setup_panel()
    
    def _setup_panel(self) -> None:
        """Set up the history panel structure."""
        # Create main panel
        self.panel = self.renderer.create_panel(
            'panel1',
            title='',
            rounded=True,
            border_color=ANSIColors.BRIGHT_CYAN
        )
        
        # Set up panel1 with VLayout containing multi-line graphs
        # Create a VLayout inside panel1
        self.vlayout = VLayout(margin=0, spacing=0)
        self.panel.add_child(self.vlayout)
        
        # Create borderless panels for graphs
        self.graph_top = self.renderer.create_panel(
            'panel1_graph_top',
            borderless=True
        )
        
        # Create separator panel
        self.separator = self.renderer.create_panel(
            'panel1_separator',
            borderless=True,
            max_height=1
        )
        
        self.graph_bottom = self.renderer.create_panel(
            'panel1_graph_bottom',
            borderless=True
        )
        
        # Create inline panel for CPU uptime (gray label)
        self.uptime = self.renderer.create_panel(
            'panel1_uptime',
            borderless=True,
            max_height=1
        )
        
        # Add panels to VLayout
        self.vlayout.add_panel(self.graph_top)
        self.vlayout.add_panel(self.separator)
        self.vlayout.add_panel(self.graph_bottom)
        self.vlayout.add_panel(self.uptime)
        
        # Create multi-line graphs (dimensions will be updated dynamically)
        self.graph_top_obj = self.renderer.create_multi_line_graph(40, 8, min_value=0.0, max_value=100.0, use_braille=True, top_to_bottom=False)
        self.graph_bottom_obj = self.renderer.create_multi_line_graph(40, 8, min_value=0.0, max_value=100.0, use_braille=True, top_to_bottom=True)
    
    def update_layout(self) -> None:
        """Update panel layout bounds based on current panel size."""
        content_row, content_col, content_width, content_height = self.panel.get_content_area()
        self.vlayout.set_bounds(content_row, content_col, content_width, content_height)
        self.vlayout.update()
    
    def update(self, metrics: Dict[str, Any]) -> None:
        """
        Update the history panel with current metrics.
        
        Args:
            metrics: Dictionary of metrics from collectors
        """
        cpu_data = metrics.get('cpu', {})
        gpu_data = metrics.get('gpu', {})
        
        # Get overall CPU usage
        cpu_usage = cpu_data.get('overall', 0.0)
        
        # Update separator panel with CPU↑ and GPU↓ labels
        self.separator.clear()
        cpu_text = "CPU"
        gpu_text = "GPU"
        cpu_arrow = "↑"
        gpu_arrow = "↓"
        cpu_label_text = cpu_text + cpu_arrow
        gpu_label_text = gpu_text + gpu_arrow
        cpu_label = ANSIColors.BRIGHT_WHITE + cpu_text + ANSIColors.RESET + ANSIColors.CYAN + cpu_arrow + ANSIColors.RESET
        gpu_label = ANSIColors.BRIGHT_WHITE + gpu_text + ANSIColors.RESET + ANSIColors.CYAN + gpu_arrow + ANSIColors.RESET
        
        # Calculate centered layout: ...───CPU↑─GPU↓───...
        total_width = self.separator.width
        label_width = len(cpu_label_text) + 1 + len(gpu_label_text)  # CPU↑─GPU↓
        line_width = total_width - label_width
        left_lines = line_width // 2
        right_lines = line_width - left_lines
        
        line_char = ANSIColors.BRIGHT_BLACK + '─' + ANSIColors.RESET
        separator_line = line_char * left_lines + cpu_label + line_char + gpu_label + line_char * right_lines
        self.separator.add_line(separator_line)
        
        # Update top graph panel (CPU usage, normal orientation)
        self.graph_top.clear()
        
        # Update graph dimensions to match panel size
        if self.graph_top_obj.width_chars != self.graph_top.width or self.graph_top_obj.height_chars != self.graph_top.height:
            self.graph_top_obj.width_chars = self.graph_top.width
            self.graph_top_obj.height_chars = self.graph_top.height
        
        # Update graph with CPU usage
        self.graph_top_obj.add_value(cpu_usage)
        
        # Get graph as string and split into lines
        graph_string = self.graph_top_obj.get_graph_string(self.renderer)
        graph_lines = graph_string.split('\n')
        
        # Add graph lines to panel
        for line in graph_lines:
            if line:  # Skip empty lines
                self.graph_top.add_line(line)
        
        # Update bottom graph panel (GPU usage, top-to-bottom rendering)
        gpu_usage = 0.0
        if gpu_data:
            gpu_usage = gpu_data.get('overall', {}).get('usage', 0.0)
        
        self.graph_bottom.clear()
        
        # Update graph dimensions to match panel size
        if self.graph_bottom_obj.width_chars != self.graph_bottom.width or self.graph_bottom_obj.height_chars != self.graph_bottom.height:
            self.graph_bottom_obj.width_chars = self.graph_bottom.width
            self.graph_bottom_obj.height_chars = self.graph_bottom.height
        
        # Update graph with GPU usage
        self.graph_bottom_obj.add_value(gpu_usage)
        
        # Get graph as string and split into lines
        graph_string = self.graph_bottom_obj.get_graph_string(self.renderer)
        graph_lines = graph_string.split('\n')
        
        # Add graph lines to panel
        for line in graph_lines:
            if line:  # Skip empty lines
                self.graph_bottom.add_line(line)
        
        # Update CPU uptime inline (from CPU collector)
        cpu_uptime = cpu_data.get('uptime')
        self.uptime.clear()
        if cpu_uptime:
            gray_uptime = ANSIColors.BRIGHT_BLACK + cpu_uptime + ANSIColors.RESET
            self.uptime.add_inline(
                InlineText(gray_uptime),
                renderer=self.renderer
            )

