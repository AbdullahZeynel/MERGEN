#!/usr/bin/env bash
# Check the dispatcher/executor service contract without changing anything.
#
#   bash infra/gpu-host/verify-services.sh --before        # is the host ready to stage?
#   sudo bash infra/gpu-host/verify-services.sh --after    # the release `current` names
#
# --before checks accounts, groups, directories, env files, the unit files
# about to be staged and that no drop-in overrides either unit. --after adds
# the release itself: its manifest, each venv's imports and dependencies, the
# spool gate version, the configuration each service would load, the
# installed units and `systemd-analyze verify`. stage-services.sh runs both.
# Nothing is written, enabled or started.
#
# Output names paths, versions and variable names only: never a value from an
# env file, an address, a hostname or anything found under the spool.
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
# shellcheck source=lib/services.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/services.sh"

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
usage='Usage: verify-services.sh --before|--after [--root DIR] [--release-dir DIR]'
phase='' prefix='' release=''
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --before|--after) phase="${1#--}"; shift ;;
        --root) [[ "$#" -ge 2 ]] || { echo "$usage" >&2; exit 2; }; prefix="${2%/}"; shift 2 ;;
        --release-dir) [[ "$#" -ge 2 ]] || { echo "$usage" >&2; exit 2; }; release="$2"; shift 2 ;;
        -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo "$usage" >&2; exit 2 ;;
    esac
done
[[ -n "$phase" ]] || { echo "$usage" >&2; exit 2; }
services_paths "$prefix"
as_root=0
[[ "$(id -u)" == 0 ]] && as_root=1

# -- accounts ---------------------------------------------------------------
section 'Accounts and groups'
for account in "$MERGEN_DISPATCHER_USER" "$MERGEN_EXECUTOR_USER"; do
    if ! user_exists "$account"; then
        fail "Service account is missing: $account (run install-base.sh --apply)"
        continue
    fi
    is_nologin_shell "$(user_shell "$account")" && pass "$account exists and cannot log in" \
        || fail "$account has a login shell"
    in_group "$account" "$MERGEN_SERVICE_GROUP" && pass "$account is in $MERGEN_SERVICE_GROUP" \
        || fail "$account is not in $MERGEN_SERVICE_GROUP; the spool hand-off needs it"
done
# The token file is group-readable by mergen-dispatcher, so that group must
# stay the dispatcher's alone.
if in_group "$MERGEN_EXECUTOR_USER" "$MERGEN_DISPATCHER_USER"; then
    fail "$MERGEN_EXECUTOR_USER is in group $MERGEN_DISPATCHER_USER and could read the worker token"
else
    pass "$MERGEN_EXECUTOR_USER is not in group $MERGEN_DISPATCHER_USER"
fi
device_groups=''
for gpu_group in video render; do
    if group_exists "$gpu_group" && in_group "$MERGEN_DISPATCHER_USER" "$gpu_group"; then
        device_groups="$device_groups $gpu_group"
    fi
done
[[ -z "$device_groups" ]] && pass "$MERGEN_DISPATCHER_USER is in no GPU device group" \
    || fail "$MERGEN_DISPATCHER_USER is in a group that may open GPU devices:$device_groups"

# -- directories --------------------------------------------------------------
section 'Directories and spool'
expect_dir() {
    local path="$1" owner="$2" mode="$3" exact="${4:-}" found
    if [[ -L "$path" || ! -d "$path" ]]; then
        fail "Not a real directory: $path"
        return
    fi
    read -r -a found <<< "$(meta "$path")"
    if [[ "${found[1]}:${found[2]}" != "$owner" ]]; then
        fail "$path is owned by ${found[1]}:${found[2]}, expected $owner"
    elif [[ -n "$exact" && "${found[0]}" != "$mode" ]] || mode_too_wide "${found[0]}" "$mode"; then
        fail "$path has mode ${found[0]}, expected ${exact:+exactly }$mode"
    else
        pass "$path ($owner, ${found[0]})"
    fi
}
expect_dir "$APP_ROOT" root:root 755
expect_dir "$CONFIG_ROOT" root:root 751
expect_dir "$DISPATCHER_STATE" "$MERGEN_DISPATCHER_USER:$MERGEN_DISPATCHER_USER" 700
expect_dir "$EXECUTOR_STATE" "$MERGEN_EXECUTOR_USER:$MERGEN_EXECUTOR_USER" 700
expect_dir "$RUNTIME_ROOT" "$MERGEN_DISPATCHER_USER:$MERGEN_SERVICE_GROUP" "$MERGEN_RUNTIME_MODE" exact
# The dispatcher creates these on its first start with the spool contract's modes.
# The maintenance account is not in the spool group and cannot enter it.
if [[ -d "$RUNTIME_ROOT" && ! -x "$RUNTIME_ROOT" ]]; then
    info 'This account cannot enter the runtime directory; root checks jobs/, staging/ and trash/.'
else
    for sub in jobs:2750 staging:2700 trash:2700; do
        [[ -e "$RUNTIME_ROOT/${sub%%:*}" ]] &&
            expect_dir "$RUNTIME_ROOT/${sub%%:*}" "$MERGEN_DISPATCHER_USER:$MERGEN_SERVICE_GROUP" "${sub##*:}" exact
    done
fi

# -- env files ----------------------------------------------------------------
section 'Configuration files'
for service in "${SERVICES[@]}"; do
    path="$(env_file "$service")"
    group="$(service_user "$service")"
    if [[ ! -e "$path" && ! -L "$path" ]]; then
        warn "$path is missing; stage-services.sh seeds it from the example"
        continue
    fi
    if [[ -L "$path" || ! -f "$path" ]]; then
        fail "$path is not a regular file"
        continue
    fi
    read -r -a found <<< "$(meta "$path")"
    if [[ "${found[1]}:${found[2]}" != "root:$group" ]] || mode_too_wide "${found[0]}" 640; then
        fail "$path is ${found[1]}:${found[2]} ${found[0]}; the contract is root:$group 640"
    else
        pass "$path (root:$group, ${found[0]})"
    fi
done
executor_env="$(env_file executor)" dispatcher_env="$(env_file dispatcher)"
if [[ -f "$executor_env" ]]; then
    # By prefix, not by a list of today's names: a new or misspelt control
    # setting must not reach the executor either. Names only, never a value.
    # The maintenance account cannot read the file (root:mergen-executor 640,
    # on purpose), so a plan it runs leaves this check to root. Root must read
    # it: an unreadable file never counts as clean.
    if keys="$(env_keys "$executor_env" 2>/dev/null)"; then
        leaked="$(printf '%s\n' "$keys" | control_keys)"
        [[ -z "$leaked" ]] && pass 'executor.env sets no MERGEN_CONTROL_*, MERGEN_WORKER_* or MERGEN_VPS_* key' \
            || fail "executor.env must not set: ${leaked% }"
    elif [[ "$as_root" -eq 1 ]]; then
        fail 'executor.env cannot be read even as root; its keys cannot be checked'
    else
        warn 'executor.env is not readable by this account, as its 640 mode intends; root checks its keys (sudo verify-services.sh --before, and every --apply)'
    fi
fi
if [[ -f "$dispatcher_env" && "$as_root" -eq 1 ]] && have runuser && user_exists "$MERGEN_EXECUTOR_USER"; then
    if runuser -u "$MERGEN_EXECUTOR_USER" -- test -r "$dispatcher_env"; then
        fail "$MERGEN_EXECUTOR_USER can read dispatcher.env (mode, group or ACL)"
    else
        pass "$MERGEN_EXECUTOR_USER cannot read dispatcher.env"
    fi
elif [[ -f "$dispatcher_env" ]]; then
    info 'The read test as mergen-executor needs root; only owner, group and mode were checked.'
fi

# -- drop-ins -------------------------------------------------------------------
# A drop-in changes a unit without touching its file: it could hand the executor
# a control setting or turn PrivateNetwork off while the unit itself looks clean.
# None is accepted, including service.d/ ones that systemd applies to every
# service on the host: the release's unit is the whole definition. A drop-in
# the distribution ships is not assumed safe either. Paths only, never content.
section 'Unit drop-ins'
dropins="$(mergen_dropins; global_dropins)"
if [[ -n "$dropins" ]]; then
    while IFS= read -r file; do
        fail "Drop-in found: $file; it could override these units' environment, network or devices. Remove it."
    done <<< "$dropins"
else
    pass 'No drop-in overrides mergen-dispatcher.service or mergen-executor.service'
fi

# -- units ----------------------------------------------------------------------
check_unit() {
    local service="$1" file="$2" label="$3"
    local want_python="$MERGEN_APP_ROOT/current/$service/bin/python"
    [[ -f "$file" ]] || { fail "$label: missing unit file"; return; }
    [[ "$(unit_value "$file" ExecStart)" == "$want_python -P -m mergen_$service" ]] \
        && pass "$label: ExecStart runs the $service venv of current" \
        || fail "$label: ExecStart does not match the release layout"
    [[ "$(unit_values "$file" Environment)" == *"PYTHONPATH=$MERGEN_APP_ROOT/current/src"* ]] \
        && pass "$label: imports from $MERGEN_APP_ROOT/current/src" \
        || fail "$label: PYTHONPATH does not name $MERGEN_APP_ROOT/current/src"
    [[ "$(unit_value "$file" EnvironmentFile)" == "$MERGEN_CONFIG_ROOT/$service.env" ]] \
        || fail "$label: EnvironmentFile is not $MERGEN_CONFIG_ROOT/$service.env"
    [[ "$(unit_value "$file" User)" == "$(service_user "$service")" ]] \
        || fail "$label: User is not $(service_user "$service")"
    if [[ "$service" == executor ]]; then
        local problems=''
        grep -q 'dispatcher.env' -- "$file" && problems=' names-dispatcher.env'
        for directive in PrivateNetwork=true IPAddressDeny=any RestrictAddressFamilies=AF_UNIX; do
            grep -qx -- "$directive" "$file" || problems="$problems missing-$directive"
        done
        # Environment= lines reach the executor as surely as its env file.
        for key in $(unit_env_keys "$file" | control_keys); do
            problems="$problems sets-$key"
        done
        [[ -z "$problems" ]] && pass "$label: no network and no access to the dispatcher's configuration" \
            || fail "$label: isolation problem:$problems"
    else
        grep -qx 'PrivateDevices=true' -- "$file" && ! grep -q '^DeviceAllow=' -- "$file" \
            && pass "$label: PrivateDevices=true, no DeviceAllow: no NVIDIA device" \
            || fail "$label: the dispatcher unit could reach a GPU device"
    fi
}

if [[ "$phase" == before ]]; then
    section 'Unit files to be staged'
    for service in "${SERVICES[@]}"; do
        check_unit "$service" "$here/systemd/$(unit_name "$service").example" "$(unit_name "$service")"
    done
    summary 'Service staging (before)'
    exit
fi

# -- the release ----------------------------------------------------------------
section 'Release'
candidate=1
if [[ -z "$release" ]]; then
    candidate=0
    version="$(current_version)"
    if [[ -z "$version" ]]; then
        fail "$CURRENT does not point at a release"
        summary 'Service staging (after)'
        exit 1
    fi
    release="$RELEASES/$version"
fi
if [[ ! -f "$release/RELEASE" ]]; then
    fail "Not a complete release (no RELEASE file): $release"
    summary 'Service staging (after)'
    exit 1
fi
pass "Release $(release_value "$release" version) at $release"
if [[ "$(tree_manifest "$release")" == "$(cat -- "$release/MANIFEST.sha256")" ]]; then
    pass 'Every source and unit file matches MANIFEST.sha256'
else
    fail 'The release no longer matches its MANIFEST.sha256'
fi
writable="$(find "$release" -perm /022 ! -type l -print -quit)"
[[ -z "$writable" ]] && pass 'Nothing in the release is writable by group or others' \
    || fail 'The release has files writable by group or others'
owners_ok=1
for item in "$release" "$release/src" "$release/units" "$release/dispatcher" "$release/executor" "$release/RELEASE"; do
    read -r -a found <<< "$(meta "$item")"
    [[ "${found[1]:-}:${found[2]:-}" == root:root ]] || owners_ok=0
done
[[ "$owners_ok" -eq 1 ]] && pass 'The release belongs to root:root; no service account can change its code' \
    || fail 'Part of the release is not owned by root:root'
for service in "${SERVICES[@]}"; do
    [[ -d "$MODEL_ROOT" && "$(cd -- "$release/$service" && pwd -P)" == "$(cd -- "$MODEL_ROOT" && pwd -P)"/* ]] \
        && fail "The $service venv lives inside the model tree"
done

gates=()
for service in "${SERVICES[@]}"; do
    section "The $service venv"
    env_path="$(env_file "$service")"
    [[ -r "$env_path" ]] || env_path=''
    if ! report="$(probe "$release" "$service" "$env_path" 2>/dev/null)"; then
        fail "$service: a release module does not import (${report#imports=failed:})"
        continue
    fi
    while IFS='=' read -r key value; do
        case "$key" in
            imports) pass "$service: every module imports from the release's src/" ;;
            gate_version) gates+=("$value") ;;
            adapter)
                if [[ "$value" == none ]]; then
                    pass 'executor: G3 ships no imaging adapter; it runs and advertises no capability'
                    info 'With no capability the dispatcher advertises nothing and claims no job.'
                else
                    warn 'executor: an imaging adapter is registered; G4 isolation must be in place'
                fi
                ;;
            model_packages)
                [[ "$value" == none ]] && pass "$service: no model packages in this venv" \
                    || fail "$service: model packages in a service venv: $value"
                ;;
            http_client)
                if [[ "$service" == executor ]]; then
                    [[ "$value" == absent ]] && pass 'executor: no HTTP client installed' \
                        || fail "executor: an HTTP client is installed (${value#present:})"
                else
                    [[ "$value" == *httpx* ]] && pass 'dispatcher: httpx is installed' \
                        || fail 'dispatcher: httpx is missing'
                fi
                ;;
            config)
                case "$value" in
                    ok) pass "$service: $(env_file "$service") is accepted" ;;
                    skipped) warn "$service: no readable env file to validate" ;;
                    *)
                        # Names only; the probe never prints a value.
                        message="$service: $(env_file "$service") is not accepted: ${value#invalid:}"
                        [[ "$candidate" -eq 1 ]] && warn "$message" || fail "$message"
                        ;;
                esac
                ;;
        esac
    done <<< "$report"
done

section 'Spool gate'
if [[ "${#gates[@]}" -eq 2 && "${gates[0]}" == "${gates[1]}" ]]; then
    pass "Dispatcher and executor load spool gate version ${gates[0]} from the same src/"
    stale=0
    if [[ -d "$RUNTIME_ROOT/jobs" && -r "$RUNTIME_ROOT/jobs" ]]; then
        while IFS= read -r -d '' job; do
            [[ "$(head -c 64 -- "$job/gate" 2>/dev/null)" == "mergen-spool-gate ${gates[0]}" ]] || stale=$((stale + 1))
        done < <(find "$RUNTIME_ROOT/jobs" -mindepth 1 -maxdepth 1 -type d -print0)
    fi
    [[ "$stale" -eq 0 ]] || warn "$stale job(s) in the spool carry no version-${gates[0]} gate; the executor fails them"
else
    fail 'Dispatcher and executor disagree on the spool gate version'
fi

if [[ "$candidate" -eq 0 ]]; then
    section 'Installed units'
    for service in "${SERVICES[@]}"; do
        installed="$UNIT_DIR/$(unit_name "$service")"
        check_unit "$service" "$installed" "$installed"
        cmp -s -- "$installed" "$release/units/$(unit_name "$service")" \
            && pass "$(unit_name "$service") matches the release's copy" \
            || fail "$(unit_name "$service") differs from the release's copy"
    done
    if have systemd-analyze; then
        if systemd-analyze verify "$UNIT_DIR/mergen-dispatcher.service" "$UNIT_DIR/mergen-executor.service" >/dev/null 2>&1; then
            pass 'systemd-analyze verify accepts both units'
        else
            fail 'systemd-analyze verify rejects a unit; run it by hand for the details'
        fi
    else
        info 'systemd-analyze is not available; unit verification skipped'
    fi
    for service in "${SERVICES[@]}"; do
        service_active "$(unit_name "$service")" && info "$(unit_name "$service") is running" \
            || info "$(unit_name "$service") is not running (nothing here starts it)"
    done
fi
summary 'Service staging (after)'
