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
    
    def __init__(self):
        """
        Initialize the collector and collect all system information.
        
        This runs once at startup and caches all data.
        """
        self._data: Dict[str, Any] = {}
        self._collect_all()
    
    def _collect_all(self) -> None:
        """Collect all system information and cache it."""
        system = platform.system()
        
        # Collect OS and host metadata using new high-resolution schema
        os_info = self._collect_os_info(system)
        host_info = self._collect_host_info(system)
        
        # Store new structured schema
        self._data['os'] = os_info
        self._data['host'] = host_info
        
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
        
        # CPU model
        self._data['cpu'] = self._get_cpu_model()
        
        # Total system memory (using psutil for cross-platform support)
        self._data['memory_total'] = self._get_total_memory()
        
        # Uptime
        self._data['uptime'] = self._get_uptime()
        
        # CPU frequency
        self._data['cpu_freq'] = self._get_cpu_frequency()
        
        # GPU
        self._data['gpu'] = self._get_gpu_info()
        
        # Shell
        self._data['shell'] = self._get_shell()
        
        # Desktop environment / Window manager
        self._data['de_wm'] = self._get_de_wm()
        
        # Terminal
        self._data['terminal'] = self._get_terminal()
        
        # Package count (optional)
        self._data['packages'] = self._get_package_count()
        
        # Resolution (display)
        self._data['resolution'] = self._get_resolution()
        
        # Local IP address
        self._data['local_ip'] = self._get_local_ip()
        
        # Display server (Linux - Wayland/X11)
        self._data['display_server'] = self._get_display_server()
    
    def _collect_os_info(self, system: str) -> Dict[str, Any]:
        """
        Collect OS information using high-resolution platform-specific methods.
        
        Returns:
            Dictionary with keys: name, version, codename, arch
        """
        arch = platform.machine()
        
        if system == 'Darwin':
            return self._collect_macos_os_info(arch)
        elif system == 'Linux':
            return self._collect_linux_os_info(arch)
        elif system == 'Windows':
            return self._collect_windows_os_info(arch)
        else:
            # Fallback for other systems
            return {
                'name': system,
                'version': platform.release(),
                'codename': None,
                'arch': arch
            }
    
    def _collect_macos_os_info(self, arch: str) -> Dict[str, Any]:
        """Collect macOS OS information using sw_vers."""
        name = 'macOS'
        version = None
        codename = None
        
        # Use sw_vers for OS version
        try:
            result = subprocess.run(
                ['sw_vers', '-productVersion'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                version = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Fallback to platform.mac_ver()
            try:
                version = platform.mac_ver()[0]
            except Exception:
                pass
        
        # Derive codename from major version
        if version:
            try:
                major_version = int(version.split('.')[0])
                codename = self._macos_codename_from_version(major_version)
            except (ValueError, IndexError):
                pass
        
        return {
            'name': name,
            'version': version,
            'codename': codename,
            'arch': arch
        }
    
    def _macos_codename_from_version(self, major_version: int) -> Optional[str]:
        """Map macOS major version to codename."""
        codenames = {
            15: 'Sequoia',
            14: 'Sonoma',
            13: 'Ventura',
            12: 'Monterey',
            11: 'Big Sur',
            10: 'Catalina',
        }
        return codenames.get(major_version)
    
    def _collect_linux_os_info(self, arch: str) -> Dict[str, Any]:
        """Collect Linux OS information from /etc/os-release."""
        name = None
        version = None
        codename = None
        
        try:
            os_release_data = {}
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os_release_data[key] = value
            
            # Extract name
            name = os_release_data.get('NAME') or os_release_data.get('ID', 'Linux')
            # Clean up name (remove quotes if any)
            name = name.strip('"').strip("'")
            
            # Extract version
            version = os_release_data.get('VERSION_ID') or os_release_data.get('VERSION')
            if version:
                version = version.strip('"').strip("'")
            
            # Extract codename
            codename = os_release_data.get('VERSION_CODENAME') or os_release_data.get('BUILD_ID')
            if codename:
                codename = codename.strip('"').strip("'")
        except (IOError, OSError):
            pass
        
        # Fallback if no data found
        if not name:
            name = 'Linux'
        
        return {
            'name': name,
            'version': version,
            'codename': codename,
            'arch': arch
        }
    
    def _collect_windows_os_info(self, arch: str) -> Dict[str, Any]:
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
    
    def _collect_host_info(self, system: str) -> Dict[str, Any]:
        """
        Collect host/machine information using high-resolution platform-specific methods.
        
        Returns:
            Dictionary with keys: model, identifier, details
        """
        if system == 'Darwin':
            return self._collect_macos_host_info()
        elif system == 'Linux':
            return self._collect_linux_host_info()
        elif system == 'Windows':
            return self._collect_windows_host_info()
        else:
            return {
                'model': None,
                'identifier': None,
                'details': None
            }
    
    def _collect_macos_host_info(self) -> Dict[str, Any]:
        """Collect macOS host information using system_profiler and sysctl."""
        model = None
        identifier = None
        details_parts = []
        
        # Get model name from system_profiler
        try:
            result = subprocess.run(
                ['system_profiler', 'SPHardwareDataType', '-json'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    hardware = data.get('SPHardwareDataType', [])
                    if hardware and len(hardware) > 0:
                        hw_data = hardware[0]
                        model = hw_data.get('machine_name') or hw_data.get('model_name')
                        # Get model identifier (e.g., Mac15,7)
                        identifier = hw_data.get('machine_model')
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        # Fallback: Get model identifier from sysctl
        if not identifier:
            try:
                result = subprocess.run(
                    ['sysctl', '-n', 'hw.model'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    identifier = result.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        
        # Derive details dynamically
        screen_size = self._derive_screen_size()
        year = self._derive_release_year(identifier) if identifier else None
        thunderbolt_info = self._derive_thunderbolt_ports()
        
        # Build details parts
        if screen_size:
            details_parts.append(screen_size)
        if year:
            details_parts.append(year)
        if thunderbolt_info:
            details_parts.append(thunderbolt_info)
        
        return {
            'model': model,
            'identifier': identifier,
            'details': ', '.join(details_parts) if details_parts else None
        }
    
    def _derive_screen_size(self) -> Optional[str]:
        """
        Derive screen size from built-in display native resolution.
        
        Uses system_profiler SPDisplaysDataType to get native resolution
        and maps it to screen size using resolution heuristics.
        """
        try:
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType', '-json'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    displays = data.get('SPDisplaysDataType', [])
                    
                    # Find built-in display
                    for display in displays:
                        ndrvs = display.get('spdisplays_ndrvs', [])
                        for ndrv in ndrvs:
                            if ndrv.get('spdisplays_connection_type') == 'spdisplays_internal':
                                # Get native resolution from pixelresolution or pixels
                                pixel_res = ndrv.get('spdisplays_pixelresolution', '')
                                pixels = ndrv.get('_spdisplays_pixels', '')
                                
                                # Parse resolution (e.g., "3456x2234Retina" or "4112 x 2658")
                                width, height = None, None
                                
                                if pixel_res:
                                    # Extract resolution from string like "3456x2234Retina"
                                    import re
                                    match = re.search(r'(\d+)x(\d+)', pixel_res)
                                    if match:
                                        width = int(match.group(1))
                                        height = int(match.group(2))
                                
                                if not width or not height:
                                    # Try parsing from pixels field like "4112 x 2658"
                                    if pixels:
                                        import re
                                        match = re.search(r'(\d+)\s*x\s*(\d+)', pixels)
                                        if match:
                                            width = int(match.group(1))
                                            height = int(match.group(2))
                                
                                if width and height:
                                    # Map resolution to screen size using common resolutions
                                    # Common Mac resolutions:
                                    # 16-inch: 3456x2234, 3024x1964
                                    # 15-inch: 2880x1864
                                    # 14-inch: 3024x1964, 3024x1890
                                    # 13-inch: 2560x1600, 2560x1440
                                    # 24-inch iMac: 4480x2520
                                    
                                    if width >= 3440 or (width >= 3000 and height >= 2200):
                                        return '16-inch'
                                    elif width >= 2880 and width < 3000:
                                        return '15-inch'
                                    elif width >= 3000 and height < 2200:
                                        return '14-inch'
                                    elif width >= 2560 and width < 2880:
                                        return '13-inch'
                                    elif width >= 4000:
                                        return '24-inch'
                except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                    pass
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        return None
    
    def _derive_release_year(self, identifier: str) -> Optional[str]:
        """
        Derive release year/generation from model identifier prefix.
        
        Examples:
        - Mac15,* -> Late 2023
        - MacBookPro18,* -> Late 2021
        - Mac14,* -> Early 2023
        """
        if not identifier:
            return None
        
        # Extract prefix (e.g., "Mac15" or "MacBookPro18")
        prefix_match = identifier.split(',')[0] if ',' in identifier else identifier
        
        # Map prefix patterns to release periods
        # This is a simplified mapping based on known patterns
        year_map = {
            'Mac15': 'Late 2023',
            'Mac14': 'Early 2023',
            'MacBookPro18': 'Late 2021',
            'MacBookPro17': 'Late 2020',
            'MacBookPro16': 'Late 2019',
            'MacBookAir10': 'Late 2020',
            'MacBookAir9': 'Early 2020',
            'Mac24': 'Early 2021',
        }
        
        # Find matching prefix (exact match or starts with)
        for pattern, year in year_map.items():
            if prefix_match.startswith(pattern):
                return year
        
        # Try to extract number from prefix (e.g., Mac15 -> 15, MacBookPro18 -> 18)
        # and estimate year (rough heuristic: MacN -> 2000 + N, MacBookProN -> 2000 + N)
        import re
        num_match = re.search(r'(\d+)', prefix_match)
        if num_match:
            num = int(num_match.group(1))
            # Very rough heuristic - this is not accurate for all models
            # Better to extend year_map above for accuracy
            if 'MacBookPro' in prefix_match or 'MacBookAir' in prefix_match:
                if num >= 18:
                    return '2021-2023'
                elif num >= 16:
                    return '2019-2021'
        
        return None
    
    def _derive_thunderbolt_ports(self) -> Optional[str]:
        """
        Derive Thunderbolt port count by enumerating Thunderbolt-capable USB-C ports.
        
        On Apple Silicon Macs, counts AppleUSB40XHCITypeCPort entries (USB4/Thunderbolt 4 ports).
        On Intel Macs, attempts to count Thunderbolt controllers via system_profiler.
        """
        thunderbolt_count = 0
        thunderbolt_version = None
        
        # On Apple Silicon Macs, count USB4/Thunderbolt 4 ports via IORegistry
        # AppleUSB40XHCITypeCPort represents USB 4.0 Type-C ports (Thunderbolt 4 compatible)
        try:
            result = subprocess.run(
                ['ioreg', '-p', 'IOService', '-r', '-c', 'AppleUSB40XHCITypeCPort', '-w0'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                import re
                # Count occurrences of AppleUSB40XHCITypeCPort class
                port_matches = re.findall(r'class AppleUSB40XHCITypeCPort', result.stdout)
                if port_matches:
                    thunderbolt_count = len(port_matches)
                    thunderbolt_version = '4'  # USB4 ports are Thunderbolt 4 compatible
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        # Fallback: Try system_profiler SPUSBDataType for Intel Macs or if IORegistry didn't work
        if thunderbolt_count == 0:
            try:
                result = subprocess.run(
                    ['system_profiler', 'SPUSBDataType', '-json'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    try:
                        data = json.loads(result.stdout)
                        usb_items = data.get('SPUSBDataType', [])
                        
                        # Recursively count Thunderbolt controllers
                        def count_thunderbolt(items, depth=0):
                            nonlocal thunderbolt_count, thunderbolt_version
                            if depth > 10:  # Prevent infinite recursion
                                return
                            for item in items:
                                name = item.get('_name', '').lower()
                                if 'thunderbolt' in name:
                                    thunderbolt_count += 1
                                    # Try to detect version
                                    if 'thunderbolt 4' in name or 'thunderbolt/usb4' in name or 'usb4' in name:
                                        thunderbolt_version = '4'
                                    elif 'thunderbolt 3' in name:
                                        thunderbolt_version = '3'
                                # Recursively check children
                                children = item.get('_items', [])
                                if children:
                                    count_thunderbolt(children, depth + 1)
                        
                        count_thunderbolt(usb_items)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        
        if thunderbolt_count > 0:
            # Format port count with version
            version_str = f" Thunderbolt {thunderbolt_version}" if thunderbolt_version else ""
            port_str = "port" if thunderbolt_count == 1 else "ports"
            return f"{thunderbolt_count}{version_str} {port_str}"
        
        return None
    
    def _collect_linux_host_info(self) -> Dict[str, Any]:
        """Collect Linux host information from DMI sysfs."""
        model = None
        identifier = None
        details_parts = []
        
        # Try /sys/devices/virtual/dmi/id/product_name for model
        try:
            with open('/sys/devices/virtual/dmi/id/product_name', 'r') as f:
                product_name = f.read().strip()
                if product_name and product_name != 'None' and 'To be filled' not in product_name:
                    model = product_name
        except (IOError, OSError):
            pass
        
        # Try /sys/devices/virtual/dmi/id/product_version for version/identifier
        try:
            with open('/sys/devices/virtual/dmi/id/product_version', 'r') as f:
                product_version = f.read().strip()
                if product_version and product_version != 'None' and 'To be filled' not in product_version:
                    # If we have both name and version, combine them for model
                    if model and product_version:
                        identifier = product_version
                    elif not model:
                        model = product_version
        except (IOError, OSError):
            pass
        
        # Try /sys/devices/virtual/dmi/id/board_name as fallback
        if not model:
            try:
                with open('/sys/devices/virtual/dmi/id/board_name', 'r') as f:
                    board_name = f.read().strip()
                    if board_name and board_name != 'None' and 'To be filled' not in board_name:
                        model = board_name
            except (IOError, OSError):
                pass
        
        return {
            'model': model,
            'identifier': identifier,
            'details': ', '.join(details_parts) if details_parts else None
        }
    
    def _collect_windows_host_info(self) -> Dict[str, Any]:
        """Collect Windows host information."""
        # Windows host info collection would require WMI or similar
        # For now, return None values
        return {
            'model': None,
            'identifier': None,
            'details': None
        }
    
    def _get_cpu_model(self) -> str:
        """Get CPU model using stdlib and direct file access only."""
        system = platform.system()
        
        if system == 'Linux':
            # Read from /proc/cpuinfo
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line.lower():
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                return parts[1].strip()
                        elif 'Processor' in line and ':' in line:
                            # ARM Linux sometimes uses 'Processor' instead
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                return parts[1].strip()
            except (IOError, OSError):
                pass
        elif system == 'Darwin':  # macOS
            # On macOS, platform.processor() usually returns 'arm' or 'i386'
            # We can't use subprocess, so we use platform.processor() as fallback
            # This is a limitation of stdlib-only approach on macOS
            processor = platform.processor()
            if processor and processor.lower() != 'arm' and processor.lower() != 'i386':
                return processor
            # Try to read from sysctl via ctypes (advanced, but stdlib-adjacent)
            # Actually, ctypes is stdlib, but sysctl interface is complex
            # For now, fall back to platform.machine() which gives architecture
            # Real CPU name would require subprocess, which we avoid
            return platform.machine()
        elif system == 'Windows':
            # platform.processor() works on Windows
            processor = platform.processor()
            if processor:
                return processor
        
        # Final fallback
        return platform.machine()
    
    def _get_total_memory(self) -> int:
        """
        Get total system memory in bytes using psutil (cross-platform).
        
        Falls back to /proc/meminfo on Linux if psutil is unavailable.
        """
        if HAS_PSUTIL:
            try:
                return psutil.virtual_memory().total
            except Exception:
                pass
        
        # Fallback to /proc/meminfo on Linux
        system = platform.system()
        if system == 'Linux':
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            parts = line.split()
                            if len(parts) >= 2:
                                kb = int(parts[1])
                                return kb * 1024  # Convert KB to bytes
            except (IOError, OSError, ValueError):
                pass
        
        return 0
    
    def _get_uptime(self) -> Optional[float]:
        """
        Get system uptime in seconds.
        
        Uses psutil if available, otherwise /proc/uptime on Linux.
        """
        if HAS_PSUTIL:
            try:
                return time.time() - psutil.boot_time()
            except Exception:
                pass
        
        # Fallback to /proc/uptime on Linux
        system = platform.system()
        if system == 'Linux':
            try:
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.read().split()[0])
                    return uptime_seconds
            except (IOError, OSError, ValueError, IndexError):
                pass
        
        # macOS/BSD/Windows: psutil should work, but if not, return None
        return None
    
    def _get_cpu_frequency(self) -> Optional[float]:
        """
        Get CPU frequency in MHz.
        
        Uses psutil if available, otherwise /proc/cpuinfo on Linux.
        Returns current frequency if available, or max frequency.
        """
        if HAS_PSUTIL:
            try:
                freq = psutil.cpu_freq()
                if freq:
                    # Return current frequency if available, otherwise max
                    return freq.current if freq.current else freq.max
            except Exception:
                pass
        
        # Fallback to /proc/cpuinfo on Linux
        system = platform.system()
        if system == 'Linux':
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'cpu MHz' in line.lower():
                            parts = line.split(':')
                            if len(parts) == 2:
                                mhz = float(parts[1].strip())
                                return mhz
            except (IOError, OSError, ValueError):
                pass
        
        return None
    
    def _get_gpu_info(self) -> Optional[str]:
        """
        Get GPU information.
        
        Reads from /sys on Linux, attempts to detect GPU from environment
        or system files. Returns simple GPU name if available.
        """
        system = platform.system()
        
        if system == 'Linux':
            # Try to read GPU info from /sys
            try:
                # Check for NVIDIA
                nvidia_path = '/sys/class/drm/card0/device/uevent'
                try:
                    with open(nvidia_path, 'r') as f:
                        for line in f:
                            if line.startswith('PCI_ID='):
                                # Extract vendor/device IDs
                                pci_id = line.split('=', 1)[1].strip()
                                if '10de' in pci_id.lower():  # NVIDIA vendor ID
                                    return 'NVIDIA'
                except (IOError, OSError):
                    pass
                
                # Check /proc/driver/nvidia/version for NVIDIA
                try:
                    with open('/proc/driver/nvidia/version', 'r') as f:
                        first_line = f.readline()
                        if 'NVIDIA' in first_line:
                            return 'NVIDIA'
                except (IOError, OSError):
                    pass
                
                # Check for AMD
                try:
                    amd_paths = ['/sys/class/drm/card0/device/vendor']
                    for path in amd_paths:
                        try:
                            with open(path, 'r') as f:
                                vendor_id = f.read().strip()
                                if '1002' in vendor_id.lower():  # AMD vendor ID
                                    return 'AMD'
                        except (IOError, OSError):
                            continue
                except Exception:
                    pass
                
                # Try to get GPU from lspci equivalent (read /sys/bus/pci/devices)
                try:
                    import glob
                    for device_path in glob.glob('/sys/bus/pci/devices/*/class'):
                        try:
                            with open(device_path, 'r') as f:
                                device_class = f.read().strip()
                                # 0x030000 = Display controller
                                if device_class.startswith('0x03') or device_class.startswith('030'):
                                    # Get vendor/device from uevent
                                    uevent_path = device_path.replace('/class', '/uevent')
                                    try:
                                        with open(uevent_path, 'r') as uf:
                                            for uline in uf:
                                                if uline.startswith('PCI_ID='):
                                                    pci_id = uline.split('=', 1)[1].strip()
                                                    vendor_id = pci_id.split(':')[0].lower()
                                                    if vendor_id == '10de':
                                                        return 'NVIDIA'
                                                    elif vendor_id == '1002':
                                                        return 'AMD'
                                                    elif vendor_id == '8086':
                                                        return 'Intel'
                                    except (IOError, OSError):
                                        continue
                        except (IOError, OSError):
                            continue
                except Exception:
                    pass
            except Exception:
                pass
        
        # macOS: Try to detect from IOKit (complex, skip for now)
        # Windows: Would need WMI or similar (skip for now)
        
        return None
    
    def _get_shell(self) -> Optional[str]:
        """
        Get default shell.
        
        Uses SHELL environment variable, or /etc/passwd on Unix systems.
        """
        # Try environment variable first
        shell = os.environ.get('SHELL')
        if shell:
            # Extract just the executable name (e.g., /bin/zsh -> zsh)
            return os.path.basename(shell)
        
        # On Unix systems, try /etc/passwd for current user
        system = platform.system()
        if system != 'Windows':
            try:
                import pwd
                username = os.environ.get('USER') or os.environ.get('USERNAME')
                if username:
                    pw_entry = pwd.getpwnam(username)
                    shell_path = pw_entry.pw_shell
                    if shell_path:
                        return os.path.basename(shell_path)
            except (ImportError, KeyError, OSError):
                pass
        
        return None
    
    def _get_de_wm(self) -> Optional[str]:
        """
        Get desktop environment or window manager.
        
        Linux/BSD: Reads from XDG environment variables or detects from processes.
        """
        system = platform.system()
        if system == 'Windows':
            return 'Windows'
        elif system == 'Darwin':
            return 'Aqua'
        
        # Linux/BSD: Check XDG environment variables
        de = os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION')
        if de:
            # Clean up common values
            de = de.split(':')[0].split('/')[0]  # Handle "GNOME:GNOME-Classic" or "gnome/xorg"
            return de
        
        # Try alternative environment variables
        de = os.environ.get('XDG_SESSION_DESKTOP') or os.environ.get('GDMSESSION')
        if de:
            return de.split(':')[0].split('/')[0]
        
        # Try to detect from common window manager processes
        # This is a simple heuristic - check if common WM processes exist
        # Note: We can't easily check running processes without subprocess,
        # so we'll just return None if env vars don't work
        return None
    
    def _get_terminal(self) -> Optional[str]:
        """
        Get terminal emulator name.
        
        Reads from environment variables or /proc on Linux.
        """
        # Try common environment variables
        term = os.environ.get('TERM_PROGRAM') or os.environ.get('TERMINAL_EMULATOR')
        if term:
            return term
        
        # macOS specific
        system = platform.system()
        if system == 'Darwin':
            term = os.environ.get('TERM_PROGRAM_VERSION')
            if term:
                # This gives version, but we want the program name
                # TERM_PROGRAM should be set instead
                pass
        
        # Linux: Try to get from parent process or environment
        term = os.environ.get('COLORTERM') or os.environ.get('XTERM_VERSION')
        if term:
            return term
        
        # Fallback: Use TERM environment variable (but filter out generic values)
        term = os.environ.get('TERM')
        if term and term not in ['xterm', 'xterm-256color', 'screen', 'tmux', 'dumb', 'unknown']:
            # Only use TERM if it looks like a specific terminal name
            if len(term) > 4 and not term.startswith('xterm'):
                return term
        
        # Linux: Try to read from /proc/self/comm or parent process
        if system == 'Linux':
            try:
                # Get parent process ID
                ppid = os.getppid()
                comm_path = f'/proc/{ppid}/comm'
                try:
                    with open(comm_path, 'r') as f:
                        parent_comm = f.read().strip()
                        # Common terminal emulators
                        if any(t in parent_comm.lower() for t in ['gnome-terminal', 'konsole', 'xterm', 'alacritty', 'kitty', 'wezterm', 'foot']):
                            return parent_comm
                except (IOError, OSError):
                    pass
            except Exception:
                pass
        
        return None
    
    def _get_package_count(self) -> Optional[str]:
        """
        Get package count with package manager name.
        
        Detects package managers and counts installed packages:
        - Linux: pacman (Arch), apt (Debian/Ubuntu), rpm/dnf/yum/zypper (RPM-based), portage (Gentoo), apk (Alpine)
        - macOS: brew (Homebrew)
        - Windows: winget, chocolatey, scoop
        - FreeBSD: pkg, ports
        - OpenBSD: pkg_add
        - NetBSD: pkgin, pkgsrc
        
        Returns formatted string like "123 (pacman)" or None if unavailable.
        """
        system = platform.system()
        import subprocess
        import shutil
        
        # macOS: Try Homebrew
        if system == 'Darwin':
            try:
                # Check if brew is available by checking common paths
                brew_paths = [
                    '/opt/homebrew/bin/brew',  # Apple Silicon
                    '/usr/local/bin/brew',     # Intel
                    os.path.expanduser('~/.homebrew/bin/brew'),  # User install
                ]
                brew_cmd = None
                for path in brew_paths:
                    if os.path.exists(path):
                        brew_cmd = path
                        break
                
                # Also try to find brew in PATH
                if not brew_cmd:
                    brew_cmd = shutil.which('brew')
                
                if brew_cmd:
                    try:
                        result = subprocess.run(
                            [brew_cmd, 'list', '--formula'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            packages = [line for line in result.stdout.strip().split('\n') if line.strip()]
                            count = len(packages)
                            if count > 0:
                                return f"{count} (brew)"
                    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                        pass
            except Exception:
                pass
            return None
        
        # Windows: Try winget, chocolatey, scoop
        if system == 'Windows':
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
                            # Count non-empty lines (skip header)
                            lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Name')]
                            count = len(lines)
                            if count > 0:
                                return f"{count} (winget)"
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
                                return f"{count} (chocolatey)"
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
                                return f"{count} (scoop)"
                    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                        pass
            except Exception:
                pass
            return None
        
        # FreeBSD: Try pkg and ports
        if system == 'FreeBSD':
            try:
                # Try pkg (binary packages)
                pkg_cmd = shutil.which('pkg')
                if pkg_cmd:
                    try:
                        result = subprocess.run(
                            [pkg_cmd, 'info'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            lines = [line for line in result.stdout.strip().split('\n') if line.strip()]
                            count = len(lines)
                            if count > 0:
                                return f"{count} (pkg)"
                    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                        pass
                
                # Try ports (source packages)
                ports_db = '/usr/ports'
                if os.path.isdir(ports_db):
                    # Count installed ports from /var/db/pkg
                    pkg_db = '/var/db/pkg'
                    if os.path.isdir(pkg_db):
                        count = len([d for d in os.listdir(pkg_db) if os.path.isdir(os.path.join(pkg_db, d))])
                        if count > 0:
                            return f"{count} (ports)"
            except Exception:
                pass
            return None
        
        # OpenBSD: Try pkg_add
        if system == 'OpenBSD':
            try:
                pkg_info_cmd = shutil.which('pkg_info')
                if pkg_info_cmd:
                    try:
                        result = subprocess.run(
                            [pkg_info_cmd],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            lines = [line for line in result.stdout.strip().split('\n') if line.strip()]
                            count = len(lines)
                            if count > 0:
                                return f"{count} (pkg_add)"
                    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                        pass
            except Exception:
                pass
            return None
        
        # NetBSD: Try pkgin and pkgsrc
        if system == 'NetBSD':
            try:
                # Try pkgin (binary packages)
                pkgin_cmd = shutil.which('pkgin')
                if pkgin_cmd:
                    try:
                        result = subprocess.run(
                            [pkgin_cmd, 'list'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Reading')]
                            count = len(lines)
                            if count > 0:
                                return f"{count} (pkgin)"
                    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                        pass
                
                # Try pkgsrc (source packages)
                pkgsrc_db = '/usr/pkgsrc'
                if os.path.isdir(pkgsrc_db):
                    pkg_db = '/var/db/pkg'
                    if os.path.isdir(pkg_db):
                        count = len([d for d in os.listdir(pkg_db) if os.path.isdir(os.path.join(pkg_db, d))])
                        if count > 0:
                            return f"{count} (pkgsrc)"
            except Exception:
                pass
            return None
        
        # Linux: Try different package managers
        try:
            # Try pacman (Arch) - highest priority for Arch-based systems
            try:
                pacman_db = '/var/lib/pacman/local'
                if os.path.isdir(pacman_db):
                    count = len([d for d in os.listdir(pacman_db) if os.path.isdir(os.path.join(pacman_db, d))])
                    if count > 0:
                        return f"{count} (pacman)"
            except (IOError, OSError):
                pass
            
            # Try dpkg/apt (Debian/Ubuntu)
            try:
                dpkg_db = '/var/lib/dpkg/status'
                if os.path.exists(dpkg_db):
                    count = 0
                    with open(dpkg_db, 'r') as f:
                        for line in f:
                            if line.startswith('Package:'):
                                count += 1
                    if count > 0:
                        return f"{count} (apt)"
            except (IOError, OSError):
                pass
            
            # Try apk (Alpine)
            try:
                apk_db = '/lib/apk/db/installed'
                if os.path.exists(apk_db):
                    count = 0
                    with open(apk_db, 'r') as f:
                        for line in f:
                            if line.startswith('P:'):
                                count += 1
                    if count > 0:
                        return f"{count} (apk)"
            except (IOError, OSError):
                pass
            
            # Try dnf (Fedora) - preferred over rpm/yum
            dnf_cmd = shutil.which('dnf')
            if dnf_cmd:
                try:
                    result = subprocess.run(
                        [dnf_cmd, 'list', 'installed'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Installed')]
                        count = len(lines)
                        if count > 0:
                            return f"{count} (dnf)"
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try yum (older Fedora/CentOS)
            yum_cmd = shutil.which('yum')
            if yum_cmd:
                try:
                    result = subprocess.run(
                        [yum_cmd, 'list', 'installed'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Installed')]
                        count = len(lines)
                        if count > 0:
                            return f"{count} (yum)"
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try rpm (RedHat/Fedora) - fallback if dnf/yum not available
            rpm_cmd = shutil.which('rpm')
            if rpm_cmd:
                try:
                    result = subprocess.run(
                        [rpm_cmd, '-qa'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        packages = [line for line in result.stdout.strip().split('\n') if line.strip()]
                        count = len(packages)
                        if count > 0:
                            return f"{count} (rpm)"
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try zypper (openSUSE)
            zypper_cmd = shutil.which('zypper')
            if zypper_cmd:
                try:
                    result = subprocess.run(
                        [zypper_cmd, 'search', '-i'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if '|' in line and not line.startswith('S')]
                        count = len(lines)
                        if count > 0:
                            return f"{count} (zypper)"
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try portage (Gentoo) - count categories
            try:
                portage_db = '/var/db/pkg'
                if os.path.isdir(portage_db):
                    count = 0
                    for cat in os.listdir(portage_db):
                        cat_path = os.path.join(portage_db, cat)
                        if os.path.isdir(cat_path):
                            count += len([pkg for pkg in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, pkg))])
                    if count > 0:
                        return f"{count} (portage)"
            except (IOError, OSError):
                pass
        except Exception:
            pass
        
        return None
    
    def _get_resolution(self) -> Optional[str]:
        """
        Get primary display resolution.
        
        Returns resolution string like "1920x1080" or None if unavailable.
        """
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            try:
                import ctypes
                from ctypes import util
                
                # Try to load CoreGraphics framework
                try:
                    core_graphics = ctypes.CDLL(util.find_library('CoreGraphics'))
                except (OSError, AttributeError):
                    # Try direct path as fallback
                    try:
                        core_graphics = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
                    except OSError:
                        return None
                
                # Get main display ID
                kCGDirectMainDisplay = 1
                
                # CGDisplayBounds signature: CGRect CGDisplayBounds(CGDirectDisplayID display)
                # CGRect is a struct with {x, y, width, height} as doubles
                class CGRect(ctypes.Structure):
                    _fields_ = [
                        ('x', ctypes.c_double),
                        ('y', ctypes.c_double),
                        ('width', ctypes.c_double),
                        ('height', ctypes.c_double),
                    ]
                
                # Get function
                CGDisplayBounds = core_graphics.CGDisplayBounds
                CGDisplayBounds.argtypes = [ctypes.c_uint32]
                CGDisplayBounds.restype = CGRect
                
                # Get bounds of main display
                bounds = CGDisplayBounds(kCGDirectMainDisplay)
                
                # Extract width and height (use int() to remove decimals)
                width = int(bounds.width)
                height = int(bounds.height)
                
                if width > 0 and height > 0:
                    return f"{width}x{height}"
            except Exception:
                # If anything fails, return None
                pass
        
        elif system == 'Linux':
            # On Linux, we'd need xrandr or Wayland APIs
            # For now, return None - resolution detection requires external tools
            pass
        
        elif system == 'Windows':
            try:
                import ctypes
                user32 = ctypes.windll.user32
                width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
                if width > 0 and height > 0:
                    return f"{width}x{height}"
            except Exception:
                pass
        
        return None
    
    def _get_local_ip(self) -> Optional[str]:
        """
        Get local IP address of primary network interface.
        
        Returns IP address string or None if unavailable.
        """
        try:
            # Connect to a remote address to determine local IP
            # We use a non-routable address that won't actually send packets
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Connect to a non-routable address (doesn't send packets)
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
                return ip
            except Exception:
                # Try alternative method: get hostname and resolve
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                if ip and ip != '127.0.0.1':
                    return ip
            finally:
                s.close()
        except Exception:
            pass
        
        # Try using psutil if available
        if HAS_PSUTIL:
            try:
                # Get default gateway interface
                net_if_addrs = psutil.net_if_addrs()
                # Try to find a non-loopback IPv4 address
                for interface_name, addresses in net_if_addrs.items():
                    if interface_name.startswith('lo'):
                        continue  # Skip loopback
                    for addr in addresses:
                        if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                            return addr.address
            except Exception:
                pass
        
        return None
    
    def _get_display_server(self) -> Optional[str]:
        """
        Get display server (Wayland/X11) on Linux.
        
        Returns "Wayland", "X11", or None.
        """
        system = platform.system()
        if system != 'Linux':
            return None
        
        # Check WAYLAND_DISPLAY environment variable
        if os.environ.get('WAYLAND_DISPLAY'):
            return 'Wayland'
        
        # Check DISPLAY environment variable (X11)
        if os.environ.get('DISPLAY'):
            return 'X11'
        
        # Try to detect from XDG_SESSION_TYPE
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        if session_type == 'wayland':
            return 'Wayland'
        elif session_type == 'x11':
            return 'X11'
        
        return None
    
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
        
        This method returns cached data collected at initialization.
        The data never changes during application execution, so this
        simply returns the cached dictionary.
        
        Returns:
            Dictionary containing all system information (cached from init).
        """
        return self._data.copy()
    
    def get_name(self) -> str:
        """
        Get the unique identifier for this collector.
        
        Returns:
            String identifier "system_info".
        """
        return "system_info"


