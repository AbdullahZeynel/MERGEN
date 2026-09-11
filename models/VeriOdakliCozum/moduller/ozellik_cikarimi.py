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
# Aşağıdaki sözlükler AAindex veri tabanından (Kawashima & Kanehisa, 2008)
# elle seçilmiş kanonik indekslerin sayısal değerlerini içerir. Donanım dostu
# olması ve harici bağımlılığı azaltmak için kütüphane yerine sabit kullanılır.

AAINDEX = {
    # Hidrofobiklik — Kyte & Doolittle 1982 (KYTJ820101)
    "hidrofobiklik": {
        "A": 1.8, "C": 2.5, "D": -3.5, "E": -3.5, "F": 2.8, "G": -0.4,
        "H": -3.2, "I": 4.5, "K": -3.9, "L": 3.8, "M": 1.9, "N": -3.5,
        "P": -1.6, "Q": -3.5, "R": -4.5, "S": -0.8, "T": -0.7, "V": 4.2,
        "W": -0.9, "Y": -1.3,
    },
    # Molekül hacmi (Å³) — Bigelow 1967 (BIGC670101)
    "hacim": {
        "A": 88.6, "C": 108.5, "D": 111.1, "E": 138.4, "F": 189.9, "G": 60.1,
        "H": 153.2, "I": 166.7, "K": 168.6, "L": 166.7, "M": 162.9, "N": 114.1,
        "P": 112.7, "Q": 143.8, "R": 173.4, "S": 89.0, "T": 116.1, "V": 140.0,
        "W": 227.8, "Y": 193.6,
    },
    # Polarite — Grantham 1974 (GRAR740102)
    "polarite": {
        "A": 8.1, "C": 5.5, "D": 13.0, "E": 12.3, "F": 5.2, "G": 9.0,
        "H": 10.4, "I": 5.2, "K": 11.3, "L": 4.9, "M": 5.7, "N": 11.6,
        "P": 8.0, "Q": 10.5, "R": 10.5, "S": 9.2, "T": 8.6, "V": 5.9,
        "W": 5.4, "Y": 6.2,
    },
    # İzoelektrik nokta (pI)
    "izoelektrik": {
        "A": 6.00, "C": 5.07, "D": 2.77, "E": 3.22, "F": 5.48, "G": 5.97,
        "H": 7.59, "I": 6.02, "K": 9.74, "L": 5.98, "M": 5.74, "N": 5.41,
        "P": 6.30, "Q": 5.65, "R": 10.76, "S": 5.68, "T": 5.60, "V": 5.96,
        "W": 5.89, "Y": 5.66,
    },
    # Yük (pH 7.4'te yaklaşık)
    "yuk": {
        "A": 0, "C": 0, "D": -1, "E": -1, "F": 0, "G": 0, "H": 0.1, "I": 0,
        "K": 1, "L": 0, "M": 0, "N": 0, "P": 0, "Q": 0, "R": 1, "S": 0,
        "T": 0, "V": 0, "W": 0, "Y": 0,
    },
    # Esneklik — Bhaskaran & Ponnuswamy 1988 (BHAR880101)
    "esneklik": {
        "A": 0.357, "C": 0.346, "D": 0.511, "E": 0.497, "F": 0.314, "G": 0.544,
        "H": 0.323, "I": 0.462, "K": 0.466, "L": 0.365, "M": 0.295, "N": 0.463,
        "P": 0.509, "Q": 0.493, "R": 0.529, "S": 0.507, "T": 0.444, "V": 0.386,
        "W": 0.305, "Y": 0.420,
    },
    # Yüzey erişilebilirliği — Janin 1978 (JANJ780101)
    "yuzey_erisim": {
        "A": 6.6, "C": 0.9, "D": 7.7, "E": 5.7, "F": 2.4, "G": 6.7, "H": 2.5,
        "I": 2.8, "K": 10.3, "L": 4.8, "M": 1.0, "N": 6.7, "P": 4.8, "Q": 5.2,
        "R": 4.5, "S": 9.4, "T": 7.0, "V": 4.5, "W": 1.4, "Y": 5.1,
    },
    # α-heliks tercihi — Chou & Fasman 1978 (CHOP780201)
    "heliks_tercihi": {
        "A": 1.42, "C": 0.70, "D": 1.01, "E": 1.51, "F": 1.13, "G": 0.57,
        "H": 1.00, "I": 1.08, "K": 1.16, "L": 1.21, "M": 1.45, "N": 0.67,
        "P": 0.57, "Q": 1.11, "R": 0.98, "S": 0.77, "T": 0.83, "V": 1.06,
        "W": 1.08, "Y": 0.69,
    },
    # β-tabaka tercihi — Chou & Fasman 1978 (CHOP780202)
    "beta_tercihi": {
        "A": 0.83, "C": 1.19, "D": 0.54, "E": 0.37, "F": 1.38, "G": 0.75,
        "H": 0.87, "I": 1.60, "K": 0.74, "L": 1.30, "M": 1.05, "N": 0.89,
        "P": 0.55, "Q": 1.10, "R": 0.93, "S": 0.75, "T": 1.19, "V": 1.70,
        "W": 1.37, "Y": 1.47,
    },
}


def aaindex_delta_hesapla(wt: str, mut: str) -> dict[str, float]:
    """
    Tek bir missense varyant için tüm AAindex skalalarında delta (mut - wt) verir.

    Parameters
    ----------
    wt, mut : str
        Tek harfli amino asit kodları.

    Returns
    -------
    dict[str, float]
        Anahtarlar: ``"delta_<özellik>"``
    """
    cikti: dict[str, float] = {}
    for ad, tablo in AAINDEX.items():
        if wt in tablo and mut in tablo:
            cikti[f"delta_{ad}"] = tablo[mut] - tablo[wt]
        else:
            cikti[f"delta_{ad}"] = 0.0
    # Grantham mesafesi yaklaşığı (kompozit) — fizikokimyasal şok büyüklüğü
    cikti["grantham_yakl"] = abs(cikti.get("delta_polarite", 0)) * 1.833 \
                              + abs(cikti.get("delta_hacim", 0)) * 0.1018 \
                              + abs(cikti.get("delta_hidrofobiklik", 0)) * 0.196
    return cikti


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
