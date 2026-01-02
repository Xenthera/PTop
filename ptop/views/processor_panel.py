"""
Processor panel controller.

This module manages the processor panel (panel2) which displays:
- CPU core usage and temperature graphs
- CPU/GPU inline information with progress bars
- Processor details and statistics
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from ..ui.ansi_renderer import ANSIRendererBase, VLayout, HLayout, Panel
from ..ui.colors import ANSIColors, get_gradient_color
from ..ui.history_graph import SingleLineGraph, MultiLineGraph
from ..ui.progress_bar import ProgressBar
from ..ui.inline import InlineText, InlineBar, InlineGraph
from ..ui.utils import visible_length


class ProcessorPanel:
    """
    Controller for the processor panel (panel2).
    
    This panel displays detailed processor information including:
    - CPU core usage and temperature graphs
    - Overall CPU/GPU usage with progress bars
    - CPU/GPU temperature graphs
    - Power consumption
    - Memory information
    """
    
    def __init__(self, renderer: ANSIRendererBase):
        """
        Initialize the processor panel.
        
        Args:
            renderer: The ANSI renderer instance
        """
        self.renderer = renderer
        self.panel = None
        self.vlayout = None
        self.inline1 = None
        self.inline2 = None
        self.core_grid_layout: Optional[VLayout] = None  # Grid layout for core panels
        self.core_panels: List[Panel] = []  # List of panels for each core
        
        # Graph references
        self.inline1_graph: Optional[SingleLineGraph] = None  # CPU temperature graph
        self.inline2_graph: Optional[SingleLineGraph] = None  # GPU VRAM usage graph
        self.inline2_temp_graph: Optional[SingleLineGraph] = None  # GPU temperature graph
        self.core_graphs: List[MultiLineGraph] = []  # Multi-line graphs for each core
        self.core_temp_graphs: List[MultiLineGraph] = []  # Temperature graphs for each core
        
        self._setup_panel()
    
    def _setup_panel(self) -> None:
        """Set up the processor panel structure."""
        # Create main panel
        self.panel = self.renderer.create_panel(
            'panel2',
            title='',
            rounded=True,
            border_color=ANSIColors.BRIGHT_BLACK
        )
        
        # Create graph for panel2 top inline (CPU temperature, mapped 0-100% to 30-75°C)
        self.inline1_graph = self.renderer.create_history_graph(10, min_value=30.0, max_value=75.0, use_braille=True)
        # Set blue -> purple -> white gradient
        self.inline1_graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
        
        # Create graph for panel2 bottom inline (GPU VRAM usage, 0-100%)
        self.inline2_graph = self.renderer.create_history_graph(8, min_value=0.0, max_value=100.0, use_braille=True)
        # Set red-based gradient: dark red -> red -> orange -> yellow -> white
        self.inline2_graph.colors = [
            (128, 0, 0),      # Dark red
            (255, 0, 0),      # Red
            (255, 128, 0),    # Orange
            (255, 255, 0),    # Yellow
            (255, 255, 255)  # White
        ]
        
        # Create graph for panel2 bottom inline (GPU temperature, mapped 0-100% to 30-100°C)
        self.inline2_temp_graph = self.renderer.create_history_graph(10, min_value=30.0, max_value=100.0, use_braille=True)
        # Set blue -> purple -> white gradient (same as CPU temp graph)
        self.inline2_temp_graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
        
        # Create a VLayout inside panel2
        self.vlayout = VLayout(margin=0, spacing=0)
        self.panel.add_child(self.vlayout)
        
        # Create borderless panel for inline content (separator line)
        self.inline1 = self.renderer.create_panel(
            'panel2_inline1',
            borderless=True,
            max_height=1
        )
        self.vlayout.add_panel(self.inline1)
        
        # Create grid layout for core panels (will be populated dynamically)
        self.core_grid_layout = VLayout(margin=0, spacing=0)
        self.vlayout.add_layout(self.core_grid_layout)
        
        # Create another borderless panel for inline content (will be added to layout only when GPU data exists)
        self.inline2 = self.renderer.create_panel(
            'panel2_inline2',
            borderless=True,
            max_height=1
        )
        self.inline2_in_layout = False  # Track if inline2 is currently in the layout
    
    def update_layout(self) -> None:
        """Update panel layout bounds based on current panel size."""
        content_row, content_col, content_width, content_height = self.panel.get_content_area()
        self.vlayout.set_bounds(content_row, content_col, content_width, content_height)
        self.vlayout.update()
    
    def _calculate_grid_dimensions(self, num_cores: int) -> Tuple[int, int]:
        """
    Calculate grid dimensions (rows x cols) for a square-like layout.
    For perfect squares: 4 cores = 2x2, 9 cores = 3x3, etc.
    For non-perfect squares: use the next larger square and leave empty spaces.
    """
        if num_cores == 0:
            return (0, 0)
        
        # Calculate the square root and round up
        sqrt_cores = math.sqrt(num_cores)
        cols = math.ceil(sqrt_cores)
        rows = math.ceil(num_cores / cols)
        
        return (rows, cols)
    
    def _initialize_core_graphs(self, num_cores: int, has_per_core_temp: bool = False) -> None:
        """Initialize core graphs and panels if not already done (lazy initialization)."""
        if not self.core_graphs and num_cores > 0:
            # Create a multi-line graph for each core (dimensions will be set based on panel size)
            # Start with a default size, will be updated when panel dimensions are known
            for i in range(num_cores):
                graph = self.renderer.create_multi_line_graph(
                    width_chars=20,  # Default, will be updated
                    height_chars=8,   # Default, will be updated
                    min_value=0.0,
                    max_value=100.0,
                    use_braille=True,
                    top_to_bottom=False  # Bottom to top (default)
                )
                self.core_graphs.append(graph)
        
        # Only create temperature graphs if per-core temperature data is available
        if not self.core_temp_graphs and num_cores > 0 and has_per_core_temp:
            # Create a temperature graph for each core
            for _ in range(num_cores):
                graph = self.renderer.create_multi_line_graph(
                    width_chars=20,  # Default, will be updated
                    height_chars=8,   # Default, will be updated
                    min_value=30.0,
                    max_value=75.0,
                    use_braille=True,
                    top_to_bottom=False
                )
                # Set blue -> purple -> white gradient (same as overall temp graph)
                graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
                self.core_temp_graphs.append(graph)
    
    def _setup_core_grid(self, num_cores: int) -> None:
        """Set up the grid layout for core panels."""
        if num_cores == 0:
            return
        
        # Calculate grid dimensions
        rows, cols = self._calculate_grid_dimensions(num_cores)
        
        # Clear existing grid if it exists
        while self.core_grid_layout.children:
            child = self.core_grid_layout.children[0]
            self.core_grid_layout.remove_child(child)
        self.core_panels.clear()
        
        # Create grid: rows of HLayouts, each containing core panels
        for row_idx in range(rows):
            row_layout = HLayout(margin=0, spacing=0)
            
            for col_idx in range(cols):
                core_idx = row_idx * cols + col_idx
                
                if core_idx < num_cores:
                    # Create a bordered panel for this core
                    core_panel = self.renderer.create_panel(
                        f'panel2_core_{core_idx}',
                        title=f'C{core_idx}',
                        rounded=False,
                        border_color=ANSIColors.BRIGHT_BLACK
                    )
                    self.core_panels.append(core_panel)
                    row_layout.add_panel(core_panel)
                else:
                    # Empty space for non-perfect squares
                    empty_panel = self.renderer.create_panel(
                        f'panel2_empty_{row_idx}_{col_idx}',
                        borderless=True
                    )
                    row_layout.add_panel(empty_panel)
            
            self.core_grid_layout.add_layout(row_layout)
    
    def update(self, metrics: Dict[str, Any]) -> None:
        """
        Update the processor panel with current metrics.
        
        Args:
            metrics: Dictionary of metrics from collectors
        """
        cpu_data = metrics.get('cpu', {})
        gpu_data = metrics.get('gpu', {})
        
        per_core = cpu_data.get('per_core', [])
        
        # Check if per-core temperature data is available
        temp_data = cpu_data.get('temperature')
        per_core_temp = temp_data.get('per_core') if temp_data else None
        has_per_core_temp = per_core_temp is not None and len(per_core_temp) > 0 and any(t is not None for t in per_core_temp)
        
        # Update panel2 title with simple CPU name (bold)
        cpu_name_simple = cpu_data.get('name_simple', 'CPU')
        self.panel.title = ANSIColors.BOLD + cpu_name_simple + ANSIColors.RESET
        # Update the first left label (title) if it exists
        if self.panel.left_labels:
            self.panel.left_labels[0] = ANSIColors.BOLD + cpu_name_simple + ANSIColors.RESET
        elif cpu_name_simple:
            self.panel.left_labels.insert(0, ANSIColors.BOLD + cpu_name_simple + ANSIColors.RESET)
        
        # Update panel2 right label with current CPU frequency
        current_freq = cpu_data.get('current_frequency')
        if current_freq:
            self.panel.right_labels = [current_freq]
        else:
            self.panel.right_labels = []
        
        # Update core grid
        if per_core:
            num_cores = len(per_core)
            
            # Initialize core graphs if needed
            self._initialize_core_graphs(num_cores, has_per_core_temp=has_per_core_temp)
            
            # Set up grid layout if not already done or if number of cores changed
            if len(self.core_panels) != num_cores:
                self._setup_core_grid(num_cores)
            
            # Update each core panel with graph and data
            for i in range(num_cores):
                if i < len(self.core_graphs) and i < len(self.core_panels):
                    core_usage = per_core[i]
                    core_panel = self.core_panels[i]
                    
                    # Update usage graph
                    self.core_graphs[i].add_value(core_usage)
                    
                    # Get per-core temperature if available
                    core_temp = None
                    if per_core_temp and i < len(per_core_temp):
                        core_temp = per_core_temp[i]
                    
                    # Update temperature graph if available
                    if i < len(self.core_temp_graphs):
                        if core_temp is not None:
                            self.core_temp_graphs[i].add_value(core_temp)
                    
                    # Get panel content area dimensions for graph sizing
                    content_row, content_col, content_width, content_height = core_panel.get_content_area()
                    
                    # Update graph dimensions to fill the panel (leave 1 line for percentage/temp at bottom)
                    graph_height = max(1, content_height - 1)  # Leave 1 line for text
                    graph_width = max(1, content_width)
                    
                    if self.core_graphs[i].width_chars != graph_width or self.core_graphs[i].height_chars != graph_height:
                        self.core_graphs[i].width_chars = graph_width
                        self.core_graphs[i].height_chars = graph_height
                    
                    if i < len(self.core_temp_graphs):
                        if self.core_temp_graphs[i].width_chars != graph_width or self.core_temp_graphs[i].height_chars != graph_height:
                            self.core_temp_graphs[i].width_chars = graph_width
                            self.core_temp_graphs[i].height_chars = graph_height
                    
                    # Clear and render the panel
                    core_panel.clear()
                    
                    # Render the usage graph
                    graph_string = self.core_graphs[i].get_graph_string(self.renderer)
                    graph_lines = graph_string.rstrip('\n').split('\n')
                    for line in graph_lines:
                        core_panel.add_line(line)
                    
                    # Add percentage and temperature at the bottom
                    bottom_line_parts = [f"{int(core_usage):3d}%"]
                    if core_temp is not None:
                        bottom_line_parts.append(f"{int(round(core_temp))}°C")
                    bottom_line = " ".join(bottom_line_parts)
                    core_panel.add_line(bottom_line)
                    
                    # Update right label with percentage
                    core_panel.right_labels = [f"{int(core_usage):3d}%"]
        
        # Update inline panel 1 with overall CPU usage + temp graph + temp text
        cpu_usage = cpu_data.get('overall', 0.0)
        temp_data = cpu_data.get('temperature')
        cpu_temp = temp_data.get('current') if temp_data else None
        cpu_power = cpu_data.get('power')
        
        # Update graph with current CPU temperature (if available)
        if cpu_temp is not None:
            self.inline1_graph.add_value(cpu_temp)
        
        self.inline1.clear()
        overall_bar = ProgressBar(cpu_usage, truecolor_support=self.renderer._truecolor_support)
        
        # Build inline elements
        inline_elements = [
            InlineText(ANSIColors.BOLD + "CPU" + ANSIColors.RESET),
            InlineBar(overall_bar),  # No max_size, so it can grow
            InlineText(f"{int(cpu_usage):3d}%"),
        ]
        
        
        # Add temperature text after graph if available (no decimal)
        if cpu_temp is not None:
            inline_elements.append(InlineGraph(self.inline1_graph, renderer=self.renderer, max_size=10))
            inline_elements.append(InlineText(f"{int(round(cpu_temp))}°C"))
        
        # Add power consumption if available (formatted as watts, 1 decimal place, with gradient color)
        if cpu_power is not None:
            # Calculate color based on wattage (0-100W mapped to green->lime->white gradient)
            wattage_percent = min(100.0, max(0.0, cpu_power))  # Clamp to 0-100
            
            # Define gradient colors: green -> lime -> white
            gradient_colors = [
                (0, 128, 0),      # Dark green
                (0, 255, 0),      # Green
                (191, 255, 0),    # Lime (bright yellow-green)
                (255, 255, 0),
                (255, 100, 100)
            ]
            
            # Get gradient color using common utility function
            color_code = get_gradient_color(gradient_colors, wattage_percent, self.renderer._truecolor_support)
            
            wattage_number = f"{cpu_power:.1f}"
            colored_wattage = color_code + wattage_number + ANSIColors.RESET + "W"
            inline_elements.append(InlineText(colored_wattage))
        
        self.inline1.add_inline(*inline_elements, renderer=self.renderer)
        
        # Update inline panel 2 with GPU info (only if GPU data exists)
        gpu_count = gpu_data.get('count', 0) if gpu_data else 0
        gpus = gpu_data.get('gpus', []) if gpu_data else []
        has_gpu_data = gpu_count > 0 and len(gpus) > 0
        
        # Add inline2 to layout if we have GPU data and it's not already added
        if has_gpu_data and not self.inline2_in_layout:
            self.vlayout.add_panel(self.inline2)
            self.inline2_in_layout = True
        # Remove inline2 from layout if we don't have GPU data and it's currently added
        elif not has_gpu_data and self.inline2_in_layout:
            self.vlayout.remove_child(self.inline2)
            self.inline2_in_layout = False
        
        if has_gpu_data:
            gpu_usage = 0.0
            gpu_name_simple = None
            gpu_memory_used_mb = None
            gpu_memory_total_mb = None
            gpu_memory_usage_percent = 0.0
            gpu_temp = None
            gpu_power = None
            
            gpu_usage = gpu_data.get('overall', {}).get('usage', 0.0)
            # Get simplified GPU name and memory info from first GPU (we know gpus list is not empty from has_gpu_data check)
            first_gpu = gpus[0]
            gpu_name_simple = first_gpu.get('name_simple')
            # Get memory info
            memory = first_gpu.get('memory', {})
            gpu_memory_used_mb = memory.get('used_mb')
            gpu_memory_total_mb = memory.get('total_mb')
            gpu_memory_usage_percent = memory.get('usage_percent', 0.0)
            # Get GPU temperature and power
            gpu_temp = first_gpu.get('temperature')
            gpu_power = first_gpu.get('power')
            
            # Update panel2 bottom left label with simplified GPU name (bold)
            if gpu_name_simple:
                # Clear existing bottom left labels and set simplified GPU name (bold)
                self.panel.bottom_left_labels = [ANSIColors.BOLD + gpu_name_simple + ANSIColors.RESET]
            else:
                # Clear if no GPU available
                self.panel.bottom_left_labels = []
            
            # Update GPU VRAM graph with memory usage percentage
            if gpu_memory_usage_percent is not None:
                self.inline2_graph.add_value(gpu_memory_usage_percent)
            
            # Update GPU temperature graph (if available)
            if gpu_temp is not None:
                self.inline2_temp_graph.add_value(float(gpu_temp))
            
            self.inline2.clear()
            gpu_bar = ProgressBar(gpu_usage, truecolor_support=self.renderer._truecolor_support)
            
            # Build inline elements
            inline_elements = [
                InlineText(ANSIColors.BOLD + "GPU" + ANSIColors.RESET),
                InlineBar(gpu_bar),  # No max_size, so it can grow
                InlineText(f"{int(gpu_usage):3d}%"),
                InlineGraph(self.inline2_graph, renderer=self.renderer, max_size=8),
            ]
            
            # Add VRAM label if memory data is available
            if gpu_memory_used_mb is not None and gpu_memory_total_mb is not None:
                used_gb = gpu_memory_used_mb / 1024.0
                total_gb = gpu_memory_total_mb / 1024.0
                vram_label = f"{used_gb:.1f}GB/{int(total_gb)}GB"
                inline_elements.append(InlineText(vram_label))
            
            # Add GPU temperature graph if available
            if gpu_temp is not None:
                inline_elements.append(InlineGraph(self.inline2_temp_graph, renderer=self.renderer, max_size=10))
                inline_elements.append(InlineText(f"{int(gpu_temp)}°C"))
            
            # Add GPU power consumption if available (formatted as watts, 1 decimal place, with gradient color)
            if gpu_power is not None:
                # Calculate color based on wattage (0-450W mapped to green->lime->white gradient)
                clamped_wattage = min(450.0, max(0.0, gpu_power))  # Clamp to 0-450
                wattage_percent = (clamped_wattage / 450.0) * 100.0  # Convert to 0-100% for gradient
                
                # Define gradient colors: green -> lime -> white
                gradient_colors = [
                    (0, 128, 0),      # Dark green
                    (0, 255, 0),      # Green
                    (191, 255, 0),    # Lime (bright yellow-green)
                    (255, 255, 0),
                    (255, 100, 100)
                ]
                
                # Get gradient color using common utility function
                color_code = get_gradient_color(gradient_colors, wattage_percent, self.renderer._truecolor_support)
                
                wattage_number = f"{gpu_power:.1f}"
                colored_wattage = color_code + wattage_number + ANSIColors.RESET + "W"
                inline_elements.append(InlineText(colored_wattage))
            
            self.inline2.add_inline(*inline_elements, renderer=self.renderer)
        else:
            # Clear GPU label if no GPU data (inline2 is not in layout, so no need to clear it)
            self.panel.bottom_left_labels = []

