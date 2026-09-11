#!/usr/bin/env bash
# goruntuIslemeModeli — venv kurulumu ve doğrulama
# Kullanım: bash kurulum.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo ">> .venv oluşturuluyor ($(python3 -V))"
  python3 -m venv .venv
fi

echo ">> pip güncelleniyor"
.venv/bin/python -m pip install --upgrade pip wheel

echo ">> bağımlılıklar kuruluyor (torch ~2-3 GB, sabır)"
.venv/bin/python -m pip install -r requirements.txt

echo ">> doğrulama"
.venv/bin/python - <<'PY'
import importlib, sys
mods = ["torch","monai","nnunetv2","nibabel","numpy","scipy","pandas",
        "skimage","sklearn","matplotlib","einops","tensorboardX"]
eksik = []
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"  ok  {m:<14} {getattr(mod,'__version__','?')}")
    except Exception as e:
        eksik.append(m); print(f"  HATA {m:<14} {e}")
import torch
print("  CUDA:", torch.cuda.is_available(),
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
sys.exit(1 if eksik else 0)
PY

echo ">> modüller derleniyor (syntax kontrolü)"
.venv/bin/python -m compileall -q compute_stats.py ensemble_inference.py \
  evaluate_uwcse.py nnunet_predictor.py ../../backend/legacy/serve_dashboard.py uwcse_ensemble.py \
  SwinUNETR_BRATS21 brats_mri_segmentation/scripts

echo ">> tamam. Kullanım: source .venv/bin/activate"
