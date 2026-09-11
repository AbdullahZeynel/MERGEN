#!/usr/bin/env python3
"""
UCSF-PDGM indirmesini pipeline'ın beklediği example_dataset/ düzenine bağlar.

Gerçek düzen:  UCSF-PDGM/<vaka>_nifti/<vaka>_FLAIR_bias.nii/<vaka>_FLAIR_bias.nii
Beklenen düzen: example_dataset/1/<vaka>_FLAIR.nii

Dosyaları kopyalamaz, sembolik link kurar (disk maliyeti yok).

Kullanım:
    python prepare_example_dataset.py                      # durum raporu + link
    python prepare_example_dataset.py --cases 0004 0007
    python prepare_example_dataset.py --duplicate-missing   # SADECE duman testi
"""

import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "UCSF-PDGM")
DST = os.path.join(BASE, "example_dataset")

# pipeline'ın istediği kanal -> kaynak dosyadaki olası ek adlar (öncelik sırasıyla)
MODALITIES = {
    "FLAIR": ["FLAIR_bias", "FLAIR"],
    "T1":    ["T1_bias", "T1"],
    "T1c":   ["T1c_bias", "T1c", "T1gad_bias", "T1gad"],
    "T2":    ["T2_bias", "T2"],
}
LABEL_KEYS = ["tumor_segmentation"]


def _strip_ext(name):
    for ext in (".nii.gz", ".nii"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def index_case(case_dir, case_id):
    """<vaka>_nifti klasörünü tara -> {'FLAIR_bias': gerçek_dosya_yolu, ...}"""
    found = {}
    for entry in sorted(os.listdir(case_dir)):
        path = os.path.join(case_dir, entry)
        key = _strip_ext(entry)
        if not key.startswith(case_id + "_"):
            continue
        key = key[len(case_id) + 1:]

        if os.path.isdir(path):
            # TCIA indirmesi her seriyi aynı adlı bir klasörün içine koyuyor
            inner = [f for f in sorted(os.listdir(path))
                     if f.endswith((".nii", ".nii.gz"))]
            if not inner:
                continue
            path = os.path.join(path, inner[0])
        elif not entry.endswith((".nii", ".nii.gz")):
            continue
        found[key] = path
    return found


def pick(found, keys):
    for k in keys:
        if k in found:
            return found[k]
    return None


def link(src, dst):
    if os.path.islink(dst) or os.path.exists(dst):
        os.remove(dst)
    os.symlink(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=["0004", "0007"],
                    help="vaka numaraları (varsayılan: ensemble_inference.py'deki CASES)")
    ap.add_argument("--duplicate-missing", action="store_true",
                    help="eksik T1/T2 yerine mevcut kanalı kopyala — metrikler GEÇERSİZ olur, "
                         "sadece boru hattının uçtan uca çalıştığını görmek için")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        sys.exit(f"HATA: {SRC} yok.")

    os.makedirs(DST, exist_ok=True)
    eksik_var = False      # gerçekten eksik kalan (çalıştırmayı engelleyen) bir şey
    sahte_var = False      # --duplicate-missing ile doldurulan kanal

    for i, num in enumerate(args.cases, start=1):
        case_id = f"UCSF-PDGM-{num}"
        case_dir = os.path.join(SRC, f"{case_id}_nifti")
        if not os.path.isdir(case_dir):
            print(f"[{case_id}] kaynak klasör yok: {case_dir}")
            eksik_var = True
            continue

        found = index_case(case_dir, case_id)
        out_dir = os.path.join(DST, str(i))
        os.makedirs(out_dir, exist_ok=True)
        print(f"\n[{case_id}] -> example_dataset/{i}   (bulunan seriler: {', '.join(sorted(found)) or 'yok'})")

        eksikler = []
        for mod, keys in MODALITIES.items():
            src = pick(found, keys)
            dst = os.path.join(out_dir, f"{case_id}_{mod}.nii")
            if src:
                link(src, dst)
                print(f"   ok      {mod:<6} <- {os.path.relpath(src, BASE)}")
            else:
                eksikler.append(mod)

        for mod in eksikler:
            yedek = (pick(found, MODALITIES["T1c"]) or
                     pick(found, MODALITIES["FLAIR"])) if args.duplicate_missing else None
            if yedek:
                sahte_var = True
                link(yedek, os.path.join(out_dir, f"{case_id}_{mod}.nii"))
                print(f"   SAHTE   {mod:<6} <- {os.path.basename(yedek)}  (metrik geçersiz)")
            else:
                eksik_var = True
                print(f"   EKSİK   {mod}")

        lab = pick(found, LABEL_KEYS)
        if lab:
            link(lab, os.path.join(out_dir, f"{case_id}_tumor_segmentation.nii"))
            print(f"   ok      label  <- {os.path.relpath(lab, BASE)}")
        else:
            eksik_var = True
            print("   EKSİK   tumor_segmentation")

    if eksik_var:
        print("\nEksik seriler var. Modeller 4 kanal (T1, T1c, T2, FLAIR) + etiket bekliyor;")
        print("eksik kanalla çalıştırmak Dice'ı anlamsız kılar. TCIA'dan bu vakaların")
        print("T1 ve T2 serilerini de indir. Sadece boru hattını denemek istiyorsan")
        print("--duplicate-missing ekle.")
        return 1
    if sahte_var:
        print("\nHazır ama kanalların bir kısmı SAHTE (kopyalanmış).")
        print("Çıkan Dice skorlarını rapora yazma; bu sadece boru hattı testi.")
    else:
        print("\nHazır. Sıradaki: python ensemble_inference.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
