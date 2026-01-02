# Building PTop

This document explains how to build PTop into a standalone binary executable.

## Prerequisites

- Python 3.7+
- pip

## Building

### Quick Build

Simply run the build script:

```bash
python3 build.py
```

Or make it executable and run directly:

```bash
chmod +x build.py
./build.py
```

The build script will:
1. Install PyInstaller if not already installed
2. Clean previous builds
3. Create a single-file executable in the `dist/` directory

### Manual Build

If you prefer to build manually:

```bash
# Install PyInstaller
pip install pyinstaller

# Build the executable
pyinstaller --name=ptop --onefile --console --clean --noconfirm \
    --hidden-import psutil \
    --hidden-import cpuinfo \
    --hidden-import pynvml \
    ptop/main.py
```

## Output

The built binary will be located at:
- **Linux/macOS**: `dist/ptop`
- **Windows**: `dist/ptop.exe`

## Running the Built Binary

```bash
# Linux/macOS
./dist/ptop --interval 1.0

# Windows
dist\ptop.exe --interval 1.0
```

## Build Options

The build script creates a **single-file executable** which:
- Contains all dependencies bundled
- Works on systems without Python installed
- Can be distributed as a single file

## Platform-Specific Notes

### macOS
- The built binary should work on macOS systems
- May need to allow the binary in System Preferences > Security & Privacy

### Linux
- The built binary is platform-specific (built for your current architecture)
- May need to build on each target Linux distribution for best compatibility

### Windows
- Build on Windows to create `ptop.exe`
- The executable will be a console application

## Troubleshooting

### Missing Dependencies
If PyInstaller misses some dependencies, add them to the `--hidden-import` flags in `build.py`.

### Large Binary Size
Single-file executables are larger because they include Python and all dependencies. This is normal.

### Import Errors
If you get import errors when running the binary, add the missing module to the `hidden_imports` list in `build.py`.


