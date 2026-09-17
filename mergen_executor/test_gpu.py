from __future__ import annotations

import ctypes
import unittest

from mergen_executor.gpu import NvmlGpu


class FakeNvml:
    def __init__(self, *, memory_mb=100, utilization=5, fail=None):
        self.memory_mb, self.utilization, self.fail = memory_mb, utilization, fail
        self.shutdowns = 0

    def nvmlInit_v2(self):
        return 1 if self.fail == "init" else 0

    def nvmlDeviceGetHandleByIndex_v2(self, index, pointer):
        return 1 if self.fail == "device" else 0

    def nvmlDeviceGetMemoryInfo(self, device, pointer):
        if self.fail == "memory":
            return 1
        memory = ctypes.cast(pointer, ctypes.POINTER(type(pointer._obj))).contents
        memory.used = self.memory_mb * 1024 * 1024
        return 0

    def nvmlDeviceGetUtilizationRates(self, device, pointer):
        if self.fail == "utilization":
            return 1
        utilization = ctypes.cast(pointer, ctypes.POINTER(type(pointer._obj))).contents
        utilization.gpu = self.utilization
        return 0

    def nvmlShutdown(self):
        self.shutdowns += 1
        return 0


class NvmlProbeTests(unittest.TestCase):
    def test_gpu_below_both_thresholds_is_available(self):
        library = FakeNvml(memory_mb=999, utilization=19)
        state = NvmlGpu(1000, 20, library).check()
        self.assertTrue(state.available)
        self.assertEqual(library.shutdowns, 1)

    def test_memory_or_compute_pressure_waits_without_naming_a_process(self):
        cases = ((FakeNvml(memory_mb=1001), "GPU memory busy"),
                 (FakeNvml(utilization=21), "GPU compute busy"))
        for library, reason in cases:
            with self.subTest(reason=reason):
                state = NvmlGpu(1000, 20, library).check()
                self.assertEqual((state.available, state.reason), (False, reason))
                self.assertEqual(library.shutdowns, 1)

    def test_every_nvml_failure_is_closed_and_initialized_calls_shutdown(self):
        for failure in ("init", "device", "memory", "utilization"):
            with self.subTest(failure=failure):
                library = FakeNvml(fail=failure)
                state = NvmlGpu(1000, 20, library).check()
                self.assertFalse(state.available)
                self.assertEqual(library.shutdowns, 0 if failure == "init" else 1)


if __name__ == "__main__":
    unittest.main()
