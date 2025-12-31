"""
Abstracted UI renderer interface.

This module provides a base renderer class that can be extended
or replaced with custom ANSI-based GUI implementations.

Current implementation: Simple text-based output
Future: Can be replaced with ANSI renderer for fine-grained control
"""

import os
import sys
from typing import Dict, Any
from abc import ABC, abstractmethod


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


class TextRenderer(BaseRenderer):
    """
    Simple text-based renderer for terminal output.
    
    This is the initial implementation that prints metrics as plain text.
    Later, this can be replaced with an ANSI-based renderer for:
    - Colored output
    - Progress bars
    - Precise cursor positioning
    - Multi-panel layouts
    """
    
    def __init__(self):
        """Initialize the text renderer."""
        self.lines_printed = 0
    
    def setup(self) -> None:
        """
        Set up the renderer.
        
        For text renderer, we just ensure we can write to stdout.
        For future ANSI renderer, this would:
        - Enable raw mode
        - Hide cursor
        - Set up terminal size
        """
        # Clear screen on startup
        os.system('clear' if os.name != 'nt' else 'cls')
    
    def render(self, data: Dict[str, Any]) -> None:
        """
        Render metrics data as text.
        
        Args:
            data: Dictionary with collector data, e.g.:
                  {
                      'cpu': {
                          'overall': 45.2,
                          'per_core': [40.1, 50.3, ...],
                          ...
                      }
                  }
        """
        # Clear previous output by moving cursor to top
        # (Simple approach - in ANSI version, we'd use escape sequences)
        if self.lines_printed > 0:
            # Move cursor up by number of lines printed
            sys.stdout.write(f"\033[{self.lines_printed}A")
        
        self.lines_printed = 0
        
        # Render header
        print("=" * 60)
        print("  PTop - System Monitor")
        print("=" * 60)
        print()
        self.lines_printed += 4
        
        # Render CPU metrics if available
        if 'cpu' in data:
            cpu_data = data['cpu']
            self._render_cpu(cpu_data)
        
        # Flush output
        sys.stdout.flush()
    
    def _render_cpu(self, cpu_data: Dict[str, Any]) -> None:
        """
        Render CPU metrics.
        
        Args:
            cpu_data: CPU metrics dictionary from CPUCollector
        """
        # CPU Name
        cpu_name = cpu_data.get('name', 'Unknown CPU')
        print(f"CPU: {cpu_name}")
        print(f"  Cores: {cpu_data['count_logical']} logical, "
              f"{cpu_data['count_physical']} physical")
        print()
        self.lines_printed += 3
        
        # CPU Usage
        print("CPU Usage:")
        print(f"  Overall: {cpu_data['overall']:.1f}%")
        
        # Show per-core usage
        per_core = cpu_data.get('per_core', [])
        if per_core:
            print("  Per Core:")
            # Display cores in rows of 4
            for i in range(0, len(per_core), 4):
                core_line = "    "
                for j in range(4):
                    idx = i + j
                    if idx < len(per_core):
                        core_line += f"Core {idx}: {per_core[idx]:5.1f}%  "
                print(core_line)
        
        print()
        self.lines_printed += 3 + (len(per_core) + 3) // 4
        
        # Clock Speeds
        frequencies = cpu_data.get('frequencies', [])
        if frequencies:
            print("Clock Speeds:")
            if len(frequencies) == len(per_core) if per_core else False:
                # Show per-core frequencies
                for i in range(0, len(frequencies), 4):
                    freq_line = "    "
                    for j in range(4):
                        idx = i + j
                        if idx < len(frequencies):
                            freq_mhz = frequencies[idx]
                            freq_line += f"Core {idx}: {freq_mhz:6.0f} MHz  "
                    print(freq_line)
            else:
                # Show overall frequency
                print(f"  Current: {frequencies[0]:.0f} MHz ({frequencies[0]/1000:.2f} GHz)")
            print()
            self.lines_printed += 2 + (len(frequencies) + 3) // 4 if len(frequencies) > 1 else 2
        
        # Load Average
        load_avg = cpu_data.get('load_average')
        if load_avg:
            print("Load Average:")
            print(f"  1 min: {load_avg[0]:.2f}  |  5 min: {load_avg[1]:.2f}  |  15 min: {load_avg[2]:.2f}")
            print()
            self.lines_printed += 3
        
        # Temperature
        temperature = cpu_data.get('temperature')
        if temperature:
            print("Temperature:")
            current_temp = temperature.get('current')
            if current_temp is not None:
                print(f"  Current: {current_temp:.1f}°C")
            
            per_core_temp = temperature.get('per_core')
            if per_core_temp and len(per_core_temp) > 1:
                print("  Per Core:")
                for i in range(0, len(per_core_temp), 4):
                    temp_line = "    "
                    for j in range(4):
                        idx = i + j
                        if idx < len(per_core_temp):
                            temp_line += f"Core {idx}: {per_core_temp[idx]:5.1f}°C  "
                    print(temp_line)
            print()
            self.lines_printed += 3 + (len(per_core_temp) + 3) // 4 if per_core_temp and len(per_core_temp) > 1 else 2
        
        # Power
        power = cpu_data.get('power')
        if power is not None:
            print(f"Power Consumption: {power:.2f} W")
            print()
            self.lines_printed += 2
    
    def clear(self) -> None:
        """Clear the display."""
        # For text renderer, we'll clear on next render
        # ANSI version would use escape sequences to clear specific areas
        pass
    
    def cleanup(self) -> None:
        """
        Clean up on exit.
        
        For text renderer, we just print a newline.
        For ANSI renderer, this would:
        - Show cursor
        - Reset terminal attributes
        - Clear screen
        """
        print("\n" * 2)
        print("Monitor stopped.")
        sys.stdout.flush()
