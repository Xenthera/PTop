"""
Mock system info collector for testing.

This collector returns mock system information that matches the structure
of the real SystemInfoCollector, useful for testing UI without actual system access.
"""

import random
import time
from typing import Dict, Any, Optional
from ..collectors.base import BaseCollector


class MockSystemInfoCollector(BaseCollector):
    """
    Mock system info collector that returns mock system information.
    
    This collector generates realistic-looking mock data for testing
    the UI without requiring actual system access.
    """
    
    def __init__(self):
        """Initialize the mock system info collector."""
        self.start_time = time.time()
        
        # Randomly select OS and package managers based on OS
        # OS-specific package managers (primary and secondary)
        os_primary_managers = {
            'Linux': ['pacman', 'apt', 'rpm', 'portage', 'zypper', 'dnf', 'yum', 'apk'],
            'macOS': ['brew'],
            'Windows': ['winget', 'chocolatey', 'scoop'],
            'FreeBSD': ['pkg', 'ports'],
            'OpenBSD': ['pkg_add'],
            'NetBSD': ['pkgin', 'pkgsrc'],
            'Unix': ['pkg', 'ports']
        }
        
        # Secondary package managers (commonly installed alongside primary ones)
        os_secondary_managers = {
            'Linux': ['snap', 'flatpak', 'pip', 'npm', 'cargo'],
            'macOS': ['pip', 'npm', 'cargo'],
            'Windows': ['pip', 'npm', 'cargo'],
            'FreeBSD': [],
            'OpenBSD': [],
            'NetBSD': [],
            'Unix': []
        }
        
        # Generate realistic package counts based on manager
        package_count_ranges = {
            'pacman': (500, 2000),      # Arch
            'apt': (1000, 5000),       # Debian/Ubuntu
            'rpm': (800, 3000),        # RPM-based
            'dnf': (800, 3000),        # Fedora
            'yum': (800, 3000),        # CentOS/RHEL
            'zypper': (800, 3000),     # openSUSE
            'portage': (200, 1500),    # Gentoo
            'apk': (500, 2000),        # Alpine
            'snap': (10, 50),          # Snap packages
            'flatpak': (5, 30),        # Flatpak packages
            'pip': (20, 200),          # Python packages
            'npm': (50, 500),          # Node packages
            'cargo': (10, 100),        # Rust packages
            'brew': (50, 500),         # Homebrew
            'winget': (100, 1000),     # Windows Package Manager
            'chocolatey': (50, 300),   # Chocolatey
            'scoop': (50, 200),        # Scoop
            'pkg': (500, 2000),        # FreeBSD pkg
            'ports': (200, 1500),      # FreeBSD ports
            'pkg_add': (500, 2000),    # OpenBSD
            'pkgin': (500, 2000),      # NetBSD
            'pkgsrc': (200, 1500),     # NetBSD pkgsrc
        }
        
        # Randomly select OS
        selected_os = random.choice(['Linux', 'macOS', 'Windows', 'FreeBSD', 'OpenBSD', 'NetBSD'])
        primary_managers = os_primary_managers.get(selected_os, ['pkg'])
        secondary_managers = os_secondary_managers.get(selected_os, [])
        
        # Select package managers: always 1 primary, optionally 0-3 secondary (especially for Linux)
        selected_primary = random.choice(primary_managers)
        selected_managers = [selected_primary]
        
        # For Linux, more likely to have multiple managers; for others, less likely
        if selected_os == 'Linux':
            num_secondary = random.choices([0, 1, 2, 3], weights=[20, 40, 30, 10])[0]
        else:
            num_secondary = random.choices([0, 1, 2], weights=[60, 30, 10])[0]
        
        if num_secondary > 0 and secondary_managers:
            # Randomly select secondary managers without replacement
            available_secondary = secondary_managers.copy()
            random.shuffle(available_secondary)
            selected_managers.extend(available_secondary[:num_secondary])
        
        # Generate package counts for each selected manager
        package_strings = []
        for manager in selected_managers:
            count_range = package_count_ranges.get(manager, (100, 1000))
            package_count = random.randint(count_range[0], count_range[1])
            package_strings.append(f"{package_count} ({manager})")
        
        # Format as comma-separated list: "1234 (apt), 56 (snap), 12 (flatpak)"
        packages_str = ", ".join(package_strings)
        
        # Mock static data based on selected OS (collected once, like real collector)
        if selected_os == 'Linux':
            os_data = {
                'os_name': 'Linux',
                'os_version': random.choice(['Ubuntu 22.04.3 LTS', 'Arch Linux', 'Fedora 39', 'Debian 12']),
                'kernel': '5.15.0-91-generic',
                'de_wm': random.choice(['GNOME 42.5', 'KDE Plasma 5.27', 'XFCE 4.18']),
                'display_server': random.choice(['X11', 'Wayland']),
            }
        elif selected_os == 'macOS':
            os_data = {
                'os_name': 'macOS',
                'os_version': random.choice(['14.2', '13.6', '12.7']),
                'kernel': '23.1.0',
                'de_wm': 'Aqua',
                'display_server': None,
            }
        elif selected_os == 'Windows':
            os_data = {
                'os_name': 'Windows',
                'os_version': random.choice(['11', '10']),
                'kernel': '10.0.22621',
                'de_wm': 'Windows',
                'display_server': None,
            }
        else:  # BSD
            os_data = {
                'os_name': selected_os,
                'os_version': random.choice(['14.0', '13.2', '10.0']),
                'kernel': selected_os,
                'de_wm': random.choice(['XFCE', 'KDE', None]),
                'display_server': random.choice(['X11', None]),
            }
        
        self._data = {
            **os_data,
            'arch': random.choice(['x86_64', 'arm64', 'aarch64']),
            'hostname': 'mock-server',
            'cpu': 'Mock Intel Core i7-12700K',
            'memory_total': 32 * 1024 * 1024 * 1024,  # 32 GiB in bytes
            'uptime': None,  # Will be calculated dynamically
            'cpu_freq': 3700.0,  # MHz
            'gpu': 'NVIDIA GeForce RTX 3080',
            'shell': random.choice(['/bin/bash', '/bin/zsh', '/bin/fish']),
            'terminal': random.choice(['gnome-terminal', 'alacritty', 'kitty', 'wezterm']),
            'packages': packages_str,
            'resolution': '1920x1080',
            'local_ip': '192.168.1.100',
            'machine_model': 'Mock Laptop Model XYZ'
        }
    
    def get_name(self) -> str:
        """Get the unique identifier for this collector."""
        return "system_info"
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect mock system information.
        
        Returns:
            Dictionary containing system information matching the real collector structure.
        """
        # Calculate uptime dynamically (time since collector was created)
        uptime_seconds = time.time() - self.start_time
        self._data['uptime'] = uptime_seconds
        
        # Return a copy of the cached data (matching real collector behavior)
        return self._data.copy()


