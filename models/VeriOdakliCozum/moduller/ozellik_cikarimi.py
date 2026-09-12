"""
Özellik Çıkarım Modülü
=======================

Her bir missense varyantı için iki tür özellik üretir:

1. **AAindex fizikokimyasal delta'ları** — vahşi tip vs mutant amino asit
   arasındaki hidrofobiklik, hacim, polarite, yük, esneklik, vb. farkları.
2. **ESM-2 zero-shot patojenite skoru** — Meta'nın protein dil modeliyle
   evrimsel korunum/şok skoru (log-likelihood ratio).

Çıktı: modele girilebilecek `pd.DataFrame` (sayısal özellikler + etiket).
"""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
import pandas as pd
import torch
from tqdm.auto import tqdm

from .. import config

LOG = logging.getLogger(__name__)


# ===========================================================================
# BÖLÜM 1 — AAindex tabanlı özellikler
# ===========================================================================
# Tablolar ve delta formülü bağımlılıksız `aa_ozellikler` modülüne taşındı;
# çıkarım adaptörü torch yüklemeden aynı tanımı kullanabilsin diye. İsimler
# geriye dönük uyumluluk için buradan da erişilebilir kalır.
from .aa_ozellikler import AAINDEX, aaindex_delta_hesapla  # noqa: F401


# ===========================================================================
# BÖLÜM 2 — ESM-2 zero-shot patojenite skoru
# ===========================================================================
class ESM2Skorlayici:
    """
    Meta'nın ESM-2 modelini sarmalar ve mutasyon konumunda log-likelihood
    ratio hesaplar (negatif değer ⇒ evrimsel olarak şok, patojenite işareti).

    Lazy loading: model ilk skor isteğinde belleğe alınır.
    """

    def __init__(self, model_adi: str = config.ESM_MODEL_ADI):
        self.model_adi = model_adi
        self.cihaz = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = None
        self._tokenizer = None

    @property
    def model(self):
        if self._model is None:
            self._yukle()
        return self._model

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            self._yukle()
        return self._tokenizer

    def _yukle(self) -> None:
        from transformers import AutoTokenizer, AutoModelForMaskedLM
        LOG.info("ESM-2 yükleniyor (%s) — cihaz=%s", self.model_adi, self.cihaz)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_adi)
        self._model = AutoModelForMaskedLM.from_pretrained(self.model_adi)
        self._model.eval().to(self.cihaz)

    # -----------------------------------------------------------------
    def _dizilim_kirp(self, dizilim: str, poz_1tabanli: int) -> tuple[str, int]:
        """Uzun proteinleri mutasyon merkezli bir pencereye kırparak ESM
        giriş sınırına sığdırır. Pozisyonu yeni pencereye göre günceller."""
        n = len(dizilim)
        if n <= config.ESM_MAKS_DIZILIM_UZUNLUGU:
            return dizilim, poz_1tabanli - 1     # 0-tabanlı endeks

        yari = config.ESM_PENCERE_YARI_GENISLIGI
        merkez = poz_1tabanli - 1
        bas = max(0, merkez - yari)
        son = min(n, bas + 2 * yari + 1)
        bas = max(0, son - (2 * yari + 1))
        return dizilim[bas:son], merkez - bas

    @torch.inference_mode()
    def llr_hesapla(self, dizilim: str, poz_1tabanli: int, wt: str, mut: str) -> float:
        """
        Tek bir varyant için log-likelihood ratio döndürür.

        LLR = log P(mut | context) − log P(wt | context)

        * < 0  ⇒ mutasyon evrimsel olarak şok yaratıyor (potansiyel patojenik)
        * ≈ 0  ⇒ nötr
        * > 0  ⇒ mutasyon doğal varyasyonla uyumlu
        """
        kirpilmis, yeni_endeks = self._dizilim_kirp(dizilim, poz_1tabanli)
        if not (0 <= yeni_endeks < len(kirpilmis)):
            return 0.0

        # WT kontrolü — uyumsuzlukta sıfır döndür (özellik nötrleştirilir)
        if kirpilmis[yeni_endeks] not in (wt, "X"):
            return 0.0

        maskelenmis = (kirpilmis[:yeni_endeks]
                       + self.tokenizer.mask_token
                       + kirpilmis[yeni_endeks + 1:])

        inp = self.tokenizer(maskelenmis, return_tensors="pt").to(self.cihaz)
        logits = self.model(**inp).logits[0]              # (L, V)
        # +1 CLS kayması — tokenizer EsmTokenizer her zaman CLS ekler
        token_id_mask = (inp["input_ids"][0] == self.tokenizer.mask_token_id).nonzero()
        if token_id_mask.numel() == 0:
            return 0.0
        mask_idx = int(token_id_mask[0])
        log_probs = torch.log_softmax(logits[mask_idx], dim=-1)

        wt_id = self.tokenizer.convert_tokens_to_ids(wt)
        mut_id = self.tokenizer.convert_tokens_to_ids(mut)
        return float(log_probs[mut_id] - log_probs[wt_id])

    @lru_cache(maxsize=4096)
    def _onbellekli_llr(self, dizilim: str, poz: int, wt: str, mut: str) -> float:
        return self.llr_hesapla(dizilim, poz, wt, mut)


# ===========================================================================
# BÖLÜM 3 — Üst seviye özellik matrisi üretimi
# ===========================================================================
def ozellik_matrisi_olustur(
    df: pd.DataFrame,
    esm_skorlayici: ESM2Skorlayici | None = None,
    esm_kullan: bool = True,
) -> pd.DataFrame:
    """
    Ön işlemeden geçmiş tabloyu modele hazır sayısal özellik matrisine dönüştürür.

    Parameters
    ----------
    df : pd.DataFrame
        ``on_isleme.veriyi_hazirla`` çıktısı.
    esm_skorlayici : ESM2Skorlayici | None
        Hazır skorlayıcı; None ise burada başlatılır.
    esm_kullan : bool
        ESM-2 hesaplaması kapatılabilir (donanım kısıtı durumunda).

    Returns
    -------
    pd.DataFrame
        Sayısal kolonlar + ``etiket`` + iz kolonları (gen, protein_degisim).
    """
    LOG.info("AAindex delta özellikleri hesaplanıyor…")
    aa_kayitlari: list[dict] = []
    for _, r in df.iterrows():
        aa_kayitlari.append(aaindex_delta_hesapla(r["wt_aa"], r["mut_aa"]))
    aa_df = pd.DataFrame(aa_kayitlari, index=df.index)

    if esm_kullan:
        esm_skorlayici = esm_skorlayici or ESM2Skorlayici()
        LOG.info("ESM-2 zero-shot skorları hesaplanıyor (n=%d)…", len(df))
        llr_listesi: list[float] = []
        for _, r in tqdm(df.iterrows(), total=len(df), desc="ESM-2"):
            try:
                skor = esm_skorlayici._onbellekli_llr(
                    r["protein_dizilim"], int(r["pozisyon_aa"]), r["wt_aa"], r["mut_aa"]
                )
            except Exception as exc:
                LOG.debug("ESM-2 skoru hesaplanamadı: %s", exc)
                skor = 0.0
            llr_listesi.append(skor)
        aa_df["esm_llr"] = llr_listesi
        # Patojenite proxy'si: negatif LLR ⇒ daha şiddetli mutasyon
        aa_df["esm_pathojenite"] = -aa_df["esm_llr"]
    else:
        aa_df["esm_llr"] = 0.0
        aa_df["esm_pathojenite"] = 0.0

    # COSMIC frekansı (varsa) — log dönüşüm normalize
    aa_df["cosmic_frekans_log"] = np.log1p(df["cosmic_frekans"].fillna(0).astype(float))

    # CGGA Çin glioma kohortu gen-bazlı missense frekansı (varsa)
    if "cgga_missense_frekans" in df.columns:
        aa_df["cgga_missense_frekans"] = df["cgga_missense_frekans"].fillna(0.0).values
    else:
        aa_df["cgga_missense_frekans"] = 0.0

    # Pozisyon nispi (proteindeki yer)
    aa_df["nispi_pozisyon"] = df.apply(
        lambda r: r["pozisyon_aa"] / max(len(r["protein_dizilim"]), 1), axis=1
    )

    # İz / etiket
    aa_df["etiket"] = df["etiket"].values
    aa_df["gen"] = df["gen"].values
    aa_df["protein_degisim"] = df["protein_degisim"].values
    aa_df["kohort"] = df.get("kohort", "TCGA").values \
        if "kohort" in df.columns else "TCGA"

    # MC3'ten gelen klasik araç skorlarını iz olarak taşı
    # (degerlendirme modülü bu varsa API'ye gitmez)
    if "sift_skor" in df.columns:
        aa_df["mc3_sift_skor"] = df["sift_skor"].values
    if "polyphen_skor" in df.columns:
        aa_df["mc3_polyphen_skor"] = df["polyphen_skor"].values

    LOG.info("Özellik matrisi: %d satır × %d kolon",
             aa_df.shape[0], aa_df.shape[1] - 4)
    return aa_df.reset_index(drop=True)
