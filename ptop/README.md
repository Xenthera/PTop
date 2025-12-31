# PTop

A terminal-based system monitor in Python, inspired by btop. Built with a modular architecture that supports CPU, memory, network, disk, and process monitoring.

## Features

- **Modular Architecture**: Clean separation between collectors, UI, and core logic
- **Extensible Design**: Easy to add new collectors or swap UI implementations
- **Real-time Updates**: Live system metrics with configurable update intervals
- **CPU Monitoring**: Per-core and overall CPU usage statistics

## Architecture

See [ARCHITECTURE.md](../ARCHITECTURE.md) for detailed architecture documentation.

### Quick Overview

```
ptop/
├── core/
│   └── app.py          # Main controller - orchestrates everything
├── collectors/
│   └── cpu.py          # CPU metrics collector
├── ui/
│   └── renderer.py     # Abstracted UI interface (text-based for now)
└── main.py             # Entry point
```

**Key Design Principles:**
- **Collectors**: Independent modules that gather metrics (don't know about UI)
- **UI Renderer**: Abstracted interface that can be swapped (text → ANSI GUI)
- **Core App**: Orchestrates collectors and renderer, manages main loop
- **Loose Coupling**: Modules interact through well-defined interfaces

## Installation

### Prerequisites

- Python 3.7 or higher
- `psutil` library

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the monitor:
```bash
python -m ptop.main
```

Or make it executable and run directly:
```bash
chmod +x ptop/main.py
python ptop/main.py
```

## Usage

Run the application:
```bash
python -m ptop.main
```

The monitor will:
- Display CPU usage (overall and per-core)
- Update every 1 second
- Clear and refresh the display

Press `Ctrl+C` to exit gracefully.

## Current Implementation

### CPU Collector (`collectors/cpu.py`)

Collects:
- Overall CPU usage percentage
- Per-core CPU usage percentages
- CPU count (logical and physical cores)

Uses `psutil` for cross-platform system metrics.

### Text Renderer (`ui/renderer.py`)

Simple text-based output that:
- Clears screen on startup
- Displays metrics in readable format
- Updates in place (moves cursor up to overwrite)

**Future**: This can be replaced with an ANSI-based renderer for:
- Colored output
- Progress bars
- Precise cursor positioning
- Multi-panel layouts
- Smooth animations

## Extending the System

### Adding a New Collector

1. Create a new file in `collectors/` (e.g., `memory.py`):
```python
import psutil
from typing import Dict, Any

class MemoryCollector:
    def collect(self) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            'total': mem.total,
            'used': mem.used,
            'available': mem.available,
            'percent': mem.percent,
        }
    
    def get_name(self) -> str:
        return "memory"
```

2. Register it in `core/app.py`:
```python
from ..collectors.memory import MemoryCollector

def _init_collectors(self):
    self.collectors.append(CPUCollector())
    self.collectors.append(MemoryCollector())  # Add this
```

3. Update the renderer to display it (in `ui/renderer.py`):
```python
def render(self, data):
    # ... existing code ...
    if 'memory' in data:
        self._render_memory(data['memory'])
```

That's it! No changes needed to other collectors or core app logic.

### Replacing the UI Renderer

1. Create a new renderer class (e.g., `ansi_renderer.py`):
```python
from .renderer import BaseRenderer

class ANSIRenderer(BaseRenderer):
    def setup(self):
        # Enable raw mode, hide cursor, etc.
        pass
    
    def render(self, data):
        # Use ANSI escape sequences for precise control
        pass
    
    def cleanup(self):
        # Reset terminal, show cursor
        pass
```

2. Swap it in `core/app.py`:
```python
from ..ui.ansi_renderer import ANSIRenderer

def __init__(self):
    # ...
    self.renderer = ANSIRenderer()  # Instead of TextRenderer()
```

No changes needed to collectors!

## Next Steps

### Planned Features

1. **More Collectors**:
   - Memory (RAM) usage
   - Disk I/O and usage
   - Network traffic
   - Process list with sorting/filtering

2. **ANSI GUI Layer**:
   - Colored progress bars
   - Multi-panel layout
   - Smooth refresh without flicker
   - Keyboard navigation

3. **Input Handler**:
   - Keyboard shortcuts
   - Process sorting/filtering
   - Configuration changes on the fly

4. **Configuration**:
   - Config file for intervals, colors, layout
   - Theme customization
   - Alert thresholds

## Development Notes

### Module Interactions

1. **Initialization**:
   - `main.py` creates `PTopApp`
   - App creates collectors and renderer
   - Renderer sets up display

2. **Main Loop**:
   - App collects from all collectors
   - App aggregates data
   - App passes data to renderer
   - Renderer displays data
   - Wait for next interval

3. **Shutdown**:
   - Signal handler stops loop
   - Renderer cleans up
   - Exit gracefully

### Testing

Each module can be tested independently:
- Collectors can be tested without UI
- UI can be tested with mock data
- Core app can be tested with mock collectors/renderer

## License

This is a learning project. Feel free to use and modify as needed.

## Contributing

This is a step-by-step learning project. Suggestions and improvements welcome!
