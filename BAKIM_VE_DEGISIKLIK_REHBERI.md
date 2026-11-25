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

## Ofis arayuzu (2026-11-23)

Ofis ekraninin yerlesimi ve stilleri [dashboard.html](product/frontend/office/scenes/dashboard.html) icinde. Sablon mevcut sahne ve operasyon betigiyle sunulur. Tasarim dayanagi [B v135 ilk kat tel kafesi](GUNCEL/dokumanlar/hedef-mimari-v1/kaynaklar/B_v135.md#L93386).

## Canlı görev verme ve yerel Ollama ajan koşusu (2026-11-23)

- [ollama_adapter.py](product/backend/company_os/engine/ollama_adapter.py): Loopback-only (`127.0.0.1`), ücretsiz yerel Ollama (`E:\ollama_local\bin\ollama.exe`, `qwen2.5-coder:3b`) istemcisi ve otomatik başlatıcı (otomatik paid fallback yok).
- [live_task_runner.py](product/backend/company_os/runtime/live_task_runner.py): `LiveOfficeTaskRunner` + `AutonomousWorkerDaemon` + bağımsız `verify_office_task_output` doğrulayıcısı.
- [app.py](product/backend/company_os/api/http/app.py) ve [start_office_local.py](scripts/operations/start_office_local.py) görev gönderimini, görev okumasını ve yerel SSE akışını sunar. `POST /api/office-tasks` loopback Origin kontrolü uygular. `Bearer` oturumu ile WSL Kernel üzerinden `Objective→Plan→Task` kaydı açılabilir.- Yerel SSE, kaynak olay kimliğini aynı sunucu süreci içinde tek bir imlece bağlar. 512 olaylık pencerenin dışındaki imleç veya gözlenen kaynak boşluğu `resync_required` üretir. Pencere süreç belleğinde tutulur. [Doğrulama betiği](scripts/verification/probe_office_durability.py) kayan pencere, yeniden bağlanma ve geç outbox commit senaryolarını sınar.- Doğrulama: [test_live_office_tasks.py](tests/unit/test_live_office_tasks.py) (306 birim testi PASS), `verify_layout.py` PASS ve [live-office-task-e2e-20261123.json](evidence/runs/live-office-task-e2e-20261123.json).

## Ürün hafızası terfisi ve dış işlem/bütçe canlı döngüsü (2026-11-23)

- [live_lifecycle.py](product/backend/company_os/catalog/live_lifecycle.py): `LiveMemoryAndBudgetCoordinator` — kabul edilen görevlerden otomatik `CANDIDATE→VERIFIED` hafıza adayı üretimi, görev ayrılığı (`promoted_by != verified_by`) ile `PROMOTED` terfisi, izinli-host kontrollü idempotent webhook/dış işlem çağrısı ve `BudgetAndEffectLedger` (`UNKNOWN` kilidi + uzlaştırma).
- [app.py](product/backend/company_os/api/http/app.py), [start_office_local.py](scripts/operations/start_office_local.py), [dashboard.html](product/frontend/office/scenes/dashboard.html), [office-preview.js](product/frontend/office/engine/office-preview.js): `POST /api/memory-promotions`, `POST /api/external-effects`, ofis `Onaylar` sekmesinde canlı terfi/red butonları ve bütçe özeti, canlı PG 18.6 `087` `company.memory_promotions` ve `company.external_effect_ledger` FORCE RLS kalıcılığı.
- Doğrulama: [test_live_memory_and_budget.py](tests/unit/test_live_memory_and_budget.py) ve [live-memory-budget-e2e-20261123.json](evidence/runs/live-memory-budget-e2e-20261123.json).

## Kanonik AgentInstance ve görev denemesi bağı (2026-11-23)

- [088_AGENT_INSTANCE_REGISTRY_CANDIDATE.sql](database/sources/088_AGENT_INSTANCE_REGISTRY_CANDIDATE.sql): `company.agent_instances` ve `company.agent_instance_assignments` (2 `FORCE RLS` tablosu, `(tenant_id, project_id)` bileşik FK, `RUNNING` iken `active_task_id`/`active_attempt_id` zorunlu CHECK, tekil aktif deneme indeksi); [assembly.json](database/assembly/assembly.json) 88. sıraya pinlendi ve canlı PG 18.6 (55490) üzerine uygulandı.
- [agent_instances.py](product/backend/company_os/runtime/agent_instances.py): `AgentInstanceRegistry` — aynı rolde birden fazla ajan örneği, retry sırasında eski denemenin otomatik `SUPERSEDED`/`IDLE` yapılması, bayatlama (`STALE`) tespiti ve proje/tenant kapsamlı yetkili okuma (`GET /api/agent-instances`).
- [office-preview.js](product/frontend/office/engine/office-preview.js): Ajanlar sekmesi, sahne hotspot seçimi ve Seçili Bağlam paneli gerçek `AgentInstance` kayıtlarına bağlandı; bağlantı kopunca aktif görev izlenimi temizlenir.
- Doğrulama: [test_agent_instances.py](tests/unit/test_agent_instances.py) ve [live-agent-instances-e2e-20261123.json](evidence/runs/live-agent-instances-e2e-20261123.json).
## EXP-01 katalog pilotu — 2026-11-23- Başlatıcıdaki `--engineer-pilot-service`, `087` kataloğunda yetkili bir PostgreSQL servis adı alır. Pilot `EXP-01` yazılım görevlerinde etkinleşir. Katalog kaydının tenant, rol, sürüm, etkinlik ve SHA-256 kontrolleri model çağrısından önce yapılır. Birim testi yanlış digest durumunda model çağrısının yapılmadığını doğrular.- Pilot koşusunun sonucu rol sürümünü ve digest bilgisini taşır. Canlı PostgreSQL ve normal görev girişinden pilot kabulü açık.- Sentetik A/B denemesinde gerçek `qwen2.5-coder:3b` ve test kataloğu kullanıldı. Baz koşu 191 giriş/206 çıkış, pilot yeniden denemesi 233 giriş/307 çıkış tokenı üretti. Pilot daha küçük bir fonksiyon önerdi, görev metnini tekrarladı ve testlerin çalıştırılmadığını açıkça belirtmedi. Tek görevde genel kalite artışı doğrulanmadı. İlk pilot çağrısı zaman aşımına uğradı.
### Ofiste yürütme süresi

Yerel başlatıcının PostgreSQL sorgusu ajan, görev, aktif deneme, worker ve fencing epoch eşleşince güvenilir saat üst sınırından kalan süreyi hesaplar. Tarayıcı istek süresini düşer ve süre dolunca avatarla seçili paneli birlikte günceller. Kanıt eksikse RUNNING kaydı STALE görünür. Regresyon kontrolü için scripts/verification/check_office_task_browser.py kullanılır.

### Kalıcı RESEARCH makbuzunu doğrulama

Yerel ofiste --research-readback-service seçeneği önceden tanımlı, yalnızca gerekli kayıtları okuyabilen PostgreSQL servisinin adını alır. Yerel dosya özeti kalıcı görev için kabul üretmez. Native worker aynı görev ve denemede workspace.read işlemini tamamlamışsa seçilen makbuz ayrı bir doğrulayıcı sürecinde yeni bir salt okunur işlemle denetlenir. Bu seçenek native worker başlatmaz. İzole PostgreSQL üzerinde yeniden başlatma ve yanlış kapsam regresyonu scripts/verification/check_research_readback_pg.py içindedir. Fikstür, native imza üretiminin kabulü değildir.
