# Bakım ve değişiklik rehberi



Canonical workspace: E:\Projeler\Ai_Proje_Ofisi

Son güncelleme: 2026-11-20



Ürün henüz gerçek işi baştan sona teslim etmiş olarak kabul edilmedi. Bu rehber güncel kaynaklara giriş sağlar; tam sürüm geçmişi veya ürün kabulü değildir.



| İhtiyaç | Güncel kaynak |

|---|---|

| Durum, eksik ve sıradaki iş | [İlerleme](progress/ILERLEME_TABLOSU.md) |

| Bağlayıcı mimari ve 16 modül | [Mimari giriş](docs/architecture/README.md) |

| Yeni/eski dosya karşılığı | [Tam eşleme](docs/migration/SOURCE_TO_TARGET.json) |

| Ekranı açma ve test | [Çalıştırma](docs/developer-guides/CALISTIRMA.md) |

| Görev ekranı | [HTML](product/frontend/pages/tasks/index.html), [JS](product/frontend/pages/tasks/tasks.js), [CSS](product/frontend/pages/tasks/tasks.css) |

| HTTP/oturum sınırı | [task_http.py](product/backend/company_os/api/http/task_http.py), [kernel_binding.py](product/backend/company_os/api/http/kernel_binding.py) |

| Tek domain writer | [command_host.py](product/backend/company_os/kernel/command_host.py) |

| Başlangıç kimliği ve güvenilir süre | [bootstrap](product/backend/company_os/bootstrap/) |

| Yetkili oturum | [session_provisioning.py](product/backend/company_os/kernel/session_provisioning.py), [owner_auth.py](product/backend/company_os/kernel/owner_auth.py) |

| Ajan/araç/patch bağlantısı | [composition](product/backend/company_os/composition/), [broker](product/backend/company_os/broker/), [workspace](product/backend/company_os/workspace/) |

| Süreç başlatma/IPC/ölçüm | [runtime](product/backend/company_os/runtime/) |

| Bağımsız verifier | [verifier](verifier/README.md) |

| Native kaynaklar | [native](product/backend/native/linux/) |

| Ofis görüntüsü ve kaynağı | [frontend](product/frontend/), [tasarım kaynağı](docs/developer-guides/OFIS_TASARIM_KAYNAKLARI.md) |

| İlerleme görüntüsü | [progress.py](product/backend/company_os/projections/progress.py) |

| SQL sırası ve korumalar | [assembly.json](database/assembly/assembly.json) |

| Yerel DB durum/start/stop | [araç](scripts/database/manage_local_postgres.ps1), [rehber](docs/operations/YEREL_VERITABANI.md) |

| Neden/nasıl taşındı, hangi düzeltmeler var? | [Geçiş raporu](docs/migration/MIGRATION_PLAN.md) |

| Önceki düzeltme kanıtları | [Tarihsel devirler](handover/history/), [ham kanıtlar](evidence/) |



İlgili kaynak değişince uygun test, kanıt ve ilerleme satırı güncellenir; değişmeyen satırlar yeniden test edilmiş sayılmaz. Tahmini yüzde ölçülmüş kabul değildir. Yeni bileşen veya davranış değişirse bu rehber de güncellenir. SOURCE_MANIFEST ve geçiş eşlemesinin hedef pinleri değişikliğin gerekçesiyle birlikte gözden geçirilir; eski source_sha256/historical evidence değiştirilmez.



Klasör geçişi sonrası Windows 249 test/229 başarılı/20 Linux skip; Linux 249 başarılı. Ham koşumlar evidence/runs/layout-migration-20261114 altındadır. Sonraki değişikliklerde bu sonuçlar kendiliğinden güncel sayılmaz. Gerçek profil/kimlik/DB şeması/model/verifier/ilk teslim kabulü ayrı açıktır.



## Güncel DB ve ajan devir kontrolü

2026-11-14 salt okunur uzlaştırma: [rapor](handover/STATE_RECONCILIATION_20261114.md), [ham readback](evidence/runs/state-reconciliation-20261114/database-readback.json), [tekrarlanabilir denetim](scripts/database/audit_local_state.py). Önceki boş DB anlatımı tarihseldir. Şema/Objective/Plan var; güvenilir üretim zinciri kabulü yok. Denetim yalnız kayıt sayıları ve katalog metadata okur; token veya satır içeriklerini yazdırmaz. WSL çağrısı manage_local_postgres.ps1 ile aynı distro/OS kullanıcısı/Python altında audit_local_state.py çalıştırılarak yapılır.


## Ortak temiz kod kuralı — 2026-11-14

Kullanıcı talimatı: Codex ve Antigravity her yeni/değiştirilen kodda [ortak kod kalitesi kurallarını](docs/developer-guides/KOD_KALITESI_KURALLARI.md) uygular. Açık ve okunabilir kod, güvenli hata/kaynak yönetimi, doğrulanan bağımlılıklar, mimari sınırlar ve uygun test/kanıt zorunludur. Kuralların yazılması formatter/lint/tip kontrolü veya CI kurulduğu anlamına gelmez; eksik otomatik kontrolleri açık bildir. Mevcut açık ajan oturumlarının bu dosyayı kendiliğinden yeniden yüklediğini varsayma.


## 2026-11-15 — HTTP/Kernel bağlantısı

[Adım 4 raporu](handover/STEP04_HTTP_KERNEL_20261115.md): yapılandırılmış komut/okuma ayrımı, panelde uygun form ve kayıt seçimi; HTTP üzerinden gerçek command_host zincirinin DB-API test bağlantısıyla kontrolü. Canlı DB/panel kabulü henüz doğrulanmadı.


## Panel/Kernel genişlemesi — 2026-11-15

[İş isteği/plan/görev/makbuz raporu](handover/PANEL_WORKFLOW_20261115.md): üç mevcut constructorun HTTP/panel bağları, komutu yeniden işletmeden native makbuz okuma, reload referansları ve BEGIN öncesi emisyon hatasında bağlantı cleanup. Gerçek DB oturum geçerliliği 0 gözlendi; canlı panel yazma kabulü açık. Kaynak testleriyle kalıcı ürün kabulünü ayır.


## Güvenilir oturum ve demo ayrımı — 2026-11-15

[Uygulama raporu](handover/TRUSTED_SESSION_20261115.md), [operatör rehberi](docs/operations/OWNER_OTURUMU.md). Supervisor session commit+bağımsız readback eklendi; doctor salt okunur kurulum tanısını gösterir. Demo launcher gerçek profil gerektirir. Mevcut tenant için owner-auth/recovery yaşam döngüsü açık; bootstrap tekrar koşumu yenileme değildir.

## Owner-auth / recovery yaşam döngüsü (v1) ve kaynak bütünlüğü — 2026-11-20

[Uygulama raporu](handover/OWNER_AUTH_RECOVERY_20261120.md), [086 SQL kaynağı](database/sources/086_APPLICATION_OWNER_AUTH_RECOVERY_V1.sql), [owner_auth.py](product/backend/company_os/kernel/owner_auth.py). Kaynak bütünlüğü (`serve_standalone.py` geri yükleme, `serve_persistent.py` emekliye ayırma) onarıldı. Mevcut tenant verilerini koruyan, canlı proje saatine ve `OWNER_AUTH` signer enrollment'ına bağlı `ISSUE_SESSION`/`REVOKE_SESSION`/`RECOVER_ROTATE_SESSIONS` kaynak adayı ile `owner_auth_readiness` tanısı eklendi; PG18 rollback-only derleme ve native unsafe-login reddi doğrulandı. Canlı enrollment, migration ve pozitif owner oturumu/panel kabulü G0 kapsamında açıktır.

## Canlı değerlendirme kümesi 5 adımlı akış ve kaynak düzeltmeleri — 2026-11-20

[Canlı doğrulama raporu](handover/LIVE_FLOW_VERIFICATION_20261120.md) ve ham kanıtlar (`evidence/runs/live-flow-20261120/`). Onaylı WSL PostgreSQL `18.6` değerlendirme kümesinde (`aipof-dbtest`, port `55490`) `086` canlı kurulumu + `OWNER_AUTH` enrollment, pozitif/negatif owner oturumu/iptal/rotasyon, least-privilege HTTP panel üzerinden `Objective`/`Plan`/`Task` (`MGT-TITLE-NORMALIZATION-01`) + `/api/receipts` + ayrı bağlantı readback, `qwen2.5-coder:3b` (Ollama) + OS `subprocess`/`os.pidfd_open` + `PilotSession` yaması, `RuntimeTitleVerifier` (`13/13` PASS) + `IndependentVerificationPipeline.seal_and_accept` (`ACCEPTED`) ve PG soğuk yeniden başlatması sonrası 6 `/api/details` readback'i doğrulandı. Entegrasyon sırasında ortaya çıkan `command_host.py` per-operation `grant_ids` çözümlemesi ve `kernel_adapters.py` base64 `\n` satır sarma düzeltmesi [test_host_guards.py](tests/unit/test_host_guards.py) ve [test_pipeline.py](tests/unit/test_pipeline.py) regresyon testleriyle kapatıldı. `G0 = OPEN`, `runtime = NOT_RUN`, `first13 = 0/13`; native C `r65_spawn` derlenmedi (`ruff` ve `mypy` kurulu ortamda mevcut değil).

## 2026-11-20 SQL kaynak paketi

- 038 ve 058: PL/pgSQL kayıt değişkenleriyle çakışan tablo takma adları yeniden adlandırıldı.
- 059: STARTING ve RUNNING süreçleri, doğrulanmış durma gözleminden sonra STOP_REQUESTED üzerinden STOPPED olur. İkinci geçiş güncel revision ile yapılır.
- 083: launch delivery audit ve outbox okuması aynı işlem, müşteri, proje, aktör ve başarılı launch komutuyla sınırlandı.
- Kaynak kontrolü için test_sql_source ve verify_layout kullanılır. Temiz PostgreSQL kurulumu ve davranış testi açıktir.

### Temiz SQL deneyi

Linux test hesabında `python3 -B scripts/verification/run_sql_fixture.py --synthetic-owner --probe scripts/verification/first_flow_bootstrap_readiness.sql` komutu geçici bir kümede başlangıç izinlerini kontrol eder. Diğer problar ve kapsamları `evidence/runs/sql-step1-20261120.md` içinde açıklanır.
