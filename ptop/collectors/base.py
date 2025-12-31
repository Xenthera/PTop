"""
Base collector interface.

This module provides an abstract base class for all collectors,
ensuring they implement the required interface for collecting metrics.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseCollector(ABC):
    """
    Abstract base class for all metric collectors.
    
    This defines the interface that all collectors must implement,
    ensuring consistency and allowing the core app to work with
    any collector implementation.
    """
    
    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """
        Collect current metrics from the system.
        
        Returns:
            Dictionary containing the collected metrics.
            The structure is collector-specific, but should be
            consistent across calls.
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Get the unique identifier for this collector.
        
        Returns:
            String identifier (e.g., "cpu", "memory", "disk").
            This is used as the key when aggregating metrics.
        """
        pass
