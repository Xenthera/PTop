#!/usr/bin/env python3
"""
Simple test application for ANSI Base Renderer.

Tests a single panel with basic text to debug panel rendering.
"""

import sys
import os
import time
import signal
import random
import math

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ptop.ui.ansi_renderer import ANSIRendererBase, ANSIColors, HLayout, VLayout, BaseLayout, get_panel_content_area
from ptop.ui.history_graph import SingleLineGraph, MultiLineGraph
from ptop.ui.inline import InlineText, InlineBar, InlineGraph
from ptop.ui.progress_bar import ProgressBar
from ptop.ui.colors import rgb_to_ansitruecolor


class MockCPUData:
    """Generates mock CPU data for testing."""
    
    def __init__(self):
        self.overall_usage = 25.0
        self.per_core = [20.0, 30.0, 15.0, 25.0, 35.0, 20.0, 40.0, 15.0]
        self.temperature = 42.0
        self.frequencies = [3600, 3800, 3500, 3700, 3900, 3600, 4000, 3500]
        self.load_avg = (1.2, 1.5, 1.3)
        self.power = 45.5
        
    def update(self):
        """Update mock data with small random changes."""
        # Overall usage fluctuates
        self.overall_usage += random.uniform(-5, 5)
        self.overall_usage = max(0, min(100, self.overall_usage))
        
        # Per-core usage fluctuates
        for i in range(len(self.per_core)):
            self.per_core[i] += random.uniform(-8, 8)
            self.per_core[i] = max(0, min(100, self.per_core[i]))
        
        # Temperature correlates with usage
        self.temperature = 35 + (self.overall_usage * 0.3) + random.uniform(-2, 2)
        self.temperature = max(30, min(90, self.temperature))
        
        # Frequencies fluctuate slightly
        for i in range(len(self.frequencies)):
            self.frequencies[i] += random.uniform(-100, 100)
            self.frequencies[i] = max(3000, min(4500, self.frequencies[i]))
        
        # Load average fluctuates
        self.load_avg = (
            max(0, self.load_avg[0] + random.uniform(-0.2, 0.3)),
            max(0, self.load_avg[1] + random.uniform(-0.1, 0.2)),
            max(0, self.load_avg[2] + random.uniform(-0.1, 0.1))
        )
        
        # Power correlates with usage
        self.power = 20 + (self.overall_usage * 0.5) + random.uniform(-3, 3)
        self.power = max(15, min(100, self.power))


def get_usage_color(usage: float) -> str:
    """Get color based on usage percentage."""
    if usage >= 80:
        return ANSIColors.BRIGHT_RED
    elif usage >= 50:
        return ANSIColors.BRIGHT_YELLOW
    else:
        return ANSIColors.BRIGHT_GREEN


def get_temp_color(temp: float) -> str:
    """Get color based on temperature."""
    if temp >= 70:
        return ANSIColors.BRIGHT_RED
    elif temp >= 50:
        return ANSIColors.BRIGHT_YELLOW
    else:
        return ANSIColors.BRIGHT_GREEN


def main():
    """Main test loop."""
    renderer = ANSIRendererBase()
    mock_data = MockCPUData()
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
        
        # Create panels (positions will be set by layouts) with random border colors
        border_colors = [
            ANSIColors.BRIGHT_CYAN,
            ANSIColors.BRIGHT_GREEN,
            ANSIColors.BRIGHT_YELLOW,
            ANSIColors.BRIGHT_MAGENTA,
            ANSIColors.BRIGHT_BLUE,
            ANSIColors.BRIGHT_RED,
            ANSIColors.CYAN,
        ]
        
        panel1 = renderer.create_panel('panel1', 1, 1, 40, 15, 'CPU Usage', rounded=True, border_color=border_colors[0])
        panel2 = renderer.create_panel('panel2', 1, 1, 40, 15, 'CPU Cores', rounded=True, border_color=border_colors[1])
        panel3 = renderer.create_panel('panel3', 1, 1, 40, 15, 'System Info', rounded=True, border_color=border_colors[2])
        panel4 = renderer.create_panel('panel4', 1, 1, 40, 15, 'Performance', rounded=True, border_color=border_colors[3])
        # Create a bordered container panel that will contain a VLayout
        panel5_container = renderer.create_panel('panel5_container', 1, 1, 80, 25, 'Graph Container', rounded=True, border_color=border_colors[4])
        
        # Create borderless header panel and borderless graph panel for the VLayout inside the container
        panel5_header = renderer.create_panel('panel5_header', 1, 1, 78, 5, '', borderless=True)
        panel5 = renderer.create_panel('panel5', 1, 1, 78, 18, '', borderless=True)
        
        panel7 = renderer.create_panel('panel7', 1, 1, 80, 20, 'Gradient Test', rounded=True, border_color=border_colors[5])
        
        # Create history graphs for CPU usage and temperature
        usage_graph = renderer.create_history_graph(30, min_value=0.0, max_value=100.0)
        temp_graph = renderer.create_history_graph(30, min_value=30.0, max_value=90.0)
        
        # Create history graphs for each core (reused across frames)
        core_graphs = []
        for i in range(len(mock_data.per_core)):
            core_graphs.append(renderer.create_history_graph(10, min_value=0.0, max_value=100.0))
        
        # TEST: Nested Layouts
        # Create a main horizontal layout with 2 vertical layouts inside
        # This demonstrates VLayout inside HLayout
        left_column = VLayout(margin=0, spacing=1)
        left_column.add_panel(panel1)
        left_column.add_panel(panel3)
        
        right_column = VLayout(margin=0, spacing=1)
        right_column.add_panel(panel2)
        right_column.add_panel(panel4)
        
        # Main horizontal layout containing the two vertical columns
        main_layout = HLayout(margin=0, spacing=1)
        main_layout.add_layout(left_column)
        main_layout.add_layout(right_column)
        
        # VLayout for panel 5: header panel first, then graph panel
        panel5_vlayout = VLayout(margin=0, spacing=1)
        panel5_vlayout.add_panel(panel5_header)
        panel5_vlayout.add_panel(panel5)
        
        # Bottom row: panel 5 container, panel 6 (nested panels), and panel 7 horizontally
        bottom_layout = HLayout(margin=0, spacing=1)
        bottom_layout.add_panel(panel5_container)
        bottom_layout.add_panel(panel7)
        
        # Function to update all layouts based on current terminal size
        def update_all_layouts():
            cols, rows = renderer.get_terminal_size()
            header_height = 2
            content_start_row = header_height + 1
            content_height = rows - header_height
            
            # Divide content: 2/3 for nested layout, 1/3 for bottom panel
            main_height = (content_height * 2) // 3
            bottom_height = content_height - main_height
            
            # Update main nested layout (this will recursively update nested VLayouts)
            main_layout.update_layout(content_start_row, 1, cols, main_height)
            
            # Update bottom layout
            bottom_layout.update_layout(content_start_row + main_height + 1, 1, cols, bottom_height)
            
            # Update VLayout inside panel5_container (use content area of container)
            content_row, content_col, content_width, content_height = get_panel_content_area(panel5_container)
            panel5_vlayout.update_layout(content_row, content_col, content_width, content_height)
        
        # Initial layout update
        update_all_layouts()
        
        frame_count = 0
        last_terminal_size = renderer.get_terminal_size()
        
        while running:
            frame_count += 1
            
            # Check for terminal resize
            current_terminal_size = renderer.get_terminal_size()
            if current_terminal_size != last_terminal_size:
                # Terminal was resized - clear and reinitialize
                renderer.clear()
                renderer.terminal_size = current_terminal_size
                last_terminal_size = current_terminal_size
                
                # Update all layouts for new terminal size
                update_all_layouts()
                
                # Move cursor to top after clear
                sys.stdout.write('\033[H')
            
            # Update mock data
            mock_data.update()
            
            # Move cursor to top
            sys.stdout.write('\033[H')
            
            # Render header
            renderer.render_header(f"PTop - ANSI Renderer Test (Frame: {frame_count})")
            
            # Update history graphs with actual mock data
            usage_graph.add_value(mock_data.overall_usage)
            temp_graph.add_value(mock_data.temperature)
            
            # Panel 1: CPU Usage - Example with labels
            # Clear labels and set up new ones each frame (to show dynamic updates)
            panel1.clear_labels()
            panel1.add_left_label('Usage')  # Additional left label after title
            panel1.add_right_label(f"{mock_data.overall_usage:.1f}%")  # Right label with value (aligned with bar/graph)
            panel1.add_right_label('Active')  # Another right label
            
            panel1.clear()
            # Example: Complete inline composition - Text + Percentage + Bar + Graph all on one line
            # Using resizable bars and graphs that automatically size to fit panel width
            # All use the same value: mock_data.overall_usage
            max_color = usage_graph.get_max_value_color(renderer)
            
            usage_bar = ProgressBar(mock_data.overall_usage, truecolor_support=renderer._truecolor_support)
            panel1.add_inline(
                InlineText(ANSIColors.BOLD + "Usage:" + ANSIColors.RESET),
                InlineText(f"{max_color}{mock_data.overall_usage:5.1f}%{ANSIColors.RESET}"),
                InlineBar(usage_bar),
                InlineGraph(usage_graph, renderer=renderer, max_size=25),
                renderer=renderer
            )
            panel1.add_line("")
            panel1.add_line(ANSIColors.BOLD + "Load Average:" + ANSIColors.RESET)
            panel1.add_line(f"  1m: {ANSIColors.YELLOW}{mock_data.load_avg[0]:.2f}{ANSIColors.RESET}")
            panel1.add_line(f"  5m: {ANSIColors.YELLOW}{mock_data.load_avg[1]:.2f}{ANSIColors.RESET}")
            panel1.add_line(f"  15m: {ANSIColors.YELLOW}{mock_data.load_avg[2]:.2f}{ANSIColors.RESET}")
            
            # Panel 2: CPU Cores - Example with inline composition (text + bar + graph)
            panel2.clear_labels()
            panel2.add_left_label(f"{len(mock_data.per_core)} Cores")  # Additional left label
            panel2.add_right_label('Per-Core')  # Right label
            
            panel2.clear()
            # Header using inline
            panel2.add_inline(
                InlineText(ANSIColors.BOLD + "Per Core Usage:" + ANSIColors.RESET),
                renderer=renderer
            )
            panel2.add_line("")
            
            for i, core_usage in enumerate(mock_data.per_core[:6]):  # Show first 6 cores
                core_color = get_usage_color(core_usage)
                # Reuse the graph for this core (add current value to build history)
                core_graphs[i].add_value(core_usage)
                
                # Use different gradient for cores 2, 3, 4 (blue -> purple -> white)
                # Cores 0, 1, 5 use default green -> yellow -> red
                if i in [2, 3, 4]:
                    # Blue -> Purple -> White gradient
                    # Set colors on graph (using list format)
                    core_graphs[i].colors = [ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE]
                    # Create progress bar with custom colors (list format)
                    core_bar = ProgressBar(
                        core_usage,
                        colors=[ANSIColors.BRIGHT_BLUE, ANSIColors.BRIGHT_MAGENTA, ANSIColors.BRIGHT_WHITE],
                        truecolor_support=renderer._truecolor_support
                    )
                else:
                    # Default green -> yellow -> red gradient
                    core_bar = ProgressBar(core_usage, truecolor_support=renderer._truecolor_support)
                
                # Use inline composition with resizable bar and graph
                # Bar has max_size, graph fills remaining space
                panel2.add_inline(
                    InlineText(f"  Core {i}:"),
                    InlineText(f"{core_color}{core_usage:5.1f}%{ANSIColors.RESET}"),
                    InlineBar(core_bar, max_size=12),
                    InlineGraph(core_graphs[i], renderer=renderer),
                    renderer=renderer
                )
            
            # Panel 3: System Info - Example with temperature and power in labels
            panel3.clear_labels()
            panel3.add_left_label('System')  # Additional left label
            temp_color = get_temp_color(mock_data.temperature)
            panel3.add_right_label(f"{ANSIColors.RESET}{mock_data.temperature:.1f}°C")  # Right label with color
            panel3.add_right_label(f"{mock_data.power:.1f}W")  # Another right label
            
            panel3.clear()
            # Example: Inline composition with text + value + bar + graph all on one line
            # Using resizable bar and graph that automatically size to fit panel width
            # All use the same value: mock_data.temperature (scaled to 0-100% for bar)
            temp_color = get_temp_color(mock_data.temperature)
            temp_percent = (mock_data.temperature - 30) / 60 * 100  # Scale 30-90°C to 0-100%
            
            temp_bar = ProgressBar(temp_percent, truecolor_support=renderer._truecolor_support)
            panel3.add_inline(
                InlineText(ANSIColors.BOLD + "Temperature:" + ANSIColors.RESET),
                InlineText(f"{temp_color}{mock_data.temperature:.1f}°C{ANSIColors.RESET}"),
                InlineBar(temp_bar, max_size=10),
                InlineGraph(temp_graph, renderer=renderer),
                renderer=renderer
            )
            panel3.add_line("")
            panel3.add_line(ANSIColors.BOLD + "Power:" + ANSIColors.RESET)
            panel3.add_line(f"  {ANSIColors.BRIGHT_MAGENTA}{mock_data.power:.2f} W{ANSIColors.RESET}")
            panel3.add_line("")
            panel3.add_line(ANSIColors.BOLD + "CPU Model:" + ANSIColors.RESET)
            panel3.add_line("  Test CPU")
            panel3.add_line("  8 cores")
            
            # Panel 4: Performance - Example with only right labels
            panel4.clear_labels()
            # No additional left labels, just title
            avg_freq = sum(mock_data.frequencies[:6]) / min(6, len(mock_data.frequencies))
            panel4.add_right_label(f"{avg_freq:.0f} MHz")  # Right label with average frequency
            panel4.add_right_label('Avg')  # Another right label
            
            panel4.clear()
            panel4.add_line(ANSIColors.BOLD + "Clock Speeds:" + ANSIColors.RESET)
            for i in range(0, min(6, len(mock_data.frequencies)), 2):
                idx1 = i
                idx2 = i + 1
                if idx2 < len(mock_data.frequencies):
                    panel4.add_line(f"  Core {idx1}: {ANSIColors.CYAN}{mock_data.frequencies[idx1]:.0f} MHz{ANSIColors.RESET}")
                    panel4.add_line(f"  Core {idx2}: {ANSIColors.CYAN}{mock_data.frequencies[idx2]:.0f} MHz{ANSIColors.RESET}")
                elif idx1 < len(mock_data.frequencies):
                    panel4.add_line(f"  Core {idx1}: {ANSIColors.CYAN}{mock_data.frequencies[idx1]:.0f} MHz{ANSIColors.RESET}")
            
            # Helper function to populate gradient test panel
            def populate_gradient_panel(panel):
                """Populate a panel with gradient test content."""
                panel.clear()
                # Calculate bar width based on panel width (accounting for borders and padding)
                bar_width = max(15, panel.width - 20)  # Leave space for labels and borders
                
                panel.add_line(ANSIColors.BOLD + "Static Gradient Bars:" + ANSIColors.RESET)
                panel.add_line("")
                
                # Test different values with custom colors
                test_values = [10, 25, 50, 75, 90]
                test_labels = ["Low", "Medium-Low", "Mid", "Medium-High", "High"]
                
                for label, val in zip(test_labels, test_values):
                    # Use status_bar with standard colors
                    bar = renderer.draw_status_bar(val, bar_width)
                    panel.add_line(f"  {label:12s} {val:3.0f}%: {bar}")
                
                panel.add_line("")
                panel.add_line(ANSIColors.BOLD + "Full Range:" + ANSIColors.RESET)
                # Show full range from 0 to 100 (including 80 and 100)
                for val in [0, 20, 40, 60, 80, 100]:
                    bar = renderer.draw_status_bar(val, bar_width)
                    panel.add_line(f"  {val:3d}%: {bar}")
            
            # Panel 5 Header: Simple text panel (first in VLayout, borderless)
            panel5_header.clear()
            panel5_header.add_line(ANSIColors.BOLD + "Multi-Line Graph Test" + ANSIColors.RESET)
            panel5_header.add_line("")
            panel5_header.add_line(f"Current Value: {ANSIColors.BRIGHT_GREEN}{mock_data.overall_usage:.1f}%{ANSIColors.RESET}")
            panel5_header.add_line(f"Min: {ANSIColors.YELLOW}0.0{ANSIColors.RESET} | Max: {ANSIColors.YELLOW}100.0{ANSIColors.RESET}")
            panel5_header.add_line(f"Frame: {frame_count}")
            
            # Panel 5: Multi-line graph only (top to bottom, borderless)
            # Create multi-line graph for panel 5 (reused across frames)
            if not hasattr(renderer, '_panel5_multigraph'):
                # Panel 5 is borderless, so use full dimensions
                renderer._panel5_multigraph = renderer.create_multi_line_graph(
                    width_chars=panel5.width,
                    height_chars=panel5.height,
                    min_value=0.0,
                    max_value=100.0,
                    top_to_bottom=True  # Enable top-to-bottom rendering
                )
                # Store the last known panel dimensions to detect resize
                renderer._panel5_last_width = panel5.width
                renderer._panel5_last_height = panel5.height
            
            # Check if panel resized and update graph dimensions
            if (hasattr(renderer, '_panel5_last_width') and hasattr(renderer, '_panel5_last_height') and
                (panel5.width != renderer._panel5_last_width or panel5.height != renderer._panel5_last_height)):
                # Panel resized - update graph dimensions
                renderer._panel5_multigraph.width_chars = panel5.width
                renderer._panel5_multigraph.height_chars = panel5.height
                renderer._panel5_last_width = panel5.width
                renderer._panel5_last_height = panel5.height
            
            # Update multi-line graph with actual mock data
            renderer._panel5_multigraph.add_value(mock_data.overall_usage)
            
            # Panel 5: Multi-line graph only (bordered)
            panel5.clear()
            # Add the multi-line graph as lines
            graph_lines = renderer._panel5_multigraph.get_graph_string(renderer).split('\n')
            for line in graph_lines:
                panel5.add_line(line)
            
            # Panel 7: Create history graph (reused across frames)
            if not hasattr(renderer, '_panel7_graph'):
                renderer._panel7_graph = renderer.create_history_graph(30, min_value=0.0, max_value=100.0)
            
            # Update history graph with actual mock data
            renderer._panel7_graph.add_value(mock_data.overall_usage)
            
            # Panel 7: Same setup as panel 1, but with custom RGB colors
            panel7.clear_labels()
            panel7.add_left_label('Usage')
            panel7.add_right_label(f"{mock_data.overall_usage:.1f}%")
            panel7.add_right_label('Panel 7')
            
            panel7.clear()
            max_color_p7 = renderer._panel7_graph.get_max_value_color(renderer)
            
            # Custom RGB gradient: cyan -> magenta -> yellow (using list format)
            panel7_bar = ProgressBar(
                mock_data.overall_usage,
                colors=[(0, 255, 255), (255, 0, 255), (255, 255, 0)],  # Cyan -> Magenta -> Yellow
                truecolor_support=renderer._truecolor_support
            )
            # Also set custom colors on the graph (using RGB tuples directly)
            renderer._panel7_graph.colors = [
                (0, 255, 255),    # Cyan
                (255, 0, 255),    # Magenta
                (255, 255, 0)     # Yellow
            ]
            
            panel7.add_inline(
                InlineText(ANSIColors.BOLD + "Usage:" + ANSIColors.RESET),
                InlineText(f"{max_color_p7}{mock_data.overall_usage:5.1f}%{ANSIColors.RESET}"),
                InlineBar(panel7_bar),
                InlineGraph(renderer._panel7_graph, renderer=renderer, max_size=25),
                renderer=renderer
            )
            panel7.add_line("")
            panel7.add_line(ANSIColors.BOLD + "Load Average:" + ANSIColors.RESET)
            panel7.add_line(f"  1m: {ANSIColors.YELLOW}{mock_data.load_avg[0]:.2f}{ANSIColors.RESET}")
            panel7.add_line(f"  5m: {ANSIColors.YELLOW}{mock_data.load_avg[1]:.2f}{ANSIColors.RESET}")
            panel7.add_line(f"  15m: {ANSIColors.YELLOW}{mock_data.load_avg[2]:.2f}{ANSIColors.RESET}")
            
            # Render all panels in order
            # Render all panels (sorted by z-order)
            renderer.render_all_panels()
            
            sys.stdout.flush()
            
            # Wait for next frame
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        pass
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
