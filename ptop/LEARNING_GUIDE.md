# Learning Guide - Understanding the Architecture

## What We've Built

You now have a working prototype of a modular system monitor. Let's break down what each piece does and why it's designed this way.

## Key Concepts

### 1. Separation of Concerns

Each module has ONE clear responsibility:

- **Collectors**: Only gather data (don't care about display)
- **Renderer**: Only displays data (doesn't know how it was collected)
- **Core App**: Only orchestrates (doesn't know collector/renderer internals)

**Why?** This makes the code:
- Easy to test (test each part independently)
- Easy to modify (change one part without breaking others)
- Easy to extend (add new collectors without touching renderer)

### 2. Interface-Based Design

Notice that:
- All collectors have `collect()` and `get_name()` methods
- All renderers inherit from `BaseRenderer` with `setup()`, `render()`, `clear()`, `cleanup()`

**Why?** This allows:
- Swapping implementations (text renderer → ANSI renderer)
- Adding new collectors without changing core app
- Writing tests with mock objects

### 3. Dependency Flow

```
main.py
  └─> PTopApp (core/app.py)
        ├─> Creates Collectors (collectors/cpu.py)
        └─> Creates Renderer (ui/renderer.py)
              └─> Uses Collectors' data
```

**Key Point**: Dependencies flow DOWN, not up:
- Core app knows about collectors and renderer
- Collectors don't know about core app or renderer
- Renderer doesn't know about collectors (only receives data)

## Code Walkthrough

### CPU Collector (`collectors/cpu.py`)

```python
class CPUCollector(BaseCollector):
    def collect(self) -> Dict[str, Any]:
        # Uses psutil to get CPU data
        # Returns a dictionary with comprehensive metrics
        # Doesn't know or care how this data will be displayed
    
    def get_cpu_name(self) -> str:
        # Returns CPU model name
    
    def get_frequencies(self) -> List[float]:
        # Returns per-core clock speeds
    
    def get_usage(self) -> Tuple[float, List[float]]:
        # Returns overall and per-core usage
```

**What to notice:**
- Inherits from `BaseCollector` (abstract interface)
- Simple, focused class with clear methods
- Returns structured data (dict) with all metrics
- No UI code, no dependencies on other modules
- Individual getter methods for specific metrics
- Graceful error handling for unavailable metrics (temperature, power)

### Text Renderer (`ui/renderer.py`)

```python
class TextRenderer(BaseRenderer):
    def render(self, data: Dict[str, Any]):
        # Receives data dictionary
        # Formats and prints it
        # Doesn't know where data came from
```

**What to notice:**
- Inherits from `BaseRenderer` (abstract interface)
- Receives data, doesn't collect it
- Could be swapped with `ANSIRenderer` without changing anything else

### Core App (`core/app.py`)

```python
class PTopApp:
    def __init__(self):
        # Creates collectors
        # Creates renderer
        # Sets up signal handlers
    
    def run(self):
        # Main loop:
        # 1. Collect from all collectors
        # 2. Pass data to renderer
        # 3. Wait, repeat
```

**What to notice:**
- Orchestrates everything
- Doesn't know collector/renderer internals
- Easy to add new collectors (just append to list)

## How to Extend

### Enhancing a Collector

We enhanced the CPU collector to gather more metrics (name, frequencies, load average, temperature, power). Notice how:

1. **The collector interface stayed the same**: Still implements `collect()` and `get_name()`
2. **Added individual methods**: `get_cpu_name()`, `get_frequencies()`, etc. for specific metrics
3. **Updated `collect()` method**: Now returns more data, but backward compatible
4. **Updated the renderer**: Display logic updated to show new metrics, but old code still works

**Key Learning**: You can enhance collectors without breaking existing code, as long as you:
- Keep the interface consistent
- Use `.get()` in renderers for optional fields
- Handle missing data gracefully (return `None` or empty lists)

### Adding a Memory Collector

1. **Create** `collectors/memory.py`:
   ```python
   class MemoryCollector(BaseCollector):
       def collect(self):
           mem = psutil.virtual_memory()
           return {'percent': mem.percent, ...}
       def get_name(self):
           return "memory"
   ```

2. **Register** in `core/app.py`:
   ```python
   from ..collectors.memory import MemoryCollector
   self.collectors.append(MemoryCollector())
   ```

3. **Display** in `ui/renderer.py`:
   ```python
   if 'memory' in data:
       self._render_memory(data['memory'])
   ```

**Notice**: Each step is independent. You can test the collector alone, add it to the app, then update the display.

## Design Patterns Used

1. **Strategy Pattern**: Renderer can be swapped (TextRenderer → ANSIRenderer)
2. **Observer Pattern**: Core app observes collectors and notifies renderer
3. **Factory Pattern**: Core app creates collector/renderer instances
4. **Interface Segregation**: Small, focused interfaces (collect(), render(), etc.)

## Questions to Think About

1. **Why separate collectors from renderer?**
   - What if you wanted to save metrics to a file instead of displaying?
   - What if you wanted to display the same data in different formats?

2. **Why use abstract base classes?**
   - What happens if someone creates a renderer without `render()` method?
   - How does this help with testing?

3. **Why does core app orchestrate?**
   - What if you wanted different update intervals for different collectors?
   - What if you wanted to collect metrics on-demand instead of continuously?

## Next Learning Steps

1. **Run and observe**: Run the app, watch it work, understand the flow
2. **Modify small things**: Change update interval, modify display format
3. **Add a feature**: Implement memory collector following the pattern
4. **Refactor**: Try improving the code (better formatting, error handling)
5. **Plan ANSI GUI**: Think about how you'd implement the advanced renderer

## Common Pitfalls to Avoid

1. **Don't mix concerns**: Keep collectors pure (no UI code)
2. **Don't create circular dependencies**: Collectors shouldn't import renderer
3. **Don't skip interfaces**: Always define clear contracts between modules
4. **Don't over-engineer**: Start simple, add complexity when needed

## Resources

- Read the code comments - they explain the "why"
- Check `ARCHITECTURE.md` for high-level design
- See `README.md` for usage and examples
- Try `QUICKSTART.md` for hands-on practice

Happy learning! 🎓
