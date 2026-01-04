"""
System information collector.

This module collects static system information that doesn't change during
application runtime. Data is collected once at startup and cached.

This collector uses Python stdlib, direct filesystem access (/proc, /sys),
subprocess for platform-specific detection, and psutil for cross-platform memory detection.

NOTE: This panel is static by design - system information (OS, kernel, CPU model,
hostname, memory, uptime, etc.) doesn't change during application execution.
This allows us to collect the data once at startup and cache it, avoiding any
I/O overhead in the render loop. The panel only re-renders on terminal resize
or explicit force redraw.
"""

import platform
import os
import socket
import sys
import time
import glob
import subprocess
import shutil
import json
from typing import Dict, Any, Optional, Tuple

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .base import BaseCollector

# Platform-specific sub-collectors
try:
    from .system_info_macos import MacOSSystemInfoCollector
except ImportError:
    MacOSSystemInfoCollector = None

try:
    from .system_info_linux import LinuxSystemInfoCollector
except ImportError:
    LinuxSystemInfoCollector = None

try:
    from .system_info_windows import WindowsSystemInfoCollector
except ImportError:
    WindowsSystemInfoCollector = None


class SystemInfoCollector(BaseCollector):
    """
    Collects static system information.
    
    This collector gathers data once at initialization and caches it.
    Data is read-only after initialization. This design ensures:
    - Fast collection (runs in milliseconds)
    - No blocking I/O in render loop
    - Clean separation of collection from rendering
    
    Collected data structure:
    - os: {name, version, codename, arch} - High-resolution OS metadata
    - host: {model, identifier, details} - High-resolution host/machine metadata
    - kernel: Kernel version
    - hostname: System hostname
    - cpu: CPU model
    - memory_total: Total system memory (bytes)
    - uptime: System uptime (seconds)
    - cpu_freq: CPU frequency (MHz, if available)
    - gpu: GPU name (if available)
    - shell: Default shell
    - de_wm: Desktop environment / Window manager (Linux/BSD)
    - terminal: Terminal emulator
    - packages: Package count with manager name
    - resolution: Display resolution
    - local_ip: Local IP address
    - display_server: Display server (Wayland/X11, Linux)
    """
    
    def __init__(self, live_poll_interval: float = 1.0):
        """
        Initialize the collector and collect all system information.
        
        This runs once at startup and caches all data.
        Live fields (disks, uptime) are re-collected periodically.
        
        Args:
            live_poll_interval: Time in seconds between re-collecting live fields (default: 1.0)
        """
        self._data: Dict[str, Any] = {}
        self._platform_collector = None  # Will be set in _collect_all
        self._live_poll_interval = live_poll_interval
        self._last_live_update = 0.0
        self._collect_all()
    
    def _collect_all(self) -> None:
        """Collect all system information and cache it."""
        import time
        system = platform.system()
        
        # Get platform-specific collector instance
        platform_collector = self._get_platform_collector(system)
        self._platform_collector = platform_collector  # Store for live updates
        
        # Collect OS and host metadata using platform-specific sub-collector
        platform_data = platform_collector.collect() if platform_collector else self._collect_platform_info_fallback(system)
        self._data['os'] = platform_data.get('os', {})
        self._data['host'] = platform_data.get('host', {})
        
        # Kernel version (keep for backward compatibility)
        uname = os.uname()
        kernel_version = uname.release
        # On macOS/Darwin, prepend "darwin " to match fastfetch format
        if system == 'Darwin':
            kernel_version = f"darwin {kernel_version}"
        self._data['kernel'] = kernel_version
        
        # Hostname
        try:
            self._data['hostname'] = socket.gethostname()
        except (OSError, socket.error):
            self._data['hostname'] = 'unknown'
        
        # Use platform collector methods for all platform-specific data
        if platform_collector:
            self._data['cpu'] = platform_collector.get_cpu_model()
            self._data['memory_total'] = platform_collector.get_total_memory()
            self._data['uptime'] = platform_collector.get_uptime()
            self._data['cpu_freq'] = platform_collector.get_cpu_frequency()
            self._data['gpu'] = platform_collector.get_gpu_info()
            self._data['shell'] = platform_collector.get_shell()
            self._data['de_wm'] = platform_collector.get_de_wm()
            self._data['terminal'] = platform_collector.get_terminal()
            self._data['packages'] = platform_collector.get_package_count()
            self._data['resolution'] = platform_collector.get_resolution()
            self._data['local_ip'] = platform_collector.get_local_ip()
            self._data['display_server'] = platform_collector.get_display_server()
            self._data['disks'] = platform_collector.get_disks()
        else:
            # Fallback for unsupported platforms (shouldn't happen)
            self._data['cpu'] = platform.machine()
            self._data['memory_total'] = 0
            self._data['uptime'] = None
            self._data['cpu_freq'] = None
            self._data['gpu'] = None
            self._data['shell'] = None
            self._data['de_wm'] = None
            self._data['terminal'] = None
            self._data['packages'] = None
            self._data['resolution'] = None
            self._data['local_ip'] = None
            self._data['display_server'] = None
            self._data['disks'] = []
    
    def _get_platform_collector(self, system: str):
        """Get the platform-specific collector instance."""
        if system == 'Darwin' and MacOSSystemInfoCollector:
            return MacOSSystemInfoCollector()
        elif system == 'Linux' and LinuxSystemInfoCollector:
            return LinuxSystemInfoCollector()
        elif system == 'Windows' and WindowsSystemInfoCollector:
            return WindowsSystemInfoCollector()
        return None
    
    def _collect_platform_info(self, system: str) -> Dict[str, Any]:
        """Deprecated: Use _get_platform_collector and call collect() directly."""
        platform_collector = self._get_platform_collector(system)
        if platform_collector:
            return platform_collector.collect()
        return self._collect_platform_info_fallback(system)
    
    def _collect_platform_info_fallback(self, system: str) -> Dict[str, Any]:
        """
        Collect platform-specific OS and host information using sub-collectors.
        
        Returns:
            Dictionary with 'os' and 'host' keys containing structured metadata.
        """
        # Instantiate and use platform-specific sub-collector
        if system == 'Darwin' and MacOSSystemInfoCollector:
            collector = MacOSSystemInfoCollector()
            return collector.collect()
        elif system == 'Linux' and LinuxSystemInfoCollector:
            collector = LinuxSystemInfoCollector()
            return collector.collect()
        elif system == 'Windows' and WindowsSystemInfoCollector:
            collector = WindowsSystemInfoCollector()
            return collector.collect()
        else:
            # Fallback for unsupported platforms
            arch = platform.machine()
            return {
                'os': {
                    'name': system,
                    'version': platform.release(),
                    'codename': None,
                    'arch': arch
                },
                'host': {
                    'model': None,
                    'identifier': None,
                    'details': None
                }
            }
    
    def get_data(self) -> Dict[str, Any]:
        """
        Get cached system information.
        
        Returns:
            Dictionary containing all collected system information:
            - os: {name, version, codename, arch} - High-resolution OS metadata
            - host: {model, identifier, details} - High-resolution host metadata
            - kernel: Kernel version
            - hostname: System hostname
            - cpu: CPU model string
            - memory_total: Total memory in bytes (0 if unknown)
            - uptime: System uptime in seconds (None if unknown)
            - cpu_freq: CPU frequency in MHz (None if unknown)
            - gpu: GPU name (None if unknown)
            - shell: Default shell (None if unknown)
            - de_wm: Desktop environment/Window manager (None if unknown)
            - terminal: Terminal emulator (None if unknown)
            - packages: Package count with manager name, e.g., "123 (pacman)" or "456 (apt)" or "789 (brew)" (None if unknown)
            - resolution: Display resolution (None if unknown)
            - local_ip: Local IP address (None if unknown)
            - display_server: Display server Wayland/X11 (None if unknown)
        
        Note: This returns cached data collected at initialization.
        The data never changes during application execution.
        """
        return self._data.copy()
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect system information.
        
        Static fields (OS, host, CPU model, etc.) are cached from initialization.
        Live fields (disks, uptime) are re-collected periodically based on
        the live_poll_interval setting.
        
        Returns:
            Dictionary containing all system information.
        """
        import time
        
        # Check if we need to update live fields
        current_time = time.time()
        if current_time - self._last_live_update >= self._live_poll_interval:
            self._update_live_fields()
            self._last_live_update = current_time
        
        return self._data.copy()
    
    def _update_live_fields(self) -> None:
        """Update live fields that can change during runtime (disks, uptime)."""
        if not self._platform_collector:
            return
        
        # Update uptime (changes every second)
        self._data['uptime'] = self._platform_collector.get_uptime()
        
        # Update disks (can change when files are deleted/added or drives mounted/unmounted)
        self._data['disks'] = self._platform_collector.get_disks()
    
    def get_name(self) -> str:
        """
        Get the unique identifier for this collector.
        
        Returns:
            String identifier "system_info".
        """
        return "system_info"


