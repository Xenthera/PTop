"""
Linux-specific system information collector.

This module provides platform-specific OS and host metadata collection for Linux.
"""

import platform
import os
import subprocess
import shutil
import socket
import time
from typing import Dict, Any, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .system_info_base import PlatformSystemInfoCollectorBase


class LinuxSystemInfoCollector(PlatformSystemInfoCollectorBase):
    """
    Collects Linux-specific system information (OS and host metadata only).
    
    This sub-collector is only instantiated on Linux systems and returns
    structured data for OS and host information.
    """
    
    def __init__(self):
        """Initialize the Linux system info collector."""
        pass
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect Linux OS and host information.
        
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
    
    def _collect_host_info(self) -> Dict[str, Any]:
        """Collect Linux host information from DMI sysfs."""
        model = None
        identifier = None
        
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
            'details': None
        }
    
    def get_package_count(self) -> Optional[str]:
        """Get package count for Linux (multiple package managers)."""
        package_strings = []
        
        try:
            # Primary package managers (usually only one exists)
            # Try pacman (Arch)
            try:
                pacman_db = '/var/lib/pacman/local'
                if os.path.isdir(pacman_db):
                    count = len([d for d in os.listdir(pacman_db) if os.path.isdir(os.path.join(pacman_db, d))])
                    if count > 0:
                        package_strings.append(f"{count} (pacman)")
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
                        package_strings.append(f"{count} (apt)")
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
                        package_strings.append(f"{count} (apk)")
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
                            package_strings.append(f"{count} (dnf)")
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
                            package_strings.append(f"{count} (yum)")
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
                            package_strings.append(f"{count} (rpm)")
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
                            package_strings.append(f"{count} (zypper)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try portage (Gentoo)
            try:
                portage_db = '/var/db/pkg'
                if os.path.isdir(portage_db):
                    count = 0
                    for cat in os.listdir(portage_db):
                        cat_path = os.path.join(portage_db, cat)
                        if os.path.isdir(cat_path):
                            count += len([pkg for pkg in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, pkg))])
                    if count > 0:
                        package_strings.append(f"{count} (portage)")
            except (IOError, OSError):
                pass
            
            # Secondary package managers (can coexist with primary)
            # Try snap
            snap_cmd = shutil.which('snap')
            if snap_cmd:
                try:
                    result = subprocess.run(
                        [snap_cmd, 'list'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip() and not line.startswith('Name')]
                        count = len(lines)
                        if count > 0:
                            package_strings.append(f"{count} (snap)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
            
            # Try flatpak
            flatpak_cmd = shutil.which('flatpak')
            if flatpak_cmd:
                try:
                    result = subprocess.run(
                        [flatpak_cmd, 'list'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        lines = [line for line in result.stdout.strip().split('\n') if line.strip()]
                        count = len(lines)
                        if count > 0:
                            package_strings.append(f"{count} (flatpak)")
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    pass
        except Exception:
            pass
        
        if package_strings:
            return ", ".join(package_strings)
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_resolution(self) -> Optional[str]:
        """Get primary display resolution for Linux (not implemented, returns None)."""
        # On Linux, we'd need xrandr or Wayland APIs
        # For now, return None - resolution detection requires external tools
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_display_server(self) -> Optional[str]:
        """Get display server for Linux (Wayland/X11)."""
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
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_gpu_info(self) -> Optional[str]:
        """Get GPU information for Linux."""
        try:
            # Check for NVIDIA
            nvidia_path = '/sys/class/drm/card0/device/uevent'
            try:
                with open(nvidia_path, 'r') as f:
                    for line in f:
                        if line.startswith('PCI_ID='):
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
        
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_de_wm(self) -> Optional[str]:
        """Get desktop environment/window manager for Linux."""
        # Check XDG environment variables
        de = os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION')
        if de:
            de = de.split(':')[0].split('/')[0]  # Handle "GNOME:GNOME-Classic" or "gnome/xorg"
            return de
        
        # Try alternative environment variables
        de = os.environ.get('XDG_SESSION_DESKTOP') or os.environ.get('GDMSESSION')
        if de:
            return de.split(':')[0].split('/')[0]
        
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_cpu_model(self) -> str:
        """Get CPU model for Linux."""
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
        return platform.machine()
    
    def get_total_memory(self) -> int:
        """Get total system memory for Linux."""
        if HAS_PSUTIL:
            try:
                return psutil.virtual_memory().total
            except Exception:
                pass
        
        # Fallback to /proc/meminfo
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
    
    def get_uptime(self) -> Optional[float]:
        """Get system uptime for Linux."""
        if HAS_PSUTIL:
            try:
                return time.time() - psutil.boot_time()
            except Exception:
                pass
        
        # Fallback to /proc/uptime
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
                return uptime_seconds
        except (IOError, OSError, ValueError, IndexError):
            pass
        
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_cpu_frequency(self) -> Optional[float]:
        """Get CPU frequency for Linux."""
        if HAS_PSUTIL:
            try:
                freq = psutil.cpu_freq()
                if freq:
                    return freq.current if freq.current else freq.max
            except Exception:
                pass
        
        # Fallback to /proc/cpuinfo
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
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_shell(self) -> Optional[str]:
        """Get default shell for Linux."""
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
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_terminal(self) -> Optional[str]:
        """Get terminal emulator for Linux."""
        term = os.environ.get('TERM_PROGRAM') or os.environ.get('TERMINAL_EMULATOR')
        if term:
            return term
        
        term = os.environ.get('COLORTERM') or os.environ.get('XTERM_VERSION')
        if term:
            return term
        
        term = os.environ.get('TERM')
        if term and term not in ['xterm', 'xterm-256color', 'screen', 'tmux', 'dumb', 'unknown']:
            if len(term) > 4 and not term.startswith('xterm'):
                return term
        
        # Try to read from /proc/self/comm or parent process
        try:
            ppid = os.getppid()
            comm_path = f'/proc/{ppid}/comm'
            try:
                with open(comm_path, 'r') as f:
                    parent_comm = f.read().strip()
                    if any(t in parent_comm.lower() for t in ['gnome-terminal', 'konsole', 'xterm', 'alacritty', 'kitty', 'wezterm', 'foot']):
                        return parent_comm
            except (IOError, OSError):
                pass
        except Exception:
            pass
        
        return None
    
    def get_disks(self) -> list:
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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
    
    def get_local_ip(self) -> Optional[str]:
        """Get local IP address for Linux."""
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
        """Get list of mounted disk volumes for Linux."""
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
                    
                    # Check if it's an external/removable disk (not a standard system mount)
                    standard_mounts = ['/', '/boot', '/home', '/usr', '/var', '/tmp', '/opt', '/srv', '/root']
                    if mountpoint not in standard_mounts and not mountpoint.startswith('/run/'):
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
        """Get battery information for Linux using psutil."""
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

