#!/usr/bin/env bash
# Create the MERGEN account, group and directory base on a shared GPU host.
#
#   bash infra/gpu-host/install-base.sh            # plan only, changes nothing
#   sudo bash infra/gpu-host/install-base.sh --apply
#
# Plan mode is the default and needs no privileges: it prints what --apply
# would do and touches nothing. Running --apply twice is a no-op.
#
# This script deliberately never: downloads or installs an NVIDIA driver, CUDA
# toolkit, PyTorch or model weights; logs in to Tailscale; generates a secret;
# stops a GPU process; enables or starts a service; deletes anything.
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
apply=0
create_maintenance=1

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --apply) apply=1; shift ;;
        --no-maintenance-account) create_maintenance=0; shift ;;
        -h|--help)
            sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ "$apply" -eq 1 && "$EUID" -ne 0 ]]; then
    echo 'Run --apply as root (sudo). Plan mode needs no privileges.' >&2
    exit 1
fi

planned=0
step() {
    planned=$((planned + 1))
    printf 'PLAN  %s\n' "$*"
}
done_() { printf 'DONE  %s\n' "$*"; }
skip() { printf 'SKIP  %s\n' "$*"; }

# Run a command in apply mode; describe it in plan mode.
act() {
    local description="$1"
    shift
    if [[ "$apply" -eq 0 ]]; then
        step "$description"
        return 0
    fi
    if "$@"; then
        done_ "$description"
    else
        echo "FAILED: $description" >&2
        exit 1
    fi
}

section 'Preconditions'
family="$(distro_family)"
case "$family" in
    debian|arch) pass "Supported distribution family: $family" ;;
    *)
        fail 'Unsupported or unrecognised distribution'
        info 'This script refuses to guess package or account commands.'
        info 'Add explicit support in distro_family() before running it here.'
        exit 1
        ;;
esac

if ! have systemctl || [[ ! -d /run/systemd/system ]]; then
    fail 'systemd is not the running init; the account and directory plan assumes it'
    exit 1
fi
pass 'systemd is running'

for tool in systemd-sysusers systemd-tmpfiles install getent; do
    if have "$tool"; then
        pass "Required tool present: $tool"
    else
        fail "Required tool missing: $tool"
        exit 1
    fi
done

for candidate in "$here/sysusers.d/mergen.conf" "$here/tmpfiles.d/mergen.conf" \
    "$here/dispatcher.env.example" "$here/executor.env.example"; do
    [[ -f "$candidate" ]] || { fail "Missing source file: $candidate"; exit 1; }
done
pass 'Declarative source files are present'

# Refuse to install a configuration whose paths could escape where we intend.
for path in "$MERGEN_APP_ROOT" "$MERGEN_MODEL_ROOT" "$MERGEN_STATE_ROOT" \
    "$MERGEN_RUNTIME_ROOT" "$MERGEN_CONFIG_ROOT"; do
    safe_system_path "$path" || exit 1
done
pass 'Target paths are absolute, traversal-free and not symlinks'

section 'Service accounts and groups'
# systemd-sysusers is declarative: it creates what is missing and leaves the
# rest alone, which is exactly the idempotence we need.
if [[ -f /usr/lib/sysusers.d/mergen.conf ]] &&
    cmp -s "$here/sysusers.d/mergen.conf" /usr/lib/sysusers.d/mergen.conf; then
    skip 'sysusers.d/mergen.conf already installed and identical'
else
    act 'Install /usr/lib/sysusers.d/mergen.conf (0644 root:root)' \
        install -D -m 644 -o root -g root "$here/sysusers.d/mergen.conf" /usr/lib/sysusers.d/mergen.conf
fi
# Name the file explicitly: a bare `systemd-sysusers` also applies every other
# pending definition on the host, which is not ours to decide.
act 'Apply systemd-sysusers for mergen.conf only' \
    systemd-sysusers /usr/lib/sysusers.d/mergen.conf

if [[ "$apply" -eq 1 ]]; then
    for account in "$MERGEN_DISPATCHER_USER" "$MERGEN_EXECUTOR_USER"; do
        if ! user_exists "$account"; then
            fail "sysusers did not create $account"
            exit 1
        fi
        shell="$(user_shell "$account")"
        if is_nologin_shell "$shell"; then
            pass "$account exists with a nologin shell"
        else
            fail "$account has a login shell; refusing to continue"
            exit 1
        fi
    done
fi

section 'Maintenance account'
# The model tree is owned by this account, so tmpfiles cannot run without it.
if user_exists "$MERGEN_MAINT_USER"; then
    skip "Maintenance account already exists: $MERGEN_MAINT_USER"
    info 'Ownership and sudo scope are not changed for an existing account.'
    maint_home="$(getent passwd "$MERGEN_MAINT_USER" | awk -F: '{print $6}')"
    maint_shell="$(user_shell "$MERGEN_MAINT_USER")"
    if [[ -n "$maint_home" && -d "$maint_home" ]]; then
        pass "Maintenance home directory exists"
    else
        fail "$MERGEN_MAINT_USER has no usable home directory"
        exit 1
    fi
    if is_nologin_shell "$maint_shell"; then
        fail "$MERGEN_MAINT_USER has a nologin shell; it cannot be used for maintenance"
        info 'Give it a login shell, or pick a different maintenance account.'
        exit 1
    fi
    pass 'Maintenance account has a login shell'
elif [[ "$create_maintenance" -eq 0 ]]; then
    fail "--no-maintenance-account was given but $MERGEN_MAINT_USER does not exist"
    info 'The model tree is owned by this account; tmpfiles would fail on an unknown owner.'
    info 'Create it yourself, or drop --no-maintenance-account.'
    exit 1
else
    # A human account: real home, real shell, and a locked password so it can
    # only be reached with `sudo -u mergen -i` or an explicitly set credential.
    act "Create human maintenance account $MERGEN_MAINT_USER (home, bash, locked password)" \
        useradd --create-home --shell /bin/bash --comment 'MERGEN maintenance' "$MERGEN_MAINT_USER"
    act "Lock the password of $MERGEN_MAINT_USER" passwd --lock "$MERGEN_MAINT_USER"
fi
info 'Sudo is NOT granted here. Review sudoers.d/mergen-maintenance.example and'
info 'install it with visudo on the host if the narrowed command set is right.'

section 'Directories'
# systemd-tmpfiles fails on an unknown owner or group. Check the names the
# configuration actually uses rather than assuming sysusers succeeded.
if [[ "$apply" -eq 1 ]]; then
    while read -r _ _ _ owner group _; do
        [[ -n "$owner" && "$owner" != '-' ]] && { user_exists "$owner" || { fail "tmpfiles names an unknown owner: $owner"; exit 1; }; }
        [[ -n "$group" && "$group" != '-' ]] && { group_exists "$group" || { fail "tmpfiles names an unknown group: $group"; exit 1; }; }
    done < <(grep -E '^d ' "$here/tmpfiles.d/mergen.conf")
    pass 'Every owner and group named by tmpfiles exists'
fi
if [[ -f /usr/lib/tmpfiles.d/mergen.conf ]] &&
    cmp -s "$here/tmpfiles.d/mergen.conf" /usr/lib/tmpfiles.d/mergen.conf; then
    skip 'tmpfiles.d/mergen.conf already installed and identical'
else
    act 'Install /usr/lib/tmpfiles.d/mergen.conf (0644 root:root)' \
        install -D -m 644 -o root -g root "$here/tmpfiles.d/mergen.conf" /usr/lib/tmpfiles.d/mergen.conf
fi
info 'If the runtime path is a separate mount or Btrfs subvolume, mount it before'
info 'applying tmpfiles, otherwise the new directory is hidden by the later mount.'
act 'Apply systemd-tmpfiles --create (creates and corrects modes only; deletes nothing)' \
    systemd-tmpfiles --create /usr/lib/tmpfiles.d/mergen.conf

section 'Configuration files'
# Seed empty configuration from the committed examples. These contain no
# secret: every credential field is blank, so a service started against them
# fails loudly instead of running with a guessed value.
seed_env() {
    local example="$1" target="$2" group="$3"
    if [[ -L "$target" ]]; then
        fail "Refusing to write through a symlink: $target"
        info 'Remove or replace it with a regular file before re-running.'
        exit 1
    fi
    if [[ -e "$target" ]]; then
        if [[ -f "$target" ]]; then
            skip "Already present, left untouched: $target"
            return 0
        fi
        fail "$target exists but is not a regular file"
        exit 1
    fi
    act "Seed $target from the example (0640 root:$group, all secrets blank)" \
        install -m 640 -o root -g "$group" "$example" "$target"
}
seed_env "$here/dispatcher.env.example" "$MERGEN_CONFIG_ROOT/dispatcher.env" "$MERGEN_DISPATCHER_USER"
seed_env "$here/executor.env.example" "$MERGEN_CONFIG_ROOT/executor.env" "$MERGEN_EXECUTOR_USER"
info 'No token or address is generated. Fill them on the host by hand.'

section 'Deliberately not done'
info 'NVIDIA driver, CUDA toolkit, PyTorch and model weights: installed by the'
info 'operator with the distribution method described in docs/GPU_HOST_RUNBOOK.md.'
info 'Tailscale login: performed by the operator on the host.'
info 'Services: unit files here are .example only; nothing is enabled or started.'
info 'Snapshots: taken by the operator after check-snapshot-layout.sh passes.'

if [[ "$apply" -eq 0 ]]; then
    printf '\nPlan only: %d action(s) would run. Nothing was changed.\n' "$planned"
    printf 'Re-run with --apply as root to execute them.\n'
else
    printf '\nApplied. Verify with: bash %s/audit-host.sh\n' "$here"
fi

summary 'Base install'
