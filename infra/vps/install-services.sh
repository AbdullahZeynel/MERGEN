#!/usr/bin/env bash
# Run on the VPS from a reviewed checkout. Installs code; does not enable/restart services.
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo 'Run with sudo on the VPS.' >&2; exit 1; }
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin=""
if [[ -n "${PYTHON_BIN:-}" ]]; then
    candidates=("$PYTHON_BIN")
else
    candidates=(python3.14 python3.13 python3.12 python3.11 python3)
fi
for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
        python_bin="$(command -v "$candidate")"
        break
    fi
done
if [[ -z "$python_bin" ]]; then
    echo 'Python 3.11+ is required. Set PYTHON_BIN to its absolute executable path.' >&2
    exit 1
fi
echo "Using $python_bin ($("$python_bin" --version 2>&1))"
id mergen >/dev/null 2>&1 || useradd --system --home-dir /srv/mergen --shell /usr/sbin/nologin mergen
install -d -m 755 /srv/mergen/services/backend /srv/mergen/services/mcp
install -d -m 750 -o root -g mergen /etc/mergen
install -m 644 "$repo_dir/backend/api.py" "$repo_dir/backend/requirements.txt" /srv/mergen/services/backend/
install -m 644 "$repo_dir/mcp/server.py" "$repo_dir/mcp/demo_store.py" /srv/mergen/services/mcp/
"$python_bin" -m venv /srv/mergen/services/.venv
/srv/mergen/services/.venv/bin/python -m pip install -r /srv/mergen/services/backend/requirements.txt
install -m 644 "$repo_dir/infra/vps/mergen-api.service" "$repo_dir/infra/vps/mergen-mcp.service" /etc/systemd/system/
if [[ ! -e /etc/mergen/services.env ]]; then
    install -m 640 -o root -g mergen "$repo_dir/infra/vps/services.env.example" /etc/mergen/services.env
fi
systemctl daemon-reload
echo 'Installed. Set MERGEN_DEMO_ROOT in /etc/mergen/services.env, then enable/start the services.'
