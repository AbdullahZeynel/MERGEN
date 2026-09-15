"""GPU admission: whether a job may start now.

The executor never stops a GPU process that belongs to someone else; when the
GPU is busy it simply does not start work and says so in executor.json. The
decision comes from an injected probe. G3 runs no GPU work, so its default
probe checks nothing; parsing nvidia-smi output for this decision is ruled
out, and the real NVML/CUDA preflight arrives with the G4 adapter.
"""
from __future__ import annotations

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
    """G3 default: no admission check, because no GPU work runs before G4."""

    def check(self) -> GpuState:
        return GpuState(True, "unchecked before G4")
