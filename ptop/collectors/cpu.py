"""
CPU metrics collector.

This module collects comprehensive CPU usage statistics using psutil and platform.
It provides per-core and overall CPU usage information, clock speeds, load averages,
temperature, and power consumption (where available).
"""

import platform
import psutil
import re
import time
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
        self._cpu_percent_initialized = False
        self._init_cpu_name()
        self._init_tdp()
        # Warm up cpu_percent() with initial call to establish baseline
        # This allows subsequent calls to use interval=None (non-blocking)
        psutil.cpu_percent(interval=0.01)
        self._cpu_percent_initialized = True
        
    
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
                system = platform.system()
                
                # Check if we need platform-specific detection
                # On Windows, platform.processor() returns technical string like "Intel64 Family 6 Model 158..."
                # On other platforms, it might be empty or generic
                needs_detection = (
                    not self._cpu_name or 
                    self._cpu_name == '' or 
                    self._cpu_name.lower() == 'arm' or
                    (system == 'Windows' and ('family' in self._cpu_name.lower() or 'model' in self._cpu_name.lower()))
                )
                
                if needs_detection:
                    # Try platform-specific methods
                    if system == 'Darwin':  # macOS
                        try:
                            import subprocess
                            result = subprocess.run(
                                ['sysctl', '-n', 'machdep.cpu.brand_string'],
                                capture_output=True,
                                text=True,
                                timeout=2
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                self._cpu_name = result.stdout.strip()
                        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                            pass
                    elif system == 'Linux':
                        try:
                            with open('/proc/cpuinfo', 'r') as f:
                                for line in f:
                                    if 'model name' in line.lower():
                                        self._cpu_name = line.split(':')[1].strip()
                                        break
                        except (IOError, IndexError):
                            pass
                    elif system == 'Windows':
                        # Windows: Use WMI/CIM to get proper CPU name
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
                                    self._cpu_name = cpu_name
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
                                        self._cpu_name = cpu_name
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
                                                    self._cpu_name = cpu_name
                                                break
                                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                                    pass
                    
                    if not self._cpu_name or self._cpu_name.lower() == 'arm':
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
    
    def get_cpu_name_simple(self) -> str:
        """
        Get a simplified CPU name suitable for UI display.
        
        Converts long vendor CPU brand strings into compact identifiers,
        matching btop's behavior. This is heuristic string parsing for UI purposes.
        
        Returns:
            Simplified CPU name string, e.g., "i7-10700K", "Ryzen 9 5900X", "Apple M1"
        """
        if not self._cpu_name:
            return 'Unknown'
        
        # Step 1: Remove trademark and filler tokens: (R), (TM), CPU, Processor
        cleaned = self._cpu_name
        cleaned = re.sub(r'\(R\)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\(TM\)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bCPU\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bProcessor\b', '', cleaned, flags=re.IGNORECASE)
        
        # Step 2: Strip frequency information: "@ <number>GHz"
        cleaned = re.sub(r'@\s*\d+\.?\d*\s*GHz', '', cleaned, flags=re.IGNORECASE)
        
        # Step 3: Normalize whitespace (multiple spaces -> single space, trim)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        cpu_name_lower = cleaned.lower()
        
        # Step 4: Vendor-specific handling
        
        # Intel: Detect Core i[3|5|7|9] -> keep only the model (e.g., "i7-10700K")
        intel_core_pattern = r'\b(i[3579]-\d+[a-z]?[a-z]?)\b'
        match = re.search(intel_core_pattern, cpu_name_lower)
        if match:
            return match.group(1)
        
        # Intel: Detect Xeon -> keep "Xeon <model> [vX]"
        if 'xeon' in cpu_name_lower:
            xeon_pattern = r'\b(xeon\s+[a-z0-9-]+\s*(?:v\d+)?)\b'
            match = re.search(xeon_pattern, cpu_name_lower)
            if match:
                return match.group(1).title()
            # Fallback: just "Xeon" + next token
            parts = cleaned.split()
            for i, part in enumerate(parts):
                if part.lower() == 'xeon' and i + 1 < len(parts):
                    return f"Xeon {parts[i + 1]}"
            return "Xeon"
        
        # AMD: Keep Ryzen with tier and model, drop core-count suffixes
        if 'ryzen' in cpu_name_lower:
            # Pattern: "Ryzen <tier> <model>" - drop any core-count suffix
            ryzen_pattern = r'\b(ryzen\s+\d+\s+\d+[a-z]?)\b'
            match = re.search(ryzen_pattern, cpu_name_lower)
            if match:
                return match.group(1).title()
            # Fallback: try to extract ryzen + next two tokens
            parts = cleaned.split()
            for i, part in enumerate(parts):
                if part.lower() == 'ryzen' and i + 2 < len(parts):
                    # Skip core-count suffix if present
                    result_parts = [parts[i], parts[i + 1], parts[i + 2]]
                    # Remove any part that looks like "12-Core" or similar
                    result_parts = [p for p in result_parts if not re.match(r'\d+-core', p.lower())]
                    return ' '.join(result_parts).title()
        
        # Apple: Prefer "Apple M[N] [Pro/Max/Ultra]..." (M followed by any number)
        if 'apple' in cpu_name_lower:
            # Match "M" followed by digits, then optional suffix like "Pro", "Max", "Ultra"
            apple_pattern = r'\b(m\d+)\s+([a-z]+)\b'
            match = re.search(apple_pattern, cpu_name_lower)
            if match:
                result = match.group(1).upper()
                suffix = match.group(2).title()
                # Only include suffix if it's a known Apple suffix (Pro, Max, Ultra)
                if suffix.lower() in ['pro', 'max', 'ultra']:
                    return f"Apple {result} {suffix}"
                else:
                    return f"Apple {result}"
            # Fallback: match just "M[N]" without suffix
            apple_pattern_simple = r'\b(m\d+)\b'
            match = re.search(apple_pattern_simple, cpu_name_lower)
            if match:
                return f"Apple {match.group(1).upper()}"
            # Final fallback: if 'apple' in name, try to extract after "Apple"
                parts = cleaned.split()
                for i, part in enumerate(parts):
                    if part.lower() == 'apple' and i + 1 < len(parts):
                        return f"Apple {parts[i + 1]}"
        
        # Fallback: Return cleaned version (removed trademarks, frequency, normalized whitespace)
        return cleaned
    
    def get_per_core_frequencies(self) -> List[float]:
        """
        Get live per-core CPU frequencies in MHz.
        
        This method polls each CPU core at a regular interval (200-500ms) to get current
        clock speeds. It uses platform-specific APIs for accurate live frequency tracking.
        
        Platform implementations:
        - Linux: Reads /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq for each core.
          This provides live per-core frequencies that update with CPU scaling governors.
          Very efficient (few milliseconds), reads directly from kernel.
        - BSD (FreeBSD/OpenBSD/NetBSD): Uses sysctl dev.cpu.N.freq for each core.
          Provides per-core live frequencies via sysctl.
        - Windows: Uses WMI Win32_Processor.CurrentClockSpeed via psutil.
          psutil.cpu_freq(percpu=True) internally uses WMI for per-core frequencies.
        - macOS: Uses psutil.cpu_freq(percpu=True) which may provide per-core data.
          If not available per-core, attempts to estimate based on CPU load interpolation.
          Note: macOS doesn't easily expose live per-core scaling, so this is best-effort.
        
        Performance:
        - Minimizes filesystem reads and OS calls per update
        - No unnecessary allocations
        - Efficient with high core counts
        - Non-blocking: completes in few milliseconds
        
        Returns:
            List of frequencies in MHz for each logical core.
            Returns empty list if live frequency data is unavailable.
            Never returns static/fallback values - only live data or empty list.
        """
        system = platform.system()
        frequencies = []
        
        if system == 'Linux':
            # Linux: Read from /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
            # This is the most accurate method for live per-core frequencies
            for cpu_id in range(self.cpu_count_logical):
                freq_path = f'/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_cur_freq'
                try:
                    with open(freq_path, 'r') as f:
                        freq_khz = float(f.read().strip())
                        freq_mhz = freq_khz / 1000.0  # Convert kHz to MHz
                        frequencies.append(freq_mhz)
                except (IOError, OSError, ValueError, FileNotFoundError):
                    # Core doesn't have frequency scaling file - skip it
                    # Don't break, continue trying other cores
                    frequencies.append(0.0)
            
            # If we got at least some valid frequencies, return them
            if any(f > 0 for f in frequencies):
                return frequencies
            return []
        
        elif system in ('FreeBSD', 'OpenBSD', 'NetBSD'):
            # BSD: Use sysctl dev.cpu.N.freq for each core
            import subprocess
            for cpu_id in range(self.cpu_count_logical):
                try:
                    result = subprocess.run(
                        ['sysctl', '-n', f'dev.cpu.{cpu_id}.freq'],
                        capture_output=True,
                        text=True,
                        timeout=0.5
                    )
                    if result.returncode == 0:
                        try:
                            freq_mhz = float(result.stdout.strip())
                            frequencies.append(freq_mhz)
                        except (ValueError, AttributeError):
                            frequencies.append(0.0)
                    else:
                        frequencies.append(0.0)
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    frequencies.append(0.0)
            
            # If we got at least some valid frequencies, return them
            if any(f > 0 for f in frequencies):
                return frequencies
            return []
        
        elif system == 'Windows':
            # Windows: Use psutil which internally uses WMI Win32_Processor.CurrentClockSpeed
            try:
                freq_info = psutil.cpu_freq(percpu=True)
                if freq_info:
                    # psutil returns frequencies in MHz
                    freq_list = []
                    for freq in freq_info:
                        if freq is not None and freq.current is not None:
                            freq_list.append(freq.current)
                        else:
                            freq_list.append(0.0)
                    
                    # Ensure we have the right number of cores
                    while len(freq_list) < self.cpu_count_logical:
                        freq_list.append(0.0)
                    
                    if any(f > 0 for f in freq_list):
                        return freq_list[:self.cpu_count_logical]
            except (AttributeError, RuntimeError, OSError):
                pass
            
            return []
        
        elif system == 'Darwin':  # macOS
            # macOS: Live per-core CPU frequency is not available through public APIs
            # Even btop doesn't display live CPU frequency on macOS
            # Return empty list to indicate frequency data is unavailable
            return []
        
        else:
            # Unknown platform: Try psutil as universal fallback
            try:
                freq_info = psutil.cpu_freq(percpu=True)
                if freq_info:
                    freq_list = []
                    for freq in freq_info:
                        if freq is not None and freq.current is not None:
                            freq_list.append(freq.current)
                        else:
                            freq_list.append(0.0)
                    
                    while len(freq_list) < self.cpu_count_logical:
                        freq_list.append(0.0)
                    
                    if any(f > 0 for f in freq_list):
                        return freq_list[:self.cpu_count_logical]
            except (AttributeError, RuntimeError, OSError):
                pass
            
            return []
    
    def get_current_frequency_string(self) -> Optional[str]:
        """
        Get current CPU frequency as a formatted string.
        
        Uses get_per_core_frequencies() to get live per-core frequencies and returns
        the maximum frequency among all cores to better reflect the current CPU state
        (cores can run at different frequencies).
        
        Returns:
            Formatted frequency string:
            - If below 1GHz: "800MHz" (no decimal)
            - If 1GHz or above: "1.2GHz", "3.4GHz" etc. (one decimal place)
            Returns None if frequency is not available.
        """
        try:
            # Use get_per_core_frequencies() for live per-core data
            frequencies = self.get_per_core_frequencies()
            
            if frequencies and len(frequencies) > 0:
                # Filter out zero values (cores without frequency data)
                valid_freqs = [f for f in frequencies if f > 0]
                if valid_freqs:
                    # Get the maximum frequency among all cores (most representative of current state)
                    freq_mhz = max(valid_freqs)
                    
                    # Convert to GHz
                    freq_ghz = freq_mhz / 1000.0
                    
                    # Format based on value
                    if freq_ghz < 1.0:
                        # Below 1GHz: show as MHz with no decimal
                        return f"{int(round(freq_mhz))}MHz"
                    else:
                        # 1GHz or above: show as GHz with one decimal place
                        return f"{freq_ghz:.1f}GHz"
            
            # No valid frequencies available
            return None
        except (ValueError, AttributeError, RuntimeError, OSError):
            pass
        
        return None
    
    def get_usage(self) -> Tuple[float, List[float]]:
        """
        Get CPU usage percentages.
        
        Returns:
            Tuple of (overall_usage, per_core_usage):
            - overall_usage: Overall CPU usage percentage (0-100, rounded to integer)
            - per_core_usage: List of per-core CPU usage percentages (rounded to integers)
        """
        # Get per-core CPU usage (non-blocking after initialization)
        # Using interval=None makes this instant - psutil uses time since last call
        per_core_usage = psutil.cpu_percent(interval=None, percpu=True)
        
        # Round per-core usage to integers
        per_core_usage = [round(usage) for usage in per_core_usage]
        
        # Calculate overall usage as the average of all cores
        # This ensures consistency - overall and per-core are from the same measurement period
        if per_core_usage:
            overall_usage = sum(per_core_usage) / len(per_core_usage)
        else:
            # Fallback: if per_core_usage is empty, get overall separately
            overall_usage = psutil.cpu_percent(interval=None)
        
        # Round overall usage to integer
        overall_usage = round(overall_usage)
        
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
    
    def get_uptime_string(self) -> Optional[str]:
        """
        Get system uptime as a formatted string.
        
        Returns:
            Formatted uptime string (e.g., "uptime 2d 5h 30m 15s", "uptime 3h 15m 30s", "uptime 45m 30s"),
            or None if not available.
        """
        try:
            import time
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time
            
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)
            
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
            parts.append(f"{seconds}s")
            
            return "uptime " + " ".join(parts)
        except Exception:
            return None
    
    def get_temperature(self) -> Optional[Dict[str, Any]]:
        """
        Get CPU temperature information.
        
        Returns:
            Dictionary containing temperature data:
            - 'current': Current temperature in Celsius (average if multiple sensors)
            - 'per_core': List of per-core temperatures (if available), aligned with core indices
            - 'sensors': Dictionary of sensor names and their temperatures
            Returns None if temperature sensors are not available.
        """
        try:
            sensors = psutil.sensors_temperatures()
            if not sensors:
                return None
            
            # Initialize per-core temperature list (one entry per logical core)
            per_core_temps = [None] * self.cpu_count_logical
            sensor_data = {}
            all_temps = []
            
            # Look for CPU-related temperature sensors
            # Common sensor names: 'coretemp', 'k10temp', 'cpu_thermal', etc.
            for sensor_name, entries in sensors.items():
                if any(keyword in sensor_name.lower() for keyword in ['cpu', 'core', 'package']):
                    for entry in entries:
                        if entry.current is not None:
                            all_temps.append(entry.current)
                            label = entry.label or sensor_name
                            sensor_data[label] = entry.current
                            
                            # Try to extract core number from label (e.g., "Core 0", "cpu_core_1", "Tctl")
                            # Common patterns: "Core 0", "Core 1", "cpu_core_0", "Package id 0", etc.
                            if entry.label:
                                label_lower = entry.label.lower()
                                # Try to find a number in the label
                                # Look for patterns like "core 0", "core0", "cpu 1", etc.
                                core_match = re.search(r'(?:core|cpu)[\s_]*(\d+)', label_lower)
                                if core_match:
                                    try:
                                        physical_core_idx = int(core_match.group(1))
                                        # Map physical core temperature to logical cores
                                        # With hyperthreading, each physical core has multiple logical cores
                                        # Physical core 0 -> logical cores 0 and (physical_count)
                                        # Physical core 1 -> logical cores 1 and (physical_count + 1)
                                        # etc.
                                        if physical_core_idx < self.cpu_count_physical:
                                            # First logical core of this physical core
                                            logical_idx1 = physical_core_idx
                                            if logical_idx1 < self.cpu_count_logical:
                                                per_core_temps[logical_idx1] = entry.current
                                            
                                            # Second logical core (if hyperthreading exists)
                                            logical_idx2 = physical_core_idx + self.cpu_count_physical
                                            if logical_idx2 < self.cpu_count_logical:
                                                per_core_temps[logical_idx2] = entry.current
                                    except (ValueError, IndexError):
                                        pass
                                # Also check for package temperature (usually core 0 or average)
                                elif 'package' in label_lower or 'tdie' in label_lower or 'tctl' in label_lower:
                                    # Package/Tdie/Tctl usually represents overall CPU temp
                                    # Use as fallback for cores without specific temperature
                                    # Don't overwrite existing per-core temps
                                    for idx in range(self.cpu_count_logical):
                                        if per_core_temps[idx] is None:
                                            per_core_temps[idx] = entry.current
            
            if not all_temps:
                # Try to find any temperature sensor as fallback
                for sensor_name, entries in sensors.items():
                    for entry in entries:
                        if entry.current is not None:
                            all_temps.append(entry.current)
                            label = entry.label or sensor_name
                            sensor_data[label] = entry.current
                            break
                    if all_temps:
                        break
            
            if all_temps:
                avg_temp = sum(all_temps) / len(all_temps)
                
                # If we have per-core temperatures, filter out None values and check if we have enough
                per_core_valid = [t for t in per_core_temps if t is not None]
                
                # If we have per-core temperatures, use them (even if some are None)
                # Fill any remaining None values with the average of available temps
                if len(per_core_valid) > 0:
                    avg_available = sum(per_core_valid) / len(per_core_valid)
                    # Fill any None values with the average
                    per_core_result = [t if t is not None else avg_available for t in per_core_temps]
                else:
                    # No per-core data at all
                    per_core_result = None
                
                return {
                    'current': avg_temp,
                    'per_core': per_core_result,
                    'sensors': sensor_data,
                }
        except (AttributeError, RuntimeError, OSError, Exception) as e:
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
            - 'name': CPU name/model (full name)
            - 'name_simple': Simplified CPU name (e.g., "i7-8700k")
            - 'overall': Overall CPU usage percentage (0-100)
            - 'per_core': List of per-core CPU usage percentages
            - 'frequencies': List of live per-core frequencies in MHz (from get_per_core_frequencies())
            - 'load_average': Tuple of (1min, 5min, 15min) load averages or None
            - 'temperature': Temperature dict or None
            - 'power': Power consumption in watts or None
            - 'count_logical': Number of logical CPUs
            - 'count_physical': Number of physical CPUs
        """
        overall_usage, per_core_usage = self.get_usage()
        frequencies = self.get_per_core_frequencies()
        load_avg = self.get_load_average()
        temperature = self.get_temperature()
        power = self.get_power()
        uptime = self.get_uptime_string()
        current_freq_string = self.get_current_frequency_string()
        
        return {
            'name': self.get_cpu_name(),
            'name_simple': self.get_cpu_name_simple(),
            'overall': overall_usage,
            'per_core': per_core_usage,
            'frequencies': frequencies,
            'current_frequency': current_freq_string,
            'load_average': load_avg,
            'temperature': temperature,
            'power': power,
            'uptime': uptime,
            'count_logical': self.cpu_count_logical,
            'count_physical': self.cpu_count_physical,
        }
