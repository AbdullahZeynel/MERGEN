#!/usr/bin/env bash
# Record, before MERGEN changes anything, what it is going to change, so that
# removing MERGEN later can be checked against what was there before.
#
#   sudo bash infra/gpu-host/capture-baseline.sh --output /root/mergen-baseline-<date>
#
# Writes baseline.txt and packages.txt (0600) into a new 0700 directory, or an
# empty one this account owns with no access for others. A directory that
# already holds files is refused: a baseline is never overwritten. Nothing else
# on the host is written, removed or restarted.
#
# Recorded: the service accounts and the maintenance account (ids, home,
# shell), the MERGEN groups, MERGEN's unit, sysusers, tmpfiles and sudoers
# files and drop-ins (with checksums; none of them holds a secret), the MERGEN
# directories (type, mode, owner, entry count, release names), the env files'
# existence, type, owner and mode, systemd enable/active states, the installed
# package list, whether an APT history exists, and the GPU name, driver
# version and total memory.
#
# Never recorded: env file content, size or checksum; anything inside the
# runtime spool, the model tree or a release; a hostname, an address, a GPU
# identifier, a comment field or a token. Run as root to see inside the 0700
# directories; without it they read "unreadable".
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
# shellcheck source=lib/services.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/services.sh"

usage='Usage: capture-baseline.sh --output DIR [--root DIR]'
output='' prefix=''
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --output|--root)
            [[ "$#" -ge 2 ]] || { echo "$usage" >&2; exit 2; }
            [[ "$1" == --output ]] && output="$2" || prefix="${2%/}"
            shift 2
            ;;
        -h|--help) sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo "$usage" >&2; exit 2 ;;
    esac
done
[[ "$output" == /* ]] || { echo 'Give --output as an absolute path.' >&2; echo "$usage" >&2; exit 2; }
services_paths "$prefix"
refuse() { echo "capture-baseline.sh: $*" >&2; exit 1; }

# The output directory: new, or empty and private. Nothing is ever overwritten.
if [[ -L "$output" ]]; then
    refuse "$output is a symlink"
elif [[ -e "$output" ]]; then
    [[ -d "$output" ]] || refuse "$output exists and is not a directory"
    [[ -z "$(ls -A -- "$output")" ]] || refuse "$output already holds files; a baseline is never overwritten, choose a new directory"
    [[ -O "$output" ]] || refuse "$output is not owned by this account"
    (( 8#$(stat -c '%a' -- "$output") & 8#077 )) && refuse "$output is open to other accounts; use a 0700 directory"
else
    mkdir -m 700 -- "$output" || refuse "cannot create $output (does its parent exist?)"
fi
umask 077
set -o noclobber

# -- helpers: every line names a path or an account and its metadata only ------
describe() {
    local label="$1" path="$prefix$1" kind found
    if [[ -L "$path" ]]; then
        kind="symlink to $(readlink -- "$path")"
    elif [[ -d "$path" ]]; then
        kind=directory
    elif [[ -f "$path" ]]; then
        kind=file
    elif [[ -e "$path" ]]; then
        kind=other
    else
        printf '%s: absent\n' "$label"
        return
    fi
    read -r -a found <<< "$(meta "$path")"
    printf '%s: %s mode=%s owner=%s:%s' "$label" "$kind" "${found[0]:-?}" "${found[1]:-?}" "${found[2]:-?}"
}
entries() {
    local listing
    if listing="$(find "$prefix$1" -mindepth 1 -maxdepth 1 -printf '.' 2>/dev/null)"; then
        printf ' entries=%s' "${#listing}"
    else
        printf ' entries=unreadable'
    fi
}
checksum() {
    local digest
    if digest="$(sha256sum -- "$prefix$1" 2>/dev/null)"; then
        printf ' sha256=%s' "${digest%% *}"
    else
        printf ' sha256=unreadable'
    fi
}
account() {
    local line uid gid home shell
    if ! line="$(getent passwd -- "$1" 2>/dev/null)"; then
        printf 'account %s: absent\n' "$1"
        return
    fi
    IFS=: read -r _ _ uid gid _ home shell <<< "$line"  # the comment field is skipped
    printf 'account %s: present uid=%s gid=%s home=%s shell=%s\n' "$1" "$uid" "$gid" "$home" "$shell"
}
group() {
    local line gid members member known='' others=0
    if ! line="$(getent group -- "$1" 2>/dev/null)"; then
        printf 'group %s: absent\n' "$1"
        return
    fi
    IFS=: read -r _ _ gid members <<< "$line"
    for member in ${members//,/ }; do
        case "$member" in
            "$MERGEN_MAINT_USER"|"$MERGEN_DISPATCHER_USER"|"$MERGEN_EXECUTOR_USER") known="$known,$member" ;;
            *) others=$((others + 1)) ;;
        esac
    done
    printf 'group %s: present gid=%s mergen_members=%s other_members=%s\n' "$1" "$gid" "${known#,}" "$others"
}
unit_state() {
    local enabled active
    enabled="$(systemctl is-enabled "$1" 2>/dev/null || true)"
    active="$(systemctl is-active "$1" 2>/dev/null || true)"
    printf 'unit %s: enabled=%s active=%s\n' "$1" "${enabled:-unknown}" "${active:-unknown}"
}

# -- the record ------------------------------------------------------------------
{
    printf '# MERGEN GPU host baseline, format 1\n'
    printf 'captured_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'captured_as_root=%s\n' "$([[ "$(id -u)" == 0 ]] && echo yes || echo no)"
    pretty="$(. "$prefix/etc/os-release" 2>/dev/null && printf '%s' "${PRETTY_NAME:-unknown}" || echo unknown)"
    printf 'distribution=%s\nkernel=%s\narchitecture=%s\n' "$pretty" "$(uname -r)" "$(uname -m)"

    printf '\n[accounts]\n'
    for name in "$MERGEN_DISPATCHER_USER" "$MERGEN_EXECUTOR_USER" "$MERGEN_MAINT_USER"; do account "$name"; done
    for name in "$MERGEN_SERVICE_GROUP" "$MERGEN_DISPATCHER_USER" "$MERGEN_EXECUTOR_USER"; do group "$name"; done

    printf '\n[definitions]\n'
    for path in /usr/lib/sysusers.d/mergen.conf /usr/lib/tmpfiles.d/mergen.conf /etc/sudoers.d/mergen-maintenance \
        /etc/systemd/system/mergen-dispatcher.service /etc/systemd/system/mergen-executor.service; do
        line="$(describe "$path")"
        [[ -f "$prefix$path" && ! -L "$prefix$path" ]] && line="$line$(checksum "$path")"
        printf '%s\n' "$line"
    done
    dropins="$( (mergen_dropins; global_dropins) | sed "s#^$prefix##" )"
    if [[ -z "$dropins" ]]; then
        printf 'drop-ins: none\n'
    else
        # No checksum here: a drop-in is exactly where a stray secret could sit.
        while IFS= read -r path; do printf '%s\n' "$(describe "$path")"; done <<< "$dropins"
    fi

    printf '\n[directories]\n'
    for path in /opt/mergen /srv/mergen-models /var/lib/mergen /var/lib/mergen/dispatcher \
        /var/lib/mergen/executor /var/lib/mergen/runtime /etc/mergen; do
        line="$(describe "$path")"
        [[ -d "$prefix$path" && ! -L "$prefix$path" ]] && line="$line$(entries "$path")"
        printf '%s\n' "$line"
    done
    printf '%s\n' "$(describe /opt/mergen/current)"
    releases=''
    for release in "$RELEASES"/*; do
        [[ -d "$release" ]] || continue
        valid_version "${release##*/}" && releases="$releases,${release##*/}" || releases="$releases,(other)"
    done
    printf 'releases=%s\n' "${releases#,}"
    for service in "${SERVICES[@]}"; do
        # Existence, type, owner and mode only: never content, size or checksum.
        printf '%s\n' "$(describe "$MERGEN_CONFIG_ROOT/$service.env")"
    done

    printf '\n[systemd]\n'
    if have systemctl; then
        for unit in mergen-dispatcher.service mergen-executor.service tailscaled.service; do unit_state "$unit"; done
    else
        printf 'systemctl: unavailable\n'
    fi

    printf '\n[packages]\n'
    if have dpkg-query; then
        { dpkg-query -W -f='${binary:Package}\t${Version}\n' 2>/dev/null || true; } | LC_ALL=C sort > "$output/packages.txt"
        printf 'package_manager=dpkg packages=%s (packages.txt)\n' "$(wc -l < "$output/packages.txt")"
    elif have pacman; then
        { pacman -Q 2>/dev/null || true; } | LC_ALL=C sort > "$output/packages.txt"
        printf 'package_manager=pacman packages=%s (packages.txt)\n' "$(wc -l < "$output/packages.txt")"
    else
        printf 'package_manager=unknown\n'
    fi
    rotated="$(find "$prefix/var/log/apt" -maxdepth 1 -name 'history.log.*' -printf '.' 2>/dev/null || true)"
    if [[ -f "$prefix/var/log/apt/history.log" ]]; then
        printf 'apt_history=present rotated=%s\n' "${#rotated}"
    else
        printf 'apt_history=absent rotated=%s\n' "${#rotated}"
    fi

    printf '\n[nvidia]\n'
    if have nvidia-smi && gpus="$(nvidia-smi --query-gpu=index,name,driver_version,memory.total \
        --format=csv,noheader 2>/dev/null)"; then
        while IFS=',' read -r index name driver memory; do
            printf 'gpu %s: name=%s driver=%s memory_total=%s\n' "${index// /}" "${name# }" "${driver// /}" "${memory# }"
        done <<< "$gpus"
    else
        printf 'nvidia: nvidia-smi unavailable\n'
    fi
} > "$output/baseline.txt"
[[ -e "$output/packages.txt" ]] || : > "$output/packages.txt"

printf 'Baseline written: %s/baseline.txt and packages.txt (0600, directory 0700).\n' "$output"
printf 'Nothing else was changed. Keep it with the host notes; it holds no secret.\n'
