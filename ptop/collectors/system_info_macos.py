"""
macOS-specific system information collector.

This module provides platform-specific OS and host metadata collection for macOS.
"""

import platform
import subprocess
import json
import re
import os
import shutil
import ctypes
import plistlib
from ctypes import util
from typing import Dict, Any, Optional

from .system_info_base import PlatformSystemInfoCollectorBase


class MacOSSystemInfoCollector(PlatformSystemInfoCollectorBase):
    """
    Collects macOS-specific system information (OS and host metadata only).
    
    This sub-collector is only instantiated on macOS systems and returns
    structured data for OS and host information.
    """
    
    def __init__(self):
        """Initialize the macOS system info collector."""
        pass
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect macOS OS and host information.
        
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
                codename = self._codename_from_version(major_version)
            except (ValueError, IndexError):
                pass
        
        return {
            'name': name,
            'version': version,
            'codename': codename,
            'arch': arch
        }
    
    def _codename_from_version(self, major_version: int) -> Optional[str]:
        """Map macOS major version to codename."""
        codenames = {
            26: 'Tahoe',
            15: 'Sequoia',
            14: 'Sonoma',
            13: 'Ventura',
            12: 'Monterey',
            11: 'Big Sur',
            10: 'Catalina',
        }
        return codenames.get(major_version)
    
    def _collect_host_info(self) -> Dict[str, Any]:
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
                                    match = re.search(r'(\d+)x(\d+)', pixel_res)
                                    if match:
                                        width = int(match.group(1))
                                        height = int(match.group(2))
                                
                                if not width or not height:
                                    # Try parsing from pixels field like "4112 x 2658"
                                    if pixels:
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
        Derive Thunderbolt port count by enumerating Thunderbolt controllers and ports.
        
        Detects Thunderbolt 1, 2, 3, and 4 across different Mac models:
        - Apple Silicon: AppleUSB40XHCITypeCPort (Thunderbolt 4/USB4)
        - Intel Macs: IOThunderboltFamily controllers, system_profiler SPThunderboltDataType
        """
        thunderbolt_count = 0
        thunderbolt_version = None
        
        # Method 1: Try ioreg for Thunderbolt controllers (works for Intel and Apple Silicon)
        # Check for Thunderbolt 4/USB4 ports on Apple Silicon
        try:
            result = subprocess.run(
                ['ioreg', '-p', 'IOService', '-r', '-c', 'AppleUSB40XHCITypeCPort', '-w0'],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                port_matches = re.findall(r'class AppleUSB40XHCITypeCPort', result.stdout)
                if port_matches:
                    thunderbolt_count = len(port_matches)
                    thunderbolt_version = '4'  # USB4 ports are Thunderbolt 4 compatible
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        
        # Method 2: Try ioreg for Thunderbolt controllers (Thunderbolt 1, 2, 3 on Intel Macs)
        if thunderbolt_count == 0:
            try:
                result = subprocess.run(
                    ['ioreg', '-p', 'IOService', '-r', '-c', 'IOThunderboltController', '-w0'],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                if result.returncode == 0:
                    # Count Thunderbolt controllers
                    controller_matches = re.findall(r'class IOThunderboltController', result.stdout)
                    if controller_matches:
                        thunderbolt_count = len(controller_matches)
                        # Try to detect version from controller properties
                        # Thunderbolt 1/2 controllers often show up as IOThunderboltController
                        # We'll try to get version from system_profiler if available
                        thunderbolt_version = None  # Will be detected below if possible
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        
        # Method 3: Try system_profiler SPThunderboltDataType (best for version detection)
        if thunderbolt_count == 0 or thunderbolt_version is None:
            try:
                result = subprocess.run(
                    ['system_profiler', 'SPThunderboltDataType', '-json'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    try:
                        data = json.loads(result.stdout)
                        thunderbolt_items = data.get('SPThunderboltDataType', [])
                        
                        if thunderbolt_items:
                            # Count Thunderbolt controllers/buses
                            controllers_found = 0
                            detected_version = None
                            
                            def count_thunderbolt_items(items, depth=0):
                                nonlocal controllers_found, detected_version
                                if depth > 10:
                                    return
                                for item in items:
                                    name = item.get('_name', '').lower()
                                    # Look for controller or bus entries
                                    if 'thunderbolt' in name and ('controller' in name or 'bus' in name):
                                        controllers_found += 1
                                    # Try to detect version from name or version field
                                    version_field = item.get('spthunderbolt_version', '').lower()
                                    name_lower = name.lower()
                                    if 'thunderbolt 4' in name_lower or 'thunderbolt/usb4' in name_lower or 'usb4' in name_lower or '4' in version_field:
                                        detected_version = '4'
                                    elif 'thunderbolt 3' in name_lower or '3' in version_field:
                                        detected_version = '3'
                                    elif 'thunderbolt 2' in name_lower or '2' in version_field:
                                        detected_version = '2'
                                    elif 'thunderbolt 1' in name_lower or '1' in version_field:
                                        detected_version = '1'
                                    # Recursively check children
                                    children = item.get('_items', [])
                                    if children:
                                        count_thunderbolt_items(children, depth + 1)
                            
                            count_thunderbolt_items(thunderbolt_items)
                            
                            if controllers_found > 0:
                                thunderbolt_count = controllers_found
                                if detected_version:
                                    thunderbolt_version = detected_version
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        
        # Method 4: Fallback to system_profiler SPUSBDataType (for older systems)
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
                            if depth > 10:
                                return
                            for item in items:
                                name = item.get('_name', '').lower()
                                if 'thunderbolt' in name:
                                    thunderbolt_count += 1
                                    # Try to detect version from name
                                    if 'thunderbolt 4' in name or 'thunderbolt/usb4' in name or 'usb4' in name:
                                        thunderbolt_version = '4'
                                    elif 'thunderbolt 3' in name:
                                        thunderbolt_version = '3'
                                    elif 'thunderbolt 2' in name:
                                        thunderbolt_version = '2'
                                    elif 'thunderbolt 1' in name:
                                        thunderbolt_version = '1'
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
    
    def get_package_count(self) -> Optional[str]:
        """Get package count for macOS (Homebrew formulas and casks)."""
        package_strings = []
        
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
                    formula_count = 0
                    cask_count = 0
                    
                    # Count formulas
                    result = subprocess.run(
                        [brew_cmd, 'list', '--formula'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        packages = [line for line in result.stdout.strip().split('\n') if line.strip()]
                        formula_count = len(packages)
                    
                    # Count casks
                    result = subprocess.run(
                        [brew_cmd, 'list', '--cask'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        packages = [line for line in result.stdout.strip().split('\n') if line.strip()]
                        cask_count = len(packages)
                    
                    # Add formulas and casks as separate entries
                    if formula_count > 0:
                        package_strings.append(f"{formula_count} (brew)")
                    if cask_count > 0:
                        package_strings.append(f"{cask_count} (brew-cask)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
        except Exception:
            pass
        
        if package_strings:
            return ", ".join(package_strings)
        return None
    
    def get_resolution(self) -> Optional[str]:
        """
        Get primary display information in fastfetch-style format:
        'Display (Color LCD): 4112x2658 @ 2x in 16", 120 Hz [Built-in]'
        """
        try:
            import plistlib
            
            # Get display info from system_profiler XML output
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType', '-xml'],
                capture_output=True,
                text=False,
                timeout=5
            )
            if result.returncode != 0:
                return None
            
            try:
                plist = plistlib.loads(result.stdout)
                if not plist or len(plist) == 0 or '_items' not in plist[0]:
                    return None
                
                items = plist[0]['_items']
                for item in items:
                    if 'spdisplays_ndrvs' not in item:
                        continue
                    
                    displays = item['spdisplays_ndrvs']
                    # Find the main display (usually the first one)
                    for display in displays:
                        # Get display name
                        name = display.get('_name', '')
                        if not name:
                            continue
                        
                        # Get physical pixels (e.g., "4112 x 2658")
                        pixels = display.get('_spdisplays_pixels', '')
                        if not pixels or 'x' not in pixels:
                            continue
                        
                        pixel_parts = pixels.split('x')
                        if len(pixel_parts) != 2:
                            continue
                        
                        physical_width = pixel_parts[0].strip()
                        physical_height = pixel_parts[1].strip()
                        
                        # Get resolution string (e.g., "2056 x 1329 @ 120.00Hz")
                        resolution_str = display.get('_spdisplays_resolution', '')
                        refresh_hz = None
                        scale = 1
                        
                        if '@' in resolution_str:
                            # Extract refresh rate
                            refresh_part = resolution_str.split('@')[1].strip()
                            refresh_hz_str = refresh_part.replace('Hz', '').strip()
                            try:
                                refresh_hz = float(refresh_hz_str)
                            except ValueError:
                                pass
                            
                            # Calculate scale factor from logical/physical resolution
                            logical_part = resolution_str.split('@')[0].strip()
                            if 'x' in logical_part:
                                logical_parts = logical_part.split('x')
                                if len(logical_parts) == 2:
                                    try:
                                        logical_width = int(logical_parts[0].strip())
                                        physical_width_int = int(physical_width)
                                        if logical_width > 0:
                                            scale = int(round(physical_width_int / logical_width))
                                    except ValueError:
                                        pass
                        
                        # Get connection type
                        connection = display.get('spdisplays_connection_type', '')
                        attributes = []
                        if connection == 'spdisplays_internal':
                            attributes.append('Built-in')
                        elif 'external' in connection.lower():
                            attributes.append('External')
                        
                        # Get physical size (diagonal) using CoreGraphics
                        physical_size_str = ''
                        try:
                            core_graphics = ctypes.CDLL(util.find_library('CoreGraphics'))
                            if core_graphics:
                                kCGDirectMainDisplay = 1
                                
                                class CGSize(ctypes.Structure):
                                    _fields_ = [('width', ctypes.c_double), ('height', ctypes.c_double)]
                                
                                CGDisplayScreenSize = core_graphics.CGDisplayScreenSize
                                CGDisplayScreenSize.argtypes = [ctypes.c_uint32]
                                CGDisplayScreenSize.restype = CGSize
                                
                                size = CGDisplayScreenSize(kCGDirectMainDisplay)
                                # Convert mm to inches (1 inch = 25.4 mm) and calculate diagonal
                                diagonal = (size.width**2 + size.height**2)**0.5 / 25.4
                                physical_size_str = f"in {int(round(diagonal))}\""
                        except Exception:
                            pass
                        
                        # Build the format string
                        # Format: Display (Color LCD): 4112x2658 @ 2x in 16", 120 Hz [Built-in]
                        parts = []
                        parts.append(f"Display ({name}):")
                        parts.append(f"{physical_width}x{physical_height}")
                        
                        if scale > 1:
                            parts.append(f"@ {scale}x")
                        
                        # Combine physical size and refresh rate if both exist
                        if physical_size_str and refresh_hz:
                            parts.append(f"{physical_size_str}, {int(refresh_hz)} Hz")
                        elif physical_size_str:
                            parts.append(physical_size_str)
                        elif refresh_hz:
                            parts.append(f"{int(refresh_hz)} Hz")
                        
                        if attributes:
                            parts.append(f"[{', '.join(attributes)}]")
                        
                        return " ".join(parts)
                        
            except (plistlib.InvalidFileException, ValueError, KeyError):
                pass
                
        except Exception:
            pass
        
        return None
    
    def get_de_wm(self) -> Optional[str]:
        """Get desktop environment/window manager for macOS."""
        return 'Aqua'
    
    def get_gpu_info(self) -> Optional[str]:
        """Get GPU information for macOS in format: 'Apple M3 Pro (18) @ 1.38 GHz [Integrated]'."""
        try:
            import subprocess
            
            # Get GPU info from system_profiler
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return None
            
            gpu_name = None
            core_count = None
            
            for line in result.stdout.split('\n'):
                if 'Chipset Model:' in line:
                    gpu_name = line.split(':', 1)[1].strip()
                elif 'Total Number of Cores:' in line and not core_count:
                    # Extract number from line like "Total Number of Cores: 18"
                    parts = line.split(':')
                    if len(parts) == 2:
                        core_str = parts[1].strip().split()[0]  # Get first number
                        try:
                            core_count = int(core_str)
                        except ValueError:
                            pass
            
            if not gpu_name:
                return None
            
            # For Apple Silicon, GPU frequency is typically not directly available
            # We can try to get it from IOKit or use a default, but for now we'll skip frequency
            # and just show name, cores, and [Integrated] tag
            # Format: "Apple M3 Pro (18) @ 1.38 GHz [Integrated]"
            parts = [gpu_name]
            if core_count:
                parts.append(f"({core_count})")
            # Note: GPU frequency detection on macOS is complex and may not be reliable
            # If you have a way to get it, add it here. For now, we'll skip frequency.
            parts.append("[Integrated]")
            
            return ' '.join(parts)
        except Exception:
            return None
    
    def get_display_server(self) -> Optional[str]:
        """Get display server (not applicable on macOS, returns None)."""
        return None
    
    def get_cpu_model(self) -> str:
        """Get CPU model for macOS in format: 'Apple M3 Pro (12) @ 4.06 GHz'."""
        try:
            import subprocess
            
            # Get CPU name
            result = subprocess.run(
                ['sysctl', '-n', 'machdep.cpu.brand_string'],
                capture_output=True,
                text=True,
                timeout=2
            )
            cpu_name = result.stdout.strip() if result.returncode == 0 else None
            
            if not cpu_name or cpu_name == '':
                # Try system_profiler as fallback
                result = subprocess.run(
                    ['system_profiler', 'SPHardwareDataType'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Chip:' in line:
                            cpu_name = line.split(':', 1)[1].strip()
                            break
            
            if not cpu_name:
                cpu_name = platform.machine()
            
            # Get core count
            result = subprocess.run(
                ['sysctl', '-n', 'hw.ncpu'],
                capture_output=True,
                text=True,
                timeout=2
            )
            core_count = result.stdout.strip() if result.returncode == 0 else None
            
            # Get frequency
            freq_ghz = None
            try:
                import psutil
                freq = psutil.cpu_freq()
                if freq and freq.max:
                    freq_ghz = freq.max / 1000.0  # Convert MHz to GHz
            except Exception:
                pass
            
            # Format: "Apple M3 Pro (12) @ 4.06 GHz"
            parts = [cpu_name]
            if core_count:
                parts.append(f"({core_count})")
            if freq_ghz:
                parts.append(f"@ {freq_ghz:.2f} GHz")
            
            return ' '.join(parts)
        except Exception:
            # Fallback
            return platform.machine()
    
    def get_total_memory(self) -> int:
        """Get total system memory using psutil."""
        try:
            import psutil
            return psutil.virtual_memory().total
        except Exception:
            return 0
    
    def get_uptime(self) -> Optional[float]:
        """Get system uptime using psutil."""
        try:
            import psutil
            import time
            return time.time() - psutil.boot_time()
        except Exception:
            return None
    
    def get_cpu_frequency(self) -> Optional[float]:
        """Get CPU frequency using psutil."""
        try:
            import psutil
            freq = psutil.cpu_freq()
            if freq:
                return freq.current if freq.current else freq.max
        except Exception:
            pass
        return None
    
    def get_shell(self) -> Optional[str]:
        """Get default shell for macOS."""
        shell = os.environ.get('SHELL')
        if shell:
            return os.path.basename(shell)
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
    
    def get_terminal(self) -> Optional[str]:
        """Get terminal emulator for macOS."""
        term = os.environ.get('TERM_PROGRAM') or os.environ.get('TERMINAL_EMULATOR')
        if term:
            return term
        return None
    
    def get_local_ip(self) -> Optional[str]:
        """Get local IP address for macOS."""
        try:
            import socket
            import psutil
            # Try using psutil first (cross-platform)
            net_if_addrs = psutil.net_if_addrs()
            for interface_name, addresses in net_if_addrs.items():
                if interface_name.startswith('lo'):
                    continue
                for addr in addresses:
                    if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                        return addr.address
        except Exception:
            pass
        try:
            import socket
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
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for macOS."""
        disks = []
        try:
            import psutil
            import os
            
            partitions = psutil.disk_partitions()
            for partition in partitions:
                mountpoint = partition.mountpoint
                fstype = partition.fstype
                
                # Skip virtual filesystems and special mounts
                if fstype in ('proc', 'sysfs', 'devtmpfs', 'tmpfs', 'devfs', 'procfs', 'linprocfs', 'fdescfs', 'binfmt_misc', 'autofs', 'cgroup', 'cgroup2', 'pstore', 'bpf', 'tracefs', 'debugfs', 'securityfs', 'hugetlbfs', 'mqueue', 'overlay', 'rpc_pipefs'):
                    continue
                
                # Skip if mountpoint doesn't exist
                if not os.path.exists(mountpoint):
                    continue
                
                # Skip system volumes that are part of the root filesystem
                if mountpoint.startswith('/System/Volumes/'):
                    continue
                
                try:
                    disk = psutil.disk_usage(mountpoint)
                    total = disk.total
                    # Calculate actual used space (total - free) to account for APFS purgeable space
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
                    
                    # On macOS, external disks are mounted under /Volumes
                    if mountpoint.startswith('/Volumes/'):
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
            
            # Sort disks: root first, then by mountpoint
            disks.sort(key=lambda x: (x['mountpoint'] != '/', x['mountpoint']))
        except Exception:
            pass
        
        return disks
    
    def get_battery(self) -> Optional[Dict[str, Any]]:
        """Get battery information for macOS using psutil."""
        try:
            import psutil
            
            battery = psutil.sensors_battery()
            if battery is None:
                return None
            
            # psutil.sensors_battery() returns a named tuple with:
            # - percent: battery percentage (0-100)
            # - secsleft: time left in seconds (None if unknown/calculating)
            # - power_plugged: True if AC power connected, False if on battery
            
            return {
                'percent': battery.percent,
                'power_plugged': battery.power_plugged,
                'secsleft': battery.secsleft if battery.secsleft is not None and battery.secsleft >= 0 else None
            }
        except Exception:
            return None

