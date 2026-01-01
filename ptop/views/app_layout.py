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
from ..ui.ansi_renderer import ANSIRendererBase, HLayout, VLayout
from .history_panel import HistoryPanel
from .processor_panel import ProcessorPanel


class AppLayout:
    """
    Controller for the application's UI layout structure.
    
    This class manages the entire UI layout design:
    - Root layout structure (VLayout containing HLayout)
    - Panel controllers (HistoryPanel, ProcessorPanel)
    - Layout updates and bounds management
    - Panel update coordination
    """
    
    def __init__(self, renderer: ANSIRendererBase):
        """
        Initialize the application layout.
        
        Args:
            renderer: The ANSI renderer instance
        """
        self.renderer = renderer
        
        # Create root layout structure
        self.root_layout = VLayout(margin=0, spacing=1)
        
        # Create horizontal layout for top row of panels
        self.top_hlayout = HLayout(margin=0, spacing=1)
        
        # Create panel controllers
        self.history_panel = HistoryPanel(self.renderer)
        self.processor_panel = ProcessorPanel(self.renderer)
        
        # Build layout hierarchy
        self.top_hlayout.add_panel(self.history_panel.panel)
        self.top_hlayout.add_panel(self.processor_panel.panel)
        self.root_layout.add_layout(self.top_hlayout)
        
        # Register root layout with renderer
        self.renderer.add_layout(self.root_layout)
    
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
    
    def update(self, metrics: Dict[str, Any]) -> None:
        """
        Update all panels with current metrics.
        
        Args:
            metrics: Dictionary of metrics from collectors
        """
        self.history_panel.update(metrics)
        self.processor_panel.update(metrics)

