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
| `/opt/mergen` | `root:mergen` | 0755 | Sürümlü uygulama ve runtime kodu |
| `/srv/mergen-models` | `mergen:mergen-svc` | 0750 | Sürümlü, checksum'lı model ağırlıkları |
| `/var/lib/mergen/dispatcher` | `mergen-dispatcher:mergen-dispatcher` | 0700 | Dispatcher durumu |
| `/var/lib/mergen/executor` | `mergen-executor:mergen-executor` | 0700 | Executor durumu, kilit ve pause dosyası |
| `/var/lib/mergen/runtime` | `mergen-dispatcher:mergen-executor` | 0750 | Geçici iş paketleri — **yedek dışı** |
| `/etc/mergen` | `root:root` | 0751 | Git dışı env dosyaları |
| `/etc/mergen/dispatcher.env` | `root:mergen-dispatcher` | 0640 | VPS adresi ve worker token'ı |
| `/etc/mergen/executor.env` | `root:mergen-executor` | 0640 | Model yolları ve GPU eşikleri; **token yok** |

| Hesap | Tür | Shell | Sudo |
|---|---|---|---|
| `mergen` | İnsan bakım hesabı, home'lu | `/bin/bash` | Yalnız dar liste (aşağıda) |
| `mergen-dispatcher` | Sistem hesabı | `nologin` | Yok |
| `mergen-executor` | Sistem hesabı | `nologin` | Yok |
| `mergen-svc` | Grup | — | Model ağacını okumak için ortak grup |

Runtime dizini 0750'dir: dispatcher iş dizinlerini oluşturur, executor grup
üzerinden içeri girer, **makinedeki diğer insan kullanıcılar hiçbir şey
göremez**. Executor üst düzeyde yeni iş dizini açamaz; bu kasıtlı.

`/etc/mergen/dispatcher.env` dosyasının 0640 olması systemd'ye karşı koruma
değildir — systemd `EnvironmentFile`'ı yetki düşmeden önce root olarak okur.
Koruma **diğer hesaplara** karşıdır, `mergen-executor` dahil.

---

## Sıra

Her adımın kabul ölçütü sağlanmadan sonrakine geçilmez.

### 1. Kurulum öncesi salt okunur denetim

Hiçbir şey değiştirmeden envanteri çıkar:

```bash
bash infra/gpu-host/audit-host.sh
```

Çıktı kimlik taşımaz (IP, token, tam hostname, e-posta, proses listesi, GPU
UUID yok), doğrudan issue'ya yapıştırılabilir.

*Kabul:* dağıtım ve çekirdek okunabiliyor, systemd çalışıyor, NVIDIA cihaz
düğümü ve sürücü görünüyor, `nvidia-smi` yanıt veriyor.

Sürücü henüz kurulu değilse burada FAIL görmek normaldir; 8. adımdan sonra
tekrar çalıştır.

### 2. Dosya sistemi ve snapshot kapsamı kararı

Bu, geri kalan her şeyden önce gelir. Runtime dizini kök snapshot'una
giriyorsa hasta girdisi ve sonuçlar farkında olmadan yedeklere taşınır.

```bash
bash infra/gpu-host/check-snapshot-layout.sh
```

Script şunu kanıtlamaya çalışır: `/var/lib/mergen/runtime` kök dosya
sisteminin snapshot'ına **giremez**. Kanıtlayamazsa FAIL verir; sessizce
başarılı olmaz.

**Btrfs.** Runtime'ı ayrı bir subvolume yap ve `/etc/fstab` üzerinden ayrıca
mount et:

```bash
sudo btrfs subvolume create /var/lib/mergen/runtime
# fstab satırı, subvol adını kendi düzenine göre yaz:
# UUID=<kök-uuid>  /var/lib/mergen/runtime  btrfs  subvol=@mergen-runtime,noatime  0 0
```

Yalnız iç içe (nested) subvolume bırakmak yeterli değildir: `btrfs subvolume
snapshot` varsayılan olarak özyinelemeli değildir ama birçok yedekleme aracı
ağacı kendisi gezer. Script bu durumda WARN verir; kullandığın aracı
gerçekten ölç.

**ext4 / LVM.** Runtime kök ile aynı logical volume'daysa güvenli değildir.
Ayrı bir LV veya bölüm ver:

```bash
sudo lvcreate -L 64G -n mergen-runtime <vg-adı>
sudo mkfs.ext4 /dev/<vg-adı>/mergen-runtime
# fstab: /dev/<vg-adı>/mergen-runtime  /var/lib/mergen/runtime  ext4  defaults,noatime  0 2
```

**Her düzende:** mount sınırı dosya düzeyinde çalışan yedekleme araçlarını
durdurmaz. Kullandığın araca (`restic`, `borg`, `timeshift`, `snapper`,
`rsync`) runtime yolunu **açıkça dışla**. Script bunu hatırlatır ama senin
yerine yapamaz.

*Kabul:* `check-snapshot-layout.sh` PASS veriyor **ve** yedekleme aracının
dışlama listesine runtime yolu yazıldı.

### 3. İlk geri dönüş noktası

Hiçbir hesap veya dizin oluşturmadan önce geri dönülebilir bir nokta al.
Komutu dağıtımına göre seç; bu script otomatik snapshot **almaz**, çünkü
kapsamı doğrulanmamış bir snapshot yanlış güven verir.

- Btrfs + snapper: `sudo snapper -c root create -d "MERGEN G1 öncesi"`
- Btrfs elle: `sudo btrfs subvolume snapshot -r / /.snapshots/pre-mergen`
- LVM: `sudo lvcreate -s -L 20G -n pre-mergen <vg>/<kök-lv>`
- Hiçbiri yoksa: `/etc/passwd`, `/etc/group`, `/etc/shadow`, `/etc/sudoers.d/`
  ve `/etc/systemd/system/` dizinlerini tarihli bir arşive al.

Geri yükleme adımını **şimdi** yaz ve bir kez prova et. Prova edilmemiş
rollback, rollback değildir.

*Kabul:* geri dönüş noktası mevcut, geri yükleme komutu yazılı, prova edildi.

### 4. `mergen` bakım hesabı

```bash
bash infra/gpu-host/install-base.sh            # önce plan; hiçbir şey değişmez
sudo bash infra/gpu-host/install-base.sh --apply
```

Hesap `--create-home --shell /bin/bash` ile açılır ve parolası **kilitlenir**:
kimse onunla doğrudan giriş yapamaz, sen `sudo -u mergen -i` ile geçersin.

Sudo bu adımda verilmez. [`sudoers.d/mergen-maintenance.example`](../infra/gpu-host/sudoers.d/mergen-maintenance.example)
dosyasını oku, yolları `command -v` ile doğrula, sonra:

```bash
sudo visudo -cf infra/gpu-host/sudoers.d/mergen-maintenance.example
sudo install -m 440 -o root -g root \
    infra/gpu-host/sudoers.d/mergen-maintenance.example \
    /etc/sudoers.d/mergen-maintenance
```

Örnekte iki kural var, ikisi de güvenlik açığı kapatıyor: komutlarda joker
(`*`) yok ve sayfalayıcı çalıştırabilen her komut `--no-pager` ile sabitlendi.
`journalctl -u unit *` yazarsan çağıran kişi bir sayfalayıcı seçeneği ekleyip
root shell'e çıkabilir.

*Kabul:* `sudo -l -U mergen` yalnız listelenen komutları gösteriyor; parola
soruluyor.

### 5. Yetkisiz dispatcher ve executor hesapları

Aynı `install-base.sh --apply` çağrısı bunları `systemd-sysusers` ile
oluşturur. İkinci çalıştırma hiçbir şeyi bozmaz.

*Kabul:*

```bash
getent passwd mergen-dispatcher mergen-executor   # shell nologin olmalı
sudo -l -U mergen-dispatcher                      # "not allowed" demeli
```

### 6. Dizin ve izin tabanı

`systemd-tmpfiles` dizinleri yukarıdaki tabloya göre oluşturur ve modları
düzeltir. Hiçbir satır silme yapmaz.

> Runtime ayrı mount/subvolume ise **önce mount et**, sonra tmpfiles uygula.
> Aksi halde oluşturulan dizin sonraki mount tarafından gizlenir.

*Kabul:* `bash infra/gpu-host/audit-host.sh` dizin bölümünde FAIL yok.

### 7. Tailscale kaydı

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

### 8. NVIDIA sürücüsü

Dağıtımın **resmi** yöntemini kullan. Sürücü sürümü hızlı değişiyor; bu belge
sabit sürüm yazmaz, çünkü yazsa birkaç ay içinde yanlış olur.

- Ubuntu: `ubuntu-drivers devices` çıktısına bak, önerilen sürücüyü
  `sudo ubuntu-drivers install` ile kur. `.run` dosyası kullanma.
- CachyOS / Arch: depodaki `nvidia-open-dkms` veya `nvidia-dkms` paketini
  çekirdeğine uygun başlıklarla kur. AUR'dan elle sürücü derleme.

Kurulumdan sonra **yeniden başlat**, sonra:

```bash
nvidia-smi
```

*Kabul:* `nvidia-smi` GPU adını ve sürücü sürümünü yazıyor.

> Bu adım kullanıcının masaüstü oturumunu etkiler. Sahibi makinede
> çalışırken yapma.

### 9. İki ayrı model venv'i

Görüntü ve genomik bağımlılıkları çakışır (farklı `torch`, `monai`,
`transformers` sürümleri). Tek venv'de birleştirme.

```bash
sudo -u mergen python3 -m venv /srv/mergen-models/venv/imaging
sudo -u mergen python3 -m venv /srv/mergen-models/venv/genomics
```

Yolları `/etc/mergen/executor.env` içindeki `MERGEN_IMAGING_VENV` ve
`MERGEN_GENOMICS_VENV` alanlarına yaz.

### 10. CUDA uyumlu PyTorch

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

### 11. GPU doğrulaması

Her venv için ayrı ayrı:

```bash
bash infra/gpu-host/verify-gpu-runtime.sh /srv/mergen-models/venv/imaging
bash infra/gpu-host/verify-gpu-runtime.sh /srv/mergen-models/venv/genomics
```

Script ayrı ayrı doğrular: `nvidia-smi` yanıtı, venv Python'u, `torch` importu,
wheel'ın CUDA runtime'ı, `torch.cuda.is_available()`, cihaz sayısı, toplam
VRAM ve CPU → GPU → matmul → CPU turu. Hiçbir paket kurmaz, GPU UUID
yazdırmaz.

*Kabul:* iki venv'de de FAIL yok.

### 12. Modellerin yerleşimi

Ağırlıklar Git'te değildir ve olmayacaktır
([`LOCAL_ASSETS.md`](LOCAL_ASSETS.md)). `/srv/mergen-models` altına sürümlü
yerleştir ve checksum kaydet:

```
/srv/mergen-models/
  imaging/nnunet/<sürüm>/...
  imaging/swinunetr/<sürüm>/...
  genomics/xgboost/<sürüm>/...
  genomics/esm2/<revision>/...
  MANIFEST.sha256
```

Dizin `mergen:mergen-svc` 0750'dir: servisler okur, yalnız bakım hesabı yazar.
Executor bir ağırlığı kullanmadan önce checksum'ı doğrulamalıdır (G4 işi);
manifest'i şimdi üret ki o doğrulamanın karşılaştıracağı bir referans olsun.

### 13. Hangi servisler henüz başlatılmaz

`infra/gpu-host/systemd/` altındaki iki unit **`.example`** uzantılıdır ve
`install-base.sh` onları kurmaz. Dispatcher (G2) ve executor (G3) kodu
yazılmadan `mergen-dispatcher.service` veya `mergen-executor.service`
`enable` edilmez. Şu an başlatılması gereken tek servis `tailscaled`.

### 14. Pause, bakım ve rollback

**Pause.** Executor yeni iş almasın ama servis ayakta kalsın:

```bash
sudo -u mergen-executor touch /var/lib/mergen/executor/pause
```

Dosya varken çalışan iş bitirilir, yenisi başlatılmaz. Devam:

```bash
sudo rm /var/lib/mergen/executor/pause
```

Alternatif olarak `sudo systemctl stop mergen-executor.service`; fark şu ki
pause dosyası devam eden işi yarıda kesmez.

**Bakım.** Sürücü güncellemesi, çekirdek güncellemesi veya ağır oyun
oturumundan önce pause koy. Güncelleme sonrası 11. adımı tekrar çalıştır.

**Rollback.** 3. adımdaki noktaya dön. Hesap ve dizin tabanını geri almak
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

### 15. Snapshot periyodu ve veri kapsamı

- Snapshot **kök** için alınır; runtime asla kapsama girmez (2. adım).
- Sürücü/çekirdek güncellemesinden önce bir snapshot al.
- Model ağırlıkları büyüktür ve yeniden indirilebilir; snapshot yerine
  `MANIFEST.sha256` + indirme kaynağı yeterlidir. İstersen ayrı, seyrek
  yedekle.
- `/etc/mergen/*.env` içinde token vardır. Yedeklenecekse şifrelenmiş bir
  kasaya; düz yedeğe **hayır**.
- Saklama süresi kısa tut. Silinen dosyanın SSD'de fiziksel olarak
  kurtarılamaz hale geldiği garanti değildir; disk şifreleme, kısa saklama ve
  runtime'ı yedek dışında tutmak birlikte çalışır.

### 16. Host günlük kullanımdayken GPU işi kuralları

Makine sahibinin işi önceliklidir. Uygulanacak davranış:

| Kural | Nasıl |
|---|---|
| Tek iş | `flock` ile `MERGEN_GPU_LOCK_PATH`; ikinci iş kilidi bekler |
| Meşgul GPU'da bekle | `MERGEN_GPU_MAX_MEMORY_USED_MB` ve `MERGEN_GPU_MAX_UTILIZATION_PERCENT` eşikleri aşılıyorsa iş ertelenir |
| Kullanıcı prosesini öldürme | Hiçbir kod yolu `kill`/`pkill` çağırmaz; yalnız bekler |
| Yeniden deneme aralığı | `MERGEN_GPU_WAIT_SECONDS` |
| Dispatcher davranışı | GPU meşgulken yeni ağır iş claim edilmez; claim edilmişse lease yenilenerek ertelenir |
| CPU ve RAM sınırı | systemd `Nice`, `CPUWeight`, `IOWeight`, `MemoryMax` (unit örneklerinde) |
| Pause | 14. adımdaki pause dosyası |

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
