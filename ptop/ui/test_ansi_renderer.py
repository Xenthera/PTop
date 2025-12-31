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

from ptop.ui.ansi_renderer import ANSIRendererBase, ANSIColors, HLayout, VLayout, BaseLayout
from ptop.ui.history_graph import HistoryGraph


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
        panel5 = renderer.create_panel('panel5', 1, 1, 80, 20, 'Gradient Test', rounded=True, border_color=border_colors[4])
        panel6 = renderer.create_panel('panel6', 1, 1, 80, 20, 'Gradient Test', rounded=True, border_color=border_colors[5])
        panel7 = renderer.create_panel('panel7', 1, 1, 80, 20, 'Gradient Test', rounded=True, border_color=border_colors[6])
        
        # Create history graphs for CPU usage and temperature
        usage_graph = renderer.create_history_graph(30, min_value=0.0, max_value=100.0)
        temp_graph = renderer.create_history_graph(30, min_value=30.0, max_value=90.0)
        
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
        
        # Bottom row: 3 gradient test panels horizontally
        bottom_layout = HLayout(margin=0, spacing=1)
        bottom_layout.add_panel(panel5)
        bottom_layout.add_panel(panel6)
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
        
        # Initial layout update
        update_all_layouts()
        
        frame_count = 0
        last_terminal_size = renderer.get_terminal_size()
        
        # Sine wave parameters for testing
        sine_time = 0.0
        sine_speed = 0.05  # Controls how fast the sine wave progresses
        
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
            
            # Panel 1: CPU Usage - Example with labels
            # Clear labels and set up new ones each frame (to show dynamic updates)
            panel1.clear_labels()
            panel1.add_left_label('Usage')  # Additional left label after title
            panel1.add_right_label(f"{mock_data.overall_usage:.1f}%")  # Right label with value
            panel1.add_right_label('Active')  # Another right label
            
            # Generate sine wave values for history graphs (for testing)
            # Sine wave goes from min to max smoothly
            # Usage: 0-100% (full range)
            usage_sine = 50.0 + 50.0 * math.sin(sine_time)  # Range: 0-100
            # Temperature: 30-90°C (full range)
            temp_sine = 60.0 + 30.0 * math.sin(sine_time)  # Range: 30-90
            
            # Update history graphs with sine wave values
            usage_graph.add_value(usage_sine)
            temp_graph.add_value(temp_sine)
            
            # Increment sine wave time
            sine_time += sine_speed
            if sine_time >= 2 * math.pi:
                sine_time -= 2 * math.pi  # Keep in [0, 2π] range
            
            panel1.clear()
            panel1.add_line(ANSIColors.BOLD + "Overall Usage:" + ANSIColors.RESET)
            # Use the max value color from the history graph to colorize the percentage
            # This ensures the percentage perfectly matches the RGB of the max graph value
            max_color = usage_graph.get_max_value_color(renderer)
            panel1.add_line(f"  {max_color}{mock_data.overall_usage:5.1f}%{ANSIColors.RESET}")
            bar1 = renderer.draw_status_bar(mock_data.overall_usage, 32)
            panel1.add_line("  " + bar1)
            panel1.add_line("")
            panel1.add_line(ANSIColors.BOLD + "History:" + ANSIColors.RESET)
            graph_str = usage_graph.get_graph_string(renderer)
            panel1.add_line("  " + graph_str)
            panel1.add_line("")
            panel1.add_line(ANSIColors.BOLD + "Load Average:" + ANSIColors.RESET)
            panel1.add_line(f"  1m: {ANSIColors.YELLOW}{mock_data.load_avg[0]:.2f}{ANSIColors.RESET}")
            panel1.add_line(f"  5m: {ANSIColors.YELLOW}{mock_data.load_avg[1]:.2f}{ANSIColors.RESET}")
            panel1.add_line(f"  15m: {ANSIColors.YELLOW}{mock_data.load_avg[2]:.2f}{ANSIColors.RESET}")
            
            # Panel 2: CPU Cores - Example with multiple left labels
            panel2.clear_labels()
            panel2.add_left_label(f"{len(mock_data.per_core)} Cores")  # Additional left label
            panel2.add_right_label('Per-Core')  # Right label
            
            panel2.clear()
            panel2.add_line(ANSIColors.BOLD + "Per Core Usage:" + ANSIColors.RESET)
            for i, core_usage in enumerate(mock_data.per_core[:6]):  # Show first 6 cores
                core_color = get_usage_color(core_usage)
                bar = renderer.draw_status_bar(core_usage, 20)
                panel2.add_line(f"  Core {i}: {core_color}{core_usage:5.1f}%{ANSIColors.RESET} {bar}")
            
            # Panel 3: System Info - Example with temperature and power in labels
            panel3.clear_labels()
            panel3.add_left_label('System')  # Additional left label
            temp_color = get_temp_color(mock_data.temperature)
            panel3.add_right_label(f"{ANSIColors.RESET}{mock_data.temperature:.1f}°C")  # Right label with color
            panel3.add_right_label(f"{mock_data.power:.1f}W")  # Another right label
            
            panel3.clear()
            panel3.add_line(ANSIColors.BOLD + "Temperature:" + ANSIColors.RESET)
            temp_color = get_temp_color(temp_sine)
            panel3.add_line(f"  CPU: {temp_color}{temp_sine:.1f}°C{ANSIColors.RESET}")
            panel3.add_line("")
            panel3.add_line(ANSIColors.BOLD + "History:" + ANSIColors.RESET)
            temp_graph_str = temp_graph.get_graph_string(renderer)
            panel3.add_line("  " + temp_graph_str)
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
            
            # Panel 5, 6, 7: Static gradient bars (3 identical panels in a row)
            # Panel 5: Example with labels showing test info
            panel5.clear_labels()
            panel5.add_left_label('Test')
            panel5.add_right_label('Static')
            panel5.add_right_label('Gradient')
            populate_gradient_panel(panel5)
            
            # Panel 6: Example with only right labels
            panel6.clear_labels()
            panel6.add_right_label('RGB')
            panel6.add_right_label('Truecolor')
            populate_gradient_panel(panel6)
            
            # Panel 7: Example with multiple left labels
            panel7.clear_labels()
            panel7.add_left_label('Demo')
            panel7.add_left_label('Smooth')
            panel7.add_right_label('24-bit')
            populate_gradient_panel(panel7)
            
            # Render all panels in order
            renderer.render_panel(panel1)
            renderer.render_panel(panel2)
            renderer.render_panel(panel3)
            renderer.render_panel(panel4)
            renderer.render_panel(panel5)
            renderer.render_panel(panel6)
            renderer.render_panel(panel7)
            
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
