#!/usr/bin/env python3
"""
Build script for PTop.

This script uses PyInstaller to create a standalone binary executable.
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

def main():
    """Build the PTop binary using PyInstaller."""
    
    # Get the project root directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller is not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Clean previous builds
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"
    spec_file = project_root / "ptop.spec"
    
    if build_dir.exists():
        print("Cleaning previous build directory...")
        shutil.rmtree(build_dir)
    
    if dist_dir.exists():
        print("Cleaning previous dist directory...")
        shutil.rmtree(dist_dir)
    
    if spec_file.exists():
        spec_file.unlink()
    
    # Build the executable
    print("Building PTop executable...")
    
    # PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=ptop",
        "--onefile",  # Single file executable
        "--console",  # Console application (not windowed)
        "--clean",
        "--noconfirm",
        # Entry point
        str(project_root / "ptop" / "main.py"),
    ]
    
    # Add hidden imports if needed (PyInstaller might miss some)
    hidden_imports = [
        "psutil",
        "cpuinfo",
        "pynvml",
    ]
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # Run PyInstaller
    try:
        subprocess.check_call(cmd)
        print(f"\n✓ Build successful!")
        print(f"  Binary location: {dist_dir / 'ptop'}")
        if sys.platform == "win32":
            print(f"  (On Windows: {dist_dir / 'ptop.exe'})")
        print(f"\nYou can run it with:")
        if sys.platform == "win32":
            print(f"  {dist_dir / 'ptop.exe'} --interval 1.0")
        else:
            print(f"  {dist_dir / 'ptop'} --interval 1.0")
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

