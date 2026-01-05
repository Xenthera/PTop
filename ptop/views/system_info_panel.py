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

from typing import Dict, Any, Optional, List, Tuple
from ..ui.ansi_renderer import ANSIRendererBase
from ..ui.colors import ANSIColors, get_gradient_color
from ..ui.utils import visible_length


class SystemInfoPanel:
    """
    Controller for the system information panel.
    
    This panel displays system information in a fastfetch-style format.
    Most fields are static (OS, kernel, CPU, GPU, etc.) but some update live
    (uptime, memory, disks, battery, process count) at a 2-second interval.
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
        self._battery_model_name: Optional[str] = None  # Cache battery model name (static)
        
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
    
    def _format_time_remaining(self, seconds: Optional[float]) -> Optional[str]:
        """
        Format battery time remaining in seconds to human-readable string.
        
        Args:
            seconds: Time remaining in seconds (None if unknown/calculating)
            
        Returns:
            Formatted string (e.g., "6 hours, 22 mins remaining") or None if unknown
        """
        if seconds is None or seconds < 0:
            return None
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 or not parts:
            parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
        
        return ", ".join(parts) + " remaining"
    
    def _get_battery_model_name(self) -> Optional[str]:
        """
        Get battery model name (macOS-specific using system_profiler).
        
        Returns:
            Battery model name (e.g., "bq40z651") or None if not available
        """
        try:
            import platform
            if platform.system() != 'Darwin':
                return None
            
            import subprocess
            import re
            
            result = subprocess.run(
                ['system_profiler', 'SPPowerDataType'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                # Look for "Device Name:" line in the output
                for line in result.stdout.split('\n'):
                    if 'Device Name:' in line:
                        # Extract model name (format: "          Device Name: bq40z651")
                        match = re.search(r'Device Name:\s*(.+)', line)
                        if match:
                            model_name = match.group(1).strip()
                            return model_name if model_name else None
        except Exception:
            pass
        
        return None
    
    def _render_content(self, data: Dict[str, Any], memory_used: int = 0, memory_total: int = 0, uptime: Optional[float] = None, process_count: int = 0, battery_percent: Optional[float] = None, battery_power_plugged: Optional[bool] = None, battery_secsleft: Optional[float] = None) -> None:
        """
        Render panel content from system info data.
        
        Args:
            data: System information dictionary from collector
            memory_used: Current memory used in bytes (for live updates)
            memory_total: Total memory in bytes (for live updates)
            uptime: Current system uptime in seconds (for live updates)
            process_count: Current number of running processes (for live updates)
            battery_percent: Battery percentage if available (for live updates)
            battery_power_plugged: True if AC power is connected, False if on battery, None if no battery (for live updates)
            battery_secsleft: Battery time remaining in seconds if available (for live updates)
        """
        self.panel.clear()
        
        # Extract OS and host info from new structured schema
        os_info = data.get('os', {})
        host_info = data.get('host', {})
        
        os_name = os_info.get('name', 'Unknown')
        os_version = os_info.get('version')
        os_codename = os_info.get('codename')
        os_arch = os_info.get('arch', 'Unknown')
        
        host_model = host_info.get('model')
        host_details = host_info.get('details')
        
        kernel = data.get('kernel', 'Unknown')
        hostname = data.get('hostname', 'unknown')
        cpu = data.get('cpu', 'Unknown')
        gpu = data.get('gpu')
        shell = data.get('shell')
        de_wm = data.get('de_wm')
        terminal = data.get('terminal')
        packages = data.get('packages')
        resolution = data.get('resolution')
        local_ip = data.get('local_ip')
        display_server = data.get('display_server')
        disks = data.get('disks', [])
        
        # Format lines in fastfetch style: Label: Value
        # Use color for labels, white for values
        label_color = ANSIColors.BRIGHT_BLUE
        value_color = ANSIColors.BRIGHT_WHITE
        reset = ANSIColors.RESET
        
        # Collect all label-value pairs first
        label_value_pairs: List[Tuple[str, str]] = []
        
        # OS display: format as "macOS Sequoia 15.6.1 (arm64)" or "Linux Ubuntu 22.04 (x86_64)"
        os_parts = [os_name]
        if os_codename:
            os_parts.append(os_codename)
        if os_version:
            os_parts.append(os_version)
        os_display = ' '.join(os_parts)
        if os_arch:
            os_display += f" ({os_arch})"
        label_value_pairs.append(("OS", f"{value_color}{os_display}{reset}"))
        
        # Host display: format as "MacBook Pro" or "ThinkPad X1 Carbon" (with details if available)
        if host_model:
            host_display_parts = [host_model]
            if host_details:
                host_display_parts.append(host_details)
            host_display = ' — '.join(host_display_parts) if host_details else host_model
            label_value_pairs.append(("Host", f"{value_color}{host_display}{reset}"))
        
        # Kernel
        label_value_pairs.append(("Kernel", f"{value_color}{kernel}{reset}"))
        
        # Uptime
        uptime_str = self._format_uptime(uptime)
        label_value_pairs.append(("Uptime", f"{value_color}{uptime_str}{reset}"))
        
        # CPU
        label_value_pairs.append(("CPU", f"{value_color}{cpu}{reset}"))
        
        # GPU (if available)
        if gpu:
            label_value_pairs.append(("GPU", f"{value_color}{gpu}{reset}"))
        
        # Hostname
        label_value_pairs.append(("Host", f"{value_color}{hostname}{reset}"))
        
        # Memory (used/total, updates live) - formatted as x/x (unit) with CPU gradient color on percentage
        if memory_total > 0:
            memory_percent = (memory_used / memory_total * 100.0)
            # Format used and total in appropriate units (decimals for GiB, integers for smaller)
            for unit, suffix in [(1024**3, "GiB"), (1024**2, "MiB"), (1024, "KiB")]:
                if memory_total >= unit:
                    used_value = memory_used / unit
                    total_value = memory_total / unit
                    # Use one decimal for GiB, integers for MiB and smaller
                    if suffix == "GiB":
                        used_str = f"{used_value:.1f}/{total_value:.1f}"
                    else:
                        used_str = f"{int(round(used_value))}/{int(round(total_value))}"
                    # Apply CPU gradient color only to the percentage
                    cpu_colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
                    color_code = get_gradient_color(cpu_colors, memory_percent, self.renderer._truecolor_support)
                    colored_percent = f"{color_code}{memory_percent:.0f}%{ANSIColors.RESET}"
                    memory_str = f"{used_str} ({colored_percent}) ({suffix})"
                    break
            else:
                memory_str = f"{memory_used}/{memory_total} ({memory_percent:.0f}%) (B)"
            label_value_pairs.append(("Memory", memory_str))
        
        # Shell (if available)
        if shell:
            label_value_pairs.append(("Shell", f"{value_color}{shell}{reset}"))
        
        # Desktop environment / Window manager (if available)
        if de_wm:
            label_value_pairs.append(("DE/WM", f"{value_color}{de_wm}{reset}"))
        
        # Terminal (if available)
        if terminal:
            label_value_pairs.append(("Terminal", f"{value_color}{terminal}{reset}"))
        
        # Package count (if available)
        if packages is not None:
            label_value_pairs.append(("Packages", f"{value_color}{packages}{reset}"))
        
        # Disk usage for all mounted volumes (updates live) - formatted like fastfetch
        if disks:
            for disk_info in disks:
                mountpoint = disk_info.get('mountpoint', '')
                fstype = disk_info.get('fstype', '')
                used = disk_info.get('used', 0)
                total = disk_info.get('total', 0)
                attributes = disk_info.get('attributes', [])
                
                if total > 0:
                    percent = (used / total * 100.0) if total > 0 else 0.0
                    
                    # Format used and total in appropriate units (decimals for GiB, integers for smaller)
                    for unit, suffix in [(1024**3, "GiB"), (1024**2, "MiB"), (1024, "KiB")]:
                        if total >= unit:
                            used_value = used / unit
                            total_value = total / unit
                            # Use one decimal for GiB, integers for MiB and smaller
                            if suffix == "GiB":
                                used_str = f"{used_value:.1f} {suffix}"
                                total_str = f"{total_value:.1f} {suffix}"
                            else:
                                used_str = f"{int(round(used_value))} {suffix}"
                                total_str = f"{int(round(total_value))} {suffix}"
                            break
                    else:
                        used_str = f"{used} B"
                        total_str = f"{total} B"
                    
                    # Apply CPU gradient color only to the percentage number and % sign
                    cpu_colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
                    color_code = get_gradient_color(cpu_colors, percent, self.renderer._truecolor_support)
                    colored_percent = f"{color_code}{percent:.0f}%{ANSIColors.RESET}"
                    
                    # Format: "Disk (mountpoint): used / total (percent) - fstype [attributes]"
                    usage_str = f"{used_str} / {total_str} ({colored_percent})"
                    attr_str = ', '.join(attributes) if attributes else ''
                    if attr_str:
                        disk_value = f"{usage_str} - {value_color}{fstype}{reset} [{attr_str}]"
                    else:
                        disk_value = f"{usage_str} - {value_color}{fstype}{reset}"
                    label_value_pairs.append((f"Disk ({mountpoint})", disk_value))
        
        # Display (if available) - fastfetch-style format includes name, resolution, scale, size, refresh rate
        if resolution:
            # Resolution now contains the full fastfetch-style format, so we just display it
            label_value_pairs.append(("Display", f"{value_color}{resolution}{reset}"))
        
        # Local IP (if available)
        if local_ip:
            label_value_pairs.append(("Local IP", f"{value_color}{local_ip}{reset}"))
        
        # Display server (if available, Linux)
        if display_server:
            label_value_pairs.append(("Display", f"{value_color}{display_server}{reset}"))
        
        # Process count (updates live)
        if process_count > 0:
            label_value_pairs.append(("Processes", f"{value_color}{process_count}{reset}"))
        
        # Battery (if available, updates live) - format: "Battery (model): percent (time remaining) [Status]"
        if battery_percent is not None:
            # Get battery model name (cached, only retrieved once)
            if self._battery_model_name is None:
                self._battery_model_name = self._get_battery_model_name()
            battery_model = self._battery_model_name
            
            # Format battery label: "Battery (model)" or just "Battery"
            battery_label = f"Battery ({battery_model})" if battery_model else "Battery"
            
            # Percentage uses gradient color based on battery level
            cpu_colors = [ANSIColors.BRIGHT_GREEN, ANSIColors.BRIGHT_YELLOW, ANSIColors.BRIGHT_RED]
            percent_color_code = get_gradient_color(cpu_colors, battery_percent, self.renderer._truecolor_support)
            percent_str = f"{battery_percent:.0f}%"
            
            # Format time remaining
            time_remaining_str = None
            if battery_secsleft is not None:
                time_remaining_str = self._format_time_remaining(battery_secsleft)
            
            # Build the full battery string: "percent (time remaining) [Status]"
            battery_parts = [f"{percent_color_code}{percent_str}{ANSIColors.RESET}"]
            
            if time_remaining_str:
                battery_parts.append(f"({time_remaining_str})")
            
            # Add status
            if battery_power_plugged is not None:
                if battery_power_plugged:
                    status_word = "Charging"
                    status_color = ANSIColors.BRIGHT_GREEN
                else:
                    status_word = "Discharging"
                    status_color = ANSIColors.BRIGHT_RED
                battery_parts.append(f"{value_color}[{status_color}{status_word}{value_color}]{ANSIColors.RESET}")
            
            battery_str = " ".join(battery_parts)
            
            label_value_pairs.append((battery_label, battery_str))
        
        # Find the longest label (without ANSI codes)
        max_label_len = max(visible_length(label) for label, _ in label_value_pairs) if label_value_pairs else 0
        
        # Format all lines with aligned values
        lines = []
        for label, value in label_value_pairs:
            # Pad label to max length
            label_len = visible_length(label)
            padded_label = label + ' ' * (max_label_len - label_len)
            # Format: "Label : Value"
            line = f"{label_color}{padded_label}{reset}: {value}"
            lines.append(line)
        
        # Add all lines to panel
        for line in lines:
            self.panel.add_line(line)
    
    def update(self, metrics: Dict[str, Any], force: bool = False) -> None:
        """
        Update the system information panel with current metrics.
        
        Args:
            metrics: Dictionary of metrics from collectors
            force: Unused (kept for API compatibility)
        """
        system_info_data = metrics.get('system_info', {})
        
        # Get all live values from system_info (updated at 2s interval)
        memory_used = system_info_data.get('memory_used', 0)
        memory_total = system_info_data.get('memory_total', 0)
        uptime = system_info_data.get('uptime')
        process_count = system_info_data.get('process_count', 0)
        
        # Get battery data from system_info
        battery_data = system_info_data.get('battery')
        battery_percent = battery_data.get('percent') if battery_data else None
        battery_power_plugged = battery_data.get('power_plugged') if battery_data else None
        battery_secsleft = battery_data.get('secsleft') if battery_data else None
        
        # Render content
        self._render_content(
            system_info_data,
            memory_used=memory_used,
            memory_total=memory_total,
            uptime=uptime,
            process_count=process_count,
            battery_percent=battery_percent,
            battery_power_plugged=battery_power_plugged,
            battery_secsleft=battery_secsleft
        )
