# Frontend VPS dağıtımı

Bu sprint yalnızca statik arayüzün paketlenmesini ve VPS üzerinde sürümlenmesini hazırlar. SSH bağlantısı, canlı deploy, DNS/TLS yapılandırması ve backend reverse proxy henüz yapılmadı.

## Paketi geliştirme makinesinde oluştur

Repo kökünde:

```bash
bash infra/vps/package-frontend.sh
# İnternetten alınmış, yayımlanabilir demo önizlemelerini de dahil etmek için:
bash infra/vps/package-frontend.sh --include-demo
```

Betik kilitli bağımlılıkları kurar, test/typecheck/build çalıştırır ve `.local/releases/` altında arşiv + SHA-256 çıktısı üretir. Varsayılan paket demo verisini dışlar. Kaynak kod, `.env`, ağırlıklar ve ham hacimler arşive alınmaz; yalnızca `frontend/dist/` paketlenir. `dist/` içeriği dağıtımdan önce gözden geçirilmelidir. Commitlenmemiş değişiklikler build'e girer; üretim paketini temiz sprint commitinden oluşturun.

## VPS'ye kur

VPS gereksinimleri: Python 3.11+, Caddy ve site dosyaları için `/srv/mergen` dizinine yazabilen bir deploy kullanıcısı. Caddy kullanıcısı bu dizini okuyabilmeli. Python modeli veya Node.js VPS'de frontend için gerekli değildir.

Arşivi ve `deploy_frontend.py` betiğini SCP/rsync ile VPS'ye taşıdıktan sonra **VPS üzerinde** çalıştırın (yer tutucuları yerel gerçek değerlerle değiştirin):

```bash
python3 deploy_frontend.py install --archive <PAKET_YOLU> --sha256 <SHA256>
python3 deploy_frontend.py rollback
```

Her paket checksum ile doğrulanır; path traversal, symlink ve gizli dosyalar reddedilir. Yeni sürüm `releases/<digest>/` altına açılır. `current` symlink'i atomik değiştirilir; önceki sürüm `previous` olarak saklanır. Hash'li JS/CSS/fontlar `shared/assets/` içinde korunur; açık sekmeler deploy/rollback sonrasında eski assetlerini almaya devam eder. Aynı anda tek deploy çalıştırın. Betik eski sürümleri veya assetleri silmez. Test için `--root /tmp/<TEST_DIZINI>` kullanılabilir.

## Caddy

`Caddyfile.example` şablonunu Caddy yapılandırmasına alın. `frontend.env.example` dosyasını Git dışı `frontend.env` olarak doldurun. Bu dosya otomatik yüklenmez; Caddy systemd override'ında `EnvironmentFile=` ile tam yerel yoluna bağlanmalıdır. `MERGEN_DOMAIN` gerçek alan adıdır; `MERGEN_ROOT` boş bırakılırsa `/srv/mergen` kullanılır. Shell'de export etmek çalışan systemd servisine aktarmaz.

```bash
# Gerçek yapılandırma ve ortam değişkenleriyle, VPS üzerinde:
caddy validate --config <CADDYFILE_YOLU> --adapter caddyfile
# Ortam/ünite değişikliği ilk kurulumda daemon-reload ve servis restart gerektirir.
```

Bu aşamada `/api/*` açıkça 503 döner. `/demo/*` ve `/assets/*` eksikse 404 döner; bunlar SPA HTML'ine dönüşmez. Diğer yollar `index.html` üzerinden açılır. Hash'li statik dosyalar uzun önbellek, HTML/manifest yeniden doğrulama kullanır. Backend tamamlanınca `/api/*` bloğu gerçek reverse proxy'ye çevrilecek; hedef Git dışı ayarda tutulacak.

Dağıtım sonrası ana sayfa, `/demo/manifest.json`, PNG/font/JS dosyaları ve `/api/health` durumunu kontrol edin. Hata varsa `rollback` çalıştırın. Caddy mevcut `current` yolunu okuduğundan yalnızca statik sürüm değişiminde servis restart gerekmez.

Yerel kurulum/rollback testleri:

```bash
python3 -m unittest discover -s infra/vps -p 'test_*.py'
bash -n infra/vps/package-frontend.sh
```
