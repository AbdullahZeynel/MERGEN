#!/usr/bin/env bash
# Stage the G2 dispatcher and the G3 executor as one versioned release.
#
#   bash infra/gpu-host/stage-services.sh --version V            # plan only
#   sudo bash infra/gpu-host/stage-services.sh --version V --apply
#
# --apply builds /opt/mergen/releases/V (sources, one venv per service, unit
# copies, manifest), verifies it, seeds a missing env file from its example,
# installs a missing unit file, and only then points /opt/mergen/current at V
# with a temporary link and one atomic rename. A failure before that rename
# leaves `current` exactly as it was. Running it again with the same V is a
# no-op. Existing releases, env files and unit files are never overwritten.
#
# Never: enables, starts, restarts or reloads a service; installs an NVIDIA
# driver, CUDA, Tailscale or a model package; deletes a release; prints a
# configuration value. Exit 0 staged and verified, 1 refused or failed, 2
# usage, 3 staged but verify-services.sh still reports something to fix.
# shellcheck source=lib/common.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
# shellcheck source=lib/services.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/services.sh"

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
usage='Usage: stage-services.sh --version V [--apply] [--python PATH] [--source DIR] [--root DIR]'
apply=0 version='' prefix='' python_bin='python3' source_root="$(cd -- "$here/../.." && pwd)"
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --apply) apply=1; shift ;;
        --version|--python|--source|--root)
            [[ "$#" -ge 2 ]] || { echo "$usage" >&2; exit 2; }
            case "$1" in
                --version) version="$2" ;;
                --python) python_bin="$2" ;;
                --source) source_root="$2" ;;
                --root) prefix="${2%/}" ;;
            esac
            shift 2
            ;;
        -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo "$usage" >&2; exit 2 ;;
    esac
done
if ! valid_version "$version"; then
    echo 'Give --version: 1-64 letters, digits, dot, dash or underscore, e.g. the commit id.' >&2
    echo "$usage" >&2
    exit 2
fi
if [[ "$apply" -eq 1 && "$(id -u)" != 0 ]]; then
    echo 'Run --apply as root (sudo). Plan mode needs no privileges.' >&2
    exit 1
fi
services_paths "$prefix"
target="$RELEASES/$version"

planned=0
step() { planned=$((planned + 1)); printf 'PLAN  %s\n' "$*"; }
skip() { printf 'SKIP  %s\n' "$*"; }
refuse() { fail "$*"; summary 'Service staging' || true; exit 1; }

requirement_names() {
    sed -e 's/#.*//' -- "$1" | awk 'NF {print $1}' | sed -E 's/[<>=!~;[ ].*//' | tr 'A-Z_.' 'a-z--'
}

# -- preconditions: everything is checked before anything changes --------------
section 'Preconditions'
for tool in sha256sum find stat getent cmp mktemp; do
    have "$tool" || refuse "Required tool missing: $tool"
done
for path in "$APP_ROOT" "$CONFIG_ROOT" "$UNIT_DIR"; do
    safe_system_path "$path" || refuse "Unsafe target path: $path"
done
while read -r from _; do
    [[ -f "$source_root/$from" && ! -L "$source_root/$from" ]] || refuse "Missing or linked source file: $from"
done < <(release_files "$source_root")
pass 'Every release file is present in the source tree'
if python_version="$("$python_bin" -c 'import sys, venv, ensurepip
print("%d.%d" % sys.version_info[:2])
raise SystemExit(sys.version_info < (3, 12))' 2>/dev/null)"; then
    pass "Python $python_version with venv and ensurepip"
else
    refuse 'Python 3.12+ with the venv and ensurepip modules is required (Debian: python3-venv); see --python'
fi

section 'Dependencies'
dispatcher_needs="$(requirement_names "$source_root/mergen_dispatcher/requirements.txt" | tr '\n' ' ')"
executor_needs="$(requirement_names "$source_root/mergen_executor/requirements.txt" | tr '\n' ' ')"
for name in $MODEL_DISTRIBUTIONS; do
    [[ " $dispatcher_needs $executor_needs " == *" $name "* ]] && refuse "A service requirements file names a model package: $name"
done
pass 'Neither service requirements file names a model package'
for name in $HTTP_DISTRIBUTIONS; do
    [[ " $executor_needs " == *" $name "* ]] && refuse "The executor requirements name an HTTP client: $name"
done
[[ " $dispatcher_needs " == *" httpx "* ]] || refuse 'The dispatcher requirements do not name httpx'
pass 'The executor gets no HTTP client; the dispatcher gets httpx'
info "dispatcher venv: mergen_dispatcher/requirements.txt ($dispatcher_needs)"
info "executor venv:   mergen_executor/requirements.txt ($executor_needs)"

section 'Running services'
for service in "${SERVICES[@]}"; do
    if service_active "$(unit_name "$service")"; then
        refuse "$(unit_name "$service") is running; stop it first (this script never stops or starts services)"
    fi
done
pass 'Neither service is running, so no process can mix two releases'

section 'Host contract'
if ! bash "$here/verify-services.sh" --before ${prefix:+--root "$prefix"}; then
    refuse 'verify-services.sh --before failed; fix the host first (install-base.sh, runbook steps 6-9)'
fi

section 'Release'
manifest="$(source_manifest "$source_root")"
build=1
if [[ -e "$target" || -L "$target" ]]; then
    if [[ ! -L "$target" && -f "$target/RELEASE" && "$(cat -- "$target/MANIFEST.sha256")" == "$manifest" ]]; then
        skip "Release $version is already staged with the same content"
        build=0
    else
        refuse "Release $version already exists with other or incomplete content; choose another --version"
    fi
fi
previous="$(current_version)"
if [[ -z "$previous" ]] && { [[ -e "$CURRENT" ]] || [[ -L "$CURRENT" ]]; }; then
    refuse "$CURRENT exists but is not a link to a release; it is left for a human to inspect"
fi
new_gate="$(sed -n 's/^GATE_VERSION = \([0-9]*\)$/\1/p' -- "$source_root/mergen_spool/contract.py")"
[[ -n "$new_gate" ]] || refuse 'mergen_spool/contract.py declares no GATE_VERSION'
if [[ -n "$previous" ]]; then
    old_gate="$(release_value "$RELEASES/$previous" gate_version)"
    if [[ "${old_gate:-none}" != "$new_gate" ]]; then
        warn "Spool gate version changes ${old_gate:-none} -> $new_gate: restart both services together"
        info 'Jobs published by the old dispatcher are failed by the new executor.'
    else
        pass "Spool gate version stays $new_gate"
    fi
fi

section 'Unit files'
install_units=()
for service in "${SERVICES[@]}"; do
    unit="$UNIT_DIR/$(unit_name "$service")"
    if [[ -L "$unit" || ( -e "$unit" && ! -f "$unit" ) ]]; then
        refuse "$unit is not a regular file"
    elif [[ -f "$unit" ]]; then
        cmp -s -- "$unit" "$source_root/infra/gpu-host/systemd/$(unit_name "$service").example" \
            || refuse "$unit differs from this release's unit; review it and move it aside by hand"
        skip "$unit is already installed and identical"
    else
        install_units+=("$service")
    fi
done

section 'Configuration files'
seed_envs=()
for service in "${SERVICES[@]}"; do
    path="$(env_file "$service")"
    if [[ -L "$path" || ( -e "$path" && ! -f "$path" ) ]]; then
        refuse "$path is not a regular file"
    elif [[ -f "$path" ]]; then
        skip "$path exists and is left untouched"
    else
        seed_envs+=("$service")
    fi
done

# -- plan ----------------------------------------------------------------------
section 'Actions'
[[ "$build" -eq 1 ]] && step "Build $target: src/, units/, a venv per service, MANIFEST.sha256, RELEASE"
[[ "$build" -eq 1 ]] && step 'Verify the new release (imports, dependencies, gate, units) before it is used'
for service in "${seed_envs[@]}"; do step "Seed $(env_file "$service") from the example (root:$(service_user "$service") 640)"; done
for service in "${install_units[@]}"; do step "Install $UNIT_DIR/$(unit_name "$service") (root:root 644; not enabled, not started)"; done
if [[ "$previous" == "$version" ]]; then
    skip "$CURRENT already points at $version"
else
    step "Point $CURRENT at releases/$version (was: ${previous:-none}) with one atomic rename"
fi
[[ "$planned" -eq 0 ]] && info 'Nothing to change: this release is already staged and current.'
if [[ "$apply" -eq 0 ]]; then
    printf '\nPlan only: %d action(s) would run. Nothing was changed.\n' "$planned"
    summary 'Service staging (plan)'
    exit
fi

# -- apply ---------------------------------------------------------------------
staging='' scratch=''
cleanup() {
    local status=$?
    [[ -n "$scratch" && -d "$scratch" ]] && rm -rf -- "$scratch"
    if [[ -n "$staging" && -d "$staging" ]]; then
        rm -rf -- "$staging"
        printf 'FAILED: the half-built release was removed; %s is unchanged.\n' "$CURRENT" >&2
    fi
    exit "$status"
}
trap cleanup EXIT
umask 022

if [[ "$build" -eq 1 ]]; then
    section 'Build'
    mkdir -p -- "$RELEASES"
    # Built in place, because a venv is not relocatable. mkdir claims the name;
    # RELEASE is written last, a failure removes what this run created, and
    # `current` names the release only after it has verified.
    mkdir -m 755 -- "$target"
    staging="$target"
    while read -r from to; do
        mkdir -p -- "$(dirname -- "$staging/$to")"
        cp -- "$source_root/$from" "$staging/$to"
        chmod 644 -- "$staging/$to"
    done < <(release_files "$source_root")
    printf '%s\n' "$manifest" > "$staging/MANIFEST.sha256"
    [[ "$(tree_manifest "$staging")" == "$manifest" ]] || { fail 'The copied sources do not match the manifest'; exit 1; }
    pass 'Sources and units copied; the copy matches the manifest'
    for service in "${SERVICES[@]}"; do
        "$python_bin" -m venv -- "$staging/$service" || { fail "Creating the $service venv failed"; exit 1; }
        if ! "$staging/$service/bin/python" -m pip install --no-input --disable-pip-version-check \
            --no-cache-dir --only-binary=:all: -r "$staging/src/mergen_$service/requirements.txt"; then
            fail "Installing mergen_$service/requirements.txt into the $service venv failed"
            exit 1
        fi
        "$staging/$service/bin/python" -m pip freeze --disable-pip-version-check > "$staging/$service.freeze"
        pass "$service venv: $(wc -l < "$staging/$service.freeze") distribution(s), see $service.freeze"
    done
    printf 'version=%s\ngate_version=%s\npython=%s\n' "$version" "$new_gate" "$python_version" > "$staging/RELEASE"
    chmod -R go-w -- "$staging"
    chown -R root:root -- "$staging"
fi

# Also for a release staged earlier: nothing becomes current unverified.
section 'Verify the release before it is used'
if ! bash "$here/verify-services.sh" --after ${prefix:+--root "$prefix"} --release-dir "$target"; then
    fail "Release $version did not verify; $CURRENT is not changed"
    exit 1
fi
if have systemd-analyze; then
    scratch="$(mktemp -d)"
    for service in "${SERVICES[@]}"; do
        sed "s#$MERGEN_APP_ROOT/current/#$target/#g" -- "$target/units/$(unit_name "$service")" \
            > "$scratch/$(unit_name "$service")"
    done
    systemd-analyze verify "$scratch"/*.service || { fail 'systemd-analyze verify rejects a unit'; exit 1; }
    rm -rf -- "$scratch"
    scratch=''
    pass 'systemd-analyze verify accepts both units against this release'
else
    warn 'systemd-analyze is not available; units were checked statically only'
fi
staging=''
pass "Release $version is complete and verified at $target"

for service in "${seed_envs[@]}"; do
    path="$(env_file "$service")"
    [[ -e "$path" || -L "$path" ]] && { fail "$path appeared meanwhile; left untouched"; exit 1; }
    cp -- "$source_root/infra/gpu-host/$service.env.example" "$path.staging"
    chmod 640 -- "$path.staging"
    chown "root:$(service_user "$service")" -- "$path.staging"
    mv -T -- "$path.staging" "$path"
    pass "Seeded $path; fill its blank values on the host"
done
for service in "${install_units[@]}"; do
    unit="$UNIT_DIR/$(unit_name "$service")"
    mkdir -p -- "$UNIT_DIR"
    cp -- "$target/units/$(unit_name "$service")" "$unit.staging"
    chmod 644 -- "$unit.staging"
    chown root:root -- "$unit.staging"
    mv -T -- "$unit.staging" "$unit"
    pass "Installed $unit (not enabled, not started)"
done
if [[ "$previous" != "$version" ]]; then
    link="$APP_ROOT/.current.$$"
    ln -s -- "releases/$version" "$link"
    mv -T -- "$link" "$CURRENT"
    pass "$CURRENT -> releases/$version (previous: ${previous:-none})"
    [[ -n "$previous" ]] && info "Roll back by pointing $CURRENT at releases/$previous (runbook step 16)."
fi
trap - EXIT

section 'After'
if bash "$here/verify-services.sh" --after ${prefix:+--root "$prefix"}; then
    printf '\nStaged and verified. Nothing was enabled or started.\n'
    exit 0
fi
printf '\nStaged, but verify-services.sh reports the problems above. Nothing was enabled or started.\n'
exit 3
