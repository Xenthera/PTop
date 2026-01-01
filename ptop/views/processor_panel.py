"""
Processor panel controller.

This module manages the processor panel (panel2) which displays:
- CPU core usage and temperature graphs
- CPU/GPU inline information with progress bars
- Processor details and statistics
"""

from typing import List, Dict, Any, Optional
from ..ui.ansi_renderer import ANSIRendererBase, VLayout, HLayout
from ..ui.colors import ANSIColors, get_gradient_color
from ..ui.history_graph import SingleLineGraph
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
        self.subpanel1 = None
        self.subpanel2 = None
        self.pipe = None
        self.hlayout = None
        
        # Graph references
        self.inline1_graph: Optional[SingleLineGraph] = None  # CPU temperature graph
        self.inline2_graph: Optional[SingleLineGraph] = None  # GPU VRAM usage graph
        self.inline2_temp_graph: Optional[SingleLineGraph] = None  # GPU temperature graph
        self.core_graphs: List[SingleLineGraph] = []
        self.core_temp_graphs: List[SingleLineGraph] = []
        
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
        # Set red -> pink -> white gradient
        self.inline2_graph.colors = [ANSIColors.BRIGHT_RED, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
        
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
        
        # Create an HLayout with subpanels
        self.hlayout = HLayout(margin=0, spacing=0)
        self.subpanel1 = self.renderer.create_panel(
            'panel2_subpanel1',
            borderless=True
        )
        self.subpanel2 = self.renderer.create_panel(
            'panel2_subpanel2',
            borderless=True
        )
        # Create a borderless panel for the vertical pipe separator
        self.pipe = self.renderer.create_panel(
            'panel2_pipe',
            borderless=True,
            max_width=1
        )
        self.hlayout.add_panel(self.subpanel1)
        self.hlayout.add_panel(self.pipe)
        self.hlayout.add_panel(self.subpanel2)
        self.vlayout.add_layout(self.hlayout)
        
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
    
    def _initialize_core_graphs(self, num_cores: int, has_per_core_temp: bool = False) -> None:
        """Initialize core graphs if not already done (lazy initialization)."""
        if not self.core_graphs and num_cores > 0:
            # Create a graph for each core (max width 10)
            for _ in range(num_cores):
                graph = self.renderer.create_history_graph(10, min_value=0.0, max_value=100.0, use_braille=True)
                self.core_graphs.append(graph)
        
        # Only create temperature graphs if per-core temperature data is available
        if not self.core_temp_graphs and num_cores > 0 and has_per_core_temp:
            # Create a temperature graph for each core (max width 8, mapped 30-75°C)
            for _ in range(num_cores):
                graph = self.renderer.create_history_graph(8, min_value=30.0, max_value=75.0, use_braille=True)
                # Set blue -> purple -> white gradient (same as overall temp graph)
                graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
                self.core_temp_graphs.append(graph)
    
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
        
        # Initialize core graphs if needed (only create temp graphs if per-core temp is available)
        if per_core:
            self._initialize_core_graphs(len(per_core), has_per_core_temp=has_per_core_temp)
        
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
        
        # Update core subpanels
        if per_core and self.core_graphs:
            # Calculate maximum label width for alignment (e.g., "C11" is longer than "C0")
            max_label_len = len(f"C{len(per_core) - 1}")
            
            # Split cores in half between the two subpanels
            num_cores = len(per_core)
            midpoint = num_cores // 2
            
            # Update subpanel1 with first half of cores
            self.subpanel1.clear()
            for i in range(midpoint):
                if i < len(self.core_graphs):
                    core_usage = per_core[i]
                    self.core_graphs[i].add_value(core_usage)
                    
                    # Get per-core temperature if available
                    core_temp = None
                    if per_core_temp and i < len(per_core_temp):
                        core_temp = per_core_temp[i]
                    
                    # Update temperature graph if graph exists (always show graph, even if temp data missing)
                    if i < len(self.core_temp_graphs):
                        if core_temp is not None:
                            self.core_temp_graphs[i].add_value(core_temp)
                        # If no temp data, graph will show as gray zeros (prefilled)
                    
                    # Create label with bold C and no colon
                    label_text = f"C{i}"
                    bold_label_text = ANSIColors.BOLD + "C" + ANSIColors.RESET + label_text[1:]
                    
                    # Calculate padding needed
                    visible_label_len = visible_length(bold_label_text)
                    padding_needed = max_label_len - visible_label_len
                    padded_label = bold_label_text + (" " * padding_needed)
                    
                    # Build inline elements: padded label (C bold) + usage graph + percentage
                    inline_elements = [
                        InlineText(padded_label),
                        InlineGraph(self.core_graphs[i], renderer=self.renderer),
                        InlineText(f"{core_usage:3d}%"),
                    ]
                    
                    # Add temperature graph (always show if graph exists) and value (only if temp data available)
                    if i < len(self.core_temp_graphs):
                        inline_elements.append(InlineGraph(self.core_temp_graphs[i], renderer=self.renderer, max_size=8))
                        if core_temp is not None:
                            inline_elements.append(InlineText(f"{int(round(core_temp))}°C"))
                    
                    # Add inline composition
                    self.subpanel1.add_inline(*inline_elements, renderer=self.renderer)
            
            # Update subpanel2 with second half of cores
            self.subpanel2.clear()
            for i in range(midpoint, num_cores):
                if i < len(self.core_graphs):
                    core_usage = per_core[i]
                    self.core_graphs[i].add_value(core_usage)
                    
                    # Get per-core temperature if available
                    core_temp = None
                    if per_core_temp and i < len(per_core_temp):
                        core_temp = per_core_temp[i]
                    
                    # Update temperature graph if graph exists (always show graph, even if temp data missing)
                    if i < len(self.core_temp_graphs):
                        if core_temp is not None:
                            self.core_temp_graphs[i].add_value(core_temp)
                        # If no temp data, graph will show as gray zeros (prefilled)
                    
                    # Create label with bold C and no colon
                    label_text = f"C{i}"
                    bold_label_text = ANSIColors.BOLD + "C" + ANSIColors.RESET + label_text[1:]
                    
                    # Calculate padding needed
                    visible_label_len = visible_length(bold_label_text)
                    padding_needed = max_label_len - visible_label_len
                    padded_label = bold_label_text + (" " * padding_needed)
                    
                    # Build inline elements: padded label (C bold) + usage graph + percentage
                    inline_elements = [
                        InlineText(padded_label),
                        InlineGraph(self.core_graphs[i], renderer=self.renderer),
                        InlineText(f"{core_usage:3d}%"),
                    ]
                    
                    # Add temperature graph (always show if graph exists) and value (only if temp data available)
                    if i < len(self.core_temp_graphs):
                        inline_elements.append(InlineGraph(self.core_temp_graphs[i], renderer=self.renderer, max_size=8))
                        if core_temp is not None:
                            inline_elements.append(InlineText(f"{int(round(core_temp))}°C"))
                    
                    # Add inline composition
                    self.subpanel2.add_inline(*inline_elements, renderer=self.renderer)
        
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
        
        # Update pipe separator (vertical bar) - fill to match height after layout update
        self.pipe.clear()
        pipe_height = max(1, self.pipe.height)
        gray_pipe = ANSIColors.BRIGHT_BLACK + "│" + ANSIColors.RESET
        for _ in range(pipe_height):
            self.pipe.add_line(gray_pipe)
        
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

