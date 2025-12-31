"""
Core application controller.

This module contains the main application logic that:
- Manages the main event loop
- Coordinates collectors and UI renderer
- Handles update intervals
- Manages application lifecycle
"""

import time
import signal
import sys
from typing import List, Dict, Any
from ..collectors.base import BaseCollector
from ..collectors.cpu import CPUCollector
from ..collectors.gpu import GPUCollector
from ..ui.ansi_renderer import ANSIRendererBase, HLayout, VLayout
from ..ui.colors import ANSIColors, get_gradient_color
from ..ui.history_graph import SingleLineGraph
from ..ui.progress_bar import ProgressBar
from ..ui.inline import InlineText, InlineBar, InlineGraph
from ..ui.utils import visible_length


class PTopApp:
    """
    Main application controller.
    
    This class orchestrates the entire system monitor:
    - Initializes collectors
    - Sets up UI renderer
    - Runs main loop with periodic updates
    - Handles graceful shutdown
    """
    
    def __init__(self, update_interval: float = 0.05):
        """
        Initialize the application.
        
        Args:
            update_interval: Time in seconds between updates (default: 1.0)
        """
        self.update_interval = 0.05
        self.running = False
        
        # Initialize collectors
        # This is where we'll add more collectors later (memory, disk, etc.)
        self.collectors: List[BaseCollector] = []
        self._init_collectors()
        
        # Initialize UI renderer (always use ANSI renderer)
        self.renderer = ANSIRendererBase()
        
        # Set up UI layout structure
        self._setup_ui_layout()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _init_collectors(self) -> None:
        """
        Initialize all metric collectors.
        
        This method creates instances of all collectors.
        To add a new collector:
        1. Import it here
        2. Create an instance and append to self.collectors
        """
        # Add CPU collector
        self.collectors.append(CPUCollector())
        
        # Add GPU collector
        self.collectors.append(GPUCollector())
        
        # Future collectors will be added here:
        # self.collectors.append(MemoryCollector())
        # self.collectors.append(DiskCollector())
        # self.collectors.append(NetworkCollector())
        # self.collectors.append(ProcessCollector())
    
    def _setup_ui_layout(self) -> None:
        """
        Set up the UI layout structure.
        
        Creates a VLayout containing two HLayouts, with two panels in the first HLayout.
        """
        # Create root VLayout
        self.root_layout = VLayout(margin=0, spacing=1)
        
        # Create first HLayout with 2 panels
        self.top_hlayout = HLayout(margin=0, spacing=1)
        panel1 = self.renderer.create_panel(
            'panel1',
            title='',
            rounded=True,
            border_color=ANSIColors.BRIGHT_CYAN
        )
        panel2 = self.renderer.create_panel(
            'panel2',
            title='',
            rounded=True,
            border_color=ANSIColors.BRIGHT_BLACK
        )
        self.top_hlayout.add_panel(panel1)
        self.top_hlayout.add_panel(panel2)
        
        # Add HLayout to root VLayout
        self.root_layout.add_layout(self.top_hlayout)
        
        # Register root layout with renderer
        self.renderer.add_layout(self.root_layout)
        
        # Store panel references for later use
        self.panel1 = panel1
        self.panel2 = panel2
        
        # Core graphs will be initialized lazily when we first get CPU data
        self.core_graphs: List[SingleLineGraph] = []
        self.core_temp_graphs: List[SingleLineGraph] = []
        
        # Create graph for panel2 top inline (CPU temperature, mapped 0-100% to 30-75°C)
        self.panel2_inline1_graph = self.renderer.create_history_graph(10, min_value=30.0, max_value=75.0, use_braille=True)
        # Set blue -> purple -> white gradient
        self.panel2_inline1_graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
        
        # Create graph for panel2 bottom inline (GPU VRAM usage, 0-100%)
        self.panel2_inline2_graph = self.renderer.create_history_graph(8, min_value=0.0, max_value=100.0, use_braille=True)
        # Set red -> pink -> white gradient
        self.panel2_inline2_graph.colors = [ANSIColors.BRIGHT_RED, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
        
        # Create graph for panel2 bottom inline (GPU temperature, mapped 0-100% to 30-100°C)
        self.panel2_inline2_temp_graph = self.renderer.create_history_graph(10, min_value=30.0, max_value=100.0, use_braille=True)
        # Set blue -> purple -> white gradient (same as CPU temp graph)
        self.panel2_inline2_temp_graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
        
        # Set up panel1 with VLayout containing multi-line graphs
        # Create a VLayout inside panel1
        panel1_vlayout = VLayout(margin=0, spacing=0)
        panel1.add_child(panel1_vlayout)
        
        # Create borderless panels for graphs
        panel1_graph_top = self.renderer.create_panel(
            'panel1_graph_top',
            borderless=True
        )
        
        # Create separator panel
        panel1_separator = self.renderer.create_panel(
            'panel1_separator',
            borderless=True,
            max_height=1
        )
        
        panel1_graph_bottom = self.renderer.create_panel(
            'panel1_graph_bottom',
            borderless=True
        )
        
        # Create inline panel for CPU uptime (gray label)
        panel1_uptime = self.renderer.create_panel(
            'panel1_uptime',
            borderless=True,
            max_height=1
        )
        
        # Add panels to VLayout
        panel1_vlayout.add_panel(panel1_graph_top)
        panel1_vlayout.add_panel(panel1_separator)
        panel1_vlayout.add_panel(panel1_graph_bottom)
        panel1_vlayout.add_panel(panel1_uptime)
        
        # Create multi-line graphs (dimensions will be updated dynamically)
        panel1_graph_top_obj = self.renderer.create_multi_line_graph(40, 8, min_value=0.0, max_value=100.0, use_braille=True, top_to_bottom=False)
        panel1_graph_bottom_obj = self.renderer.create_multi_line_graph(40, 8, min_value=0.0, max_value=100.0, use_braille=True, top_to_bottom=True)
        
        # Store references
        self.panel1_vlayout = panel1_vlayout
        self.panel1_graph_top = panel1_graph_top
        self.panel1_separator = panel1_separator
        self.panel1_graph_bottom = panel1_graph_bottom
        self.panel1_uptime = panel1_uptime
        self.panel1_graph_top_obj = panel1_graph_top_obj
        self.panel1_graph_bottom_obj = panel1_graph_bottom_obj
        
        # Set up panel2 with VLayout containing inline panels + HLayout
        # Create a VLayout inside panel2
        panel2_vlayout = VLayout(margin=0, spacing=0)
        panel2.add_child(panel2_vlayout)
        
        # Create borderless panel for inline content (separator line)
        panel2_inline1 = self.renderer.create_panel(
            'panel2_inline1',
            borderless=True,
            max_height=1
        )
        panel2_vlayout.add_panel(panel2_inline1)
        
        # Create an HLayout with some test panels
        panel2_hlayout = HLayout(margin=0, spacing=0)
        panel2_subpanel1 = self.renderer.create_panel(
            'panel2_subpanel1',
            borderless=True
        )
        panel2_subpanel2 = self.renderer.create_panel(
            'panel2_subpanel2',
            borderless=True
        )
        # Create a borderless panel for the vertical pipe separator
        panel2_pipe = self.renderer.create_panel(
            'panel2_pipe',
            borderless=True,
            max_width=1
        )
        panel2_hlayout.add_panel(panel2_subpanel1)
        panel2_hlayout.add_panel(panel2_pipe)
        panel2_hlayout.add_panel(panel2_subpanel2)
        panel2_vlayout.add_layout(panel2_hlayout)
        
        # Create another borderless panel for inline content
        panel2_inline2 = self.renderer.create_panel(
            'panel2_inline2',
            borderless=True,
            max_height=1
        )
        panel2_vlayout.add_panel(panel2_inline2)
        
        # Store references for updating
        self.panel2_inline1 = panel2_inline1
        self.panel2_inline2 = panel2_inline2
        self.panel2_subpanel1 = panel2_subpanel1
        self.panel2_subpanel2 = panel2_subpanel2
        self.panel2_pipe = panel2_pipe
        self.panel2_vlayout = panel2_vlayout
    
    def _update_layout(self) -> None:
        """
        Update layout bounds based on current terminal size.
        """
        cols, rows = self.renderer.get_terminal_size()
        
        # No header, so layout starts at row 1 and uses full terminal
        self.root_layout.set_bounds(1, 1, cols, rows)
        self.root_layout.update()
    
    def _signal_handler(self, signum, frame) -> None:
        """
        Handle shutdown signals (Ctrl+C, etc.).
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        self.stop()
    
    def collect_metrics(self) -> Dict[str, Any]:
        """
        Collect metrics from all registered collectors.
        
        Returns:
            Dictionary mapping collector names to their metrics:
            {
                'cpu': {...},
                'memory': {...},
                ...
            }
        """
        metrics = {}
        
        for collector in self.collectors:
            collector_name = collector.get_name()
            metrics[collector_name] = collector.collect()
        
        return metrics
    
    def run(self) -> None:
        """
        Start the main application loop.
        
        This method:
        1. Sets up the renderer
        2. Enters the main loop
        3. Collects metrics periodically
        4. Renders updates
        5. Handles cleanup on exit
        """
        self.running = True
        
        # Set up renderer
        self.renderer.setup()
        
        # Initial layout update
        self._update_layout()
        
        try:
            # Main loop
            while self.running:
                # Check for terminal resize
                current_terminal_size = self.renderer.get_terminal_size()
                if current_terminal_size != getattr(self, '_last_terminal_size', None):
                    self._last_terminal_size = current_terminal_size
                    # Clear screen on resize to remove artifacts
                    self.renderer.clear()
                    self._update_layout()
                
                # Collect metrics from all collectors
                metrics = self.collect_metrics()
                
                # Update panel content with CPU metrics
                if 'cpu' in metrics:
                    cpu_data = metrics['cpu']
                    per_core = cpu_data.get('per_core', [])
                    
                    # Initialize core graphs if not already done (lazy initialization)
                    if not self.core_graphs and per_core:
                        # Create a graph for each core (max width 10)
                        for _ in range(len(per_core)):
                            graph = self.renderer.create_history_graph(10, min_value=0.0, max_value=100.0, use_braille=True)
                            self.core_graphs.append(graph)
                    
                    # Get overall CPU usage
                    cpu_usage = cpu_data.get('overall', 0.0)
                    
                    # Get CPU temperature
                    temp_data = cpu_data.get('temperature')
                    cpu_temp = temp_data.get('current') if temp_data else None
                    per_core_temp = temp_data.get('per_core') if temp_data else None
                    
                    # Initialize core temperature graphs if not already done (lazy initialization)
                    # Initialize based on number of cores, not per_core_temp length (in case temp data is missing for some cores)
                    if per_core and not self.core_temp_graphs:
                        # Create a temperature graph for each core (max width 8, mapped 30-75°C)
                        for _ in range(len(per_core)):
                            graph = self.renderer.create_history_graph(8, min_value=30.0, max_value=75.0, use_braille=True)
                            # Set blue -> purple -> white gradient (same as overall temp graph)
                            graph.colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
                            self.core_temp_graphs.append(graph)
                    
                    # Update panel1 layout bounds first
                    content_row, content_col, content_width, content_height = self.panel1.get_content_area()
                    self.panel1_vlayout.set_bounds(content_row, content_col, content_width, content_height)
                    self.panel1_vlayout.update()
                    
                    # Update separator panel with CPU↑ and GPU↓ labels
                    self.panel1_separator.clear()
                    cpu_text = "CPU"
                    gpu_text = "GPU"
                    cpu_arrow = "↑"
                    gpu_arrow = "↓"
                    cpu_label_text = cpu_text + cpu_arrow
                    gpu_label_text = gpu_text + gpu_arrow
                    cpu_label = ANSIColors.BRIGHT_WHITE + cpu_text + ANSIColors.RESET + ANSIColors.CYAN + cpu_arrow + ANSIColors.RESET
                    gpu_label = ANSIColors.BRIGHT_WHITE + gpu_text + ANSIColors.RESET + ANSIColors.CYAN + gpu_arrow + ANSIColors.RESET
                    
                    # Calculate centered layout: ...───CPU↑─GPU↓───...
                    total_width = self.panel1_separator.width
                    label_width = len(cpu_label_text) + 1 + len(gpu_label_text)  # CPU↑─GPU↓
                    line_width = total_width - label_width
                    left_lines = line_width // 2
                    right_lines = line_width - left_lines
                    
                    line_char = ANSIColors.BRIGHT_BLACK + '─' + ANSIColors.RESET
                    separator_line = line_char * left_lines + cpu_label + line_char + gpu_label + line_char * right_lines
                    self.panel1_separator.add_line(separator_line)
                    
                    # Update top graph panel (CPU usage, normal orientation)
                    self.panel1_graph_top.clear()
                    
                    # Update graph dimensions to match panel size
                    if self.panel1_graph_top_obj.width_chars != self.panel1_graph_top.width or self.panel1_graph_top_obj.height_chars != self.panel1_graph_top.height:
                        self.panel1_graph_top_obj.width_chars = self.panel1_graph_top.width
                        self.panel1_graph_top_obj.height_chars = self.panel1_graph_top.height
                    
                    # Update graph with CPU usage
                    self.panel1_graph_top_obj.add_value(cpu_usage)
                    
                    # Get graph as string and split into lines
                    graph_string = self.panel1_graph_top_obj.get_graph_string(self.renderer)
                    graph_lines = graph_string.split('\n')
                    
                    # Add graph lines to panel
                    for line in graph_lines:
                        if line:  # Skip empty lines
                            self.panel1_graph_top.add_line(line)
                    
                    # Update bottom graph panel (GPU usage, top-to-bottom rendering)
                    gpu_usage = 0.0
                    if 'gpu' in metrics:
                        gpu_data = metrics['gpu']
                        gpu_usage = gpu_data.get('overall', {}).get('usage', 0.0)
                    
                    self.panel1_graph_bottom.clear()
                    
                    # Update graph dimensions to match panel size
                    if self.panel1_graph_bottom_obj.width_chars != self.panel1_graph_bottom.width or self.panel1_graph_bottom_obj.height_chars != self.panel1_graph_bottom.height:
                        self.panel1_graph_bottom_obj.width_chars = self.panel1_graph_bottom.width
                        self.panel1_graph_bottom_obj.height_chars = self.panel1_graph_bottom.height
                    
                    # Update graph with GPU usage
                    self.panel1_graph_bottom_obj.add_value(gpu_usage)
                    
                    # Get graph as string and split into lines
                    graph_string = self.panel1_graph_bottom_obj.get_graph_string(self.renderer)
                    graph_lines = graph_string.split('\n')
                    
                    # Add graph lines to panel
                    for line in graph_lines:
                        if line:  # Skip empty lines
                            self.panel1_graph_bottom.add_line(line)
                    
                    # Update CPU uptime inline (from CPU collector)
                    cpu_uptime = cpu_data.get('uptime')
                    self.panel1_uptime.clear()
                    if cpu_uptime:
                        gray_uptime = ANSIColors.BRIGHT_BLACK + cpu_uptime + ANSIColors.RESET
                        self.panel1_uptime.add_inline(
                            InlineText(gray_uptime),
                            renderer=self.renderer
                        )
                    
                    # Calculate maximum label width for alignment (e.g., "C11" is longer than "C0")
                    max_label_len = len(f"C{len(per_core) - 1}")
                    
                    # Split cores in half between the two subpanels
                    num_cores = len(per_core)
                    midpoint = num_cores // 2
                    
                    # Update subpanel1 with first half of cores
                    self.panel2_subpanel1.clear()
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
                            self.panel2_subpanel1.add_inline(*inline_elements, renderer=self.renderer)
                    
                    # Update subpanel2 with second half of cores
                    self.panel2_subpanel2.clear()
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
                            self.panel2_subpanel2.add_inline(*inline_elements, renderer=self.renderer)
                
                # Update panel2 title with simple CPU name (bold)
                if 'cpu' in metrics:
                    cpu_data = metrics['cpu']
                    cpu_name_simple = cpu_data.get('name_simple', 'CPU')
                    self.panel2.title = ANSIColors.BOLD + cpu_name_simple + ANSIColors.RESET
                    # Update the first left label (title) if it exists
                    if self.panel2.left_labels:
                        self.panel2.left_labels[0] = ANSIColors.BOLD + cpu_name_simple + ANSIColors.RESET
                    elif cpu_name_simple:
                        self.panel2.left_labels.insert(0, ANSIColors.BOLD + cpu_name_simple + ANSIColors.RESET)
                    
                    # Update panel2 right label with current CPU frequency
                    current_freq = cpu_data.get('current_frequency')
                    if current_freq:
                        self.panel2.right_labels = [current_freq]
                    else:
                        self.panel2.right_labels = []
                
                # Update panel2 layout bounds first (needs to match panel2's content area)
                content_row, content_col, content_width, content_height = self.panel2.get_content_area()
                self.panel2_vlayout.set_bounds(content_row, content_col, content_width, content_height)
                self.panel2_vlayout.update()
                
                # Update inline panel 1 with overall CPU usage (same as panel1) + temp graph + temp text
                if 'cpu' in metrics:
                    cpu_data = metrics['cpu']
                    cpu_usage = cpu_data.get('overall', 0.0)
                    
                    # Get CPU temperature
                    temp_data = cpu_data.get('temperature')
                    cpu_temp = temp_data.get('current') if temp_data else None
                    
                    # Get CPU power consumption
                    cpu_power = cpu_data.get('power')
                    
                    # Update graph with current CPU temperature (if available)
                    if cpu_temp is not None:
                        self.panel2_inline1_graph.add_value(cpu_temp)
                    
                    self.panel2_inline1.clear()
                    overall_bar = ProgressBar(cpu_usage, truecolor_support=self.renderer._truecolor_support)
                    
                    # Build inline elements
                    inline_elements = [
                        InlineText(ANSIColors.BOLD + "CPU" + ANSIColors.RESET),
                        InlineBar(overall_bar),  # No max_size, so it can grow
                        InlineText(f"{cpu_usage:3d}%"),
                        InlineGraph(self.panel2_inline1_graph, renderer=self.renderer, max_size=10),
                    ]
                    
                    # Add temperature text after graph if available (no decimal)
                    if cpu_temp is not None:
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
                    
                    self.panel2_inline1.add_inline(*inline_elements, renderer=self.renderer)
                
                # Update pipe separator (vertical bar) - fill to match height after layout update
                self.panel2_pipe.clear()
                pipe_height = max(1, self.panel2_pipe.height)
                gray_pipe = ANSIColors.BRIGHT_BLACK + "│" + ANSIColors.RESET
                for _ in range(pipe_height):
                    self.panel2_pipe.add_line(gray_pipe)
                
                # Update inline panel 2 with GPU info
                gpu_usage = 0.0
                gpu_name_simple = None
                gpu_memory_used_mb = None
                gpu_memory_total_mb = None
                gpu_memory_usage_percent = 0.0
                gpu_temp = None
                gpu_power = None
                if 'gpu' in metrics:
                    gpu_data = metrics['gpu']
                    gpu_usage = gpu_data.get('overall', {}).get('usage', 0.0)
                    # Get simplified GPU name and memory info from first GPU if available
                    gpus = gpu_data.get('gpus', [])
                    if gpus and len(gpus) > 0:
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
                    self.panel2.bottom_left_labels = [ANSIColors.BOLD + gpu_name_simple + ANSIColors.RESET]
                else:
                    # Clear if no GPU available
                    self.panel2.bottom_left_labels = []
                
                # Update GPU VRAM graph with memory usage percentage
                if gpu_memory_usage_percent is not None:
                    self.panel2_inline2_graph.add_value(gpu_memory_usage_percent)
                
                # Update GPU temperature graph (if available)
                if gpu_temp is not None:
                    self.panel2_inline2_temp_graph.add_value(float(gpu_temp))
                
                self.panel2_inline2.clear()
                gpu_bar = ProgressBar(gpu_usage, truecolor_support=self.renderer._truecolor_support)
                
                # Build inline elements
                inline_elements = [
                    InlineText(ANSIColors.BOLD + "GPU" + ANSIColors.RESET),
                    InlineBar(gpu_bar),  # No max_size, so it can grow
                    InlineText(f"{int(gpu_usage):3d}%"),
                    InlineGraph(self.panel2_inline2_graph, renderer=self.renderer, max_size=8),
                ]
                
                # Add VRAM label if memory data is available
                if gpu_memory_used_mb is not None and gpu_memory_total_mb is not None:
                    used_gb = gpu_memory_used_mb / 1024.0
                    total_gb = gpu_memory_total_mb / 1024.0
                    vram_label = f"{used_gb:.1f}GB/{int(total_gb)}GB"
                    inline_elements.append(InlineText(vram_label))
                
                # Add GPU temperature graph if available
                if gpu_temp is not None:
                    inline_elements.append(InlineGraph(self.panel2_inline2_temp_graph, renderer=self.renderer, max_size=10))
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
                
                self.panel2_inline2.add_inline(*inline_elements, renderer=self.renderer)
                
                # Move cursor to top
                sys.stdout.write('\033[H')
                
                # Render all panels (layouts will be handled automatically)
                self.renderer.render_all_panels()
                
                sys.stdout.flush()
                
                # Wait for next update interval
                time.sleep(self.update_interval)
        
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            pass
        
        finally:
            # Cleanup
            self.cleanup()
    
    def stop(self) -> None:
        """Stop the application loop."""
        self.running = False
    
    def cleanup(self) -> None:
        """Clean up resources on exit."""
        self.renderer.cleanup()
