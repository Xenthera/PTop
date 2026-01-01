"""
Mock GPU collector for testing.

This collector returns random GPU metrics that match the structure
of the real GPUCollector, useful for testing UI without actual hardware.
"""

import random
from typing import Dict, Any, List
from ..collectors.base import BaseCollector


class MockGPUCollector(BaseCollector):
    """
    Mock GPU collector that returns random GPU metrics.
    
    This collector generates realistic-looking random data for testing
    the UI without requiring actual GPU hardware or system access.
    """
    
    def __init__(self, num_gpus: int = 1):
        """
        Initialize the mock GPU collector.
        
        Args:
            num_gpus: Number of GPUs to simulate (default: 1)
        """
        self.num_gpus = num_gpus
        self._gpu_names = [
            "NVIDIA GeForce RTX 4090",
            "AMD Radeon RX 7900 XTX",
            "Intel Arc A770"
        ]
        self._gpu_names_simple = [
            "RTX 4090",
            "RX 7900 XTX",
            "Arc A770"
        ]
        # Select GPU names for each GPU
        self.selected_names = []
        self.selected_names_simple = []
        for i in range(num_gpus):
            idx = i % len(self._gpu_names)
            self.selected_names.append(self._gpu_names[idx])
            self.selected_names_simple.append(self._gpu_names_simple[idx])
    
    def get_name(self) -> str:
        """Get the unique identifier for this collector."""
        return "gpu"
    
    def _get_gpu_name_simple(self, gpu_name: str) -> str:
        """Get simplified GPU name."""
        if gpu_name in self._gpu_names:
            idx = self._gpu_names.index(gpu_name)
            return self._gpu_names_simple[idx]
        return gpu_name
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect mock GPU metrics with random values.
        
        Returns:
            Dictionary containing GPU metrics matching the real collector structure.
        """
        if self.num_gpus == 0:
            return {
                'count': 0,
                'gpus': [],
                'overall': {
                    'usage': 0.0,
                    'memory_usage_percent': 0.0
                }
            }
        
        gpus = []
        total_usage = 0.0
        total_memory_usage = 0.0
        valid_usage_count = 0
        valid_memory_count = 0
        
        for i in range(self.num_gpus):
            # Generate GPU usage (0-100%)
            gpu_usage = random.randint(0, 95)
            
            # Generate memory info
            total_memory_mb = random.choice([8192, 12288, 16384, 24576])  # 8GB, 12GB, 16GB, 24GB
            memory_usage_percent = random.randint(20, 80)
            used_memory_mb = int(total_memory_mb * memory_usage_percent / 100.0)
            
            # Generate temperature (30-85°C range)
            temperature = random.randint(35, 80)
            
            # Generate power consumption (50-450W range, depending on GPU)
            if "RTX 4090" in self.selected_names[i]:
                power = random.uniform(200.0, 450.0)
            elif "RX 7900" in self.selected_names[i]:
                power = random.uniform(150.0, 350.0)
            else:
                power = random.uniform(50.0, 200.0)
            
            gpu_data = {
                'name': self.selected_names[i],
                'name_simple': self.selected_names_simple[i],
                'usage': gpu_usage,
                'memory': {
                    'used_mb': used_memory_mb,
                    'total_mb': total_memory_mb,
                    'usage_percent': memory_usage_percent
                },
                'temperature': temperature,
                'power': round(power, 1)
            }
            
            gpus.append(gpu_data)
            
            total_usage += gpu_usage
            valid_usage_count += 1
            
            total_memory_usage += memory_usage_percent
            valid_memory_count += 1
        
        # Calculate overall averages
        overall_usage = (total_usage / valid_usage_count) if valid_usage_count > 0 else 0.0
        overall_memory_usage = (total_memory_usage / valid_memory_count) if valid_memory_count > 0 else 0.0
        
        return {
            'count': len(gpus),
            'gpus': gpus,
            'overall': {
                'usage': round(overall_usage),
                'memory_usage_percent': round(overall_memory_usage)
            }
        }

