#!/usr/bin/env bash
# Run on the VPS from a reviewed checkout. Installs code; does not enable/restart services.
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo 'Run with sudo on the VPS.' >&2; exit 1; }
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
id mergen >/dev/null 2>&1 || useradd --system --home-dir /srv/mergen --shell /usr/sbin/nologin mergen
install -d -m 755 /srv/mergen/services/backend /srv/mergen/services/mcp
install -d -m 750 -o root -g mergen /etc/mergen
install -m 644 "$repo_dir/backend/api.py" "$repo_dir/backend/requirements.txt" /srv/mergen/services/backend/
install -m 644 "$repo_dir/mcp/server.py" "$repo_dir/mcp/demo_store.py" /srv/mergen/services/mcp/
python3 -m venv /srv/mergen/services/.venv
/srv/mergen/services/.venv/bin/python -m pip install -r /srv/mergen/services/backend/requirements.txt
install -m 644 "$repo_dir/infra/vps/mergen-api.service" "$repo_dir/infra/vps/mergen-mcp.service" /etc/systemd/system/
if [[ ! -e /etc/mergen/services.env ]]; then
    install -m 640 -o root -g mergen "$repo_dir/infra/vps/services.env.example" /etc/mergen/services.env
fi
systemctl daemon-reload
echo 'Installed. Set MERGEN_DEMO_ROOT in /etc/mergen/services.env, then enable/start the services.'
