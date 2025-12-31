"""
CPU metrics collector.

This module collects comprehensive CPU usage statistics using psutil and platform.
It provides per-core and overall CPU usage information, clock speeds, load averages,
temperature, and power consumption (where available).
"""

import platform
import psutil
from typing import Dict, Any, List, Tuple, Optional

try:
    import cpuinfo
    HAS_CPUINFO = True
except ImportError:
    HAS_CPUINFO = False

from .base import BaseCollector


class CPUCollector(BaseCollector):
    """
    Collects comprehensive CPU metrics from the system.
    
    This collector gathers:
    - CPU name/model
    - Per-core clock speeds (MHz)
    - Overall and per-core CPU usage percentages
    - Load averages (1, 5, 15 minutes)
    - CPU temperature (if available)
    - CPU power consumption in watts (if available)
    - CPU count (logical and physical)
    
    Wattage modes:
    - "estimate": CPU usage × TDP / 100 (works without root)
    - "hwmon": Read /sys/class/hwmon/hwmon*/power1_input (may require root)
    - "rapl": Read /sys/class/powercap/intel-rapl*/energy_uj (may require root)
    - "auto": Try hwmon, then rapl, then estimate as fallback
    """
    
    def __init__(self, wattage_mode: str = "auto"):
        """
        Initialize the CPU collector.
        
        Args:
            wattage_mode: Method to use for power calculation.
                - "estimate": Estimate from CPU usage and TDP
                - "hwmon": Read from hwmon sensors
                - "rapl": Read from Intel RAPL interface
                - "auto": Try hwmon, then rapl, then estimate (default)
        """
        self.cpu_count_logical = psutil.cpu_count(logical=True)
        self.cpu_count_physical = psutil.cpu_count(logical=False)
        self._cpu_name = None
        self._cpu_tdp = None
        self.wattage_mode = wattage_mode.lower()
        self._init_cpu_name()
        self._init_tdp()
    
    def _init_cpu_name(self) -> None:
        """Initialize CPU name/model information."""
        try:
            if HAS_CPUINFO:
                # Use cpuinfo for detailed CPU information
                cpu_info = cpuinfo.get_cpu_info()
                self._cpu_name = cpu_info.get('brand_raw', cpu_info.get('brand', 'Unknown CPU'))
            else:
                # Fallback to platform module
                self._cpu_name = platform.processor()
                if not self._cpu_name or self._cpu_name == '':
                    # Try alternative method
                    if platform.system() == 'Linux':
                        try:
                            with open('/proc/cpuinfo', 'r') as f:
                                for line in f:
                                    if 'model name' in line.lower():
                                        self._cpu_name = line.split(':')[1].strip()
                                        break
                        except (IOError, IndexError):
                            pass
                    
                    if not self._cpu_name:
                        self._cpu_name = platform.machine()
        except Exception:
            self._cpu_name = 'Unknown CPU'
    
    def _init_tdp(self) -> None:
        """
        Initialize CPU TDP (Thermal Design Power) estimation.
        
        TDP is estimated from CPU name/model using common values.
        Falls back to a default if CPU model cannot be identified.
        """
        cpu_name_lower = self._cpu_name.lower()
        
        # Common TDP values by CPU family (in watts)
        # Intel
        if 'i9' in cpu_name_lower:
            if '12900' in cpu_name_lower or '13900' in cpu_name_lower or '14900' in cpu_name_lower:
                self._cpu_tdp = 125  # High-end i9
            elif '11900' in cpu_name_lower or '10900' in cpu_name_lower:
                self._cpu_tdp = 125
            else:
                self._cpu_tdp = 95  # Standard i9
        elif 'i7' in cpu_name_lower:
            if '8700' in cpu_name_lower or '9700' in cpu_name_lower:
                self._cpu_tdp = 95
            elif '10700' in cpu_name_lower or '11700' in cpu_name_lower or '12700' in cpu_name_lower:
                self._cpu_tdp = 65  # i7-10/11/12th gen
            else:
                self._cpu_tdp = 65  # Default i7
        elif 'i5' in cpu_name_lower:
            self._cpu_tdp = 65  # Most i5
        elif 'i3' in cpu_name_lower:
            self._cpu_tdp = 65  # Most i3
        # AMD
        elif 'ryzen 9' in cpu_name_lower:
            if '5950' in cpu_name_lower or '7950' in cpu_name_lower:
                self._cpu_tdp = 105
            else:
                self._cpu_tdp = 105
        elif 'ryzen 7' in cpu_name_lower:
            if '5800' in cpu_name_lower or '7800' in cpu_name_lower:
                self._cpu_tdp = 65
            else:
                self._cpu_tdp = 65
        elif 'ryzen 5' in cpu_name_lower:
            self._cpu_tdp = 65
        elif 'ryzen 3' in cpu_name_lower:
            self._cpu_tdp = 65
        # Default fallback
        else:
            # Conservative default: assume mid-range CPU
            self._cpu_tdp = 65
    
    def get_name(self) -> str:
        """
        Get the name identifier for this collector.
        
        Returns:
            String identifier: "cpu"
        """
        return "cpu"
    
    def get_cpu_name(self) -> str:
        """
        Get the CPU name/model.
        
        Returns:
            CPU name string, e.g., "Intel(R) Core(TM) i7-10750H" or "AMD Ryzen 7 5800X"
        """
        return self._cpu_name or 'Unknown CPU'
    
    def get_frequencies(self) -> List[float]:
        """
        Get current clock speeds for each logical core.
        
        Returns:
            List of frequencies in MHz for each logical core.
            Returns empty list if frequencies are not available.
        """
        try:
            freq_info = psutil.cpu_freq(percpu=True)
            if freq_info:
                # psutil returns frequencies in MHz
                return [freq.current for freq in freq_info if freq is not None]
            else:
                # Try overall frequency
                overall_freq = psutil.cpu_freq()
                if overall_freq:
                    return [overall_freq.current] * self.cpu_count_logical
        except (AttributeError, RuntimeError, OSError):
            pass
        
        return []
    
    def get_usage(self) -> Tuple[float, List[float]]:
        """
        Get CPU usage percentages.
        
        Returns:
            Tuple of (overall_usage, per_core_usage):
            - overall_usage: Overall CPU usage percentage (0-100)
            - per_core_usage: List of per-core CPU usage percentages
        """
        # Get overall CPU usage (0.1 second interval for accuracy)
        overall_usage = psutil.cpu_percent(interval=0.1)
        
        # Get per-core CPU usage
        per_core_usage = psutil.cpu_percent(interval=0.1, percpu=True)
        
        return (overall_usage, per_core_usage)
    
    def get_load_average(self) -> Optional[Tuple[float, float, float]]:
        """
        Get system load averages.
        
        Returns:
            Tuple of (1min, 5min, 15min) load averages, or None if not available.
            On Windows, this will typically return None.
        """
        try:
            load_avg = psutil.getloadavg()
            return load_avg  # Returns (1min, 5min, 15min)
        except (AttributeError, OSError):
            # Windows doesn't support load average
            return None
    
    def get_temperature(self) -> Optional[Dict[str, Any]]:
        """
        Get CPU temperature information.
        
        Returns:
            Dictionary containing temperature data:
            - 'current': Current temperature in Celsius (average if multiple sensors)
            - 'per_core': List of per-core temperatures (if available)
            - 'sensors': Dictionary of sensor names and their temperatures
            Returns None if temperature sensors are not available.
        """
        try:
            sensors = psutil.sensors_temperatures()
            if not sensors:
                return None
            
            cpu_temps = []
            sensor_data = {}
            
            # Look for CPU-related temperature sensors
            # Common sensor names: 'coretemp', 'k10temp', 'cpu_thermal', etc.
            for sensor_name, entries in sensors.items():
                if any(keyword in sensor_name.lower() for keyword in ['cpu', 'core', 'package']):
                    for entry in entries:
                        if entry.current is not None:
                            cpu_temps.append(entry.current)
                            sensor_data[entry.label or sensor_name] = entry.current
            
            if not cpu_temps:
                # Try to find any temperature sensor
                for sensor_name, entries in sensors.items():
                    for entry in entries:
                        if entry.current is not None:
                            cpu_temps.append(entry.current)
                            sensor_data[entry.label or sensor_name] = entry.current
                            break
                    if cpu_temps:
                        break
            
            if cpu_temps:
                avg_temp = sum(cpu_temps) / len(cpu_temps)
                return {
                    'current': avg_temp,
                    'per_core': cpu_temps if len(cpu_temps) > 1 else None,
                    'sensors': sensor_data,
                }
        except (AttributeError, RuntimeError, OSError):
            pass
        
        return None
    
    def _get_power_estimate(self) -> Optional[float]:
        """
        Estimate CPU power consumption from usage and TDP.
        
        Formula: estimated_watts = cpu_usage_percent * cpu_tdp / 100
        
        Returns:
            Estimated power consumption in watts, or None if calculation fails.
        """
        try:
            overall_usage, _ = self.get_usage()
            if self._cpu_tdp and overall_usage is not None:
                estimated_watts = (overall_usage / 100.0) * self._cpu_tdp
                # Add base power consumption (idle power ~10-20% of TDP)
                base_power = self._cpu_tdp * 0.15
                estimated_watts = base_power + (estimated_watts * 0.85)
                return max(0, estimated_watts)
        except Exception:
            pass
        return None
    
    def _get_power_hwmon(self) -> Optional[float]:
        """
        Get CPU power consumption from hwmon sensors.
        
        Reads from /sys/class/hwmon/hwmon*/power1_input
        
        Returns:
            Power consumption in watts, or None if not available.
        """
        try:
            if platform.system() == 'Linux':
                import os
                hwmon_base = '/sys/class/hwmon'
                if os.path.exists(hwmon_base):
                    for item in os.listdir(hwmon_base):
                        if item.startswith('hwmon'):
                            hwmon_path = os.path.join(hwmon_base, item)
                            power_path = os.path.join(hwmon_path, 'power1_input')
                            
                            if os.path.exists(power_path) and os.access(power_path, os.R_OK):
                                try:
                                    with open(power_path, 'r') as f:
                                        # hwmon provides power in microwatts, convert to watts
                                        power_uw = int(f.read().strip())
                                        power_w = power_uw / 1_000_000.0
                                        
                                        # Sanity check: power should be reasonable (0-500W)
                                        if 0 <= power_w <= 500:
                                            return power_w
                                except (OSError, IOError, ValueError, PermissionError):
                                    pass
        except (OSError, IOError, PermissionError):
            pass
        return None
    
    def _get_power_rapl(self) -> Optional[float]:
        """
        Get CPU power consumption from Intel RAPL interface.
        
        Reads from /sys/devices/virtual/powercap/intel-rapl*/energy_uj
        and calculates power from energy delta over time.
        
        Returns:
            Power consumption in watts, or None if not available.
        """
        try:
            if platform.system() == 'Linux':
                import os
                import time
                rapl_path = '/sys/devices/virtual/powercap/intel-rapl'
                if os.path.exists(rapl_path):
                    # Look for package-0 (intel-rapl:0) which represents the CPU package
                    for item in os.listdir(rapl_path):
                        if item.startswith('intel-rapl:'):
                            energy_path = os.path.join(rapl_path, item, 'energy_uj')
                            if os.path.exists(energy_path) and os.access(energy_path, os.R_OK):
                                try:
                                    # RAPL provides cumulative energy in microjoules
                                    # To get power, we need to read energy twice with a time interval
                                    # Power (W) = Delta Energy (J) / Delta Time (s)
                                    
                                    # First reading
                                    with open(energy_path, 'r') as f:
                                        energy1_uj = int(f.read().strip())
                                    
                                    # Small delay to measure power
                                    time.sleep(0.1)
                                    
                                    # Second reading
                                    with open(energy_path, 'r') as f:
                                        energy2_uj = int(f.read().strip())
                                    
                                    # Calculate power
                                    # energy is in microjoules, convert to joules
                                    delta_energy_j = (energy2_uj - energy1_uj) / 1_000_000.0
                                    power_w = delta_energy_j / 0.1  # Divide by time interval (0.1 seconds)
                                    
                                    # Sanity check: power should be reasonable (0-500W for most CPUs)
                                    if 0 <= power_w <= 500:
                                        return power_w
                                except (OSError, IOError, ValueError, PermissionError):
                                    # Permission denied or other error reading RAPL
                                    pass
        except (OSError, IOError, PermissionError):
            pass
        return None
    
    def get_power(self) -> Optional[float]:
        """
        Get CPU power consumption using the configured wattage mode.
        
        Returns:
            CPU power consumption in watts, or None if not available.
            
        Wattage modes:
        - "estimate": Estimate from CPU usage and TDP (works without root)
        - "hwmon": Read from hwmon sensors (may require root)
        - "rapl": Read from Intel RAPL interface (may require root)
        - "auto": Try hwmon, then rapl, then estimate as fallback
        """
        # Try psutil sensors_power first (if available)
        try:
            if hasattr(psutil, 'sensors_power'):
                power_sensors = psutil.sensors_power()
                if power_sensors:
                    # Look for CPU power sensor
                    for sensor_name, entries in power_sensors.items():
                        if 'cpu' in sensor_name.lower():
                            for entry in entries:
                                if hasattr(entry, 'current') and entry.current is not None:
                                    return entry.current
        except (AttributeError, RuntimeError, OSError):
            pass
        
        # Use configured wattage mode
        if self.wattage_mode == "estimate":
            return self._get_power_estimate()
        elif self.wattage_mode == "hwmon":
            return self._get_power_hwmon()
        elif self.wattage_mode == "rapl":
            return self._get_power_rapl()
        elif self.wattage_mode == "auto":
            # Try hwmon first
            power = self._get_power_hwmon()
            if power is not None:
                return power
            
            # Try RAPL
            power = self._get_power_rapl()
            if power is not None:
                return power
            
            # Fallback to estimate
            return self._get_power_estimate()
        else:
            # Unknown mode, try auto fallback
            return self._get_power_estimate()
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect all available CPU metrics.
        
        Returns:
            Dictionary containing all CPU metrics:
            - 'name': CPU name/model
            - 'overall': Overall CPU usage percentage (0-100)
            - 'per_core': List of per-core CPU usage percentages
            - 'frequencies': List of per-core frequencies in MHz
            - 'load_average': Tuple of (1min, 5min, 15min) load averages or None
            - 'temperature': Temperature dict or None
            - 'power': Power consumption in watts or None
            - 'count_logical': Number of logical CPUs
            - 'count_physical': Number of physical CPUs
        """
        overall_usage, per_core_usage = self.get_usage()
        frequencies = self.get_frequencies()
        load_avg = self.get_load_average()
        temperature = self.get_temperature()
        power = self.get_power()
        
        return {
            'name': self.get_cpu_name(),
            'overall': overall_usage,
            'per_core': per_core_usage,
            'frequencies': frequencies,
            'load_average': load_avg,
            'temperature': temperature,
            'power': power,
            'count_logical': self.cpu_count_logical,
            'count_physical': self.cpu_count_physical,
        }
