# GPU host hazırlığı (G0–G1)

Günlük kullanılan bir Linux bilgisayarı MERGEN'in paylaşımlı NVIDIA GPU
hostuna hazırlayan scriptler ve deklaratif yapılandırma. Sıra, kabul ölçütleri
ve dağıtım farkları [`docs/GPU_HOST_RUNBOOK.md`](../../docs/GPU_HOST_RUNBOOK.md)
içindedir; bu dosya yalnız neyin ne olduğunu söyler.

| Dosya | Ne yapar | Sistemi değiştirir mi |
|---|---|---|
| `audit-host.sh` | Dağıtım, dosya sistemi, şifreleme, NVIDIA, Tailscale, hesap, dizin ve Python envanteri | Hayır |
| `check-snapshot-layout.sh` | Runtime dizininin kök snapshot'ına giremeyeceğini kanıtlamaya çalışır | Hayır |
| `verify-gpu-runtime.sh` | Verilen venv'de sürücü, PyTorch ve gerçek bir GPU tensor turu | Hayır |
| `install-base.sh` | Hesap, grup, dizin ve boş env dosyaları | Yalnız `--apply` ile |
| `sysusers.d/mergen.conf` | İki yetkisiz servis hesabı ve ortak okuma grubu | `systemd-sysusers` uygularsa |
| `tmpfiles.d/mergen.conf` | Dizin sözleşmesi ve modlar | `systemd-tmpfiles` uygularsa |
| `sudoers.d/mergen-maintenance.example` | Bakım hesabı için dar sudo örneği | Hayır — elle `visudo` |
| `dispatcher.env.example`, `executor.env.example` | Boş yapılandırma şablonları | Hayır |
| `stage-services.sh` | Dispatcher ve executor'ı sürümlü release'e kurar, ayrı venv'ler, unit ve env kopyası, atomik `current` geçişi | Yalnız `--apply` ile; servis başlatmaz |
| `verify-services.sh` | Staging öncesi/sonrası doğrulama: hesap, dizin, env, token ayrımı, importlar, gate, unit; bu unit'lere uygulanan her drop-in (genel `service.d` dahil) reddedilir | Hayır |
| `lib/services.sh`, `lib/service_probe.py` | Release düzeni yardımcıları; venv içinde değer yazdırmayan probe | Hayır |
| `systemd/*.service.example` | Dispatcher ve executor unit'leri | `stage-services.sh` kopyalar; enable/start yok |
| `test_gpu_host.py`, `test_stage_services.py`, `fake_host.py` | Sözleşme ve sahte host üzerinde staging testleri | Hayır |

Varsayılan davranış hiçbir şeyi değiştirmemektir:

```bash
bash infra/gpu-host/audit-host.sh            # envanter
bash infra/gpu-host/check-snapshot-layout.sh # veri kapsamı kararı
bash infra/gpu-host/install-base.sh          # plan; hiçbir şey yapmaz
sudo bash infra/gpu-host/install-base.sh --apply
```

Sıra önemli: `check-snapshot-layout.sh` PASS vermeden `--apply` çalıştırma.
Runtime'ın kendi mount'u hesaplardan **önce** kurulur; aksi halde ilk işle
birlikte hasta girdisi kök snapshot'ına girer. Tam sıra runbook'ta.

Testler:

```bash
python -m unittest discover -s infra/gpu-host -p 'test_*.py'
bash -n infra/gpu-host/*.sh infra/gpu-host/lib/*.sh
```

Bu katmanda kurulmayanlar: NVIDIA sürücüsü, CUDA Toolkit, PyTorch, model
ağırlıkları, Tailscale oturumu. Hepsi runbook'ta operatörün elinde.
