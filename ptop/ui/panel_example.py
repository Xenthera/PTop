#!/usr/bin/env python3
"""
Minimal example demonstrating rounded corners and colored borders for Panel.

This example shows:
- Rounded border panels
- Colored border panels
- Default square corners (backward compatibility)
"""

import sys
import os
import time

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ptop.ui.ansi_renderer import ANSIRendererBase, ANSIColors


def main():
    """Demonstrate rounded and colored panel borders."""
    renderer = ANSIRendererBase()
    renderer.setup()
    
    try:
        # Clear screen
        renderer.clear()
        
        # Render header
        renderer.render_header("Panel Border Examples")
        
        # Example 1: Default square corners (backward compatible)
        panel1 = renderer.create_panel('default', 3, 1, 40, 10, 'Default (Square)')
        panel1.add_line("This panel uses default")
        panel1.add_line("square corners.")
        panel1.add_line("No border color.")
        
        # Example 2: Rounded corners, no color
        panel2 = renderer.create_panel('rounded', 3, 42, 40, 10, 'Rounded Corners', rounded=True)
        panel2.add_line("This panel uses")
        panel2.add_line("rounded corners.")
        panel2.add_line("No border color.")
        
        # Example 3: Square corners with colored border
        panel3 = renderer.create_panel('colored', 14, 1, 40, 10, 'Colored Border', 
                                      border_color=ANSIColors.BRIGHT_CYAN)
        panel3.add_line("This panel has a")
        panel3.add_line("colored border.")
        panel3.add_line("Square corners.")
        
        # Example 4: Rounded corners with colored border
        panel4 = renderer.create_panel('rounded_colored', 14, 42, 40, 10, 'Rounded + Colored',
                                      rounded=True, border_color=ANSIColors.BRIGHT_GREEN)
        panel4.add_line("This panel combines")
        panel4.add_line("rounded corners")
        panel4.add_line("with colored border.")
        
        # Render all panels
        renderer.render_panel(panel1)
        renderer.render_panel(panel2)
        renderer.render_panel(panel3)
        renderer.render_panel(panel4)
        
        sys.stdout.flush()
        
        print("\n\nPress Ctrl+C to exit...")
        time.sleep(5)
        
    except KeyboardInterrupt:
        pass
    finally:
        renderer.cleanup()
        print("\nExample complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
