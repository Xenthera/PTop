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
        
        # Mock static data (collected once, like real collector)
        self._data = {
            'os_name': 'Linux',
            'os_version': 'Ubuntu 22.04.3 LTS',
            'kernel': '5.15.0-91-generic',
            'arch': 'x86_64',
            'hostname': 'mock-server',
            'cpu': 'Mock Intel Core i7-12700K',
            'memory_total': 32 * 1024 * 1024 * 1024,  # 32 GiB in bytes
            'uptime': None,  # Will be calculated dynamically
            'cpu_freq': 3700.0,  # MHz
            'gpu': 'NVIDIA GeForce RTX 3080',
            'shell': '/bin/bash',
            'de_wm': 'GNOME 42.5',
            'terminal': 'gnome-terminal',
            'packages': 2847,
            'resolution': '1920x1080',
            'local_ip': '192.168.1.100',
            'display_server': 'X11',
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


