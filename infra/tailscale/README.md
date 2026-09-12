# Tailscale — MERGEN özel ağ katmanı

Bu belge hazırlık niteliğindedir. Buradaki hiçbir komut gerçek bir makinede
çalıştırılmadı; adımlar sırayla uygulanacak ve her adımın kabul ölçütü
doğrulandıktan sonra bir sonrakine geçilecek. Tailscale konsolunun arayüzü
sürümle değişebilir; menü adı tutmazsa komut çıktısını esas al.

## 1. Bu katman ne işe yarıyor

`docs/PLAN.md` mimarisi şu:

```
Tarayıcı → Cloudflare → VPS/Caddy → backend → Tailscale → Ubuntu/model servisleri
```

Ağır modeller (nnU-Net, Swin UNETR, ESM-2/XGBoost) VPS'te değil, GPU'lu Ubuntu
makinesinde çalışacak. O makine ev/kampüs ağında, NAT arkasında ve muhtemelen
değişken IP'li. Tailscale'in çözdüğü tek problem bu: **VPS ile GPU makinesi
arasında, port yönlendirmesi ve halka açık IP olmadan, sabit adresli özel bir
bağlantı.**

Tailscale olmadan alternatifler: GPU makinesine port açmak (ev routerında
yönlendirme + dinamik DNS + doğrudan internete açık bir çıkarım servisi),
kendi WireGuard'ını kurup anahtarları elle dağıtmak, ya da modelleri VPS'e
taşımak (GPU maliyeti). Üçü de bu projede daha fazla iş ve daha fazla risk.

Not: Tailscale halka açık yayın için değil. Kullanıcıların gördüğü HTTPS
tarafı Caddy'de kalır; Tailscale yalnızca backend ile model servisleri
arasındaki iç bacaktır.

## 2. Başlamadan bilmen gerekenler

Bunları bilmeden kurulum yaparsan ilerideki adımlar tıkanır.

**Tailnet.** Hesabına bağlı özel ağ. Kişisel (ücretsiz) plan 3 kullanıcı ve
100 cihaz veriyor; bizim ihtiyacımız 2 cihaz.

**Node ve 100.x adresi.** Ağa katılan her makine `100.64.0.0/10` (CGNAT)
aralığından sabit bir adres alır. Makine yeniden başlasa, ev IP'si değişse,
başka bir ağa taşınsa bile bu adres değişmez. Backend yapılandırmasında
kullanacağımız adres budur.

**MagicDNS.** `<hostname>.<tailnet-adı>.ts.net` biçiminde isim çözümlemesi.
Kullanmak için sunucuda `--accept-dns=true` gerekir, o da `/etc/resolv.conf`
dosyasını Tailscale'e devreder. Sunucularda bunu istemiyoruz; **backend'e
GPU makinesinin 100.x adresini yazacağız**, isim değil. İsim çözümleme
sorununa hiç girmemiş oluruz.

**Etiket (tag).** Bir cihazı kişisel hesaba değil tailnet'e ait kılar.
Sunucular için doğru yol budur, üç nedenle: erişim kurallarını hostname yerine
role göre yazarsın; hesabından çıkman cihazı düşürmez; **etiketli cihazlarda
anahtar süresi varsayılan olarak devre dışıdır**. Etiketsiz bir node 180 günde
süresi dolup sessizce ağdan düşer — sunumdan bir hafta önce bunun olması
istemediğimiz senaryo. (Yine de konsolda cihazın "Key expiry" alanını gözle
doğrula.)

**ACL.** Tailnet'teki erişim politikası, HuJSON formatında tek dosya. Yeni bir
tailnet **varsayılan olarak her cihazın her cihaza erişmesine izin verir**;
ilk işlerden biri bunu daraltmak. Politika hedef node üzerinde uygulanır, yani
servis dinlese bile ACL izin vermiyorsa bağlantı kurulamaz.

**Auth key.** Makineyi tarayıcıda oturum açmadan ağa katmak için tek seferlik
anahtar. Etiketli olarak üretilir. Anahtarın kendi ömrü (en fazla 90 gün)
yalnızca katılma anında geçerlidir; node katıldıktan sonra anahtarın süresi
dolması bağlantıyı koparmaz. Otomasyon büyürse OAuth client daha doğru yol
ama şu ölçekte gereksiz.

**Direct vs DERP.** İki node önce doğrudan bağlanmayı dener (UDP, genelde
41641). Ağ buna izin vermezse trafik Tailscale'in DERP röleleri üzerinden
TCP/443 ile akar — çalışır ama gecikme ve bant genişliği düşer. Hangisinde
olduğunu `tailscale ping` söyler. Kampüs/kurum ağında DERP'e düşme ihtimali
yüksek.

**Güven modeli.** Trafik uçtan uca WireGuard ile şifreli; Tailscale'in
koordinasyon sunucusu genel anahtarları ve bağlantı metadata'sını görür,
içeriği görmez. DERP röleleri de yalnızca şifreli paket taşır.

**Veri tarafı.** Bu bacaktan yalnızca UCSF-PDGM gibi kamuya açık,
kimliksizleştirilmiş veri geçecek. Gerçek hasta verisi bu prototipin
kapsamında değil.

## 3. Karar noktaları

Kuruluma başlamadan bunlar netleşmeli; her biri sonraki adımların içeriğini
değiştiriyor.

| # | Karar | Neden önemli |
|---|---|---|
| D1 | VPS var mı, hangi sağlayıcı ve dağıtım? | Konteyner tabanlı bazı VPS'lerde `/dev/net/tun` yok; o durumda userspace mod gerekir (§7) |
| D2 | GPU makinesi hangi makine, hangi ağda? | Kampüs ağıysa DERP'e düşme ve kurum politikası riski var |
| D3 | Tailscale hesabı hangi kimlikle açılacak? | Takım arkadaşları da erişecekse kişisel plan sınırları ve ACL'de kullanıcı tanımı değişir |
| D4 | Bağlantı yönü | **Karar: GPU → VPS pull**, yalnız özel TCP 9100 |
| D5 | Yönetim erişimi: Tailscale SSH mi, klasik SSH mi? | Politikadaki `ssh` bloğu buna göre kalır ya da silinir |

## 4. Repo kuralları

`AGENTS.md` gereği bu klasöre hiçbir zaman girmeyecekler: gerçek tailnet adı,
`100.x` adresleri, makine hostname'leri, auth key'ler, e-posta adresleri.

- Politika şablonu: `policy.example.hujson` — yalnızca etiket kullanır, gerçek
  değer içermez.
- Gerçek adresler: `infra/README.md`'de tarif edilen Git dışı yerel dosyalarda
  (`backend.env`, `imaging.env`, `genomics.env`).
- Auth key'ler hiçbir dosyaya yazılmaz; doğrudan komut satırında kullanılıp
  konsolda tüketilmiş olarak bırakılır.

## 5. Bağlantı yönü (D4 — kararlaştırıldı)

İlk plandaki VPS → GPU push yaklaşımı uygulanmayacak. Bu yaklaşım GPU makinesinde
dinleyen bir model portu, ev ağı yönünde erişim ve primary/standby seçimi gerektirir.

**GPU → VPS (pull).** GPU makinesi kuyruktan iş çeker. Makine uyanınca kaldığı
yerden devam eder, VPS'in GPU'ya erişmesi hiç gerekmez, ACL tek yönlü ve daha
dar olur. Dezavantajı: yoklama (polling) mantığı ve iş sahipliği/kilitleme
yazmak gerekir.

**Seçilen düzen pull'dur.** VPS'teki `mergen-control` yalnız kendi Tailscale
adresinde TCP 9100 dinler. GPU worker bu uçta heartbeat gönderir, işi atomik
olarak claim eder, girdiyi indirir, lease yeniler ve sonucu geri yükler. GPU
makinesinde dinleyen model portu bulunmaz. Worker token'ı ikinci korumadır;
Tailscale ACL'nin yerine geçmez.

## 6. Adım adım plan

Her adımın kabul ölçütü sağlanmadan sonrakine geçilmez.

**T1 — Hesap ve tailnet.** Tailscale hesabı açılır, tailnet adı not edilir
(Git dışı). Henüz hiçbir cihaz eklenmez.
*Kabul:* konsolda 0 cihaz görünüyor, tailnet adı yerel notta.

**T2 — Politikayı önce yaz.** `policy.example.hujson` içeriği Access Controls
bölümüne yapıştırılır. Cihazlar
katılmadan önce yapılır ki varsayılan "herkes herkese" hiç yürürlükte olmasın.
*Kabul:* politika kaydedildi ve `tests` bloğu hatasız geçti.

**T3 — VPS'e kurulum.**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo systemctl enable --now tailscaled
sudo tailscale up --advertise-tags=tag:mergen-edge --accept-dns=false
```
*Kabul:* `tailscale status` cihazı `tag:mergen-edge` ile gösteriyor; konsolda
key expiry devre dışı; `tailscale ip -4` bir 100.x adresi veriyor.

**T4 — GPU makinesine kurulum.** Aynı komutlar, `--advertise-tags=tag:mergen-gpu`
ile.
*Kabul:* T3 ile aynı; ayrıca iki cihaz konsolda birbirini görüyor.

**T5 — Bağlantı ve politika doğrulaması.** GPU makinesinden:
```bash
tailscale ping <VPS_100X_ADRESI>     # direct mi DERP mi olduğunu yazar
tailscale netcheck                   # UDP/NAT durumu
```
*Kabul:* ping yanıt veriyor; VPS TCP 9100'e erişiliyor; 22, 443 ve 9000'e GPU
etiketiyle erişilemiyor; VPS'ten GPU üzerinde uygulama portuna erişilemiyor.

**T6 — Worker kontrol servisini doğru arayüze bağla.** VPS'teki servis `0.0.0.0`
yerine VPS'in Tailscale adresinde TCP 9100'e bind edilir; yerel güvenlik duvarı
portu diğer arayüzlerde kapalı tutar. GPU tarafında gelen bağlantı portu açılmaz.
*Kabul:* GPU'dan kontrol servisine erişiliyor; internetten, yerel ağdan ve VPS'ten
GPU üzerinde bir model portuna erişilemiyor.

**T7 — Kalıcılık provası.** Her iki makine yeniden başlatılır.
*Kabul:* elle müdahale olmadan ikisi de ağa dönüyor, adresler değişmiyor.

**T8 — Worker'ı bağlama.** VPS Tailscale adresi, worker token'ı ve worker kimliği
GPU makinesindeki Git dışı ortama yazılır. Worker heartbeat ve claim çağrıları
başlatılır.
*Kabul:* VPS sağlık ucu worker'ın bildirdiği yetenekleri gösteriyor; Caddy
`/internal/*` yolunu yayınlamıyor.

**T9 — Arıza provası.** GPU makinesi kapatılır ve aynı istek tekrarlanır.
*Kabul:* iş kuyrukta ve worker ulaşılamıyor olarak kalıyor; `AGENTS.md` 6. kural
gereği sessizce demo sonucuna düşmüyor.

## 7. Bilinen tuzaklar

- **Konteyner tabanlı VPS.** `/dev/net/tun` yoksa `tailscaled` normal modda
  açılmaz; `--tun=userspace-networking` ile çalıştırılır ve giden bağlantılar
  için SOCKS5/HTTP proxy kullanılır. D1 netleşince bakacağız.
- **`--accept-dns=true` sürprizi.** Sunucuda `/etc/resolv.conf` devralınır;
  başka bir DNS kurulumun varsa bozulabilir. Biz kapalı gidiyoruz.
- **Etiketsiz katılma.** `--advertise-tags` unutulursa cihaz kişisel hesabına
  bağlanır ve 180 gün sonra süresi dolar. Sonradan etiketlemek cihazın yeniden
  doğrulanmasını gerektirir; en baştan doğru yapmak daha ucuz.
- **Politikayı sonra yazmak.** Cihazlar varsayılan izinle katılırsa aradaki
  sürede tailnet açık kalır.
- **Kurum ağı.** Kampüs güvenlik duvarı UDP'yi kapatırsa bağlantı DERP'e düşer;
  çalışır ama yavaşlar. Ölçmeden "yavaş kalacak" demeyelim, `tailscale ping`
  çıktısına bakarız.
- **Ev yükleme hızı.** Segmentasyon maskesi ve önizlemeler GPU makinesinden
  VPS'e dönerken ev bağlantısının **upload** hızını kullanır; bu genelde
  download'dan çok daha düşüktür. Gerçek dosya boyutuyla ölçülmeli, tahmin
  edilmemeli.
- **Makinenin uykuya dalması.** Uyuyan GPU makinesi ağdan düşer. Sunum
  senaryosunda bu en olası arıza; makinenin uyku ayarları kapatılmalı.

## 8. Sunum günü

`docs/PLAN.md` zaten "Ubuntu kapalıyken gösterim devam etmeli" diyor. Tailscale
bacağı bu kararı değiştirmiyor, aksine güçlendiriyor: demo modu VPS'te duran
hazır sonuçlarla çalıştığı için tailnet tamamen kopsa bile sunum yürür. Canlı
mod ayrı bir düğme olarak kalmalı ve başarısız olduğunda demo sonucu gibi
görünmemeli.

## 9. Doğrulama komutları

```bash
tailscale status              # node'lar, etiketler, bağlantı tipi
tailscale ip -4               # bu makinenin 100.x adresi
tailscale ping <ADRES>        # direct/DERP ve gecikme
tailscale netcheck            # NAT tipi, en yakın DERP
sudo tailscale up --reset ... # bayrakları temiz baştan uygulamak için
journalctl -u tailscaled -n 50
```
