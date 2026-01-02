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
from ..ui.ansi_renderer import ANSIRendererBase
from ..views.app_layout import AppLayout


class PTopApp:
    """
    Main application controller.
    
    This class orchestrates the entire system monitor:
    - Initializes collectors
    - Sets up UI renderer
    - Runs main loop with periodic updates
    - Handles graceful shutdown
    """
    
    def __init__(self, update_interval: float = 0.05, debug: bool = False):
        """
        Initialize the application.
        
        Args:
            update_interval: Time in seconds between updates (default: 0.05)
            debug: If True, use mock collectors with random data instead of real collectors
        """
        self.update_interval = update_interval
        self.running = False
        self.debug = debug
        
        # Initialize collectors
        # This is where we'll add more collectors later (memory, disk, etc.)
        self.collectors: List[BaseCollector] = []
        self._init_collectors()
        
        # Initialize UI renderer (always use ANSI renderer)
        self.renderer = ANSIRendererBase()
        
        # Initialize UI layout
        self.layout = AppLayout(self.renderer, debug=self.debug)
        
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
        if self.debug:
            # Use mock collectors for testing/debugging
            from ..mock_collectors.mock_cpu import MockCPUCollector
            from ..mock_collectors.mock_gpu import MockGPUCollector
            from ..mock_collectors.mock_system_info import MockSystemInfoCollector
            
            self.collectors.append(MockCPUCollector(num_cores=5))
            self.collectors.append(MockGPUCollector(num_gpus=3))
            self.collectors.append(MockSystemInfoCollector())
        else:
            # Use real collectors
            from ..collectors.cpu import CPUCollector
            from ..collectors.gpu import GPUCollector
            from ..collectors.system_info import SystemInfoCollector
            
            self.collectors.append(CPUCollector())
            self.collectors.append(GPUCollector())
            self.collectors.append(SystemInfoCollector())
        
        # Future collectors will be added here:
        # self.collectors.append(MemoryCollector())
        # self.collectors.append(DiskCollector())
        # self.collectors.append(NetworkCollector())
        # self.collectors.append(ProcessCollector())
    
    
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
        cols, rows = self.renderer.get_terminal_size()
        self.layout.update_layout(cols, rows)
        
        # Collect initial metrics and update panels to ensure content is populated
        initial_metrics = self.collect_metrics()
        self.layout.update(initial_metrics, force_redraw=True)  # Force initial render
        
        # Update layout again after content is populated to ensure proper bounds calculation
        # This recalculates nested panel layouts with the actual content
        self.layout.update_layout(cols, rows)
        
        try:
            # Main loop
            while self.running:
                # Check for terminal resize
                current_terminal_size = self.renderer.get_terminal_size()
                resize_occurred = current_terminal_size != getattr(self, '_last_terminal_size', None)
                if resize_occurred:
                    self._last_terminal_size = current_terminal_size
                    # Clear screen on resize to remove artifacts
                    self.renderer.clear()
                    cols, rows = current_terminal_size
                    # Update layout with new terminal size (matches startup sequence)
                    self.layout.update_layout(cols, rows)
                
                # Collect metrics from all collectors
                metrics = self.collect_metrics()
                
                # Update UI layout and panels with metrics
                # Pass force_redraw=True on resize to force system info panel to re-wrap
                self.layout.update(metrics, force_redraw=resize_occurred)
                
                # Update layout again after content is populated (matches startup sequence)
                # This ensures nested panel layouts are recalculated with the new content
                if resize_occurred:
                    cols, rows = current_terminal_size
                    self.layout.update_layout(cols, rows)
                    # Force system info panel to re-render after layout update (to re-wrap text)
                    self.layout.update(metrics, force_redraw=True)
                
                # Render all panels using double buffering (layouts will be handled automatically)
                # Double buffering eliminates flicker by building the entire frame in memory,
                # diffing it against the previous frame, and writing only changed rows atomically.
                # Force redraw on resize to ensure everything is recalculated
                self.renderer.render_all_panels(force_redraw=resize_occurred)
                
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
