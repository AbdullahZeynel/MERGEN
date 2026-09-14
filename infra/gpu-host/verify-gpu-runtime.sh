#!/usr/bin/env bash
# Prove that one model virtual environment can actually reach the GPU.
#
#   bash infra/gpu-host/verify-gpu-runtime.sh /path/to/venv
#
# Installs nothing: no driver, no CUDA toolkit, no Python package. It only
# reads the driver through nvidia-smi and runs a tiny tensor round trip in the
# venv you name. Run it once per model venv (imaging and genomics).
#
# Output carries no GPU UUID, serial number, or process list, so it is safe to
# paste into an issue.
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

if [[ "$#" -ne 1 ]]; then
    echo 'Usage: verify-gpu-runtime.sh /path/to/venv' >&2
    exit 2
fi
venv="$1"

section 'Driver'
if ! have nvidia-smi; then
    fail 'nvidia-smi is not installed; install the driver with the distribution method first'
    summary 'GPU runtime' || exit 1
fi
if nvidia-smi >/dev/null 2>&1; then
    name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1)"
    driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1)"
    pass "nvidia-smi responds: ${name:-unknown}, driver ${driver:-unknown}"
else
    fail 'nvidia-smi is installed but cannot talk to the driver (reboot after a driver update?)'
    summary 'GPU runtime' || exit 1
fi

section 'Virtual environment'
if ! safe_system_path "$venv"; then
    summary 'GPU runtime' || exit 1
fi
python="$venv/bin/python"
if [[ ! -x "$python" ]]; then
    fail "No executable interpreter at $python"
    summary 'GPU runtime' || exit 1
fi
if version="$("$python" --version 2>&1)"; then
    pass "Interpreter runs: $version"
else
    fail 'The interpreter in that venv does not run'
    summary 'GPU runtime' || exit 1
fi

section 'PyTorch'
if ! "$python" -c 'import torch' >/dev/null 2>&1; then
    fail 'PyTorch is not importable in this venv'
    info 'Install a CUDA-enabled build in the venv; this script does not install packages.'
    summary 'GPU runtime' || exit 1
fi
torch_report="$("$python" - <<'PY' 2>&1
import torch

print(f"torch={torch.__version__}")
print(f"cuda_build={torch.version.cuda or 'none'}")
print(f"available={torch.cuda.is_available()}")
PY
)" || { fail 'Querying PyTorch failed'; summary 'GPU runtime' || exit 1; }
while IFS='=' read -r key value; do
    case "$key" in
        torch) pass "PyTorch $value" ;;
        cuda_build)
            if [[ "$value" == 'none' ]]; then
                fail 'This PyTorch build has no CUDA runtime (CPU-only wheel)'
            else
                pass "PyTorch bundles CUDA runtime $value"
            fi
            ;;
        available)
            if [[ "$value" == 'True' ]]; then
                pass 'torch.cuda.is_available() is True'
            else
                fail 'torch.cuda.is_available() is False'
            fi
            ;;
    esac
done <<< "$torch_report"

if [[ "$MERGEN_FAIL_COUNT" -ne 0 ]]; then
    summary 'GPU runtime' || exit 1
fi

section 'Device and tensor round trip'
# Device name and total memory only. Never capability UUIDs or serials.
device_report="$("$python" - <<'PY' 2>&1
import torch

count = torch.cuda.device_count()
if count < 1:
    raise SystemExit("no_device")
props = torch.cuda.get_device_properties(0)
print(f"count={count}")
print(f"name={props.name}")
print(f"vram_mib={props.total_memory // (1024 * 1024)}")

# Smallest honest end-to-end check: build on the CPU, move to the GPU, do real
# arithmetic there, bring it back, and compare against the CPU result.
cpu = torch.arange(16, dtype=torch.float32).reshape(4, 4)
gpu = cpu.to("cuda")
result = (gpu @ gpu).sum().cpu()
expected = (cpu @ cpu).sum()
ok = bool(torch.allclose(result, expected))
print(f"roundtrip={ok}")
torch.cuda.synchronize()
PY
)" || { fail 'The CUDA device query or tensor round trip raised an error'; info "$device_report"; summary 'GPU runtime' || exit 1; }

while IFS='=' read -r key value; do
    case "$key" in
        count) pass "CUDA devices visible: $value" ;;
        name) pass "Device 0: $value" ;;
        vram_mib) pass "Total VRAM: ${value} MiB" ;;
        roundtrip)
            if [[ "$value" == 'True' ]]; then
                pass 'CPU to GPU transfer, matmul and read back match the CPU result'
            else
                fail 'The GPU result does not match the CPU result'
            fi
            ;;
    esac
done <<< "$device_report"

info 'No package was installed and no GPU process was touched.'
summary 'GPU runtime'
