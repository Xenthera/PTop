"""
Mock CPU collector for testing.

This collector returns random CPU metrics that match the structure
of the real CPUCollector, useful for testing UI without actual hardware.
"""

import random
import time
from typing import Dict, Any, List, Tuple
from ..collectors.base import BaseCollector


class MockCPUCollector(BaseCollector):
    """
    Mock CPU collector that returns random CPU metrics.
    
    This collector generates realistic-looking random data for testing
    the UI without requiring actual CPU hardware or system access.
    """
    
    def __init__(self, num_cores: int = 8):
        """
        Initialize the mock CPU collector.
        
        Args:
            num_cores: Number of CPU cores to simulate (default: 8)
        """
        self.num_cores = num_cores
        self.start_time = time.time()
        self._cpu_name = "Mock Intel Core i7-12700K"
        self._cpu_name_simple = "i7-12700K"
        self._base_frequencies = [random.randint(3000, 4500) for _ in range(num_cores)]
        self._usage_history = [[0.0] for _ in range(num_cores)]
    
    def get_name(self) -> str:
        """Get the unique identifier for this collector."""
        return "cpu"
    
    def _get_random_usage(self, base: float, variation: float = 20.0) -> float:
        """Generate random usage with some variation around a base value."""
        value = base + random.uniform(-variation, variation)
        return max(0.0, min(100.0, value))
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect mock CPU metrics with random values.
        
        Returns:
            Dictionary containing CPU metrics matching the real collector structure.
        """
        # Generate overall CPU usage (0-100%)
        overall_usage = random.uniform(10.0, 80.0)
        
        # Generate per-core usage with some correlation to overall
        per_core_usage = []
        for i in range(self.num_cores):
            # Add some variation per core
            core_base = overall_usage + random.uniform(-15.0, 15.0)
            core_usage = self._get_random_usage(core_base, 10.0)
            per_core_usage.append(int(round(core_usage)))
            self._usage_history[i].append(core_usage)
            # Keep history limited
            if len(self._usage_history[i]) > 100:
                self._usage_history[i].pop(0)
        
        # Generate frequencies with slight variation
        frequencies = []
        for base_freq in self._base_frequencies:
            freq = base_freq + random.randint(-200, 200)
            frequencies.append(max(1000, freq))
        
        # Current frequency string
        avg_freq = sum(frequencies) // len(frequencies)
        current_freq_string = f"{avg_freq} MHz"
        
        # Generate load averages (simulated)
        load_1min = overall_usage / 100.0 * self.num_cores * random.uniform(0.8, 1.2)
        load_5min = load_1min * random.uniform(0.9, 1.1)
        load_15min = load_5min * random.uniform(0.95, 1.05)
        load_average = (round(load_1min, 2), round(load_5min, 2), round(load_15min, 2))
        
        # Generate temperature (30-75°C range)
        cpu_temp = random.uniform(35.0, 65.0)
        per_core_temp = [cpu_temp + random.uniform(-5.0, 5.0) for _ in range(self.num_cores)]
        temperature = {
            'current': round(cpu_temp, 1),
            'per_core': [round(t, 1) for t in per_core_temp]
        }
        
        # Generate power consumption (20-80W range)
        power = random.uniform(25.0, 70.0)
        
        # Generate uptime string
        uptime_seconds = int(time.time() - self.start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        if days > 0:
            uptime = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            uptime = f"{hours}h {minutes}m"
        else:
            uptime = f"{minutes}m"
        
        return {
            'name': self._cpu_name,
            'name_simple': self._cpu_name_simple,
            'overall': round(overall_usage, 1),
            'per_core': per_core_usage,
            'frequencies': frequencies,
            'current_frequency': current_freq_string,
            'load_average': load_average,
            'temperature': temperature,
            'power': round(power, 1),
            'uptime': uptime,
            'count_logical': self.num_cores,
            'count_physical': self.num_cores // 2,  # Assume hyperthreading
        }






