"""
GPU metrics collector.

This module collects comprehensive GPU usage statistics using multiple backends.
Supports NVIDIA NVML, AMD ROCm, Intel sysfs, and vendor CLI fallbacks.
"""

import platform
import subprocess
import os
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod

try:
    import logging
    logger = logging.getLogger(__name__)
except ImportError:
    # Fallback if logging not available
    class NullLogger:
        def debug(self, *args, **kwargs): pass
    logger = NullLogger()

from .base import BaseCollector


@dataclass
class GpuStats:
    """
    Common GPU statistics structure.
    
    All fields are nullable to handle partial data availability.
    """
    name: Optional[str] = None
    utilization_percent: Optional[int] = None  # 0-100
    temperature_c: Optional[int] = None
    memory_used_bytes: Optional[int] = None
    memory_total_bytes: Optional[int] = None
    power_watts: Optional[float] = None


class GpuBackend(ABC):
    """Abstract base class for GPU backend implementations."""
    
    @abstractmethod
    def get_stats(self) -> List[GpuStats]:
        """
        Get GPU statistics for all detected GPUs.
        
        Returns:
            List of GpuStats, one per GPU. Empty list if no GPUs or error.
        """
        pass
    
    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """
        Check if this backend is available on the system.
        
        Returns:
            True if backend can be initialized, False otherwise.
        """
        pass


class NvmlBackend(GpuBackend):
    """NVIDIA NVML backend using pynvml."""
    
    def __init__(self):
        """Initialize NVML backend."""
        self._nvml_initialized = False
        self._gpu_handles: List = []
        self._gpu_names: List[str] = []
        
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_initialized = True
            self.pynvml = pynvml
            
            gpu_count = pynvml.nvmlDeviceGetCount()
            for i in range(gpu_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                self._gpu_handles.append(handle)
                try:
                    name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode('utf-8')
                    self._gpu_names.append(name)
                except Exception:
                    self._gpu_names.append(f"GPU {i}")
            
            logger.debug(f"NVML backend initialized: {gpu_count} GPU(s)")
        except Exception as e:
            logger.debug(f"NVML backend initialization failed: {e}")
            self._nvml_initialized = False
    
    @staticmethod
    def is_available() -> bool:
        """Check if NVML backend is available."""
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            pynvml.nvmlShutdown()
            return count > 0
        except Exception:
            return False
    
    def get_stats(self) -> List[GpuStats]:
        """Get GPU statistics using NVML."""
        if not self._nvml_initialized:
            return []
        
        stats_list = []
        pynvml = self.pynvml
        
        for i, handle in enumerate(self._gpu_handles):
            stats = GpuStats()
            stats.name = self._gpu_names[i] if i < len(self._gpu_names) else f"GPU {i}"
            
            try:
                # Utilization
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                stats.utilization_percent = util.gpu
            except Exception:
                pass
            
            try:
                # Memory
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                stats.memory_used_bytes = mem_info.used
                stats.memory_total_bytes = mem_info.total
            except Exception:
                pass
            
            try:
                # Temperature
                stats.temperature_c = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )
            except Exception:
                pass
            
            try:
                # Power
                power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
                stats.power_watts = power_mw / 1000.0
            except Exception:
                pass
            
            stats_list.append(stats)
        
        return stats_list
    
    def __del__(self):
        """Cleanup: shutdown NVML if initialized."""
        if self._nvml_initialized:
            try:
                self.pynvml.nvmlShutdown()
            except Exception:
                pass


class RocmBackend(GpuBackend):
    """AMD ROCm backend using rocm-smi."""
    
    def __init__(self):
        """Initialize ROCm backend."""
        self._gpu_count = 0
        self._gpu_names: List[str] = []
        self._rocm_smi_path = self._find_rocm_smi()
        
        if self._rocm_smi_path:
            try:
                # Try to get GPU count and names
                result = subprocess.run(
                    [self._rocm_smi_path, '--list'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    # Count non-empty lines (each GPU is typically one line)
                    self._gpu_count = len([l for l in lines if l.strip()])
                    # Try to get names
                    for i in range(self._gpu_count):
                        name_result = subprocess.run(
                            [self._rocm_smi_path, '-i', str(i), '-n'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if name_result.returncode == 0:
                            name = name_result.stdout.strip()
                            self._gpu_names.append(name if name else f"AMD GPU {i}")
                        else:
                            self._gpu_names.append(f"AMD GPU {i}")
                    
                    logger.debug(f"ROCm backend initialized: {self._gpu_count} GPU(s)")
            except Exception as e:
                logger.debug(f"ROCm backend initialization failed: {e}")
                self._rocm_smi_path = None
    
    @staticmethod
    def _find_rocm_smi() -> Optional[str]:
        """Find rocm-smi executable."""
        common_paths = [
            '/opt/rocm/bin/rocm-smi',
            '/usr/bin/rocm-smi',
            'rocm-smi'  # Let subprocess find it in PATH
        ]
        for path in common_paths:
            try:
                result = subprocess.run(
                    [path, '--version'],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None
    
    @staticmethod
    def is_available() -> bool:
        """Check if ROCm backend is available."""
        backend = RocmBackend()
        return backend._rocm_smi_path is not None and backend._gpu_count > 0
    
    def get_stats(self) -> List[GpuStats]:
        """Get GPU statistics using rocm-smi."""
        if not self._rocm_smi_path or self._gpu_count == 0:
            return []
        
        stats_list = []
        
        for i in range(self._gpu_count):
            stats = GpuStats()
            stats.name = self._gpu_names[i] if i < len(self._gpu_names) else f"AMD GPU {i}"
            
            try:
                # Utilization (GPU use %)
                result = subprocess.run(
                    [self._rocm_smi_path, '-i', str(i), '-u', '-t'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # Parse output like "GPU[0]          : 45 %"
                    for line in result.stdout.split('\n'):
                        if '%' in line and 'GPU' in line:
                            try:
                                parts = line.split('%')
                                if parts:
                                    percent_str = parts[0].strip().split()[-1]
                                    stats.utilization_percent = int(float(percent_str))
                            except (ValueError, IndexError):
                                pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            try:
                # Memory (used and total)
                result = subprocess.run(
                    [self._rocm_smi_path, '-i', str(i), '--showmemuse', '-t'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # Parse output for memory info
                    # Format varies, try to extract memory values
                    for line in result.stdout.split('\n'):
                        if 'Memory' in line or 'MB' in line or 'GB' in line:
                            # Try to parse memory values (implementation depends on exact format)
                            # This is a simplified parser
                            import re
                            # Look for patterns like "1234 MB" or "1.2 GB"
                            mem_match = re.search(r'(\d+(?:\.\d+)?)\s*(MB|GB)', line, re.IGNORECASE)
                            if mem_match:
                                value = float(mem_match.group(1))
                                unit = mem_match.group(2).upper()
                                bytes_val = int(value * (1024**2 if unit == 'MB' else 1024**3))
                                # Assume we're getting used memory, try to find total separately
                                if stats.memory_used_bytes is None:
                                    stats.memory_used_bytes = bytes_val
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            try:
                # Temperature
                result = subprocess.run(
                    [self._rocm_smi_path, '-i', str(i), '-t'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Temperature' in line or 'Temp' in line:
                            import re
                            temp_match = re.search(r'(\d+)\s*C', line, re.IGNORECASE)
                            if temp_match:
                                stats.temperature_c = int(temp_match.group(1))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            try:
                # Power
                result = subprocess.run(
                    [self._rocm_smi_path, '-i', str(i), '-P'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Power' in line or 'W' in line:
                            import re
                            power_match = re.search(r'(\d+(?:\.\d+)?)\s*W', line, re.IGNORECASE)
                            if power_match:
                                stats.power_watts = float(power_match.group(1))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            stats_list.append(stats)
        
        return stats_list


class IntelSysfsBackend(GpuBackend):
    """Intel GPU backend using sysfs."""
    
    def __init__(self):
        """Initialize Intel sysfs backend."""
        self._gpu_paths: List[str] = []
        self._gpu_names: List[str] = []
        
        # Probe for Intel GPUs in /sys/class/drm
        try:
            drm_path = '/sys/class/drm'
            if os.path.isdir(drm_path):
                for entry in os.listdir(drm_path):
                    if entry.startswith('card') and entry[4:].isdigit():
                        card_path = os.path.join(drm_path, entry)
                        gt_busy_path = os.path.join(card_path, 'gt_busy_percent')
                        
                        # Check if this is an Intel GPU (has gt_busy_percent)
                        if os.path.isfile(gt_busy_path) and os.access(gt_busy_path, os.R_OK):
                            self._gpu_paths.append(card_path)
                            # Try to get name from device path
                            try:
                                device_path = os.path.join(card_path, 'device', 'uevent')
                                if os.path.isfile(device_path):
                                    with open(device_path, 'r') as f:
                                        for line in f:
                                            if line.startswith('DRIVER='):
                                                driver = line.split('=', 1)[1].strip()
                                                if 'i915' in driver.lower():
                                                    self._gpu_names.append(f"Intel GPU {len(self._gpu_paths) - 1}")
                                                else:
                                                    self._gpu_names.append(f"GPU {len(self._gpu_paths) - 1}")
                                                break
                                            else:
                                                self._gpu_names.append(f"Intel GPU {len(self._gpu_paths) - 1}")
                                else:
                                    self._gpu_names.append(f"Intel GPU {len(self._gpu_paths) - 1}")
                            except Exception:
                                self._gpu_names.append(f"Intel GPU {len(self._gpu_paths) - 1}")
                
                if self._gpu_paths:
                    logger.debug(f"Intel sysfs backend initialized: {len(self._gpu_paths)} GPU(s)")
        except Exception as e:
            logger.debug(f"Intel sysfs backend initialization failed: {e}")
    
    @staticmethod
    def is_available() -> bool:
        """Check if Intel sysfs backend is available."""
        try:
            drm_path = '/sys/class/drm'
            if not os.path.isdir(drm_path):
                return False
            
            for entry in os.listdir(drm_path):
                if entry.startswith('card') and entry[4:].isdigit():
                    card_path = os.path.join(drm_path, entry)
                    gt_busy_path = os.path.join(card_path, 'gt_busy_percent')
                    if os.path.isfile(gt_busy_path) and os.access(gt_busy_path, os.R_OK):
                        return True
            return False
        except Exception:
            return False
    
    def get_stats(self) -> List[GpuStats]:
        """Get GPU statistics using Intel sysfs."""
        if not self._gpu_paths:
            return []
        
        stats_list = []
        
        for i, gpu_path in enumerate(self._gpu_paths):
            stats = GpuStats()
            stats.name = self._gpu_names[i] if i < len(self._gpu_names) else f"Intel GPU {i}"
            
            try:
                # Utilization (gt_busy_percent)
                gt_busy_path = os.path.join(gpu_path, 'gt_busy_percent')
                if os.path.isfile(gt_busy_path):
                    with open(gt_busy_path, 'r') as f:
                        busy_percent = f.read().strip()
                        stats.utilization_percent = int(float(busy_percent))
            except (IOError, ValueError, OSError):
                pass
            
            try:
                # Temperature (hwmon)
                # Intel GPUs may expose temperature via hwmon
                hwmon_base = os.path.join(gpu_path, 'hwmon')
                if os.path.isdir(hwmon_base):
                    for hwmon_dir in os.listdir(hwmon_base):
                        hwmon_path = os.path.join(hwmon_base, hwmon_dir)
                        temp_input = os.path.join(hwmon_path, 'temp1_input')
                        if os.path.isfile(temp_input):
                            with open(temp_input, 'r') as f:
                                temp_millidegrees = int(f.read().strip())
                                stats.temperature_c = temp_millidegrees // 1000
                                break
            except (IOError, OSError):
                pass
            
            # Memory and power are typically not available via Intel sysfs
            # These would require additional interfaces
            
            stats_list.append(stats)
        
        return stats_list


class NvidiaCliBackend(GpuBackend):
    """NVIDIA CLI fallback backend using nvidia-smi."""
    
    def __init__(self):
        """Initialize NVIDIA CLI backend."""
        self._nvidia_smi_path = self._find_nvidia_smi()
        self._gpu_count = 0
        self._gpu_names: List[str] = []
        
        if self._nvidia_smi_path:
            try:
                # Query GPU count and names
                result = subprocess.run(
                    [self._nvidia_smi_path, '--query-gpu=count,name', '--format=csv,noheader'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                    self._gpu_count = len(lines)
                    for line in lines:
                        parts = line.split(',', 1)
                        name = parts[-1].strip() if len(parts) > 1 else "NVIDIA GPU"
                        self._gpu_names.append(name)
                    
                    logger.debug(f"NVIDIA CLI backend initialized: {self._gpu_count} GPU(s)")
            except Exception as e:
                logger.debug(f"NVIDIA CLI backend initialization failed: {e}")
                self._nvidia_smi_path = None
    
    @staticmethod
    def _find_nvidia_smi() -> Optional[str]:
        """Find nvidia-smi executable."""
        common_paths = [
            '/usr/bin/nvidia-smi',
            'nvidia-smi'  # Let subprocess find it in PATH
        ]
        for path in common_paths:
            try:
                result = subprocess.run(
                    [path, '--version'],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None
    
    @staticmethod
    def is_available() -> bool:
        """Check if NVIDIA CLI backend is available."""
        backend = NvidiaCliBackend()
        return backend._nvidia_smi_path is not None and backend._gpu_count > 0
    
    def get_stats(self) -> List[GpuStats]:
        """Get GPU statistics using nvidia-smi."""
        if not self._nvidia_smi_path or self._gpu_count == 0:
            return []
        
        stats_list = []
        
        for i in range(self._gpu_count):
            stats = GpuStats()
            stats.name = self._gpu_names[i] if i < len(self._gpu_names) else f"NVIDIA GPU {i}"
            
            try:
                # Query all metrics at once
                query = 'utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw'
                result = subprocess.run(
                    [self._nvidia_smi_path, '-i', str(i), f'--query-gpu={query}', '--format=csv,noheader,nounits'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(',')
                    if len(parts) >= 6:
                        try:
                            stats.utilization_percent = int(float(parts[0].strip()))
                            # parts[1] is memory utilization, skip for now
                            stats.memory_used_bytes = int(float(parts[2].strip()) * 1024 * 1024)  # MB to bytes
                            stats.memory_total_bytes = int(float(parts[3].strip()) * 1024 * 1024)  # MB to bytes
                            stats.temperature_c = int(float(parts[4].strip()))
                            stats.power_watts = float(parts[5].strip())
                        except (ValueError, IndexError):
                            pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            stats_list.append(stats)
        
        return stats_list


class GpuBackendDetector:
    """Detects and selects the best available GPU backend."""
    
    # Detection priority order (strict order)
    BACKENDS = [
        ('NVML', NvmlBackend),
        ('ROCm', RocmBackend),
        ('Intel Sysfs', IntelSysfsBackend),
        ('NVIDIA CLI', NvidiaCliBackend),
    ]
    
    @staticmethod
    def detect() -> Optional[GpuBackend]:
        """
        Detect and initialize the best available GPU backend.
        
        Returns:
            Initialized backend instance, or None if no backend is available.
        """
        for backend_name, backend_class in GpuBackendDetector.BACKENDS:
            try:
                logger.debug(f"Probing {backend_name} backend...")
                if backend_class.is_available():
                    try:
                        backend = backend_class()
                        # Verify it can actually get stats
                        stats = backend.get_stats()
                        if stats:  # At least one GPU detected
                            logger.debug(f"Selected {backend_name} backend")
                            return backend
                        else:
                            logger.debug(f"{backend_name} backend available but no GPUs detected")
                    except Exception as e:
                        logger.debug(f"{backend_name} backend initialization failed: {e}")
                        continue
            except Exception as e:
                logger.debug(f"{backend_name} backend probe failed: {e}")
                continue
        
        logger.debug("No GPU backend available")
        return None


class GPUCollector(BaseCollector):
    """
    Collects comprehensive GPU metrics from the system.
    
    Uses a multi-backend detection system to support:
    - NVIDIA GPUs (NVML or nvidia-smi)
    - AMD GPUs (ROCm)
    - Intel GPUs (sysfs)
    
    Backend selection happens once at initialization.
    If no backend is available, the collector returns empty data.
    """
    
    def __init__(self):
        """Initialize the GPU collector with backend detection."""
        self.backend: Optional[GpuBackend] = GpuBackendDetector.detect()
    
    def get_name(self) -> str:
        """Get the unique identifier for this collector."""
        return "gpu"
    
    def _get_gpu_name_simple(self, gpu_name: Optional[str]) -> str:
        """
        Get a simplified GPU name using pattern matching.
        
        Similar to CPU name simplification, extracts a compact, readable name.
        Examples:
        - "NVIDIA GeForce RTX 4090" -> "RTX 4090"
        - "AMD Radeon RX 7900 XTX" -> "RX 7900 XTX"
        - "Intel Arc A770" -> "Arc A770"
        
        Args:
            gpu_name: Full GPU name string
        
        Returns:
            Simplified GPU name string
        """
        if not gpu_name:
            return 'Unknown'
        
        # Step 1: Remove trademark and filler tokens: (R), (TM), GPU, Graphics
        cleaned = gpu_name
        cleaned = re.sub(r'\(R\)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\(TM\)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bGPU\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bGraphics\b', '', cleaned, flags=re.IGNORECASE)
        
        # Step 2: Normalize whitespace (multiple spaces -> single space, trim)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        gpu_name_lower = cleaned.lower()
        
        # Step 3: Vendor-specific handling
        
        # NVIDIA: Extract model series (GeForce RTX/GTX series, Quadro, Tesla, etc.)
        if 'nvidia' in gpu_name_lower or 'geforce' in gpu_name_lower:
            # Pattern for GeForce RTX/GTX models: "RTX 4090", "GTX 1080 Ti", etc.
            geforce_pattern = r'\b((?:rtx|gtx)\s+\d+[a-z]*(?:\s+(?:ti|super))?)\b'
            match = re.search(geforce_pattern, gpu_name_lower)
            if match:
                return match.group(1).upper()
            
            # Pattern for Quadro: "Quadro RTX 5000" -> "Quadro RTX 5000"
            if 'quadro' in gpu_name_lower:
                quadro_pattern = r'\b(quadro(?:\s+rtx)?(?:\s+\d+[a-z]*)?)\b'
                match = re.search(quadro_pattern, gpu_name_lower)
                if match:
                    return match.group(1).title()
                # Fallback: just "Quadro" + next significant token
                parts = cleaned.split()
                for i, part in enumerate(parts):
                    if part.lower() == 'quadro' and i + 1 < len(parts):
                        # Skip generic words
                        if parts[i + 1].lower() not in ['series', 'professional']:
                            return f"Quadro {parts[i + 1]}"
                return "Quadro"
            
            # Pattern for Tesla: "Tesla V100" -> "Tesla V100"
            if 'tesla' in gpu_name_lower:
                tesla_pattern = r'\b(tesla\s+[a-z]\d+)\b'
                match = re.search(tesla_pattern, gpu_name_lower)
                if match:
                    return match.group(1).title()
            
            # Fallback for other NVIDIA: try to extract series name (first capitalized word after NVIDIA/GeForce)
            parts = cleaned.split()
            for i, part in enumerate(parts):
                if part.lower() in ['nvidia', 'geforce'] and i + 1 < len(parts):
                    # Take next significant parts
                    result_parts = []
                    for j in range(i + 1, min(i + 3, len(parts))):
                        if parts[j].lower() not in ['series', 'graphics']:
                            result_parts.append(parts[j])
                    if result_parts:
                        return ' '.join(result_parts)
        
        # AMD: Extract Radeon RX/Pro/WX series
        if 'amd' in gpu_name_lower or 'radeon' in gpu_name_lower:
            # Pattern for Radeon RX: "RX 7900 XTX" -> "RX 7900 XTX"
            rx_pattern = r'\b(rx\s+\d+[a-z]*(?:\s+[a-z]+)?)\b'
            match = re.search(rx_pattern, gpu_name_lower)
            if match:
                return match.group(1).upper()
            
            # Pattern for Radeon Pro: "Pro W6800" -> "Pro W6800"
            if 'pro' in gpu_name_lower:
                pro_pattern = r'\b(pro\s+[w]\d+[a-z]*)\b'
                match = re.search(pro_pattern, gpu_name_lower)
                if match:
                    return match.group(1).title()
            
            # Pattern for Radeon WX: "WX 9100" -> "WX 9100"
            wx_pattern = r'\b(wx\s+\d+)\b'
            match = re.search(wx_pattern, gpu_name_lower)
            if match:
                return match.group(1).upper()
            
            # Fallback: try to extract after "Radeon"
            parts = cleaned.split()
            for i, part in enumerate(parts):
                if part.lower() == 'radeon' and i + 1 < len(parts):
                    result_parts = []
                    for j in range(i + 1, min(i + 3, len(parts))):
                        if parts[j].lower() not in ['series', 'graphics']:
                            result_parts.append(parts[j])
                    if result_parts:
                        return ' '.join(result_parts).upper()
        
        # Intel: Extract Arc series
        if 'intel' in gpu_name_lower or 'arc' in gpu_name_lower:
            # Pattern for Arc: "Arc A770" -> "Arc A770"
            arc_pattern = r'\b(arc\s+[a]\d+[a-z]*)\b'
            match = re.search(arc_pattern, gpu_name_lower)
            if match:
                return match.group(1).title()
            
            # Fallback: try to extract after "Intel"
            parts = cleaned.split()
            for i, part in enumerate(parts):
                if part.lower() == 'intel' and i + 1 < len(parts):
                    result_parts = []
                    for j in range(i + 1, min(i + 3, len(parts))):
                        if parts[j].lower() not in ['graphics']:
                            result_parts.append(parts[j])
                    if result_parts:
                        return ' '.join(result_parts).title()
        
        # Fallback: Return cleaned version (removed trademarks, normalized whitespace)
        return cleaned
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect current GPU metrics from the system.
        
        Returns:
            Dictionary containing GPU metrics with the following structure:
            {
                'count': int,  # Number of GPUs detected
                'gpus': [
                    {
                        'name': str or None,
                        'usage': int or None,  # GPU usage percentage (0-100)
                        'memory': {
                            'used_mb': int or None,
                            'total_mb': int or None,
                            'usage_percent': int or None  # Memory usage percentage (0-100)
                        },
                        'temperature': int or None,  # Temperature in °C
                        'power': float or None,  # Power consumption in watts
                    },
                    ...
                ],
                'overall': {
                    'usage': float,  # Average GPU usage across all GPUs
                    'memory_usage_percent': float  # Average memory usage percentage
                }
            }
        """
        if self.backend is None:
            return {
                'count': 0,
                'gpus': [],
                'overall': {
                    'usage': 0.0,
                    'memory_usage_percent': 0.0
                }
            }
        
        try:
            stats_list = self.backend.get_stats()
        except Exception as e:
            logger.debug(f"Error collecting GPU stats: {e}")
            return {
                'count': 0,
                'gpus': [],
                'overall': {
                    'usage': 0.0,
                    'memory_usage_percent': 0.0
                }
            }
        
        if not stats_list:
            return {
                'count': 0,
                'gpus': [],
                'overall': {
                    'usage': 0.0,
                    'memory_usage_percent': 0.0
                }
            }
        
        # Convert GpuStats to dictionary format
        gpus = []
        total_usage = 0.0
        total_memory_usage = 0.0
        valid_usage_count = 0
        valid_memory_count = 0
        
        for stats in stats_list:
            # Calculate memory usage percent if we have both used and total
            memory_usage_percent = None
            if stats.memory_used_bytes is not None and stats.memory_total_bytes is not None and stats.memory_total_bytes > 0:
                memory_usage_percent = int((stats.memory_used_bytes / stats.memory_total_bytes) * 100)
            
            gpu_data = {
                'name': stats.name,
                'name_simple': self._get_gpu_name_simple(stats.name),
                'usage': stats.utilization_percent,
                'memory': {
                    'used_mb': stats.memory_used_bytes // (1024 * 1024) if stats.memory_used_bytes is not None else None,
                    'total_mb': stats.memory_total_bytes // (1024 * 1024) if stats.memory_total_bytes is not None else None,
                    'usage_percent': memory_usage_percent
                },
                'temperature': stats.temperature_c,
                'power': stats.power_watts
            }
            
            gpus.append(gpu_data)
            
            if stats.utilization_percent is not None:
                total_usage += stats.utilization_percent
                valid_usage_count += 1
            
            if memory_usage_percent is not None:
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
