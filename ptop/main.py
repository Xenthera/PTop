#!/usr/bin/env python3
"""
PTop - Terminal-based system monitor.

Entry point for the application.
Run this script to start the system monitor.
"""

import sys
import os
import argparse

# Add parent directory to path so we can import from ptop package
# This allows running both as: python -m ptop.main
# and as: python ptop/main.py
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ptop.core.app import PTopApp


def main():
    """
    Main entry point for the application.
    
    Creates and runs the PTopApp instance.
    """
    parser = argparse.ArgumentParser(description='PTop - Terminal system monitor')
    parser.add_argument('--interval', type=float, default=0.05,
                       help='Update interval in seconds (default: 0.05)')
    parser.add_argument('--debug', action='store_true',
                       help='Use mock collectors with random data instead of real hardware')
    parser.add_argument('--profile', action='store_true',
                       help='Enable profiling and save results to profile_stats.prof')
    
    args = parser.parse_args()
    
    if args.profile:
        import cProfile
        import pstats
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            # Create application instance
            app = PTopApp(update_interval=args.interval, debug=args.debug)
            # Run the application
            app.run()
        finally:
            profiler.disable()
            # Save stats to file
            profiler.dump_stats('profile_stats.prof')
            print("\nProfiling data saved to profile_stats.prof")
            print("\nTop 20 functions by cumulative time:")
            print("=" * 80)
            stats = pstats.Stats(profiler)
            stats.sort_stats('cumulative')
            stats.print_stats(20)
            print("\nTo view detailed profile, run:")
            print("  python -m pstats profile_stats.prof")
            print("  # In pstats prompt: sort cumulative | stats 30")
            print("\nOr install snakeviz and run:")
            print("  snakeviz profile_stats.prof")
    else:
        # Create application instance
        app = PTopApp(update_interval=args.interval, debug=args.debug)
        # Run the application
        app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Handle Ctrl+C at top level
        print("\nExiting...")
        sys.exit(0)
