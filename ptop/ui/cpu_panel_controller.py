"""
CPU Panel Controller.

This module provides a controller that formats and renders CPU metrics
using the base ANSI renderer. All CPU-specific logic, thresholds, and
formatting decisions are handled here, not in the renderer.
"""

from typing import Dict, Any
from .ansi_renderer import ANSIRendererBase, ANSIColors, Panel


class CPUPanelController:
    """
    Controller for rendering CPU metrics panel.
    
    This controller handles:
    - CPU metric formatting
    - Color decisions based on thresholds
    - Panel content generation
    - All CPU-specific logic
    
    The base renderer only draws what this controller provides.
    """
    
    # Thresholds for color decisions
    USAGE_WARNING = 50.0
    USAGE_CRITICAL = 80.0
    TEMP_WARNING = 50.0
    TEMP_CRITICAL = 70.0
    
    def __init__(self, renderer: ANSIRendererBase):
        """
        Initialize the CPU panel controller.
        
        Args:
            renderer: Base ANSI renderer to use for drawing
        """
        self.renderer = renderer
        self.panel: Panel = None
        self._init_panel()
    
    def _init_panel(self) -> None:
        """Initialize the CPU panel."""
        width = min(80, self.renderer.terminal_size[0] - 2)
        height = 20
        self.panel = self.renderer.create_panel('cpu', 3, 1, width, height, "CPU")
    
    def _get_usage_color(self, usage: float) -> str:
        """
        Get color for CPU usage based on thresholds.
        
        Args:
            usage: Usage percentage (0-100)
        
        Returns:
            ANSI color code
        """
        if usage >= self.USAGE_CRITICAL:
            return ANSIColors.BRIGHT_RED
        elif usage >= self.USAGE_WARNING:
            return ANSIColors.BRIGHT_YELLOW
        else:
            return ANSIColors.BRIGHT_GREEN
    
    def _get_temp_color(self, temp: float) -> str:
        """
        Get color for temperature based on thresholds.
        
        Args:
            temp: Temperature in Celsius
        
        Returns:
            ANSI color code
        """
        if temp >= self.TEMP_CRITICAL:
            return ANSIColors.BRIGHT_RED
        elif temp >= self.TEMP_WARNING:
            return ANSIColors.BRIGHT_YELLOW
        else:
            return ANSIColors.BRIGHT_GREEN
    
    def render(self, cpu_data: Dict[str, Any]) -> None:
        """
        Render CPU metrics to the panel.
        
        Args:
            cpu_data: CPU metrics dictionary from CPUCollector
        """
        # Update panel dimensions if terminal size changed
        width = min(80, self.renderer.terminal_size[0] - 2)
        if self.panel.width != width:
            self.panel.width = width
            self.panel.height = 20
        
        # Clear panel content
        self.panel.clear()
        
        # CPU Name
        cpu_name = cpu_data.get('name', 'Unknown CPU')
        self.panel.add_line(ANSIColors.BOLD + "CPU: " + ANSIColors.RESET + cpu_name)
        self.panel.add_line(f"Cores: {cpu_data['count_logical']} logical, {cpu_data['count_physical']} physical")
        self.panel.add_line("")
        
        # Overall CPU Usage with bar
        overall = cpu_data.get('overall', 0.0)
        usage_color = self._get_usage_color(overall)
        self.panel.add_line(ANSIColors.BOLD + "Overall Usage:" + ANSIColors.RESET)
        
        # Create bar using renderer utility
        bar_width = width - 20
        bar = self.renderer.draw_status_bar(overall, bar_width)
        usage_text = f"{overall:5.1f}%"
        self.panel.add_line(f"  {usage_color}{usage_text}{ANSIColors.RESET} {bar}")
        self.panel.add_line("")
        
        # Per-core usage with bars
        per_core = cpu_data.get('per_core', [])
        if per_core:
            self.panel.add_line(ANSIColors.BOLD + "Per Core:" + ANSIColors.RESET)
            label_width = 15  # "  Core XX: XX.X% "
            bar_width = max(10, (width - label_width - 2))
            
            for i, core_usage in enumerate(per_core):
                core_color = self._get_usage_color(core_usage)
                bar = self.renderer.draw_status_bar(core_usage, bar_width)
                usage_text = f"{core_usage:5.1f}%"
                self.panel.add_line(f"  Core {i:2d}: {core_color}{usage_text}{ANSIColors.RESET} {bar}")
        
        # Clock Speeds
        frequencies = cpu_data.get('frequencies', [])
        if frequencies and len(frequencies) == len(per_core):
            self.panel.add_line("")
            self.panel.add_line(ANSIColors.BOLD + "Clock Speeds:" + ANSIColors.RESET)
            for i in range(0, len(frequencies), 4):
                freq_line = "  "
                for j in range(4):
                    idx = i + j
                    if idx < len(frequencies):
                        freq_mhz = frequencies[idx]
                        freq_text = f"Core {idx}: {ANSIColors.CYAN}{freq_mhz:6.0f} MHz{ANSIColors.RESET}"
                        freq_line += freq_text + "  "
                self.panel.add_line(freq_line)
        
        # Load Average
        load_avg = cpu_data.get('load_average')
        if load_avg:
            self.panel.add_line("")
            self.panel.add_line(ANSIColors.BOLD + "Load Average:" + ANSIColors.RESET)
            load_text = (f"  1 min: {ANSIColors.YELLOW}{load_avg[0]:.2f}{ANSIColors.RESET}  |  "
                        f"5 min: {ANSIColors.YELLOW}{load_avg[1]:.2f}{ANSIColors.RESET}  |  "
                        f"15 min: {ANSIColors.YELLOW}{load_avg[2]:.2f}{ANSIColors.RESET}")
            self.panel.add_line(load_text)
        
        # Temperature
        temperature = cpu_data.get('temperature')
        if temperature:
            self.panel.add_line("")
            self.panel.add_line(ANSIColors.BOLD + "Temperature:" + ANSIColors.RESET)
            current_temp = temperature.get('current')
            if current_temp is not None:
                temp_color = self._get_temp_color(current_temp)
                temp_text = f"  Current: {temp_color}{current_temp:.1f}°C{ANSIColors.RESET}"
                self.panel.add_line(temp_text)
        
        # Power
        power = cpu_data.get('power')
        if power is not None:
            self.panel.add_line("")
            self.panel.add_line(ANSIColors.BOLD + "Power Consumption:" + ANSIColors.RESET)
            power_text = f"  {ANSIColors.BRIGHT_MAGENTA}{power:.2f} W{ANSIColors.RESET}"
            self.panel.add_line(power_text)
        
        # Render the panel
        self.renderer.render_panel(self.panel)
