#!/usr/bin/env python3
"""
Debug test for container system - single panel only.
"""

import sys
import os
import time
import signal
import random

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ptop.ui.ansi_renderer import ANSIRendererBase, ANSIColors, HLayout, VLayout
from ptop.ui.inline import InlineText, InlineBar, InlineGraph
from ptop.ui.progress_bar import ProgressBar
from ptop.ui.utils import visible_length


class MockCPUData:
    """Generates mock CPU data for testing."""
    
    def __init__(self):
        self.overall_usage = 25.0
        
    def update(self):
        """Update mock data with small random changes."""
        # Overall usage fluctuates
        self.overall_usage += random.uniform(-5, 5)
        self.overall_usage = max(0, min(100, self.overall_usage))


def main():
    """Simple test with one panel in an HLayout."""
    renderer = ANSIRendererBase()
    running = True
    
    def signal_handler(signum, frame):
        nonlocal running
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        renderer.setup()
        
        # Get terminal size
        cols, rows = renderer.get_terminal_size()
        print(f"Terminal size: {cols}x{rows}")
        
        # Create two simple panels (bounds will be set by layout)
        panel1 = renderer.create_panel(
            'test_panel1',
            title='Panel 1',
            rounded=True,
            border_color=ANSIColors.BRIGHT_CYAN
        )
        
        panel2 = renderer.create_panel(
            'test_panel2',
            title='Panel 2',
            rounded=True,
            border_color=ANSIColors.BRIGHT_GREEN
        )
        
        # Create 2 panels for the VLayout inside panel2
        panel2a = renderer.create_panel(
            'test_panel2a',
            title='Panel 2A',
            rounded=True,
            border_color=ANSIColors.BRIGHT_YELLOW
        )
        
        panel2b = renderer.create_panel(
            'test_panel2b',
            title='Panel 2B',
            rounded=True,
            border_color=ANSIColors.BRIGHT_MAGENTA
        )
        
        # Create history graph for panel 2a
        panel2a_graph = renderer.create_history_graph(15, min_value=0.0, max_value=100.0)
        
        # Create VLayout for panel2b with two graphs and separator
        panel2b_vlayout = VLayout(margin=0, spacing=0)
        
        # Create two borderless panels for graphs
        panel2b_graph_top = renderer.create_panel(
            'test_panel2b_graph_top',
            title='',
            borderless=True
        )
        
        # Create separator panel with "=="
        panel2b_separator = renderer.create_panel(
            'test_panel2b_separator',
            title='',
            borderless=True
        )
        panel2b_separator.max_height = 1  # Fixed height of 1 line
        
        panel2b_graph_bottom = renderer.create_panel(
            'test_panel2b_graph_bottom',
            title='',
            borderless=True
        )
        
        # Add panels to VLayout
        panel2b_vlayout.add_panel(panel2b_graph_top)
        panel2b_vlayout.add_panel(panel2b_separator)
        panel2b_vlayout.add_panel(panel2b_graph_bottom)
        
        # Add VLayout as child of panel2b
        panel2b.add_child(panel2b_vlayout)
        
        # Create multi-line graphs (dimensions will be updated dynamically)
        panel2b_graph_top_obj = renderer.create_multi_line_graph(40, 8, min_value=0.0, max_value=100.0, use_braille=True, top_to_bottom=False)
        panel2b_graph_bottom_obj = renderer.create_multi_line_graph(40, 8, min_value=0.0, max_value=100.0, use_braille=True, top_to_bottom=True)
        
        # Set different gradient for bottom graph: blue -> cyan -> white
        panel2b_graph_bottom_obj.colors = [ANSIColors.RED, ANSIColors.GREEN, ANSIColors.YELLOW]
        
        # Create VLayout and add panels to it
        panel2_vlayout = VLayout(margin=0, spacing=1)
        panel2_vlayout.add_panel(panel2a)
        panel2_vlayout.add_panel(panel2b)
        
        # Add VLayout as child of panel2 (nested container!)
        panel2.add_child(panel2_vlayout)
        
        # Create an HLayout and add both panels
        hlayout = HLayout(margin=1, spacing=1)
        hlayout.add_panel(panel1)
        hlayout.add_panel(panel2)
        
        # Register layout with renderer (layout is the root, no panel wrapper needed)
        renderer.add_layout(hlayout)
        
        # Function to update layout
        def update_layout():
            cols, rows = renderer.get_terminal_size()
            # No header, so layout starts at row 1 and uses full terminal
            hlayout.set_bounds(1, 1, cols, rows)
            hlayout.update()
            
            # Update VLayout inside panel2 to fit within panel2's content area
            content_row, content_col, content_width, content_height = panel2.get_content_area()
            panel2_vlayout.set_bounds(content_row, content_col, content_width, content_height)
            panel2_vlayout.update()
            
            # Update VLayout inside panel2b to fit within panel2b's content area
            panel2b_content_row, panel2b_content_col, panel2b_content_width, panel2b_content_height = panel2b.get_content_area()
            panel2b_vlayout.set_bounds(panel2b_content_row, panel2b_content_col, panel2b_content_width, panel2b_content_height)
            panel2b_vlayout.update()
        
        # Initial layout update
        update_layout()
        
        # Create mock CPU data
        mock_data = MockCPUData()
        
        frame_count = 0
        
        while running:
            frame_count += 1
            
            # Check for terminal resize
            current_terminal_size = renderer.get_terminal_size()
            if current_terminal_size != getattr(renderer, '_last_terminal_size', None):
                renderer._last_terminal_size = current_terminal_size
                # Clear screen on resize to remove artifacts
                renderer.clear()
                update_layout()
            
            # Update panel 1 content
            panel1.clear()
            panel1.add_line(ANSIColors.BOLD + "Panel 1" + ANSIColors.RESET)
            panel1.add_line("")
            panel1.add_line(f"Frame: {frame_count}")
            panel1.add_line(f"Bounds: row={panel1.row}, col={panel1.col}")
            panel1.add_line(f"Size: {panel1.width}x{panel1.height}")
            panel1.add_line("")
            content_row, content_col, content_width, content_height = panel1.get_content_area()
            panel1.add_line(f"Content: {content_width}x{content_height}")
            panel1.add_line("")
            panel1.add_line(f"Parent: {type(panel1.parent).__name__ if panel1.parent else 'None'}")
            panel1.add_line(f"Children: {len(panel1.children)}")
            
            # Update panel 2 content (VLayout will render its own panels)
            panel2.clear()
            panel2.add_line(ANSIColors.BOLD + "Panel 2 (Container)" + ANSIColors.RESET)
            panel2.add_line("")
            panel2.add_line(f"Frame: {frame_count}")
            panel2.add_line(f"Bounds: row={panel2.row}, col={panel2.col}")
            panel2.add_line(f"Size: {panel2.width}x{panel2.height}")
            panel2.add_line("")
            content_row, content_col, content_width, content_height = panel2.get_content_area()
            panel2.add_line(f"Content: {content_width}x{content_height}")
            panel2.add_line("")
            panel2.add_line(f"Parent: {type(panel2.parent).__name__ if panel2.parent else 'None'}")
            panel2.add_line(f"Children: {len(panel2.children)}")
            panel2.add_line(f"  - {type(panel2.children[0]).__name__ if panel2.children else 'None'}")
            
            # Update nested panels content
            # Update mock CPU data
            mock_data.update()
            cpu_usage = mock_data.overall_usage
            
            # Update history graph
            panel2a_graph.add_value(cpu_usage)
            
            # Create progress bar
            panel2a_bar = ProgressBar(cpu_usage, truecolor_support=renderer._truecolor_support)
            
            panel2a.clear()
            panel2a.add_line(ANSIColors.BOLD + "Panel 2A" + ANSIColors.RESET)
            panel2a.add_line("")
            panel2a.add_line(f"Frame: {frame_count}")
            panel2a.add_line(f"CPU Usage: {cpu_usage:.1f}%")
            panel2a.add_line("")
            # Add inline composition: text + bar + graph
            panel2a.add_inline(
                InlineText(ANSIColors.BOLD + "Usage:" + ANSIColors.RESET),
                InlineText(f"{cpu_usage:5.1f}%"),
                InlineBar(panel2a_bar, max_size=12),
                InlineGraph(panel2a_graph, renderer=renderer),
                renderer=renderer
            )
            
            # Update panel2b - clear content so inner panel is visible
            panel2b.clear()
            # Don't add content lines - let the inner panel show through
            
            # Update separator panel: all "=" with CPU↑=GPU↓ centered
            panel2b_separator.clear()
            cpu_text = "CPU"
            gpu_text = "GPU"
            cpu_arrow = "↑"
            gpu_arrow = "↓"
            cpu_label_text = cpu_text + cpu_arrow
            gpu_label_text = gpu_text + gpu_arrow
            cpu_label = ANSIColors.BRIGHT_WHITE + cpu_text + ANSIColors.RESET + ANSIColors.CYAN + cpu_arrow + ANSIColors.RESET
            gpu_label = ANSIColors.BRIGHT_WHITE + gpu_text + ANSIColors.RESET + ANSIColors.CYAN + gpu_arrow + ANSIColors.RESET
            
            # Calculate centered layout: ...───CPU↑─GPU↓───...
            total_width = panel2b_separator.width
            label_width = len(cpu_label_text) + 1 + len(gpu_label_text)  # CPU↑─GPU↓
            line_width = total_width - label_width
            left_lines = line_width // 2
            right_lines = line_width - left_lines
            
            line_char = ANSIColors.BRIGHT_BLACK + '─' + ANSIColors.RESET
            separator_line = line_char * left_lines + cpu_label + line_char + gpu_label + line_char * right_lines
            panel2b_separator.add_line(separator_line)
            
            # Update top graph panel
            panel2b_graph_top.clear()
            
            # Update graph dimensions to match panel size (if changed)
            if panel2b_graph_top_obj.width_chars != panel2b_graph_top.width or panel2b_graph_top_obj.height_chars != panel2b_graph_top.height:
                panel2b_graph_top_obj.width_chars = panel2b_graph_top.width
                panel2b_graph_top_obj.height_chars = panel2b_graph_top.height
            
            # Update graph with CPU usage
            panel2b_graph_top_obj.add_value(cpu_usage)
            
            # Get graph as string and split into lines
            graph_string = panel2b_graph_top_obj.get_graph_string(renderer)
            graph_lines = graph_string.split('\n')
            
            # Add graph lines to panel
            for line in graph_lines:
                if line:  # Skip empty lines
                    panel2b_graph_top.add_line(line)
            
            # Update bottom graph panel (top-to-bottom rendering)
            panel2b_graph_bottom.clear()
            
            # Update graph dimensions to match panel size (if changed)
            if panel2b_graph_bottom_obj.width_chars != panel2b_graph_bottom.width or panel2b_graph_bottom_obj.height_chars != panel2b_graph_bottom.height:
                panel2b_graph_bottom_obj.width_chars = panel2b_graph_bottom.width
                panel2b_graph_bottom_obj.height_chars = panel2b_graph_bottom.height
            
            # Update graph with CPU usage
            panel2b_graph_bottom_obj.add_value(cpu_usage)
            
            # Get graph as string and split into lines
            graph_string = panel2b_graph_bottom_obj.get_graph_string(renderer)
            graph_lines = graph_string.split('\n')
            
            # Add graph lines to panel
            for line in graph_lines:
                if line:  # Skip empty lines
                    panel2b_graph_bottom.add_line(line)
            
            # Move cursor to top (don't clear screen to avoid flicker)
            sys.stdout.write('\033[H')
            
            # Render panel
            renderer.render_all_panels()
            
            sys.stdout.flush()
            
            # Wait for next frame
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        renderer.cleanup()
        print("\nTest complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
