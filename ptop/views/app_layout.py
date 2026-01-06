"""
Application layout controller.

This module manages the overall UI layout structure of the application.
It is responsible for:
- Creating and organizing the layout hierarchy
- Creating panel controllers
- Managing layout updates
- Coordinating panel updates with metrics
"""

from typing import Dict, Any
from ..ui.ansi_renderer import ANSIRendererBase
from ..ui.ui_elements import HLayout, VLayout, Panel
from .history_panel import HistoryPanel
from .processor_panel import ProcessorPanel
from .system_info_panel import SystemInfoPanel


class AppLayout:
    """
    Controller for the application's UI layout structure.
    
    This class manages the entire UI layout design:
    - Root layout structure (VLayout containing HLayout for top row, SystemInfoPanel below)
    - Panel controllers (HistoryPanel, ProcessorPanel, SystemInfoPanel)
    - Layout updates and bounds management
    - Panel update coordination
    """
    
    def __init__(self, renderer: ANSIRendererBase, debug: bool = False):
        """
        Initialize the application layout.
        
        Args:
            renderer: The ANSI renderer instance
            debug: If True, skip battery detection (for mock data testing)
        """
        self.renderer = renderer
        self.debug = debug
        
        # Create root layout structure
        self.root_layout = VLayout(margin=0, spacing=1)
        
        # Create horizontal layout for top row of panels
        self.top_hlayout = HLayout(margin=0, spacing=1)
        
        # Create horizontal layout for bottom row (system info + blank panels)
        self.bottom_hlayout = HLayout(margin=0, spacing=1)
        
        # Create panel controllers
        self.history_panel = HistoryPanel(self.renderer)
        self.processor_panel = ProcessorPanel(self.renderer)
        self.system_info_panel = SystemInfoPanel(self.renderer, debug=debug)
        
        # Create blank panel for bottom row (with border, no content)
        self.blank_panel1 = Panel(1, 1, 1, 1, title='')
        
        # Build layout hierarchy
        # Top row: history, processor (side by side)
        self.top_hlayout.add_panel(self.history_panel.panel)
        self.top_hlayout.add_panel(self.processor_panel.panel)
        self.root_layout.add_layout(self.top_hlayout)
        
        # Bottom row: system info panel + blank panel
        self.bottom_hlayout.add_panel(self.system_info_panel.panel)
        self.bottom_hlayout.add_panel(self.blank_panel1)
        self.root_layout.add_layout(self.bottom_hlayout)
        
        # Store root layout for rendering
        self.containers = [self.root_layout]
    
    def update_layout(self, cols: int, rows: int) -> None:
        """
        Update layout bounds based on terminal size.
        
        Args:
            cols: Terminal width in columns
            rows: Terminal height in rows
        """
        # No header, so layout starts at row 1 and uses full terminal
        self.root_layout.set_bounds(1, 1, cols, rows)
        self.root_layout.update()
        
        # Update panel layouts
        self.history_panel.update_layout()
        self.processor_panel.update_layout()
        self.system_info_panel.update_layout()
    
    def update(self, metrics: Dict[str, Any], force_redraw: bool = False) -> None:
        """
        Update all panels with current metrics.
        
        Args:
            metrics: Dictionary of metrics from collectors
            force_redraw: If True, force all panels to redraw (used on resize)
        """
        self.history_panel.update(metrics)
        self.processor_panel.update(metrics)
        # System info panel is static - only update on first call or force
        self.system_info_panel.update(metrics, force=force_redraw)

