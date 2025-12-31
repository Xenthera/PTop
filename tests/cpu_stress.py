#!/usr/bin/env python3
"""
CPU Stress Test Script

This script performs CPU-intensive calculations to generate CPU load.
Useful for testing CPU monitoring and metrics collection.

Usage:
    python tests/cpu_stress.py [--cores N] [--duration SECONDS]

Options:
    --cores N        Number of CPU cores to stress (default: all cores)
    --duration SEC   Duration to run stress test in seconds (default: run indefinitely)
    --intensity F    Intensity factor (0.0-1.0, default: 1.0 = 100% CPU usage)
"""

import sys
import os
import time
import argparse
import multiprocessing
from typing import Optional

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def cpu_intensive_task(intensity: float = 1.0, duration: Optional[float] = None):
    """
    Perform CPU-intensive calculations.
    
    Args:
        intensity: Intensity factor (0.0-1.0), controls CPU usage percentage
        duration: Duration to run in seconds (None = run indefinitely)
    """
    start_time = time.time()
    iterations = 0
    
    # Adjust calculation count based on intensity
    # Higher intensity = more calculations per loop
    calc_multiplier = max(1, int(intensity * 1000))
    
    try:
        while True:
            # Check if duration limit reached
            if duration is not None and (time.time() - start_time) >= duration:
                break
            
            # CPU-intensive calculation (factorial-like computation)
            for _ in range(calc_multiplier):
                # Perform mathematical operations
                result = 0
                for i in range(1000):
                    result += i * i
                iterations += 1
            
            # If intensity < 1.0, add sleep to reduce CPU usage
            if intensity < 1.0:
                sleep_time = (1.0 - intensity) * 0.1
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        pass
    
    return iterations


def stress_core(core_id: int, intensity: float, duration: Optional[float]):
    """Stress a single CPU core."""
    print(f"Core {core_id}: Starting stress test (intensity={intensity:.1%})", file=sys.stderr)
    iterations = cpu_intensive_task(intensity, duration)
    print(f"Core {core_id}: Completed {iterations} iterations", file=sys.stderr)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='CPU stress test utility for testing system monitors',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--cores',
        type=int,
        default=multiprocessing.cpu_count(),
        help='Number of CPU cores to stress (default: all cores)'
    )
    parser.add_argument(
        '--duration',
        type=float,
        default=None,
        help='Duration to run stress test in seconds (default: run indefinitely)'
    )
    parser.add_argument(
        '--intensity',
        type=float,
        default=1.0,
        help='Intensity factor 0.0-1.0 (default: 1.0 = 100%% CPU usage)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.cores < 1:
        print("Error: --cores must be at least 1", file=sys.stderr)
        sys.exit(1)
    
    if args.cores > multiprocessing.cpu_count():
        print(f"Warning: Requested {args.cores} cores, but only {multiprocessing.cpu_count()} available", file=sys.stderr)
        args.cores = multiprocessing.cpu_count()
    
    if args.intensity < 0.0 or args.intensity > 1.0:
        print("Error: --intensity must be between 0.0 and 1.0", file=sys.stderr)
        sys.exit(1)
    
    if args.duration is not None and args.duration <= 0:
        print("Error: --duration must be positive", file=sys.stderr)
        sys.exit(1)
    
    # Print configuration
    print(f"CPU Stress Test", file=sys.stderr)
    print(f"  Cores: {args.cores}/{multiprocessing.cpu_count()}", file=sys.stderr)
    print(f"  Intensity: {args.intensity:.1%}", file=sys.stderr)
    if args.duration:
        print(f"  Duration: {args.duration:.1f} seconds", file=sys.stderr)
    else:
        print(f"  Duration: Indefinite (Ctrl+C to stop)", file=sys.stderr)
    print(f"", file=sys.stderr)
    
    # Start stress processes
    processes = []
    for core_id in range(args.cores):
        process = multiprocessing.Process(
            target=stress_core,
            args=(core_id, args.intensity, args.duration)
        )
        process.start()
        processes.append(process)
    
    # Wait for all processes to complete
    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping stress test...", file=sys.stderr)
        for process in processes:
            process.terminate()
            process.join(timeout=1.0)
            if process.is_alive():
                process.kill()
    
    print("Stress test completed.", file=sys.stderr)


if __name__ == '__main__':
    main()
