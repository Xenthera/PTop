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
from ..ui.ansi_renderer import ANSIRendererBase, BaseRenderer
from ..ui.cpu_panel_controller import CPUPanelController


class PTopApp:
    """
    Main application controller.
    
    This class orchestrates the entire system monitor:
    - Initializes collectors
    - Sets up UI renderer
    - Runs main loop with periodic updates
    - Handles graceful shutdown
    """
    
    def __init__(self, update_interval: float = 1.0):
        """
        Initialize the application.
        
        Args:
            update_interval: Time in seconds between updates (default: 1.0)
        """
        self.update_interval = update_interval
        self.running = False
        
        # Initialize collectors
        # This is where we'll add more collectors later (memory, disk, etc.)
        self.collectors: List[BaseCollector] = []
        self._init_collectors()
        
        # Initialize UI renderer (always use ANSI renderer)
        self.renderer: BaseRenderer = ANSIRendererBase()
        # Create CPU panel controller
        self.cpu_controller = CPUPanelController(self.renderer)
        
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
        
        try:
            # Main loop
            while self.running:
                # Collect metrics from all collectors
                metrics = self.collect_metrics()
                
                # Render the collected data using ANSI renderer with controllers
                self.renderer.terminal_size = self.renderer.get_terminal_size()
                sys.stdout.write('\033[H')  # Move to top
                
                # Render header
                self.renderer.render_header("PTop - System Monitor")
                
                # Render CPU panel using controller
                if 'cpu' in metrics and self.cpu_controller:
                    self.cpu_controller.render(metrics['cpu'])
                
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
