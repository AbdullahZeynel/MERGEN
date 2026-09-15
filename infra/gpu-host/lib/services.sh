# Shared by stage-services.sh and verify-services.sh. Source after common.sh.
#
# Release layout under /opt/mergen (root:root, nothing writable by a service):
#
#   releases/<version>/src/          backend/archive_io.py, backend/live_contracts.py,
#                                    mergen_spool/, mergen_dispatcher/, mergen_executor/
#   releases/<version>/units/        the two unit files this release was staged with
#   releases/<version>/dispatcher/   venv: mergen_dispatcher/requirements.txt only
#   releases/<version>/executor/     venv: mergen_executor/requirements.txt only
#   releases/<version>/*.freeze      what pip actually installed in each venv
#   releases/<version>/MANIFEST.sha256
#   releases/<version>/RELEASE       written last; a release without it is not one
#   current -> releases/<version>    switched with a temporary link and one rename
#
# The imaging model environment (MERGEN_IMAGING_VENV, G4) lives outside this
# tree and is never created, read or changed here.

MERGEN_LIB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICES=(dispatcher executor)
SOURCE_FILES=(backend/archive_io.py backend/live_contracts.py)
SOURCE_PACKAGES=(mergen_spool mergen_dispatcher mergen_executor)
# Names that must never appear in either service venv: the model stack is G4's
# own environment, and the executor has no network client at all.
MODEL_DISTRIBUTIONS='torch torchvision torchaudio monai nnunet nnunetv2 tensorflow jax jaxlib onnxruntime onnxruntime-gpu cupy triton'
HTTP_DISTRIBUTIONS='httpx httpcore h11 anyio requests urllib3 aiohttp'
VERSION_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'

# All system paths, optionally below an alternate root (--root, for tests and
# image builds). Units and env files always name the real paths.
services_paths() {
    local prefix="${1:-}"
    APP_ROOT="$prefix$MERGEN_APP_ROOT"
    RELEASES="$APP_ROOT/releases"
    CURRENT="$APP_ROOT/current"
    CONFIG_ROOT="$prefix$MERGEN_CONFIG_ROOT"
    UNIT_DIR="$prefix/etc/systemd/system"
    STATE_ROOT="$prefix$MERGEN_STATE_ROOT"
    RUNTIME_ROOT="$prefix$MERGEN_RUNTIME_ROOT"
    DISPATCHER_STATE="$prefix$MERGEN_DISPATCHER_STATE"
    EXECUTOR_STATE="$prefix$MERGEN_EXECUTOR_STATE"
    MODEL_ROOT="$prefix$MERGEN_MODEL_ROOT"
    SYSTEM_PREFIX="$prefix"
}

# The system manager's unit search path (systemd.unit(5)), plus /lib for a
# split-/usr host. A drop-in in any of them changes a unit without touching
# its file.
SYSTEMD_UNIT_PATHS=(/etc/systemd/system.control /run/systemd/system.control /run/systemd/transient
    /run/systemd/generator.early /etc/systemd/system /etc/systemd/system.attached /run/systemd/system
    /run/systemd/system.attached /run/systemd/generator /usr/local/lib/systemd/system
    /usr/lib/systemd/system /lib/systemd/system /run/systemd/generator.late)

# Every *.conf drop-in systemd would merge into a MERGEN unit: the unit's own
# .d directory and the shared mergen- prefix directory, in each search path.
mergen_dropins() {
    local path dir file
    for path in "${SYSTEMD_UNIT_PATHS[@]}"; do
        for dir in mergen-dispatcher.service.d mergen-executor.service.d mergen-.service.d; do
            for file in "$SYSTEM_PREFIX$path/$dir"/*.conf; do
                if [[ -e "$file" || -L "$file" ]]; then printf '%s\n' "$file"; fi
            done
        done
    done
}

# Drop-ins for every service on the host, which reach these units too.
global_dropins() {
    local path file
    for path in "${SYSTEMD_UNIT_PATHS[@]}"; do
        for file in "$SYSTEM_PREFIX$path/service.d"/*.conf; do
            if [[ -e "$file" || -L "$file" ]]; then printf '%s\n' "$file"; fi
        done
    done
}

valid_version() { [[ "$1" =~ $VERSION_PATTERN ]]; }

service_user() { [[ "$1" == dispatcher ]] && printf '%s' "$MERGEN_DISPATCHER_USER" || printf '%s' "$MERGEN_EXECUTOR_USER"; }
unit_name() { printf 'mergen-%s.service' "$1"; }
env_file() { printf '%s/%s.env' "$CONFIG_ROOT" "$1"; }

# "<source path> <path inside the release>" for every file a release carries.
# Packages are flat: their non-test modules and requirements.txt.
release_files() {
    local source="$1" file package service
    for file in "${SOURCE_FILES[@]}"; do
        printf '%s src/%s\n' "$file" "$file"
    done
    for package in "${SOURCE_PACKAGES[@]}"; do
        while IFS= read -r file; do
            printf '%s src/%s\n' "$file" "$file"
        done < <(cd -- "$source" && find "$package" -maxdepth 1 -type f \
            \( -name '*.py' ! -name 'test_*.py' -o -name requirements.txt \) | LC_ALL=C sort)
    done
    for service in "${SERVICES[@]}"; do
        printf 'infra/gpu-host/systemd/%s.example units/%s\n' "$(unit_name "$service")" "$(unit_name "$service")"
    done
}

# The manifest a release built from $source would carry, without writing anything.
source_manifest() {
    local source="$1" from to digest
    while read -r from to; do
        digest="$(sha256sum -- "$source/$from" | awk '{print $1}')"
        printf '%s  %s\n' "$digest" "$to"
    done < <(release_files "$source") | LC_ALL=C sort -k2
}

# The same manifest recomputed from a staged or installed release.
tree_manifest() {
    local release="$1"
    (cd -- "$release" && find src units -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) |
        LC_ALL=C sort -k2
}

# "MODE OWNER GROUP" of a path, or nothing when it does not exist.
meta() { stat -c '%a %U %G' -- "$1" 2>/dev/null || true; }

# Keys assigned in an env file. Values are never read into the shell.
env_keys() {
    sed -n 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)[[:space:]]*=.*/\2/p' -- "$1"
}

# Keys that would tell the executor about the control plane: the VPS address,
# the worker identity or any token. Matched by prefix and without regard to
# case, so a new or misspelt setting is caught too. Names in, names out.
CONTROL_KEY_PATTERN='^MERGEN_(CONTROL|WORKER|VPS)_'
control_keys() { { grep -iE "$CONTROL_KEY_PATTERN" || true; } | LC_ALL=C sort -u | tr '\n' ' '; }

# Keys a unit's Environment= lines assign, e.g. `Environment=A=1 "B=two words"`.
unit_env_keys() {
    unit_values "$1" Environment | { grep -oE '(^|[[:space:]"])[A-Za-z_][A-Za-z0-9_]*=' || true; } | tr -d ' "='
}

# First value of a unit directive (KEY=value), comments ignored.
unit_value() { sed -n "s/^$2=//p" -- "$1" | head -n 1; }
unit_values() { sed -n "s/^$2=//p" -- "$1"; }

# Members of a group, primary members included; looked up once per run.
declare -A GROUP_MEMBERS=()
group_members() {
    local line gid
    line="$(getent group -- "$1" || true)"
    gid="$(printf '%s' "$line" | awk -F: '{print $3}')"
    printf '%s ' "$(printf '%s' "$line" | awk -F: '{print $4}' | tr ',' ' ')"
    [[ -z "$gid" ]] || getent passwd | awk -F: -v gid="$gid" '$4 == gid {printf "%s ", $1}'
}
in_group() {
    [[ -n "${GROUP_MEMBERS[$2]+set}" ]] || GROUP_MEMBERS[$2]="$(group_members "$2")"
    [[ " ${GROUP_MEMBERS[$2]} " == *" $1 "* ]]
}

service_active() {
    have systemctl || return 1
    systemctl is-active --quiet "$1" 2>/dev/null
}

# The release that `current` points at, as a version name, or nothing.
current_version() {
    local target
    [[ -L "$CURRENT" ]] || return 0
    target="$(readlink -- "$CURRENT")"
    if [[ "$target" == releases/* ]] && valid_version "${target#releases/}"; then
        printf '%s' "${target#releases/}"
    fi
}

release_value() {
    if [[ -f "$1/RELEASE" ]]; then
        sed -n "s/^$2=//p" -- "$1/RELEASE" | head -n 1
    fi
}

# Run lib/service_probe.py inside a service venv with nothing inherited but
# PATH: `-P` and PYTHONPATH make the release's src/ the only code it imports.
# Prints key=value lines; never a configuration value.
probe() {
    local release="$1" service="$2" env_path="${3:-}"
    local -a args=("--service" "$service")
    [[ -n "$env_path" ]] && args+=("--env-file" "$env_path")
    env -i PATH=/usr/bin:/bin PYTHONPATH="$release/src" PYTHONDONTWRITEBYTECODE=1 \
        "$release/$service/bin/python" -P "$MERGEN_LIB_DIR/service_probe.py" "${args[@]}"
}
