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
MERGEN_DISPATCHER_USER='mergen-dispatcher'
MERGEN_EXECUTOR_USER='mergen-executor'
MERGEN_SERVICE_GROUP='mergen-svc'

# Directory contract. Keep in sync with docs/GPU_HOST_RUNBOOK.md and
# tmpfiles.d/mergen.conf.
#
# Spool contract: the runtime tree is setgid to the shared service group, so a
# file the dispatcher writes is readable by the executor and a result the
# executor writes is readable by the dispatcher. Both units run with
# UMask=0007, which makes that group access real while leaving "others" with
# nothing. Without both halves the hand-off cannot work.
MERGEN_RUNTIME_MODE='2770'
MERGEN_SERVICE_UMASK='0007'

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

# Reject a path that is not absolute, contains a traversal segment, or crosses
# a symlink at ANY component. Checking only the final component is not enough:
# /tmp/link/not-created has no symlink at the leaf (it does not exist yet) but
# still resolves through one, so the walk starts at / and stops at the first
# component that does not exist.
#
# Empty segments are skipped, so "/", "//srv//x" and "/srv/x" behave the same.
safe_system_path() {
    local path="$1" part current=''
    local -a parts=()
    [[ "$path" == /* ]] || { fail "Path is not absolute: $path"; return 1; }
    IFS='/' read -r -a parts <<< "$path"

    # First pass: reject traversal anywhere in the path. This must cover the
    # whole string, including segments below a component that does not exist
    # yet, otherwise /opt/missing/../../etc would slip through.
    for part in "${parts[@]}"; do
        if [[ "$part" == '.' || "$part" == '..' ]]; then
            fail "Path contains a traversal segment: $path"
            return 1
        fi
    done

    # Second pass: walk down from / and stop at the first component that does
    # not exist; nothing below it can be a symlink yet.
    for part in "${parts[@]}"; do
        [[ -z "$part" ]] && continue
        current="$current/$part"
        if [[ -L "$current" ]]; then
            fail "Path crosses a symlink at $current"
            return 1
        fi
        [[ -e "$current" ]] || return 0
    done
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
