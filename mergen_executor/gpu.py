"""GPU admission: whether a job may start now.

The executor never stops a GPU process that belongs to someone else; when the
GPU is busy it simply does not start work and says so in executor.json. G4 uses
the driver-provided NVML C API directly; it never parses nvidia-smi output.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GpuState:
    available: bool
    # Short, fixed wording for logs; never a device name, UUID or process.
    reason: str


class GpuProbe(Protocol):
    def check(self) -> GpuState: ...


class UncheckedGpu:
    """No admission check when no model adapter is configured."""

    def check(self) -> GpuState:
        return GpuState(True, "no model configured")


class _Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class NvmlGpu:
    """Fail-closed admission probe for one desktop GPU (index zero)."""

    def __init__(self, max_memory_used_mb: int, max_utilization_percent: int, library=None):
        self.max_memory = max_memory_used_mb
        self.max_utilization = max_utilization_percent
        self.library = library

    def check(self) -> GpuState:
        library = self.library
        initialized = False
        try:
            if library is None:
                library = ctypes.CDLL("libnvidia-ml.so.1")
            if library.nvmlInit_v2() != 0:
                return GpuState(False, "NVML unavailable")
            initialized = True
            device = ctypes.c_void_p()
            if library.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(device)) != 0:
                return GpuState(False, "GPU unavailable")
            memory, utilization = _Memory(), _Utilization()
            if library.nvmlDeviceGetMemoryInfo(device, ctypes.byref(memory)) != 0:
                return GpuState(False, "GPU memory unknown")
            if library.nvmlDeviceGetUtilizationRates(device, ctypes.byref(utilization)) != 0:
                return GpuState(False, "GPU utilization unknown")
            if memory.used // (1024 * 1024) > self.max_memory:
                return GpuState(False, "GPU memory busy")
            if utilization.gpu > self.max_utilization:
                return GpuState(False, "GPU compute busy")
            return GpuState(True, "GPU available")
        except (AttributeError, OSError):
            return GpuState(False, "NVML unavailable")
        finally:
            if initialized:
                try:
                    library.nvmlShutdown()
                except (AttributeError, OSError):
                    pass
