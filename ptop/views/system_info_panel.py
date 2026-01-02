"""
System information panel controller.

This module manages the system information panel which displays system
information in a fastfetch-style format.

NOTE: This panel is mostly static by design - most system information (OS, kernel,
CPU model, hostname) doesn't change during application execution. However, some
fields update live (memory, uptime, disk, processes, battery). The panel updates
its content on:
- First initialization
- Terminal resize (to re-wrap content)
- Explicit force redraw
- Every frame (to update live fields like memory, uptime, disk, processes, battery)

The double-buffering renderer ensures minimal screen writes, only updating changed
lines for efficiency.
"""

from typing import Dict, Any, Optional
from ..ui.ansi_renderer import ANSIRendererBase
from ..ui.colors import ANSIColors, get_gradient_color


class SystemInfoPanel:
    """
    Controller for the system information panel.
    
    This panel displays static system information in a fastfetch-style format:
    - OS name and version
    - Kernel version
    - CPU model
    - Architecture
    - Hostname
    - Total system memory
    - Uptime
    - CPU frequency (if available)
    - GPU (if available)
    - Shell
    - Desktop environment/Window manager (Linux/BSD)
    - Terminal emulator
    - Package count (Linux/BSD, if available)
    
    The panel is static - content is set once and only re-renders on resize
    or explicit force redraw to handle text re-wrapping.
    """
    
    def __init__(self, renderer: ANSIRendererBase, debug: bool = False):
        """
        Initialize the system information panel.
        
        Args:
            renderer: The ANSI renderer instance
            debug: If True, skip battery detection (for mock data testing)
        """
        self.renderer = renderer
        self.debug = debug
        self.panel = None
        self._initialized = False
        self._last_data_hash = None
        
        self._setup_panel()
    
    def _setup_panel(self) -> None:
        """Set up the system information panel structure."""
        # Create main panel
        self.panel = self.renderer.create_panel(
            'system_info',
            title='System',
            rounded=True,
            border_color=ANSIColors.BRIGHT_MAGENTA
        )
    
    def update_layout(self) -> None:
        """Update panel layout bounds (no-op for this simple panel)."""
        # This panel doesn't have nested layouts, so nothing to update
        pass
    
    def _format_memory(self, used_bytes: int, total_bytes: int, apply_color: bool = False) -> str:
        """
        Format memory used/total into human-readable string.
        
        Args:
            used_bytes: Memory used in bytes
            total_bytes: Total memory in bytes
            apply_color: If True, apply CPU gradient color based on percentage
            
        Returns:
            Formatted string (e.g., "8.0/16.0 (GiB)", "512/1024 (MiB)")
        """
        if total_bytes == 0:
            return "Unknown"
        
        # Calculate percentage for color gradient
        percent = (used_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
        
        # Format both used and total in appropriate unit
        for unit, suffix in [(1024**3, "GiB"), (1024**2, "MiB"), (1024, "KiB")]:
            if total_bytes >= unit:
                used_value = used_bytes / unit
                total_value = total_bytes / unit
                formatted = f"{used_value:.1f}/{total_value:.1f} ({suffix})"
                
                # Apply CPU gradient color if requested
                if apply_color:
                    cpu_colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
                    color_code = get_gradient_color(cpu_colors, percent, self.renderer._truecolor_support)
                    return f"{color_code}{formatted}{ANSIColors.RESET}"
                else:
                    return formatted
        
        formatted = f"{used_bytes}/{total_bytes} (B)"
        if apply_color:
            cpu_colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
            color_code = get_gradient_color(cpu_colors, percent, self.renderer._truecolor_support)
            return f"{color_code}{formatted}{ANSIColors.RESET}"
        else:
            return formatted
    
    def _format_uptime(self, seconds: Optional[float]) -> str:
        """
        Format uptime seconds into human-readable string.
        
        Args:
            seconds: Uptime in seconds
            
        Returns:
            Formatted string (e.g., "2d 3h 15m", "5h 30m", "45m")
        """
        if seconds is None or seconds <= 0:
            return "Unknown"
        
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}m")
        
        return " ".join(parts)
    
    def _format_frequency(self, mhz: Optional[float]) -> str:
        """
        Format CPU frequency in MHz to human-readable string.
        
        Args:
            mhz: Frequency in MHz
            
        Returns:
            Formatted string (e.g., "3.4 GHz", "800 MHz")
        """
        if mhz is None or mhz <= 0:
            return "Unknown"
        
        if mhz >= 1000:
            ghz = mhz / 1000.0
            return f"{ghz:.2f} GHz"
        else:
            return f"{int(mhz)} MHz"
    
    def _render_content(self, data: Dict[str, Any], cpu_name: Optional[str] = None, memory_used: int = 0, memory_total: int = 0, uptime: Optional[float] = None, disk_used: int = 0, disk_total: int = 0, process_count: int = 0, battery_percent: Optional[float] = None, battery_power_plugged: Optional[bool] = None) -> None:
        """
        Render panel content from system info data.
        
        Args:
            data: System information dictionary from collector
            cpu_name: CPU name from CPU collector (optional, overrides data['cpu'])
            memory_used: Current memory used in bytes (for live updates)
            memory_total: Total memory in bytes (for live updates)
            uptime: Current system uptime in seconds (for live updates)
            disk_used: Current disk used in bytes (for live updates)
            disk_total: Total disk space in bytes (for live updates)
            process_count: Current number of running processes (for live updates)
            battery_percent: Battery percentage if available (for live updates)
            battery_power_plugged: True if AC power is connected, False if on battery, None if no battery (for live updates)
        """
        self.panel.clear()
        
        os_name = data.get('os_name', 'Unknown')
        os_version = data.get('os_version', 'Unknown')
        kernel = data.get('kernel', 'Unknown')
        arch = data.get('arch', 'Unknown')
        hostname = data.get('hostname', 'unknown')
        # Use CPU name from CPU collector if provided, otherwise fall back to system_info
        cpu = cpu_name if cpu_name else data.get('cpu', 'Unknown')
        # Use provided uptime (live) or fall back to cached data if not provided
        if uptime is None:
            uptime = data.get('uptime')
        cpu_freq = data.get('cpu_freq')
        gpu = data.get('gpu')
        shell = data.get('shell')
        de_wm = data.get('de_wm')
        terminal = data.get('terminal')
        packages = data.get('packages')
        resolution = data.get('resolution')
        local_ip = data.get('local_ip')
        display_server = data.get('display_server')
        machine_model = data.get('machine_model')
        
        # Format lines in fastfetch style: Label: Value
        # Use color for labels, white for values
        label_color = ANSIColors.BRIGHT_BLUE
        value_color = ANSIColors.BRIGHT_WHITE
        reset = ANSIColors.RESET
        
        lines = []
        
        # OS and version
        os_line = f"{label_color}OS{reset}: {value_color}{os_name} {os_version}{reset}"
        lines.append(os_line)
        
        # Kernel
        kernel_line = f"{label_color}Kernel{reset}: {value_color}{kernel}{reset}"
        lines.append(kernel_line)
        
        # Uptime
        uptime_str = self._format_uptime(uptime)
        uptime_line = f"{label_color}Uptime{reset}: {value_color}{uptime_str}{reset}"
        lines.append(uptime_line)
        
        # CPU
        cpu_line = f"{label_color}CPU{reset}: {value_color}{cpu}{reset}"
        lines.append(cpu_line)
        
        # CPU frequency (if available)
        if cpu_freq is not None:
            freq_str = self._format_frequency(cpu_freq)
            freq_line = f"{label_color}CPU Freq{reset}: {value_color}{freq_str}{reset}"
            lines.append(freq_line)
        
        # Architecture
        arch_line = f"{label_color}Arch{reset}: {value_color}{arch}{reset}"
        lines.append(arch_line)
        
        # GPU (if available)
        if gpu:
            gpu_line = f"{label_color}GPU{reset}: {value_color}{gpu}{reset}"
            lines.append(gpu_line)
        
        # Hostname
        hostname_line = f"{label_color}Host{reset}: {value_color}{hostname}{reset}"
        lines.append(hostname_line)
        
        # Memory (used/total, updates live) - formatted as x/x (unit) with CPU gradient color
        memory_str = self._format_memory(memory_used, memory_total, apply_color=True)
        memory_line = f"{label_color}Memory{reset}: {memory_str}"
        lines.append(memory_line)
        
        # Shell (if available)
        if shell:
            shell_line = f"{label_color}Shell{reset}: {value_color}{shell}{reset}"
            lines.append(shell_line)
        
        # Desktop environment / Window manager (if available)
        if de_wm:
            de_wm_line = f"{label_color}DE/WM{reset}: {value_color}{de_wm}{reset}"
            lines.append(de_wm_line)
        
        # Terminal (if available)
        if terminal:
            terminal_line = f"{label_color}Terminal{reset}: {value_color}{terminal}{reset}"
            lines.append(terminal_line)
        
        # Package count (if available)
        if packages is not None:
            packages_line = f"{label_color}Packages{reset}: {value_color}{packages}{reset}"
            lines.append(packages_line)
        
        # Disk usage (used/total, updates live) - formatted as x/x (unit) with CPU gradient color
        if disk_total > 0:
            disk_str = self._format_memory(disk_used, disk_total, apply_color=True)
            disk_line = f"{label_color}Disk{reset}: {disk_str}"
            lines.append(disk_line)
        
        # Resolution (if available)
        if resolution:
            resolution_line = f"{label_color}Resolution{reset}: {value_color}{resolution}{reset}"
            lines.append(resolution_line)
        
        # Local IP (if available)
        if local_ip:
            ip_line = f"{label_color}Local IP{reset}: {value_color}{local_ip}{reset}"
            lines.append(ip_line)
        
        # Display server (if available, Linux)
        if display_server:
            display_line = f"{label_color}Display{reset}: {value_color}{display_server}{reset}"
            lines.append(display_line)
        
        # Machine model (if available)
        if machine_model:
            model_line = f"{label_color}Model{reset}: {value_color}{machine_model}{reset}"
            lines.append(model_line)
        
        # Process count (updates live)
        if process_count > 0:
            process_line = f"{label_color}Processes{reset}: {value_color}{process_count}{reset}"
            lines.append(process_line)
        
        # Battery (if available, updates live) - percentage uses gradient, status words are colored in parens
        if battery_percent is not None:
            # Percentage uses gradient color based on battery level
            cpu_colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
            percent_color_code = get_gradient_color(cpu_colors, battery_percent, self.renderer._truecolor_support)
            percent_str = f"{battery_percent:.0f}%"
            
            # Build the full battery string with separate colors for percentage and status
            if battery_power_plugged is not None:
                if battery_power_plugged:
                    status_word = "charging"
                    status_color = ANSIColors.BRIGHT_GREEN
                else:
                    status_word = "draining"
                    status_color = ANSIColors.BRIGHT_RED
                # Parentheses are white, status word is colored
                battery_str = f"{percent_color_code}{percent_str}{ANSIColors.RESET} {value_color}({status_color}{status_word}{value_color}){ANSIColors.RESET}"
            else:
                # If power status is unknown, just show percentage with gradient
                battery_str = f"{percent_color_code}{percent_str}{ANSIColors.RESET}"
            
            battery_line = f"{label_color}Battery{reset}: {battery_str}"
            lines.append(battery_line)
        
        # Add all lines to panel
        for line in lines:
            self.panel.add_line(line)
    
    def update(self, metrics: Dict[str, Any], force: bool = False) -> None:
        """
        Update the system information panel with current metrics.
        
        Args:
            metrics: Dictionary of metrics from collectors
            force: If True, force update even if already initialized
            
        Note: This panel is mostly static, but memory, uptime, disk, processes, and battery update live.
        Most system information doesn't change during application execution,
        but these live metrics do, so we always re-render to show current values.
        """
        system_info_data = metrics.get('system_info', {})
        cpu_data = metrics.get('cpu', {})
        
        if not system_info_data:
            # No data available yet, skip
            return
        
        # Get CPU name from CPU collector (uses proper detection logic)
        cpu_name = cpu_data.get('name_simple') or cpu_data.get('name')
        
        # Get current memory usage (live data)
        uptime_seconds = None
        try:
            import psutil
            import time
            mem = psutil.virtual_memory()
            memory_used = mem.used
            memory_total = mem.total
            
            # Get system uptime (live data)
            try:
                boot_time = psutil.boot_time()
                uptime_seconds = time.time() - boot_time
            except Exception:
                uptime_seconds = None
            
            # Get disk usage (live data) - use root filesystem
            # On macOS with APFS, disk.used may exclude purgeable space,
            # so calculate actual used as total - free for accurate display
            try:
                disk = psutil.disk_usage('/')
                disk_total = disk.total
                # Calculate actual used space (total - free) to account for APFS purgeable space
                disk_used = disk.total - disk.free
            except Exception:
                disk_used = 0
                disk_total = 0
            
            # Get process count (live data)
            try:
                process_count = len(psutil.pids())
            except Exception:
                process_count = 0
            
            # Get battery status (live data, if available)
            # Skip battery detection in debug mode to test "no battery" scenario
            battery_percent = None
            battery_power_plugged = None
            if not self.debug:
                try:
                    battery = psutil.sensors_battery()
                    if battery is not None:
                        battery_percent = battery.percent
                        battery_power_plugged = battery.power_plugged
                except (AttributeError, Exception):
                    # psutil.sensors_battery() might not be available on all systems
                    battery_percent = None
                    battery_power_plugged = None
        except Exception:
            # Fallback to static data if psutil fails
            memory_used = 0
            memory_total = system_info_data.get('memory_total', 0)
            uptime_seconds = system_info_data.get('uptime')  # Fall back to cached uptime
            disk_used = 0
            disk_total = 0
            process_count = 0
            battery_percent = None
            battery_power_plugged = None
        
        # Always update since we have live data (memory, uptime, disk, processes, battery)
        # The double-buffering renderer will efficiently only update changed lines
        # We still track static data hash for potential future optimizations
        static_data = {k: v for k, v in system_info_data.items() if k not in ['memory_total', 'uptime']}
        static_data['cpu_name'] = cpu_name  # Include CPU name in hash
        data_hash = hash(tuple(sorted(static_data.items())))
        
        # Always render to update live fields (memory, uptime, disk, processes, battery)
        # The renderer's diffing will handle efficient screen updates
        self._render_content(
            system_info_data, 
            cpu_name=cpu_name, 
            memory_used=memory_used, 
            memory_total=memory_total,
            uptime=uptime_seconds,
            disk_used=disk_used,
            disk_total=disk_total,
            process_count=process_count,
            battery_percent=battery_percent,
            battery_power_plugged=battery_power_plugged
        )
        self._initialized = True
        self._last_data_hash = data_hash

