#!/usr/bin/env bash
# Read-only: decide whether the runtime directory can be kept out of a root
# snapshot. Takes no snapshot, deletes no snapshot, restores nothing.
#
#   bash infra/gpu-host/check-snapshot-layout.sh [--runtime /var/lib/mergen/runtime]
#
# The rule this enforces: live job input, results and spool under the runtime
# directory must never be captured by a root snapshot or a backup of the root
# filesystem. Proving that requires the runtime path to sit on its own mount
# or its own Btrfs subvolume. If the layout cannot be proven safe, the script
# fails; it never assumes safety from a filesystem name alone.
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

runtime="$MERGEN_RUNTIME_ROOT"
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --runtime)
            [[ "$#" -ge 2 ]] || { echo 'Usage: check-snapshot-layout.sh [--runtime PATH]' >&2; exit 2; }
            runtime="$2"
            shift 2
            ;;
        -h|--help)
            echo 'Usage: check-snapshot-layout.sh [--runtime PATH]'
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

section 'Runtime path'
if ! safe_system_path "$runtime"; then
    summary 'Snapshot layout' || exit 1
fi
if [[ ! -d "$runtime" ]]; then
    fail "Runtime directory does not exist yet: $runtime"
    info 'Create the directory tree first (install-base.sh --apply), then re-run.'
    summary 'Snapshot layout' || exit 1
fi
pass "Runtime directory: $runtime"

if ! have findmnt; then
    fail 'findmnt is unavailable; the mount layout cannot be proven'
    summary 'Snapshot layout' || exit 1
fi

root_fs="$(fstype_of /)"
root_src="$(mount_source_of /)"
runtime_fs="$(fstype_of "$runtime")"
runtime_mp="$(mount_point_of "$runtime")"
runtime_src="$(mount_source_of "$runtime")"

section 'Root filesystem'
info "Root: ${root_fs:-unknown}"
info "Runtime carrier: ${runtime_fs:-unknown} mounted at ${runtime_mp:-unknown}"

section 'Snapshot scope'
separate_mount=0
[[ -n "$runtime_mp" && "$runtime_mp" != '/' ]] && separate_mount=1

case "$root_fs" in
    btrfs)
        if [[ "$runtime_fs" != 'btrfs' && "$separate_mount" -eq 1 ]]; then
            pass 'Runtime sits on a separate non-Btrfs mount; a root snapshot cannot capture it'
        elif ! have btrfs; then
            fail 'btrfs-progs is missing; subvolume membership cannot be proven'
        else
            root_subvol="$(btrfs subvolume show / 2>/dev/null | awk -F': *' '/^[[:space:]]*(Name|UUID)/ {print; exit}')"
            if ! btrfs subvolume show "$runtime" >/dev/null 2>&1; then
                fail 'Runtime is not its own Btrfs subvolume; a root snapshot would capture live job data'
                info "Create one, then move the contents into it: btrfs subvolume create $runtime"
            elif [[ "$separate_mount" -eq 0 ]]; then
                # A nested subvolume is excluded from a snapshot of its parent,
                # but only when the snapshot is non-recursive. That is the
                # default for `btrfs subvolume snapshot`, yet several backup
                # tools walk the tree instead. Do not call that proven.
                warn 'Runtime is a nested Btrfs subvolume; snapshots of the parent exclude it only when non-recursive'
                info 'Prove it for the tool actually in use, or mount the subvolume separately in /etc/fstab.'
                [[ -n "$root_subvol" ]] && info 'Root subvolume identity is intentionally not printed.'
            else
                pass 'Runtime is a separately mounted Btrfs subvolume; root snapshots exclude it'
            fi
        fi
        ;;
    ext4|xfs|'')
        if [[ "$separate_mount" -eq 1 && "$runtime_src" != "$root_src" ]]; then
            pass 'Runtime is on a different block device than root; root snapshots exclude it'
        elif [[ "$separate_mount" -eq 1 ]]; then
            fail 'Runtime is a separate mount but shares the root block device; an LVM snapshot would capture it'
        else
            fail "Runtime lives inside the root ${root_fs:-filesystem}; any root snapshot or image would capture live job data"
            info 'Give the runtime its own logical volume or partition, mount it, then re-run.'
        fi
        ;;
    *)
        fail "Unsupported root filesystem for an automated decision: $root_fs"
        info 'Decide the snapshot scope by hand and record it in docs/GPU_HOST_RUNBOOK.md.'
        ;;
esac

section 'Backup exclusions'
# A correct mount layout still loses if a file-level backup walks into it.
if [[ -d "$runtime" ]]; then
    mode="$(path_mode "$runtime")"
    if mode_too_wide "$mode" 750; then
        fail "Runtime directory mode $mode is wider than 750; other desktop users could read job data"
    else
        pass "Runtime directory mode is $mode"
    fi
fi
info 'File-level backup tools ignore mount boundaries unless told to.'
info 'Add an explicit exclusion for the runtime path in whatever backup tool this host uses.'
info 'This script does not create, delete or restore any snapshot.'

summary 'Snapshot layout'
