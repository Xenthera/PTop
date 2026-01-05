"""
Base class for platform-specific system information collectors.

This module provides an abstract base class that all platform sub-collectors
must extend, defining the interface for platform-specific system information collection.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None


class PlatformSystemInfoCollectorBase(ABC):
    """
    Base class for platform-specific system information collectors.
    
    All platform sub-collectors (macOS, Linux, Windows) must extend this class
    and implement the required abstract methods. Optional methods can return None
    if the functionality is not available on that platform.
    """
    
    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """
        Collect platform-specific OS and host information.
        
        This is the only required method. It must return a dictionary with
        'os' and 'host' keys containing structured metadata.
        
        Returns:
            Dictionary with 'os' and 'host' keys:
            {
                'os': {
                    'name': str,
                    'version': str or None,
                    'codename': str or None,
                    'arch': str
                },
                'host': {
                    'model': str or None,
                    'identifier': str or None,
                    'details': str or None
                }
            }
        """
        pass
    
    def get_package_count(self) -> Optional[str]:
        """
        Get package count with package manager names.
        
        Returns formatted string like "1234 (apt), 56 (snap)" or None if not available.
        
        Returns:
            Package count string or None
        """
        return None
    
    def get_resolution(self) -> Optional[str]:
        """
        Get primary display resolution.
        
        Returns resolution string like "1920x1080" or None if not available.
        
        Returns:
            Resolution string or None
        """
        return None
    
    def get_display_server(self) -> Optional[str]:
        """
        Get display server (Wayland/X11 on Linux).
        
        Returns "Wayland", "X11", or None if not applicable.
        
        Returns:
            Display server string or None
        """
        return None
    
    def get_gpu_info(self) -> Optional[str]:
        """
        Get GPU information.
        
        Returns simple GPU name if available, or None.
        
        Returns:
            GPU name string or None
        """
        return None
    
    def get_de_wm(self) -> Optional[str]:
        """
        Get desktop environment or window manager.
        
        Returns desktop environment/window manager name or None if not available.
        
        Returns:
            DE/WM name string or None
        """
        return None
    
    def get_cpu_model(self) -> str:
        """
        Get CPU model string.
        
        Returns:
            CPU model string
        """
        return 'Unknown CPU'
    
    def get_total_memory(self) -> int:
        """
        Get total system memory in bytes.
        
        Returns:
            Total memory in bytes, or 0 if unknown
        """
        return 0
    
    def get_uptime(self) -> Optional[float]:
        """
        Get system uptime in seconds.
        
        Returns:
            Uptime in seconds, or None if unknown
        """
        return None
    
    def get_cpu_frequency(self) -> Optional[float]:
        """
        Get CPU frequency in MHz.
        
        Returns:
            CPU frequency in MHz, or None if unknown
        """
        return None
    
    def get_shell(self) -> Optional[str]:
        """
        Get default shell.
        
        Returns:
            Shell name or None if unknown
        """
        return None
    
    def get_terminal(self) -> Optional[str]:
        """
        Get terminal emulator name.
        
        Returns:
            Terminal name or None if unknown
        """
        return None
    
    def get_local_ip(self) -> Optional[str]:
        """
        Get local IP address of primary network interface.
        
        Returns:
            IP address string or None if unavailable
        """
        return None
    
    def get_disks(self) -> list:
        """
        Get list of mounted disk volumes with usage information.
        
        Returns:
            List of dictionaries, each containing:
            - mountpoint: str - Mount point path (e.g., "/", "/Volumes/MyDisk")
            - fstype: str - Filesystem type (e.g., "apfs", "ext4", "ntfs")
            - used: int - Used space in bytes
            - total: int - Total space in bytes
            - attributes: list[str] - List of attributes (e.g., ["Read-only", "External"])
        """
        return []
    
    def get_battery(self) -> Optional[Dict[str, Any]]:
        """
        Get battery information.
        
        Returns:
            Dictionary with battery information or None if not available:
            {
                'percent': float,  # Battery percentage (0-100)
                'power_plugged': bool,  # True if AC power connected, False if on battery
                'secsleft': float or None  # Time remaining in seconds, or None if unknown/calculating
            }
        """
        return None
    
    def get_memory_used(self) -> int:
        """
        Get current memory used in bytes.
        
        Returns:
            Memory used in bytes (0 if not available).
        """
        if HAS_PSUTIL:
            try:
                return psutil.virtual_memory().used
            except Exception:
                pass
        return 0
    
    def get_process_count(self) -> int:
        """
        Get current number of running processes.
        
        Returns:
            Number of running processes (0 if not available).
        """
        if HAS_PSUTIL:
            try:
                return len(psutil.pids())
            except Exception:
                pass
        return 0

