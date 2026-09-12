"""
ESM-2 Zero-Shot Skorlayıcı
===========================

Mutasyon konumundaki log-likelihood ratio'yu üretir. Eğitim hattı ve canlı
çıkarım adaptörü aynı sınıfı kullanır; sınıf eğitim modüllerinden bağımsız
olsun diye ``ozellik_cikarimi`` içinden buraya taşındı (eski import yolu
korunur). Ağırlık yalnız yerelden yüklenir: bkz. ``esm_yerel``.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import torch

from . import config
from .esm_yerel import ESMYokHatasi, kaynagi_coz

LOG = logging.getLogger(__name__)


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
        self._kaynak = None

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

    @property
    def kaynak(self):
        """Ağırlığın çözümlenmiş yerel kaynağı (yol, revision, çevrimdışı mı)."""
        if self._kaynak is None:
            self._kaynak = kaynagi_coz(self.model_adi)
        return self._kaynak

    def _yukle(self) -> None:
        from transformers import AutoModelForMaskedLM, AutoTokenizer
        kaynak = self.kaynak
        LOG.info("ESM-2 yükleniyor (%s, revision=%s, çevrimdışı=%s) — cihaz=%s",
                 kaynak.model_adi, kaynak.revision, kaynak.cevrimdisi, self.cihaz)
        # Çevrimdışı modda transformers ağa hiç çıkmaz; ağırlık eksikse
        # sessiz indirme yerine anlaşılır hata üretilir.
        secenek = {"local_files_only": kaynak.cevrimdisi}
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                kaynak.yukleme_hedefi, **secenek)
            self._model = AutoModelForMaskedLM.from_pretrained(
                kaynak.yukleme_hedefi, **secenek)
        except (OSError, ValueError) as exc:
            raise ESMYokHatasi(
                f"ESM-2 yüklenemedi ({kaynak.yukleme_hedefi}, "
                f"çevrimdışı={kaynak.cevrimdisi}): {exc}"
            ) from exc
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
