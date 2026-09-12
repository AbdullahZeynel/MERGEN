"""
ESM-2 Ağırlıklarının Çevrimdışı Çözümlenmesi
=============================================

Canlı çıkarım sırasında ağa çıkılmaz. Bu modül ağırlığın diskte nerede
olduğunu bulur, hangi revision'ın kullanıldığını söyler ve kritik dosyaların
SHA-256 değerlerini üretir; denetim kaydı bu değerlerle yazılır.

Arama sırası:

1. ``MERGEN_ESM_YEREL_YOL`` — doğrudan snapshot dizini (config.json içerir).
2. ``MERGEN_ESM_CACHE_DIZINI`` — Hugging Face hub cache kökü.
3. ``HF_HUB_CACHE`` / ``HF_HOME`` / ``~/.cache/huggingface/hub``.

Hiçbirinde bulunamazsa ``ESMYokHatasi`` yükselir; indirme yalnız
``MERGEN_ESM_INDIRME_IZNI=1`` verildiğinde ve hazırlık adımında yapılır.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from . import config

# Snapshot'ta bulunması beklenen dosyalar; tokenizer.json bu modelde yoktur.
KRITIK_DOSYALAR = ("config.json", "model.safetensors", "vocab.txt",
                   "tokenizer_config.json", "special_tokens_map.json")
AGIRLIK_ADAYLARI = ("model.safetensors", "pytorch_model.bin")


class ESMYokHatasi(RuntimeError):
    """ESM-2 ağırlığı yerelde bulunamadı; sessiz indirme yapılmaz."""


@dataclass(frozen=True)
class ESMKaynagi:
    model_adi: str
    yol: Path | None            # yerel snapshot dizini (bulunduysa)
    revision: str | None        # HF cache'teki commit kimliği
    cache_dizini: Path | None
    cevrimdisi: bool

    @property
    def yukleme_hedefi(self) -> str:
        """from_pretrained'e verilecek değer: yerel dizin ya da model adı."""
        return str(self.yol) if self.yol is not None else self.model_adi


def _cache_adaylari() -> list[Path]:
    adaylar: list[str | None] = [config.ESM_CACHE_DIZINI,
                                 os.environ.get("HF_HUB_CACHE")]
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        adaylar.append(str(Path(hf_home) / "hub"))
    adaylar.append(str(Path.home() / ".cache" / "huggingface" / "hub"))
    goruldu: list[Path] = []
    for ham in adaylar:
        if not ham:
            continue
        yol = Path(ham).expanduser()
        if yol.is_dir() and yol not in goruldu:
            goruldu.append(yol)
    return goruldu


def _snapshot_sec(model_dizini: Path) -> tuple[Path, str] | None:
    """Cache'teki model klasöründen kullanılabilir snapshot ve revision."""
    refs = model_dizini / "refs" / "main"
    snapshots = model_dizini / "snapshots"
    if not snapshots.is_dir():
        return None
    tercihler: list[str] = []
    if refs.is_file():
        tercihler.append(refs.read_text().strip())
    tercihler += sorted(p.name for p in snapshots.iterdir() if p.is_dir())
    for revision in tercihler:
        aday = snapshots / revision
        if (aday / "config.json").is_file() and any(
                (aday / ad).is_file() for ad in AGIRLIK_ADAYLARI):
            return aday, revision
    return None


def kaynagi_coz(model_adi: str | None = None) -> ESMKaynagi:
    """ESM-2'nin yerel konumunu çözer; indirme izni yoksa bulunamazsa hata verir."""
    model_adi = model_adi or config.ESM_MODEL_ADI
    cevrimdisi = not config.ESM_INDIRME_IZNI

    if config.ESM_YEREL_YOL:
        yol = Path(config.ESM_YEREL_YOL).expanduser()
        if not (yol / "config.json").is_file():
            raise ESMYokHatasi(
                f"MERGEN_ESM_YEREL_YOL={yol} altında config.json yok. "
                "Yol bir snapshot dizinini göstermeli."
            )
        return ESMKaynagi(model_adi, yol.resolve(), None, None, cevrimdisi)

    klasor_adi = "models--" + model_adi.replace("/", "--")
    for cache in _cache_adaylari():
        bulunan = _snapshot_sec(cache / klasor_adi)
        if bulunan:
            yol, revision = bulunan
            return ESMKaynagi(model_adi, yol.resolve(), revision, cache.resolve(),
                              cevrimdisi)

    if cevrimdisi:
        bakilan = ", ".join(str(p) for p in _cache_adaylari()) or "(cache yok)"
        raise ESMYokHatasi(
            f"ESM-2 ağırlığı ({model_adi}) yerelde bulunamadı. Bakılan cache: "
            f"{bakilan}. Canlı çıkarım indirme yapmaz; hazırlık adımında "
            "MERGEN_ESM_INDIRME_IZNI=1 ile indirin ya da MERGEN_ESM_YEREL_YOL "
            "değişkenini snapshot dizinine ayarlayın."
        )
    return ESMKaynagi(model_adi, None, None, None, cevrimdisi)


def sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def varlik_kaydi(kaynak: ESMKaynagi | None = None) -> dict:
    """Denetim kaydı için model kimliği, revision ve dosya checksum'ları."""
    kaynak = kaynak or kaynagi_coz()
    dosyalar: dict[str, dict] = {}
    if kaynak.yol is not None:
        for ad in KRITIK_DOSYALAR:
            hedef = kaynak.yol / ad
            if hedef.is_file():
                gercek = hedef.resolve()          # cache'te blob'a symlink
                dosyalar[ad] = {"sha256": sha256(gercek),
                                "bytes": gercek.stat().st_size}
    return {
        "modelId": kaynak.model_adi,
        "revision": kaynak.revision,
        "localPath": str(kaynak.yol) if kaynak.yol else None,
        "offline": kaynak.cevrimdisi,
        "files": dosyalar,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(varlik_kaydi(), ensure_ascii=False, indent=2))
