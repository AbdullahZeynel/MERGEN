#!/usr/bin/env bash
# Read-only inventory of a shared computer before it becomes a MERGEN GPU host.
#
# Changes nothing: no package is installed, no account is created, no service
# is started or stopped, no GPU process is touched. Run it as the normal user;
# a few checks report "not visible without privileges" instead of escalating.
#
#   bash infra/gpu-host/audit-host.sh [--venv /path/to/venv]
#
# Output is deliberately identity-free so it can be pasted into an issue:
# no IP address, token, full hostname, e-mail, process command line, case file
# name or GPU UUID. Exit code is non-zero only when a FAIL was recorded.
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

venv_path=''
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --venv)
            [[ "$#" -ge 2 ]] || { echo 'Usage: audit-host.sh [--venv PATH]' >&2; exit 2; }
            venv_path="$2"
            shift 2
            ;;
        -h|--help)
            echo 'Usage: audit-host.sh [--venv PATH]'
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo 'Usage: audit-host.sh [--venv PATH]' >&2
            exit 2
            ;;
    esac
done

section 'Operating system'
family="$(distro_family)"
if [[ -r /etc/os-release ]]; then
    # Distribution name and version are needed to pick package commands; they
    # do not identify the machine the way a hostname does.
    pretty="$(. /etc/os-release 2>/dev/null && printf '%s' "${PRETTY_NAME:-unknown}")"
    pass "Distribution: $pretty (family: $family)"
else
    fail 'No /etc/os-release; the distribution cannot be identified'
fi
info "Kernel: $(uname -r)"
info "Architecture: $(uname -m)"

if [[ "$family" == 'unknown' ]]; then
    warn 'Unrecognised distribution family; install-base.sh will refuse to run'
fi

section 'Init system and package manager'
if have systemctl && [[ -d /run/systemd/system ]]; then
    pass "systemd is running (version $(systemctl --version | awk 'NR==1{print $2}'))"
else
    fail 'systemd is not the running init; the service plan assumes systemd units'
fi
pkg_found=''
for candidate in apt-get pacman dnf zypper; do
    if have "$candidate"; then
        pkg_found="$candidate"
        break
    fi
done
if [[ -n "$pkg_found" ]]; then
    pass "Package manager: $pkg_found"
else
    warn 'No known package manager found'
fi

section 'Filesystem layout'
root_fs="$(fstype_of /)"
info "Root filesystem: ${root_fs:-unknown}"
info "Root mount point: $(mount_point_of /)"
case "$root_fs" in
    btrfs)
        if have btrfs; then
            if btrfs subvolume show / >/dev/null 2>&1; then
                pass 'Root is a Btrfs subvolume; snapshot scope can be reasoned about'
            else
                warn 'Btrfs root is not a subvolume; snapshot scope needs a manual decision'
            fi
        else
            warn 'Btrfs root but btrfs-progs is missing; cannot inspect subvolumes'
        fi
        ;;
    ext4|xfs)
        if have lvs && lvs --noheadings >/dev/null 2>&1; then
            pass "Root is $root_fs on LVM; snapshots need free extents in the volume group"
        else
            warn "Root is $root_fs without LVM; there is no built-in snapshot mechanism"
        fi
        ;;
    '') fail 'Root filesystem type could not be read' ;;
    *) warn "Unhandled root filesystem: $root_fs" ;;
esac
info 'Runtime snapshot scope is judged separately by check-snapshot-layout.sh'

section 'Disk encryption'
# Presence only. Device names and UUIDs stay out of the output.
crypt_signals=0
if have lsblk && lsblk -no TYPE 2>/dev/null | grep -qx 'crypt'; then
    crypt_signals=$((crypt_signals + 1))
fi
if have cryptsetup && [[ -d /sys/module/dm_crypt ]]; then
    crypt_signals=$((crypt_signals + 1))
fi
if [[ "$crypt_signals" -gt 0 ]]; then
    pass 'Block-level encryption is in use on at least one device'
else
    warn 'No dm-crypt signal found; runtime data would sit on unencrypted storage'
fi

section 'NVIDIA GPU'
if [[ -e /dev/nvidiactl ]] || compgen -G '/dev/nvidia[0-9]*' >/dev/null 2>&1; then
    pass 'NVIDIA device nodes are present'
else
    fail 'No NVIDIA device node; this host cannot run GPU inference yet'
fi
if [[ -r /proc/modules ]] && grep -q '^nvidia ' /proc/modules; then
    pass 'The nvidia kernel module is loaded'
else
    fail 'The nvidia kernel module is not loaded'
fi
if [[ -r /sys/module/nvidia/version ]]; then
    info "Kernel driver version: $(cat /sys/module/nvidia/version)"
fi
if have nvidia-smi; then
    if nvidia-smi >/dev/null 2>&1; then
        # Name and total memory only: no UUID, serial, or process list.
        gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1)"
        gpu_mem="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -n 1)"
        pass "nvidia-smi works: ${gpu_name:-unknown} (${gpu_mem:-unknown})"
        busy="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -n 1)"
        if [[ -n "$busy" && "$busy" -gt 512 ]]; then
            warn "GPU memory is already in use (${busy} MiB); a MERGEN job must wait, not kill it"
        else
            pass 'GPU memory is mostly free right now'
        fi
    else
        fail 'nvidia-smi is installed but fails to query the driver'
    fi
else
    fail 'nvidia-smi is not installed'
fi

section 'Tailscale'
if have tailscale; then
    pass 'The tailscale client is installed'
    if systemctl is-active --quiet tailscaled 2>/dev/null; then
        pass 'tailscaled is active'
    else
        warn 'tailscaled is not active'
    fi
    # Backend state only. Never print addresses, tailnet name or node identity.
    if state="$(tailscale status --json 2>/dev/null | sed -n 's/.*"BackendState": *"\([A-Za-z]*\)".*/\1/p' | head -n 1)" \
        && [[ -n "$state" ]]; then
        if [[ "$state" == 'Running' ]]; then
            pass 'Tailscale backend state: Running'
        else
            warn "Tailscale backend state: $state"
        fi
    else
        info 'Tailscale state is not readable without privileges; check it as the operator'
    fi
else
    warn 'Tailscale is not installed; the operator registers this node manually'
fi

section 'Accounts'
if user_exists "$MERGEN_MAINT_USER"; then
    pass "Maintenance account exists: $MERGEN_MAINT_USER"
else
    warn "Maintenance account is missing: $MERGEN_MAINT_USER"
fi
for account in "$MERGEN_DISPATCHER_USER" "$MERGEN_EXECUTOR_USER"; do
    if user_exists "$account"; then
        shell="$(user_shell "$account")"
        if is_nologin_shell "$shell"; then
            pass "Service account $account exists and cannot log in"
        else
            fail "Service account $account has a login shell"
        fi
    else
        warn "Service account is missing: $account"
    fi
done
if group_exists "$MERGEN_SERVICE_GROUP"; then
    pass "Shared service group exists: $MERGEN_SERVICE_GROUP"
else
    warn "Shared service group is missing: $MERGEN_SERVICE_GROUP"
fi

section 'Directories'
# Maximum permissive mode each path may carry. Anything wider is a finding.
audit_dir() {
    local path="$1" want_owner="$2" max_mode="$3" mode owner
    if [[ ! -e "$path" ]]; then
        warn "Missing: $path"
        return
    fi
    if [[ -L "$path" ]]; then
        fail "Symlink where a directory is expected: $path"
        return
    fi
    mode="$(path_mode "$path")"
    owner="$(path_owner "$path")"
    if mode_too_wide "$mode" "$max_mode"; then
        fail "$path has mode $mode, wider than $max_mode"
    elif [[ "$owner" != "$want_owner" ]]; then
        warn "$path is owned by $owner, expected $want_owner"
    else
        pass "$path ($owner, mode $mode)"
    fi
}
audit_dir "$MERGEN_APP_ROOT" "root:$MERGEN_MAINT_GROUP" 755
audit_dir "$MERGEN_MODEL_ROOT" "$MERGEN_MAINT_USER:$MERGEN_SERVICE_GROUP" 750
audit_dir "$MERGEN_DISPATCHER_STATE" "$MERGEN_DISPATCHER_USER:$MERGEN_DISPATCHER_USER" 700
audit_dir "$MERGEN_EXECUTOR_STATE" "$MERGEN_EXECUTOR_USER:$MERGEN_EXECUTOR_USER" 700
audit_dir "$MERGEN_RUNTIME_ROOT" "$MERGEN_DISPATCHER_USER:$MERGEN_EXECUTOR_USER" 750
audit_dir "$MERGEN_CONFIG_ROOT" 'root:root' 751

section 'Python'
if have python3; then
    pass "System Python: $(python3 --version 2>&1)"
else
    fail 'python3 is not installed'
fi
if [[ -n "$venv_path" ]]; then
    if safe_system_path "$venv_path" && [[ -x "$venv_path/bin/python" ]]; then
        if "$venv_path/bin/python" -c 'import torch' >/dev/null 2>&1; then
            cuda_ok="$("$venv_path/bin/python" -c \
                'import torch; print("yes" if torch.cuda.is_available() else "no")' 2>/dev/null || echo 'error')"
            case "$cuda_ok" in
                yes) pass 'PyTorch in the given venv reports CUDA available' ;;
                no) fail 'PyTorch in the given venv reports CUDA unavailable' ;;
                *) fail 'PyTorch is installed but the CUDA query failed' ;;
            esac
        else
            warn 'The given venv exists but PyTorch is not importable'
        fi
    else
        warn 'The given venv path is unusable; skipping the PyTorch check'
    fi
else
    info 'No venv given; run verify-gpu-runtime.sh once a model venv exists'
fi

summary 'Host audit'
