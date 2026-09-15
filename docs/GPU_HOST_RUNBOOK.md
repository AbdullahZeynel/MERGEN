# GPU host runbook

Bu belge, **günlük kullanılan** bir Linux bilgisayarı MERGEN'in paylaşımlı GPU
hostuna dönüştürme sırasını anlatır. Host bir VM veya golden image değildir:
sahibi aynı makinede çalışmaya, oyun oynamaya ve GPU kullanmaya devam eder.
Buradaki her adım bu kısıtla yazıldı.

Kapsam G0–G1'dir. Dispatcher ve executor uygulamaları
([`SYSTEM_SPRINTS.md`](SYSTEM_SPRINTS.md) G2–G3) burada yazılmaz; bu belge
onların ihtiyaç duyacağı hesap, dizin, izin ve GPU paylaşım sınırlarını
hazırlar.

## Değişmez kurallar

1. Kurulum mevcut GPU süreçlerini durdurmaz, NVIDIA sürücüsünü kaldırmaz,
   masaüstü oturumunu değiştirmez.
2. Kullanıcının GPU prosesi hiçbir koşulda otomatik öldürülmez. GPU meşgulse
   MERGEN işi **bekler**.
3. Aynı anda en fazla bir MERGEN çıkarım işi çalışır.
4. Servis hesaplarının login shell'i ve sudo yetkisi yoktur.
5. Runtime dizini (iş girdisi, sonuç, spool) snapshot ve yedek kapsamına
   girmez. Kanıtlanamıyorsa kurulum durur.
6. Gerçek token, IP, hostname ve e-posta hiçbir repo dosyasına yazılmaz.

## Terim karışıklığı uyarısı

İki ayrı makine, benzer isimli iki dizin:

| Makine | Dizin | İçerik |
|---|---|---|
| VPS | `/srv/mergen/runtime/sessions/<id>/` | Tarayıcı oturumunun yüklemeleri ve sonuçları |
| GPU hostu | `/var/lib/mergen/runtime/` | Dispatcher'ın indirdiği iş paketleri ve executor çıktısı |

VPS tarafı `infra/vps/` altında ayrı yönetilir. Bu belge yalnız GPU hostunu
anlatır. Ayrıca VPS'teki `mergen` **sistem** hesabıdır (nologin); GPU hostundaki
`mergen` ise **insan** bakım hesabıdır. Aynı isim, farklı roller.

## Dizin ve hesap sözleşmesi

| Yol | Sahip:Grup | Mod | Amaç |
|---|---|---|---|
| `/opt/mergen` | `root:root` | 0755 | Sürümlü uygulama ve runtime kodu |
| `/srv/mergen-models` | `mergen:mergen-svc` | 0750 | Sürümlü, checksum'lı model ağırlıkları |
| `/var/lib/mergen/dispatcher` | `mergen-dispatcher:mergen-dispatcher` | 0700 | Dispatcher durumu |
| `/var/lib/mergen/executor` | `mergen-executor:mergen-executor` | 0700 | Executor durumu, kilit ve pause dosyası |
| `/var/lib/mergen/runtime` | `mergen-dispatcher:mergen-svc` | **2770** | Geçici iş paketleri — **yedek dışı** |
| `/etc/mergen` | `root:root` | 0751 | Git dışı env dosyaları |
| `/etc/mergen/dispatcher.env` | `root:mergen-dispatcher` | 0640 | VPS adresi ve worker token'ı |
| `/etc/mergen/executor.env` | `root:mergen-executor` | 0640 | Model yolları ve GPU eşikleri; **token yok** |

| Hesap | Tür | Shell | Sudo |
|---|---|---|---|
| `mergen` | İnsan bakım hesabı, home'lu | `/bin/bash` | Yalnız dar liste (aşağıda) |
| `mergen-dispatcher` | Sistem hesabı | `nologin` | Yok |
| `mergen-executor` | Sistem hesabı | `nologin` | Yok |
| `mergen-svc` | Grup | — | Model ağacını okumak için ortak grup |

### Spool izin sözleşmesi

Runtime dizini iki yönlü bir teslim alanıdır: dispatcher girdiyi yazar,
executor okuyup sonucu yazar, dispatcher sonucu geri okur. Bunun izin
düzeyinde gerçekten mümkün olması için üç parça birlikte çalışır:

| Parça | Değer | Ne sağlar |
|---|---|---|
| Dizin modu | `2770` (setgid) | İçeride oluşan her dizin ve dosya `mergen-svc` grubunu devralır |
| Ortak grup | `mergen-svc` | İki servis de üye; model ağacını da bu grupla okurlar |
| Unit umask | `UMask=0007` | Dosyalar `0660`, dizinler `0770` doğar — grup okuyup yazabilir |

Üçünden biri eksikse teslim çalışmaz: `UMask=0077` ile dosyalar `0600` doğar
ve karşı taraf okuyamaz; setgid olmadan grup devralınmaz.

`others` her düzeyde sıfırdır — bu makinede başka insan kullanıcılar var ve
runtime'da hasta girdisi bulunur.

`/etc/mergen/dispatcher.env` dosyasının 0640 olması systemd'ye karşı koruma
değildir — systemd `EnvironmentFile`'ı yetki düşmeden önce root olarak okur.
Koruma **diğer hesaplara** karşıdır, `mergen-executor` dahil.

---

## Sıra

Her adımın kabul ölçütü sağlanmadan sonrakine geçilmez. Sıra gelişigüzel
değil: **veri kapsamı kararı hesap açmaktan önce gelir.** Runtime dizini kök
snapshot'ına giren bir düzende hesaplar kurulursa, ilk işle birlikte hasta
girdisi sessizce yedeklere taşınır.

### 1. Kurulum öncesi salt okunur denetim

```bash
bash infra/gpu-host/audit-host.sh
```

Hiçbir şey değiştirmez. Çıktı kimlik taşımaz (IP, token, tam hostname,
e-posta, proses listesi, GPU UUID yok), doğrudan issue'ya yapıştırılabilir.

*Kabul:* dağıtım ve çekirdek okunabiliyor, systemd çalışıyor. Sürücü henüz
kurulu değilse NVIDIA bölümündeki FAIL normaldir; 10. adımdan sonra tekrar
çalıştırılacak.

### 2. İlk geri dönüş noktası — henüz hasta verisi yokken

Bu noktayı **şimdi** al: makinede henüz MERGEN'e ait hiçbir veri yok, yani
snapshot'ın kapsamı tartışmasız temiz.

- Btrfs + snapper: `sudo snapper -c root create -d "MERGEN G1 öncesi"`
- Btrfs elle: `sudo btrfs subvolume snapshot -r / /.snapshots/pre-mergen`
- LVM: `sudo lvcreate -s -L 20G -n pre-mergen <vg>/<kök-lv>`
- Hiçbiri yoksa: `/etc/passwd`, `/etc/group`, `/etc/shadow`, `/etc/sudoers.d/`,
  `/etc/systemd/system/` ve `/usr/lib/{sysusers,tmpfiles}.d/` dizinlerini
  tarihli bir arşive al.

Geri yükleme adımını yaz ve **bir kez prova et**. Prova edilmemiş rollback,
rollback değildir.

*Kabul:* geri dönüş noktası mevcut, geri yükleme komutu yazılı, prova edildi.

### 3. Runtime için ayrı LV / subvolume / mount oluştur

Henüz hiçbir MERGEN hesabı veya dizini yok. Önce boş bir mount noktası aç,
sonra runtime'a kendi depolamasını ver.

**Btrfs:**

```bash
sudo mkdir -p /var/lib/mergen
sudo btrfs subvolume create /var/lib/mergen/runtime
# /etc/fstab, subvol adını kendi düzenine göre yaz:
# UUID=<kök-uuid>  /var/lib/mergen/runtime  btrfs  subvol=@mergen-runtime,noatime  0 0
sudo mount /var/lib/mergen/runtime
```

Yalnız iç içe (nested) subvolume bırakmak yeterli değildir: `btrfs subvolume
snapshot` varsayılan olarak özyinelemeli değildir ama birçok yedekleme aracı
ağacı kendisi gezer. Ayrıca mount et.

**ext4 / LVM:**

```bash
sudo lvcreate -L 64G -n mergen-runtime <vg-adı>
sudo mkfs.ext4 /dev/<vg-adı>/mergen-runtime
sudo mkdir -p /var/lib/mergen/runtime
# /etc/fstab:
# /dev/<vg-adı>/mergen-runtime  /var/lib/mergen/runtime  ext4  defaults,noatime  0 2
sudo mount /var/lib/mergen/runtime
```

Loop device ile "ayrı cihaz" görüntüsü yaratma: backing dosyası kök dosya
sistemindeyse snapshot her şeyi yine alır. Script bunu yakalar ve FAIL verir.

### 4. Snapshot kapsamını doğrula

```bash
bash infra/gpu-host/check-snapshot-layout.sh
```

Script kanıtlamaya çalışır: `/var/lib/mergen/runtime` kök snapshot'ına
**giremez**. Kanıtlayamazsa FAIL verir, sessizce başarılı olmaz.

*Kabul:* PASS. WARN görüyorsan (örneğin mount edilmemiş nested subvolume)
3. adıma dön.

### 5. Yedekleme aracına açık dışlama ekle ve prova et

Mount sınırı dosya düzeyinde çalışan araçları durdurmaz. Kullandığın araca
runtime yolunu **açıkça** dışla:

| Araç | Dışlama |
|---|---|
| restic | `--exclude /var/lib/mergen/runtime` (veya `--exclude-file`) |
| borg | `--exclude /var/lib/mergen/runtime` |
| timeshift | GUI'de "Exclude" listesine ekle |
| snapper | Runtime ayrı subvolume ve snapper config'e dahil değil — doğrula |
| rsync | `--exclude 'var/lib/mergen/runtime/***'` |

**Provası:** runtime içine tanınabilir bir işaret dosyası koy, bir yedek al,
yedeğin içeriğini listele ve işaretin **bulunmadığını** gör.

```bash
sudo install -d -m 2770 /var/lib/mergen/runtime
echo 'exclusion-drill' | sudo tee /var/lib/mergen/runtime/DRILL >/dev/null
# ... yedeği al, sonra içeriği listele ...
sudo rm /var/lib/mergen/runtime/DRILL
```

*Kabul:* yedeğin dosya listesinde runtime yolu geçmiyor.

### 6. Hesap, grup ve dizin tabanı

Artık veri kapsamı kararlı; hesapları kurabiliriz.

```bash
bash infra/gpu-host/install-base.sh            # önce plan; hiçbir şey değişmez
sudo bash infra/gpu-host/install-base.sh --apply
```

Ne yapar: `mergen-svc` grubu ile `mergen-dispatcher` ve `mergen-executor`
hesaplarını `systemd-sysusers` ile (yalnız kendi conf dosyasını uygulayarak),
`mergen` bakım hesabını `useradd --create-home --shell /bin/bash` ile açar ve
**parolasını kilitler**, dizinleri `systemd-tmpfiles` ile oluşturur, iki env
dosyasını boş örneklerden tohumlar.

Ne yapmaz: sürücü, CUDA, PyTorch, model ağırlığı indirmez; Tailscale'e giriş
yapmaz; sır üretmez; servis başlatmaz; hiçbir şey silmez.

> Runtime ayrı mount ise 3. adımda zaten mount edildi. Edilmediyse tmpfiles
> mount altında kalacak boş bir dizin oluşturur.

Mevcut bir `mergen` hesabı varsa script onu değiştirmez ama home dizinini ve
login shell'ini doğrular; kullanılamaz durumdaysa açık hatayla durur.

*Kabul:* ikinci çalıştırma hata vermiyor ve hiçbir şeyi değiştirmiyor.

### 7. İkinci denetim

```bash
bash infra/gpu-host/audit-host.sh
```

*Kabul:* hesap ve dizin bölümlerinde FAIL yok; runtime dizini setgid raporlanıyor.

### 8. Bakım hesabı için dar sudo

[`sudoers.d/mergen-maintenance.example`](../infra/gpu-host/sudoers.d/mergen-maintenance.example)
dosyasını oku, ikili yolları `command -v` ile doğrula, sonra:

```bash
sudo visudo -cf infra/gpu-host/sudoers.d/mergen-maintenance.example
sudo install -m 440 -o root -g root \
    infra/gpu-host/sudoers.d/mergen-maintenance.example \
    /etc/sudoers.d/mergen-maintenance
```

**Neden NOPASSWD?** `mergen` hesabının parolası kilitli — kimse onunla
doğrudan giriş yapamaz, sen `sudo -u mergen -i` ile geçersin. Kilitli parola
sudo'nun kendi sorusunu **karşılayamaz**; parola isteyen bir kural hiç
çalışmazdı. Bu yüzden bariyer parola değil, komut listesidir: her satır sabit
argümanlı sabit bir komut, listede shell, editör, paket yöneticisi veya serbest
`systemctl` yok.

İki kural açık bırakılırsa dar yetki root shell'e dönüşür, ikisi de dosyada
uygulanıyor: komutlarda joker (`*`) yok, ve sayfalayıcı çalıştırabilen her
komut `--no-pager` ile sabitlenmiş.

`mergen` hesabına gerçek parola vermeyi tercih edersen NOPASSWD'yi kaldır ve
doğrudan giriş yüzeyini (SSH, display manager) ayrıca kapat — ve bunu test et.

*Kabul:*

```bash
sudo -l -U mergen                 # yalnız dört alias, hepsi NOPASSWD
sudo -u mergen -i -- sudo -n systemctl --no-pager is-active mergen-executor.service
```

İkinci komut parola sormadan çalışmalı (servis henüz yoksa "inactive" der; önemli
olan yetkinin işlemesi).

### 9. Yetkisiz servis hesaplarının doğrulaması

```bash
getent passwd mergen-dispatcher mergen-executor   # shell nologin olmalı
sudo -l -U mergen-dispatcher                      # "not allowed" demeli
sudo -l -U mergen-executor                        # "not allowed" demeli
id mergen-dispatcher; id mergen-executor          # ikisi de mergen-svc üyesi
```

### 10. Tailscale kaydı

Bu adımı **sen** yaparsın; script Tailscale hesabına giriş yapmaz.
Ayrıntı ve politika: [`infra/tailscale/README.md`](../infra/tailscale/README.md).

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up --advertise-tags=tag:mergen-gpu --accept-dns=false
```

Etiketi unutma: etiketsiz node 180 günde sessizce düşer. `--accept-dns=false`
bilinçli; backend MagicDNS adı değil 100.x adresi kullanır.

*Kabul:* `tailscale status` node'u `tag:mergen-gpu` ile gösteriyor; konsolda
key expiry kapalı. Adresi hiçbir repo dosyasına yazma.

### 11. NVIDIA sürücüsü

Dağıtımın **resmi** yöntemini kullan. Sürücü sürümü hızlı değişiyor; bu belge
sabit sürüm yazmaz, çünkü yazsa birkaç ay içinde yanlış olur.

- Ubuntu: `ubuntu-drivers devices` çıktısına bak, önerilen sürücüyü
  `sudo ubuntu-drivers install` ile kur. `.run` dosyası kullanma.
- CachyOS / Arch: depodaki `nvidia-open-dkms` veya `nvidia-dkms` paketini
  çekirdeğine uygun başlıklarla kur. AUR'dan elle sürücü derleme.

Kurulumdan sonra **yeniden başlat**, sonra `nvidia-smi`.

*Kabul:* `nvidia-smi` GPU adını ve sürücü sürümünü yazıyor.

> Bu adım kullanıcının masaüstü oturumunu etkiler. Sahibi makinede
> çalışırken yapma.

### 12. Görüntü model ortamı

Görüntü bağımlılıklarını ayrı ve kilitli bir venv'de tut.

```bash
sudo -u mergen python3 -m venv /srv/mergen-models/venv/imaging
```

Yolu `/etc/mergen/executor.env` içindeki `MERGEN_IMAGING_VENV` alanına yaz.

### 13. CUDA uyumlu PyTorch

Önce **PyTorch wheel'ının içindeki CUDA runtime'ıyla** dene. Tam CUDA Toolkit
(`nvcc`) kurma; bir modelin gerçekten kaynak derlemesi gerektiği kanıtlanana
kadar gereksiz yüzlerce megabayt ve bir sürüm çakışması kaynağıdır.

```bash
/srv/mergen-models/venv/imaging/bin/pip install torch --index-url <pytorch-cuda-index>
```

Doğru index URL'sini kurulum anında pytorch.org'dan al; CUDA sürümüne göre
değişir ve burada sabitlemek yanlış olur.

**`nvcc` ne zaman gerekir?** Yalnız bir paket kurulum sırasında CUDA kaynağı
derliyorsa. Belirtisi açıktır: `pip install` sırasında `nvcc: command not
found` veya `CUDA_HOME` hatası. O zaman toolkit'i kur ve **neden gerektiğini
bu belgeye yaz**.

### 14. GPU doğrulaması

Görüntü ortamı için:

```bash
bash infra/gpu-host/verify-gpu-runtime.sh /srv/mergen-models/venv/imaging
```

Script ayrı ayrı doğrular: `nvidia-smi` yanıtı, venv Python'u, `torch` importu,
wheel'ın CUDA runtime'ı, `torch.cuda.is_available()`, cihaz sayısı, toplam
VRAM ve CPU → GPU → matmul → CPU turu. Hiçbir paket kurmaz, GPU UUID
yazdırmaz.

*Kabul:* görüntü venv'inde FAIL yok.

### 15. Modellerin yerleşimi

Ağırlıklar Git'te değildir ve olmayacaktır
([`LOCAL_ASSETS.md`](LOCAL_ASSETS.md)). `/srv/mergen-models` altına sürümlü
yerleştir ve checksum kaydet:

```
/srv/mergen-models/
  imaging/nnunet/<sürüm>/...
  imaging/swinunetr/<sürüm>/...
  MANIFEST.sha256
```

Dizin `mergen:mergen-svc` 0750'dir: servisler okur, yalnız bakım hesabı yazar.
Executor bir ağırlığı kullanmadan önce checksum'ı doğrulamalıdır (G4 işi);
manifest'i şimdi üret ki o doğrulamanın karşılaştıracağı bir referans olsun.

### 16. Servis staging'i ve release geçişi (başlatmadan)

`install-base.sh` hesapları, dizinleri ve env dosyalarını kurduktan sonra dispatcher
(`mergen_dispatcher`, G2) ve executor (`mergen_executor`, G3) tek bir sürümlü
release olarak kurulur. Unit örnekleri bu düzeni bekler:

```
/opt/mergen/releases/<sürüm>/src/         backend/archive_io.py, backend/live_contracts.py,
                                          mergen_spool/, mergen_dispatcher/, mergen_executor/
/opt/mergen/releases/<sürüm>/units/       bu release'in iki unit dosyası
/opt/mergen/releases/<sürüm>/dispatcher/  venv: yalnız mergen_dispatcher/requirements.txt
/opt/mergen/releases/<sürüm>/executor/    venv: yalnız mergen_executor/requirements.txt
/opt/mergen/releases/<sürüm>/*.freeze     pip'in her venv'e gerçekten kurduğu paketler
/opt/mergen/releases/<sürüm>/MANIFEST.sha256, RELEASE (en son yazılır)
/opt/mergen/current -> releases/<sürüm>
```

Release `root:root`'tur ve servis hesapları onu değiştiremez. Görüntü model ortamı
(`MERGEN_IMAGING_VENV`, 12. adım) bu ağacın dışındadır; iki servis venv'ine model
paketi kurulmaz ve executor venv'inde HTTP istemcisi bulunmaz.

Bakım hesabıyla, incelenmiş bir depo kopyasından:

```bash
bash infra/gpu-host/verify-services.sh --before                       # salt okunur
bash infra/gpu-host/stage-services.sh --version "$(git rev-parse --short=12 HEAD)"   # plan
sudo bash infra/gpu-host/stage-services.sh --version <sürüm> --apply
sudo bash infra/gpu-host/verify-services.sh --after                   # salt okunur
```

Plan hiçbir dosyayı değiştirmez. `--apply` yalnız root ile çalışır ve sırayla:
önkoşulları doğrular (hesaplar, gruplar, dizin modları, env dosyaları, çalışan servis
yok), release'i kendi adıyla kurar, iki venv'i ayrı ayrı oluşturur, release'i
doğrular (importlar, bağımlılık ayrımı, gate sürümü, `systemd-analyze verify`),
eksik env dosyasını örnekten tohumlar, eksik unit'i kurar ve en sonda `current`'ı
geçici bir link ve tek `rename` ile yeni release'e çevirir. Bu adımdan önceki her
hata yarım release'i siler; `current` değişmez. Aynı sürümle ikinci çalıştırma
hiçbir şeyi değiştirmez.

Hiçbir zaman: mevcut bir release'i, env dosyasını veya farklı içerikli bir unit'i
ezer; servis `enable`/`start`/`restart` eder ya da `daemon-reload` çalıştırır;
sürücü, CUDA, Tailscale veya model paketi kurar; bir release'i siler; env değeri
yazdırır. Farklı bir unit bulunursa betik durur; unit elle incelenip kenara alınır.
İki unit için hiçbir drop-in kabul edilmez: ne `mergen-*.service.d/*.conf` ne de
systemd'nin bütün servislere uyguladığı genel `service.d/*.conf`, arama yolundaki
hiçbir dizinde. Drop-in unit dosyasına dokunmadan ortamı, ağı veya cihazları
değiştirebilir. Bulunursa `verify-services.sh` ve `--apply` yalnız dosya yolunu
gösterip durur ve hiçbir şeyi değiştirmez; genel `service.d` drop-in'leri de
reddedilir. Dağıtımın kendi koyduğu bir drop-in de güvenli sayılmaz: host
yöneticisi onu kaldırır. MERGEN servislerini böyle bir dosyadan koruyan, ayrıca
doğrulanan bir yol tasarlanana kadar bu kural geçerlidir.

Env dosyalarında elle doldurulacak alanlar yalnız adlarıyla: `dispatcher.env`
içinde `MERGEN_CONTROL_URL`, `MERGEN_WORKER_TOKEN`, `MERGEN_WORKER_ID`. Executor
env'i G3 için örnekteki değerlerle çalışır; GPU eşikleri ve `MERGEN_IMAGING_VENV`
G4'tedir. `verify-services.sh --after` doğrulanmayan ayarı yalnız adıyla gösterir.

Dispatcher ile executor aynı `current/src`'den aynı `mergen_spool` gate sürümünü
yükler; biri tek başına güncellenemez. Gate sürümü release'ler arasında değişirse
iki servis birlikte yeniden başlatılır; eski dispatcher'ın spool'da bıraktığı işleri
yeni executor `failed/internal-error` yapar. Betik bu değişimi ve etkilenen iş
sayısını raporlar.

**Rollback** yalnız `current` bağlantısını önceki release'e çevirmektir; hiçbir
release veya veri silinmez:

```bash
sudo ln -s releases/<önceki-sürüm> /opt/mergen/.current.rollback
sudo mv -T /opt/mergen/.current.rollback /opt/mergen/current
sudo bash infra/gpu-host/verify-services.sh --after
```

`ln -sfn` kullanma: eski bağlantıyı silip yenisini yazar, arada `current` yoktur.
Servisler çalışıyorsa önce durdurulur, geçişten sonra birlikte başlatılır.

İki servis de G4'ten önce `enable` edilmez. G3 sürümünde gerçek görüntü adaptörü yoktur:
executor `executor.json`'a hiçbir yetenek yazmaz, dispatcher da bu yüzden VPS'e
yetenek bildirmez ve iş almaz. Executor unit'i ağ ve GPU cihazı açmaz; NVIDIA cihaz
izinleri G4 adaptörüyle eklenir. G3'te adaptör executor sürecinin içinde çalışır ve
unit onu executor'dan ayırmaz; gerçek adaptör, ayrı süreç/venv, süreç grubu
sonlandırma ve yalnız `work/output`'a yazma sınırı
([`mergen_executor/README.md`](../mergen_executor/README.md)) sağlanmadan
etkinleştirilmez. Şu an başlatılması gereken tek servis `tailscaled`.

### 17. Pause, bakım ve rollback

**Pause.** Executor yeni iş almasın ama servis ayakta kalsın:

```bash
sudo -u mergen-executor touch /var/lib/mergen/executor/pause
```

Dosya varken çalışan iş bitirilir, yenisi başlatılmaz ve `executor.json`
`acceptingJobs=false` der; dispatcher da yeni iş almaz. Devam için dosyayı sil.
Alternatif `sudo systemctl stop mergen-executor.service`; fark şu ki durdurma
çalışan işi `failed/internal-error` ile bitirir, pause dosyası ise yarıda kesmez.

**Bakım.** Sürücü güncellemesi, çekirdek güncellemesi veya ağır oyun
oturumundan önce pause koy. Güncelleme sonrası 14. adımı tekrar çalıştır.

**Rollback.** 2. adımdaki noktaya dön. Hesap ve dizin tabanını geri almak
için minimum sıra:

```bash
sudo systemctl disable --now mergen-dispatcher.service mergen-executor.service 2>/dev/null || true
sudo rm -f /etc/sudoers.d/mergen-maintenance
sudo rm -f /usr/lib/sysusers.d/mergen.conf /usr/lib/tmpfiles.d/mergen.conf
sudo userdel mergen-dispatcher; sudo userdel mergen-executor
sudo groupdel mergen-svc
```

Dizinleri **silmeden önce** içeriğe bak: `/srv/mergen-models` altında saatler
süren indirmeler olabilir. Runtime dizinini boşaltmak ise istenen davranıştır.

### 18. Snapshot periyodu ve veri kapsamı

- Snapshot **kök** için alınır; runtime asla kapsama girmez (3.–5. adımlar).
- Sürücü/çekirdek güncellemesinden önce bir snapshot al.
- Model ağırlıkları büyüktür ve yeniden indirilebilir; snapshot yerine
  `MANIFEST.sha256` + indirme kaynağı yeterlidir.
- `/etc/mergen/*.env` içinde token vardır. Yedeklenecekse şifrelenmiş bir
  kasaya; düz yedeğe **hayır**.
- Saklama süresi kısa tut. Silinen dosyanın SSD'de fiziksel olarak
  kurtarılamaz hale geldiği garanti değildir; disk şifreleme, kısa saklama ve
  runtime'ı yedek dışında tutmak birlikte çalışır.

### 19. Host günlük kullanımdayken GPU işi kuralları

Makine sahibinin işi önceliklidir. Uygulanacak davranış:

| Kural | Nasıl |
|---|---|
| Tek iş | `flock` ile `MERGEN_GPU_LOCK_PATH`; ikinci iş kilidi bekler |
| Meşgul GPU'da bekle | `MERGEN_GPU_MAX_MEMORY_USED_MB` ve `MERGEN_GPU_MAX_UTILIZATION_PERCENT` eşikleri aşılıyorsa iş ertelenir |
| Kullanıcı prosesini öldürme | Hiçbir kod yolu `kill`/`pkill` çağırmaz; yalnız bekler |
| Yeniden deneme aralığı | `MERGEN_GPU_WAIT_SECONDS` |
| Dispatcher davranışı | GPU meşgulken yeni ağır iş claim edilmez; claim edilmişse lease yenilenerek ertelenir |
| CPU ve RAM sınırı | systemd `Nice`, `CPUWeight`, `IOWeight`, `MemoryMax` (unit örneklerinde) |
| Pause | 17. adımdaki pause dosyası |

Eşikler `executor.env` içinde **boş** gelir. Bu kasıtlı: doğru değer GPU'nun
VRAM'ine ve sahibinin kullanım alışkanlığına bağlıdır, tahmin edilmiş bir
varsayılan sessizce yanlış davranır.

**Tüketici NVIDIA GPU'sunda güvenilir bir yüzde kotası yoktur.** MPS ve MIG bu
sınıf kartlarda kullanılabilir değildir; cgroup'lar VRAM'i bölmez. Bu yüzden
kabul kontrolü ya hep ya hiçtir: iş ya GPU'yu yeterince boş bulur ve çalışır,
ya da bekler. systemd sınırları yalnız CPU, IO ve sistem RAM'i içindir.

---

## Ubuntu ile CachyOS/Arch farkları

Yalnız gerçekten değişen komutlar:

| Konu | Ubuntu / Debian | CachyOS / Arch |
|---|---|---|
| Sürücü | `ubuntu-drivers install` | `pacman -S nvidia-open-dkms` (veya `nvidia-dkms`) + uygun kernel headers |
| Paket yöneticisi | `apt-get` | `pacman` |
| `nologin` yolu | `/usr/sbin/nologin` | `/usr/bin/nologin` — `/usr/sbin` `/usr/bin`'e symlink olduğu için sysusers dosyasındaki yol iki dağıtımda da çözülür |
| Btrfs varsayılanı | Genelde ext4 | CachyOS kurulumlarında Btrfs + snapper sık |
| `sudo` ikili yolu | `/usr/bin/systemctl` | `/usr/bin/systemctl` (aynı, yine de `command -v` ile doğrula) |

`systemd-sysusers` ve `systemd-tmpfiles` her ikisinde de aynıdır; sözleşmeyi
bu yüzden deklaratif tuttuk.

Bu belge tek bir dağıtım varsaymaz: `audit-host.sh` önce ölçer,
`install-base.sh` tanımadığı bir dağıtımda tahmin yürütmek yerine açık hatayla
durur.

---

## Bu katmanda henüz kanıtlanmamış olanlar

Aşağıdakiler gerçek makinede doğrulanana kadar
[Issue #20](https://github.com/AbdullahZeynel/MERGEN/issues/20) kapanmaz:

- Kurulum öncesi geri dönüş noktası ve **prova edilmiş** geri yükleme
- Runtime'ın snapshot kapsamı dışında olduğunun ölçülmesi
- Gerçek hesapların ve izinlerin oluşturulması
- Tailscale bağlantısı ve etiketli node
- NVIDIA sürücüsü
- İki venv'de CUDA'lı PyTorch
- Gerçek GPU tensor smoke testi
- Yeniden başlatma sonrası Tailscale ve GPU doğrulamasının tekrarı

Repo tarafında hazır olan şey yalnız bu adımları güvenli ve tekrarlanabilir
biçimde yürütecek scriptler, deklaratif yapılandırma ve bu sıradır.
