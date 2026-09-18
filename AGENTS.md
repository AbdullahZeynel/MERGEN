# Geliştirme kuralları

Codex, Claude ve insan katkıcılar için ortak kaynak bu dosyadır.

1. **Önce oku:** README, `docs/PLAN.md` ve değiştireceğin kodu incele. Başka projedeki kuralları buraya kendiliğinden uygulama.
2. **Kaynakla doğrula:** Teknik iddiaya `dosya:satır` veya komut çıktısı göster. Doğrulanmayanı açıkça belirt. Proje klasöründe bulunmayan ağırlık için yapılandırılmış model cache'ini de kontrol et.
3. **Dar kapsam:** Yaklaşımı kısaca açıkla; yalnızca istenen işi yap. İlgisiz refactor, toplu biçimlendirme ve bağımlılık değişikliği ekleme.
4. **Sınırları koru:** Arayüz → backend → model servisleri. Model çalıştırma ve anahtarlar tarayıcıya taşınmaz. MCP ortak backend işlevlerini kullanır.
5. **Modelleri koru:** Açık talep olmadan yeniden eğitim, ağırlık/fold, eşik veya ön işleme değişikliği yapma. Eğitim/değerlendirme ile canlı çıkarımı ayrı tut.
6. **Sonuç uydurma:** Demo ve canlı sonucu etiketle. Eksik veri yerine sessizce sahte modalite, rastgele skor veya başarılı sonuç üretme. Farklı hastaları eşleştirme; referans etiketi olmadan Dice gösterme.
7. **Git temizliği:** Ağırlık, veri seti, sanal ortam, çıktı ve sırları commit etme. Dosyaları bilinçli seç; iç içe `.git` ve büyük dosyaları kontrol et. Üçüncü taraf lisanslarını koru.
8. **Doğrula:** Değişikliğe uygun kontrolleri çalıştır. Sözdizimi kontrolünü model/arayüz çalıştı diye sunma. Yapılmayan testi ve engelini yaz.
9. **Kayıt bırak:** Davranış veya kurulum değiştiğinde ilgili kısa belgeyi güncelle. Gelecek işler için ayrı dal/PR kullan; commit başlığı `feat:`, `fix:`, `docs:` veya `chore:` ile başlasın.
10. **Yetki ve belirsizlik:** Mevcut kullanıcı talebi kapsamındaki geri alınabilir işleri tamamla. Veri silme, geçmişi yeniden yazma veya izinsiz yayınlama yapma. Kritik belirsizlikte somut soruyu sor; aynı hatayı körlemesine tekrarlama.

## Sırlar ve örnek yapılandırmalar

- Gerçek VPS/ev/Tailscale IP'si, özel hostname, kullanıcı/parola, token, SSH anahtarı ve bağlantı sırrı kodda, belgede, testte veya logda yer almaz; yerel yapılandırmada tutulur.
- `.env.example`, `*.env.example` ve diğer örneklerde yalnızca boş değer veya açık yer tutucu kullan. `example.com`, `<VPS_HOST>` gibi örnekler uygundur; gerçek altyapı adresi veya çalışır credential kopyalama. `localhost`, `127.0.0.1`, `0.0.0.0` yerel/dinleme ayarı olarak kullanılabilir.
- `.env` otomatik yüklenmez: servis okuyucusunu açıkça yapılandır; gerekli sır eksikse anlaşılır hatayla dur, koda gömülü yedek sır kullanma. Tarayıcıya çıkan değişkenlere sır koyma.
- Commit/push öncesi seçilmiş diff'i credential ve altyapı adresleri açısından kontrol et; eşleşen sırrı çıktıya yazma. `.gitignore` içerik taramaz ve daha önce takip edilen dosyayı korumaz. Sır yayımlandıysa önce iptal/yenileme gerekir; dosyayı sonraki committe silmek geçmişten kaldırmaz.
- Bu kontrolün otomatik kısmı `python infra/ci/repo_guard.py`; CI'da her değişiklikte çalışır. Takip edilen dosyalarda şunları arar: sır atamaları ve sağlayıcı anahtar biçimleri (AWS, GitHub, Slack, HuggingFace, Google, JWT), gerçek IP ve `.ts.net` adresleri, özel/SSH anahtarları, Git'te bulunmaması gereken dosya adları (`.env`, `*.pem`, `*.key`, `id_*`, `credentials*.json`, `*.tfstate`, iç içe `.git/`), ağırlık/veri uzantıları ve 1 MiB üstü dosyalar. Ayrıca `.gitignore`'un koruyucu desenlerini kaybetmediğini doğrular ve `*.env.example` dosyalarının yalnız boş ya da açık yer tutucu değer taşıdığını kontrol eder. Bulguları değer yazdırmadan raporlar; gerçekten zararsız bir satırı `# repo-guard: allow` yorumuyla geçebilirsiniz. Betik elle incelemenin yerini tutmaz.

<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->
