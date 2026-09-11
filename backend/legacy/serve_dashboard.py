"""
Dashboard Server
─────────────────
Serves the visualization dashboard and provides API endpoints
for slice images, 3D meshes, and metrics.

Usage:  python serve_dashboard.py
Then open http://localhost:8000
"""

import http.server
import json
import os
import io
import struct
import numpy as np
from urllib.parse import urlparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.join(REPO_ROOT, "frontend", "legacy")
RESULTS_DIR = os.path.join(REPO_ROOT, "models", "imaging", "results")
PORT = 8000

# ── In-memory cache ──────────────────────────────────────────────────
_cache = {}


def _load(case_name):
    if case_name in _cache:
        return _cache[case_name]
    cd = os.path.join(RESULTS_DIR, case_name)
    d = {}
    fp = os.path.join(cd, "flair.npz")
    if os.path.exists(fp):
        d["flair"] = np.load(fp)["data"]
    sp = os.path.join(cd, "seg_volumes.npz")
    if os.path.exists(sp):
        s = np.load(sp)
        d["seg_nnunet"] = s["nnunet"]
        d["seg_swin"] = s["swin"]
        d["seg_ensemble"] = s["ensemble"]
        d["seg_gt"] = s["gt"]
    _cache[case_name] = d
    return d


# ── Slice renderer ───────────────────────────────────────────────────
COLORS = {0: [0,0,0,0], 1: [46,213,115,160], 2: [30,144,255,160], 4: [255,71,87,160]}

def render_slice(case_name, axis, idx, model):
    """Return a PNG showing the FLAIR slice with segmentation overlay."""
    data = _load(case_name)
    if "flair" not in data:
        return None
    flair = data["flair"]

    # Clamp index
    max_idx = flair.shape[{"axial":2,"coronal":1,"sagittal":0}[axis]] - 1
    idx = max(0, min(idx, max_idx))

    if axis == "axial":
        bg = flair[:, :, idx]
    elif axis == "coronal":
        bg = flair[:, idx, :]
    else:
        bg = flair[idx, :, :]

    seg_key = f"seg_{model}"
    seg_vol = data.get(seg_key)
    if seg_vol is not None:
        if axis == "axial":
            seg_sl = seg_vol[:, :, idx]
        elif axis == "coronal":
            seg_sl = seg_vol[:, idx, :]
        else:
            seg_sl = seg_vol[idx, :, :]
    else:
        seg_sl = None

    fig, ax = plt.subplots(1, 1, figsize=(4, 4), dpi=100)
    ax.imshow(bg.T, cmap="gray", origin="lower", aspect="equal")
    if seg_sl is not None:
        overlay = np.zeros((*seg_sl.T.shape, 4), dtype=np.uint8)
        for lv, c in COLORS.items():
            if lv == 0:
                continue
            overlay[seg_sl.T == lv] = c
        ax.imshow(overlay, origin="lower", aspect="equal")
    ax.axis("off")
    fig.tight_layout(pad=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0,
                facecolor="black")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── HTTP Handler ─────────────────────────────────────────────────────
class H(http.server.BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # silence logs

    def handle_one_request(self):
        # Tarayıcı hızlıca dilim değiştirince yarım kalan istekleri iptal eder;
        # bu normaldir, traceback basmaya gerek yok.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _png(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path, ct):
        if not os.path.exists(path):
            self.send_error(404); return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path

        # ── Dashboard ────────────────────────────────────────────
        if p in ("/", "/dashboard.html"):
            self._file(os.path.join(BASE_DIR, "dashboard.html"), "text/html")

        # ── API: case list ───────────────────────────────────────
        elif p == "/api/cases":
            cases = []
            if os.path.isdir(RESULTS_DIR):
                for d in sorted(os.listdir(RESULTS_DIR)):
                    dd = os.path.join(RESULTS_DIR, d)
                    if os.path.isdir(dd):
                        data = _load(d)
                        shape = list(data["flair"].shape) if "flair" in data else [0,0,0]
                        cases.append({"name": d, "shape": shape})
            self._json(cases)

        # ── API: metrics ─────────────────────────────────────────
        elif p == "/api/metrics":
            mp = os.path.join(RESULTS_DIR, "metrics.json")
            if os.path.exists(mp):
                with open(mp) as f:
                    self._json(json.load(f))
            else:
                self._json({})

        # ── API: mesh ────────────────────────────────────────────
        elif p.startswith("/api/mesh/"):
            parts = p.split("/")
            if len(parts) >= 5:
                fp = os.path.join(RESULTS_DIR, parts[3], f"mesh_{parts[4]}.json")
                self._file(fp, "application/json")
            else:
                self.send_error(400)

        # ── API: slice ───────────────────────────────────────────
        elif p.startswith("/api/slice/"):
            # /api/slice/<case>/<axis>/<index>/<model>
            parts = p.split("/")
            if len(parts) >= 7:
                png = render_slice(parts[3], parts[4], int(parts[5]), parts[6])
                if png:
                    self._png(png)
                else:
                    self.send_error(404)
            else:
                self.send_error(400)

        # ── API: volume dimensions ───────────────────────────────
        elif p.startswith("/api/dims/"):
            cn = p.split("/")[3]
            data = _load(cn)
            if "flair" in data:
                self._json({"shape": list(data["flair"].shape)})
            else:
                self.send_error(404)

        else:
            self.send_error(404)


def main():
    print(f"Starting dashboard server at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.\n")
    # ThreadingHTTPServer: dashboard aynı anda çok sayıda dilim/mesh isteği
    # atıyor; tek thread'de keep-alive bağlantıları birbirini bekletiyordu.
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
