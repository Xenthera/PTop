"""
Windows-specific system information collector.

This module provides platform-specific OS and host metadata collection for Windows.
"""

import platform
import os
import subprocess
import shutil
import socket
import ctypes
from typing import Dict, Any, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .system_info_base import PlatformSystemInfoCollectorBase


class WindowsSystemInfoCollector(PlatformSystemInfoCollectorBase):
    """
    Collects Windows-specific system information (OS and host metadata only).
    
    This sub-collector is only instantiated on Windows systems and returns
    structured data for OS and host information.
    """
    
    def __init__(self):
        """Initialize the Windows system info collector."""
        pass
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect Windows OS and host information.
        
        Returns:
            Dictionary with 'os' and 'host' keys containing structured metadata:
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
        arch = platform.machine()
        
        return {
            'os': self._collect_os_info(arch),
            'host': self._collect_host_info()
        }
    
    def _collect_os_info(self, arch: str) -> Dict[str, Any]:
        """Collect Windows OS information."""
        name = 'Windows'
        version = None
        
        try:
            version_info = platform.win32_ver()
            if version_info and len(version_info) > 0:
                version = version_info[0]
        except Exception:
            pass
        
        return {
            'name': name,
            'version': version,
            'codename': None,  # Windows doesn't use codenames in the same way
            'arch': arch
        }
    
    def _collect_host_info(self) -> Dict[str, Any]:
        """Collect Windows host information."""
        # Windows host info collection would require WMI or similar
        # For now, return None values
        return {
            'model': None,
            'identifier': None,
            'details': None
        }
    
    def get_package_count(self) -> Optional[str]:
        """Get package count for Windows (winget, chocolatey, scoop)."""
        package_strings = []
        
        try:
            # Try winget (Windows Package Manager)
            winget_cmd = shutil.which('winget')
            if winget_cmd:
                try:
                    result = subprocess.run(
                        [winget_cmd, 'list'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Name')]
                        count = len(lines)
                        if count > 0:
                            package_strings.append(f"{count} (winget)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try chocolatey
            choco_cmd = shutil.which('choco')
            if choco_cmd:
                try:
                    result = subprocess.run(
                        [choco_cmd, 'list', '--local-only'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Chocolatey')]
                        count = len(lines)
                        if count > 0:
                            package_strings.append(f"{count} (chocolatey)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try scoop
            scoop_cmd = shutil.which('scoop')
            if scoop_cmd:
                try:
                    result = subprocess.run(
                        [scoop_cmd, 'list'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Name')]
                        count = len(lines)
                        if count > 0:
                            package_strings.append(f"{count} (scoop)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
        except Exception:
            pass
        
        if package_strings:
            return ", ".join(package_strings)
        return None
    
    def get_resolution(self) -> Optional[str]:
        """Get primary display resolution for Windows."""
        try:
            user32 = ctypes.windll.user32
            width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            if width > 0 and height > 0:
                return f"{width}x{height}"
        except Exception:
            pass
        return None
    
    def get_display_server(self) -> Optional[str]:
        """Get display server (not applicable on Windows, returns None)."""
        return None
    
    def get_gpu_info(self) -> Optional[str]:
        """Get GPU information for Windows (not implemented, returns None)."""
        # Windows: Would need WMI or similar (skip for now)
        return None
    
    def get_de_wm(self) -> Optional[str]:
        """Get desktop environment/window manager for Windows."""
        return 'Windows'
    
    def get_cpu_model(self) -> str:
        """Get CPU model for Windows."""
        # On Windows, platform.processor() returns technical string like "Intel64 Family 6 Model 158..."
        # Use WMI/CIM to get proper CPU name instead
        try:
            import subprocess
            # Try PowerShell with Get-CimInstance first (faster than Get-WmiObject on modern Windows)
            result = subprocess.run(
                ['powershell', '-Command', 
                 '(Get-CimInstance Win32_Processor).Name'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                cpu_name = result.stdout.strip().split('\n')[0].strip()
                if cpu_name and cpu_name.lower() != 'arm':
                    return cpu_name
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Fallback to Get-WmiObject (older PowerShell versions)
            try:
                result = subprocess.run(
                    ['powershell', '-Command', 
                     '(Get-WmiObject Win32_Processor).Name'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    cpu_name = result.stdout.strip().split('\n')[0].strip()
                    if cpu_name and cpu_name.lower() != 'arm':
                        return cpu_name
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                # Final fallback to wmic (very old Windows)
                try:
                    result = subprocess.run(
                        ['wmic', 'cpu', 'get', 'name', '/value'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if line.startswith('Name='):
                                cpu_name = line.split('=', 1)[1].strip()
                                if cpu_name and cpu_name.lower() != 'arm':
                                    return cpu_name
                                break
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
        
        # Final fallback to platform.processor() or platform.machine()
        processor = platform.processor()
        if processor and 'family' not in processor.lower() and 'model' not in processor.lower():
            return processor
        return platform.machine()
    
    def get_total_memory(self) -> int:
        """Get total system memory for Windows using psutil."""
        if HAS_PSUTIL:
            try:
                return psutil.virtual_memory().total
            except Exception:
                pass
        return 0
    
    def get_uptime(self) -> Optional[float]:
        """Get system uptime for Windows using psutil."""
        if HAS_PSUTIL:
            try:
                import time
                return time.time() - psutil.boot_time()
            except Exception:
                pass
        return None
    
    def get_cpu_frequency(self) -> Optional[float]:
        """Get CPU frequency for Windows using psutil."""
        if HAS_PSUTIL:
            try:
                freq = psutil.cpu_freq()
                if freq:
                    return freq.current if freq.current else freq.max
            except Exception:
                pass
        return None
    
    def get_shell(self) -> Optional[str]:
        """Get default shell for Windows."""
        shell = os.environ.get('COMSPEC')
        if shell:
            return os.path.basename(shell)
        return None
    
    def get_terminal(self) -> Optional[str]:
        """Get terminal emulator for Windows."""
        term = os.environ.get('TERM_PROGRAM') or os.environ.get('TERMINAL_EMULATOR')
        if term:
            return term
        return None
    
    def get_local_ip(self) -> Optional[str]:
        """Get local IP address for Windows."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
                return ip
            except Exception:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                if ip and ip != '127.0.0.1':
                    return ip
            finally:
                s.close()
        except Exception:
            pass
        
        if HAS_PSUTIL:
            try:
                net_if_addrs = psutil.net_if_addrs()
                for interface_name, addresses in net_if_addrs.items():
                    if interface_name.startswith('lo'):
                        continue
                    for addr in addresses:
                        if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                            return addr.address
            except Exception:
                pass
        
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Windows."""
        disks = []
        try:
            import psutil
            import os
            import string
            
            partitions = psutil.disk_partitions()
            for partition in partitions:
                mountpoint = partition.mountpoint
                fstype = partition.fstype
                
                # Skip virtual filesystems
                if fstype in ('', 'UNKNOWN'):
                    continue
                
                # Skip if mountpoint doesn't exist
                if not os.path.exists(mountpoint):
                    continue
                
                try:
                    disk = psutil.disk_usage(mountpoint)
                    total = disk.total
                    used = disk.total - disk.free
                    
                    # Skip if total is 0 (invalid)
                    if total == 0:
                        continue
                    
                    # Determine attributes
                    attributes = []
                    if partition.opts:
                        opts_lower = partition.opts.lower().split(',')
                        opts_lower = [opt.strip() for opt in opts_lower]
                        if 'ro' in opts_lower or 'readonly' in opts_lower:
                            attributes.append('Read-only')
                    
                    # On Windows, check if it's a removable drive
                    # Drive letters like A:, B: are typically floppy/removable
                    # C: is typically the main drive
                    if len(mountpoint) == 3 and mountpoint.endswith(':\\'):
                        drive_letter = mountpoint[0].upper()
                        if drive_letter in string.ascii_uppercase:
                            # Check if it's removable (heuristic: A:, B:, D:, E: etc. might be removable)
                            # C: is typically the main drive, so don't mark it as external
                            if drive_letter not in ('C',):
                                # For now, we'll mark all non-C: drives as potentially external
                                # A more accurate method would use Win32 API
                                attributes.append('External')
                    
                    disks.append({
                        'mountpoint': mountpoint,
                        'fstype': fstype,
                        'used': used,
                        'total': total,
                        'attributes': attributes
                    })
                except (OSError, PermissionError):
                    # Skip if we can't access this mountpoint
                    continue
            
            # Sort disks by mountpoint (typically C:, D:, E:, etc.)
            disks.sort(key=lambda x: x['mountpoint'])
        except Exception:
            pass
        
        return disks
    
    def get_battery(self) -> Optional[Dict[str, Any]]:
        """Get battery information for Windows using psutil."""
        try:
            import psutil
            
            battery = psutil.sensors_battery()
            if battery is None:
                return None
            
            return {
                'percent': battery.percent,
                'power_plugged': battery.power_plugged,
                'secsleft': battery.secsleft if battery.secsleft is not None and battery.secsleft >= 0 else None
            }
        except Exception:
            return None

