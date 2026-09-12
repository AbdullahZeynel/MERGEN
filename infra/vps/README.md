# Frontend VPS dağıtımı

Statik arayüz paketi, özel demo MCP ve API servislerinin kurulum dosyaları hazırdır. Gerçek VPS üzerinde SSH/deploy ve DNS/TLS doğrulaması henüz yapılmadı. Demo dosyaları VPS'te tutulur; Ubuntu'ya bağımlı değildir.

## Paketi geliştirme makinesinde oluştur

Repo kökünde:

```bash
bash infra/vps/package-frontend.sh
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

`/api/*` özel loopback API'ye yönlenir; `/mcp*` ve eski `/demo/*` yolları 404 döner. MCP internete açılmaz. Diğer yollar `index.html` üzerinden açılır. Hash'li statik dosyalar uzun önbellek, vaka listesi no-store, demo varlıkları kısa özel önbellek kullanır.

Dağıtım sonrası ana sayfa, `/api/demo/cases`, kesit/mesh/font/JS dosyaları ve `/api/health` durumunu kontrol edin. Hata varsa frontend için `rollback` çalıştırın. Caddy mevcut `current` yolunu okuduğundan yalnızca statik sürüm değişiminde servis restart gerekmez. Frontend rollback servis kodunu veya demo paketini geri almaz; bunları uyumlu sürümde tutun.

Yerel kurulum/rollback testleri:

```bash
python3 -m unittest discover -s infra/vps -p 'test_*.py'
bash -n infra/vps/package-frontend.sh
```

## Demo API ve MCP'yi kur

VPS'te Python 3.11+, venv, pip ve systemd gerekir. Model/CUDA/bilimsel Python ortamı VPS'ye kurulmaz. Gözden geçirilmiş checkout'tan **VPS üzerinde**:

```bash
sudo bash infra/vps/install-services.sh
```

Betik `python3.14`, `python3.13`, `python3.12`, `python3.11` ve son olarak `python3`
sırasıyla desteklenen bir yorumlayıcı arar. Oracle Linux'ta sistem `python3` komutu daha eski
bir sürüme gidiyorsa yorumlayıcıyı açıkça seçebilirsiniz:

```bash
sudo env PYTHON_BIN=/usr/bin/python3.12 bash infra/vps/install-services.sh
```

`PYTHON` değişkeni kullanılmaz. Seçilen yorumlayıcının `venv` modülü de kurulu olmalıdır.

Betik `mergen` servis kullanıcısını ve `/srv/mergen/services` altındaki ayrı venv'i hazırlar; sistem Python'una paket kurmaz. Servisleri otomatik başlatmaz. Güncelleme mevcut servis dosyalarını değiştirir; bakım sırasında iki servisi durdurup kurulumu uygulayın. Bu ilk kurulum betiği servis kodunda atomik sürüm/rollback sağlamaz; güncellemeden önce mevcut servis dizinini yedekleyin.

Geliştirme makinesinde [demo paketini](../../docs/DEMO_SERVICES.md) üretin. `.local/demo-v2` dizinini ayrı olarak VPS'te `/srv/mergen/demo-v2` yoluna rsync/SCP ile taşıyın; kopyalamadan önce/sonra checksum doğrulayın. Dizin `mergen` kullanıcısı tarafından okunabilmeli, Caddy'nin `current/shared` dizinleri altında olmamalıdır. `/etc/mergen/services.env` içindeki `MERGEN_DEMO_ROOT` değerini bu VPS dizinine ayarlayın. Örnek dosyada gerçek makine bilgisi yoktur.

```bash
sudo systemctl enable --now mergen-mcp mergen-api
curl --fail http://127.0.0.1:9000/api/health
python3 infra/vps/smoke-demo.py
```

Yalnızca Caddy'nin HTTP/HTTPS portlarını internete açın; 9000/9010 loopback'te kalır. Caddy ayarını doğruladıktan sonra yükleyin. Henüz oturum doğrulaması yoktur: sadece yayımlanabilir demo vakaları sunulur. 5–10 kullanıcı sınırı bu kurulumun parçası değildir; API bağlantı limiti kullanıcı sayısı olarak sunulmaz. Gerçek Oracle ARM/VPS kurulumu ayrıca prova edilecektir.
