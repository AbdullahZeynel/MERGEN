# Shared helpers for the MERGEN GPU host scripts. Source; do not execute.
#
# Every script that sources this file inherits strict mode and one reporting
# vocabulary: PASS (verified), WARN (needs a human decision), FAIL (unsafe or
# unproven). Nothing here writes outside a caller-supplied path.
#
# Redaction rule: these scripts run on a computer the owner uses daily and
# their output is pasted into issues and chat. Never print an IP address, a
# token, the full hostname, an e-mail address, a process command line, a case
# or patient file name, or a GPU UUID/serial. Report presence, not identity.

set -euo pipefail

MERGEN_PASS_COUNT=0
MERGEN_WARN_COUNT=0
MERGEN_FAIL_COUNT=0

# Accounts and groups. The maintenance account is a human login; the two
# service accounts never log in and never hold sudo.
MERGEN_MAINT_USER='mergen'
MERGEN_MAINT_GROUP='mergen'
MERGEN_DISPATCHER_USER='mergen-dispatcher'
MERGEN_EXECUTOR_USER='mergen-executor'
MERGEN_SERVICE_GROUP='mergen-svc'

# Directory contract. Keep in sync with docs/GPU_HOST_RUNBOOK.md.
MERGEN_APP_ROOT='/opt/mergen'
MERGEN_MODEL_ROOT='/srv/mergen-models'
MERGEN_STATE_ROOT='/var/lib/mergen'
MERGEN_DISPATCHER_STATE="$MERGEN_STATE_ROOT/dispatcher"
MERGEN_EXECUTOR_STATE="$MERGEN_STATE_ROOT/executor"
MERGEN_RUNTIME_ROOT="$MERGEN_STATE_ROOT/runtime"
MERGEN_CONFIG_ROOT='/etc/mergen'

pass() {
    MERGEN_PASS_COUNT=$((MERGEN_PASS_COUNT + 1))
    printf 'PASS  %s\n' "$*"
}

warn() {
    MERGEN_WARN_COUNT=$((MERGEN_WARN_COUNT + 1))
    printf 'WARN  %s\n' "$*"
}

fail() {
    MERGEN_FAIL_COUNT=$((MERGEN_FAIL_COUNT + 1))
    printf 'FAIL  %s\n' "$*"
}

info() { printf '      %s\n' "$*"; }

section() { printf '\n== %s ==\n' "$*"; }

# Exit 0 only when nothing failed. WARN keeps exit 0 because a warning is a
# decision for the operator, not a broken host; the summary still shows it.
summary() {
    printf '\n%s: %d PASS, %d WARN, %d FAIL\n' \
        "${1:-Summary}" "$MERGEN_PASS_COUNT" "$MERGEN_WARN_COUNT" "$MERGEN_FAIL_COUNT"
    [[ "$MERGEN_FAIL_COUNT" -eq 0 ]]
}

have() { command -v "$1" >/dev/null 2>&1; }

# Distribution family, from os-release only. No guessing from package managers:
# an unknown family must stop the installer rather than run Debian commands on
# an Arch host.
distro_family() {
    local id='' like=''
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        id="$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-}")"
        like="$(. /etc/os-release 2>/dev/null && printf '%s' "${ID_LIKE:-}")"
    fi
    case " $id $like " in
        *' debian '*|*' ubuntu '*) printf 'debian' ;;
        *' arch '*|*' archlinux '*|*' cachyos '*) printf 'arch' ;;
        *) printf 'unknown' ;;
    esac
}

# Reject a path that is not absolute, contains a traversal segment, or whose
# parents cross a symlink. Callers use this before touching any system path.
safe_system_path() {
    local path="$1" part resolved
    [[ "$path" == /* ]] || { fail "Path is not absolute: $path"; return 1; }
    IFS='/' read -r -a _mergen_parts <<< "$path"
    for part in "${_mergen_parts[@]}"; do
        if [[ "$part" == '.' || "$part" == '..' ]]; then
            fail "Path contains a traversal segment: $path"
            return 1
        fi
    done
    if [[ -L "$path" ]]; then
        fail "Path is a symlink and will not be used: $path"
        return 1
    fi
    if [[ -e "$path" ]]; then
        resolved="$(readlink -f -- "$path" 2>/dev/null || true)"
        if [[ "$resolved" != "$path" ]]; then
            fail "Path resolves elsewhere through a symlink: $path"
            return 1
        fi
    fi
    return 0
}

# Octal mode of an existing path, or the empty string.
path_mode() { stat -c '%a' -- "$1" 2>/dev/null || true; }
path_owner() { stat -c '%U:%G' -- "$1" 2>/dev/null || true; }

# A mode is too wide when it grants anything to "others", or group-write on a
# directory we declared group-read.
mode_too_wide() {
    local mode="$1" max="$2"
    [[ -n "$mode" && -n "$max" ]] || return 1
    (( 8#$mode & ~8#$max ))
}

user_exists() { id -u -- "$1" >/dev/null 2>&1; }
group_exists() { getent group -- "$1" >/dev/null 2>&1; }

# Login shell of an account, for asserting that service accounts cannot log in.
user_shell() { getent passwd -- "$1" 2>/dev/null | awk -F: '{print $7}'; }

is_nologin_shell() {
    case "$1" in
        */nologin|*/false) return 0 ;;
        *) return 1 ;;
    esac
}

# The mount point that actually carries a path, and its filesystem type.
mount_point_of() { findmnt -n -o TARGET --target "$1" 2>/dev/null || true; }
fstype_of() { findmnt -n -o FSTYPE --target "$1" 2>/dev/null || true; }
mount_source_of() { findmnt -n -o SOURCE --target "$1" 2>/dev/null || true; }
