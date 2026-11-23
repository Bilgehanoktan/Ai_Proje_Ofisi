# Kalan işler — 2026-11-13

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-13
Kaynak ajan: Codex
Durum: CURRENT_BACKLOG_SYNTHESIS; ürün kabulü değildir
Kanıt: UYGULAMA_DURUM_MATRISI.md ve son ekleri; ILERLEME_TAKIBI_20261112.md; CODEX_SERVIS_VERIFIER_20261112.md; ilgili kaynak constructor/portları; evidence/CODEX_SERVICE_20261112_manifest.json ve inventory.json.

## Güncellik ve tamamlanmış alt kapsam

13Kasımda son servis manifestindeki23dosya yeniden SHA256 ile karşılaştırıldı; fark yok. config/profiles altında JSON dosyası hâlâ yok. Bugün testler veya Linux ortam envanteri yeniden çalıştırılmadı. Son12Kasım koşumu Linux194PASS0SKIP; Windows174PASS20SKIP. Bu, tüm16modülün kabulü veya first13kanıtı değildir.

Kanonik workflow bağlantıları, güvenli consent/secret girişleri, descriptor sahipliği/cleanup, Linux observer sensörleri ve pinli ölçüm alt profili, bounded IPC/SCM_RIGHTS, verifier13case evaluator, private receipt store ve servis istemcileri kaynakta uygulanmış ve belirtilen test kapsamlarında doğrulanmıştır. Gerçek uid999/65534 IPCmekanizma deneyi de geçti; enrollment/namespace/uygulama qualificationı değildir. Bunları sıfırdan yeniden yazmak kalan iş olarak sayılmaz.

Kalanlar yalnız deployment değildir: bazı current authority readback, immutable resolver ve qualified launcher/qualification adapterleri hâlâ gerçek implementasyon ve bağlama gerektirir. Alt profil okuyucusu tam runtime konfigürasyonu yerine geçmez. Matrisin10Kasım ana satırlarındaki eski ctor/verifier iddialarını12Kasım ekleri olmadan güncel sayma. Eski15çağrı uyuşmazlığı yedek trialda korunur; aktif preflight0finding ile aynı payda değildir.

## Öncelik 0 — İlk gerçek SOFTWARE akışının teknik engelleri

| Paket | Kalan somut iş | Çıkış kanıtı |
|---|---|---|
| P0-1 Güvenilir başlangıç | Gerçek owner/teknik principal enrollmentı, ayrı signer/custody bağları, current clock/policy/session/grant ve host/boot/generation readback; sentetik bootstrap yerine gerçek kayıtları kullanma | Yetkili pozitif ve revoked/expired/wrong-scope ret; bağımsız kalıcı readback; mevcut tek-insan kararı korunur |
| P0-2 Tam runtime profili ve Linux qualification | Pinli native/model/toolchain, ayrı kimlik/namespace, dedicated cgroup/delegation/limits, network/fs/hidden-fixture ve deadline/kill/recovery sınırları | Profil onayı ve exact build/config bağları; actual spawn/stop/revoke/crash/cleanup ölçümü; dosya varlığı yeterli değil |
| P0-3 Kernel otorite adapterleri | Peer/scope/enrollment validatorları; observer current enrollment readback; workspace fence/no-respawn journal/usage-ledger readback | Her portun gerçek Kernel/OS otoritesine bağlanması; hardcodedTrue veya fake-driver yok; stale/revoke/epoch/lease negatifleri |
| P0-4 Immutable aday ve izole verifier launcherı | task/attempt/patch/headden candidate resolver; rootless isolated candidate session open/read/write/finish/close; BEFORE_LAUNCH/RUNNING/STOPPED/RECEIPT_READBACK qualification | Adayın oracle/servis/key/parent kaynaklarına erişememesi; exact bytes/build/profile; wrong mutant/forgedPASS/nonzeroexit/timeout/tamper ret |
| P0-5 Gerçek model/worker/Broker zinciri | Scheduler/claim/engine binding; ücretsiz yerel varsayılan exact model/provider adapterı; gerçek DB consume→effect→patch receipt | Tek görev/tek dosya bounded başarı; çift claim/stale fence/path/egress/replay/UNKNOWN negatifleri; yeniden etki veya ücretli fallback yok |
| P0-6 Gerçek uçtan uca kanıt | Aynı source/build/configte Objective→Plan→TaskREADY→worker→patch→bağımsız verifier→Kernel kabul/ret; işlem sonrası bağımsız readback | Pozitif ve negatif ham log, artifact/receipt bağları, cleanup, bağımsız teknik inceleme; first13insan kapıları ayrıca |

P0-1/2 önkoşulları altında P0-3/4 somut adapter bağları hazırlanır; P0-5/6 gerçek deneyle kanıtlanır. Hazır IPC/evaluator kodunu yeniden yazmak bu paketlerin yerine geçmez. G0OPEN,first13 0/13 korunur; yeni kabul kaydı yok.

## Öncelik 1 — İlk görünür/kullanılabilir ürün ve kanıt tutarlılığı

1. MOD-010/011: AuthenticatedReadbackApp sınıfını gerçek HTTP oturum/command/readback akışına bağlama;401/403/409,scope/revoke,consistent snapshot,cursor/replay/resync ve restart/relogin/reload. Mevcut WSGI matris önizlemesi gerçek iş paneli kabulü değildir.
2. Görsel inceleme: masaüstü/dar ekran/klavye/boş-hata-yükleniyor durumları; gerçek veriyle görev/ajan/sonuç/kanıt görünümü. Gelişmiş ofis görseli domain doğruluğunun yerine geçmez; renderer ve ayrıntılı görsel kapsam ayrıca mevcut tasarımla yürütülür.
3. MOD-016: README,module-map,implementation_status ve matris/kanıt tarihlerini uzlaştırma; görev→REQ/BR/AC/TEST→exact source/build/config/fixture→log/readback→independent review zinciri; reproducible paket/CI.
4. GUNCEL/DOGRULA.py CALISMA_DURUMU.md hash ayrışmasının owning değişiklik/kök neden incelemesi ve gerekçeli üretim akışıyla düzeltilmesi. Bugün yeniden koşulmadı:REPORTED_NOT_RETESTED. Kör manifest hash güncellemesi kapanış değildir.

## Tam mimari — 16 modülde kapanışı açık kalan kapsam

Bu tablo matris ve son eklerin sentezidir; bugün bütün modüllerin kaynakları yeniden semantik denetlenmedi. Kalan kapsamın tamamı uygulanmadı diye değil, belirtilen implementasyon/gerçek entegrasyon/kabulün açık olması bakımından listelenir.

| Modül | Kalan kapsam |
|---|---|
| MOD-001 Kimlik/Policy/Command | Gerçek enrollment/custody/clock/auth/scope ve DB/HTTP yetki zinciri kabulü |
| MOD-002 Hedef/Plan/CEO | Kalıcı Objective→immutable Plan→TaskREADY; gerçek CEO plan/DecisionCase önerileri, DAG/idempotency/rollback kabulü |
| MOD-003 Scheduler/Qualification | Exact model/rol/tool/suite/catalog/resource binding; gerçek claim/lease/heartbeat/fence/revoke kabulü |
| MOD-004 Launch/Isolation | Pinli binary ve qualified rootless host/ns/cgroup; gerçek spawn/stop ve bağımsız gözlem kabulü |
| MOD-005 Engine/Provider | Gerçek ücretsiz yerel model/adapter, exact pin, bounded stream/deadline/EOF ve runtime binding |
| MOD-006 Broker/Etki | Gerçek DB/OS consume-effect-receipt, path/egress/replay/revoke ve UNKNOWN reconciliation |
| MOD-007 Workspace/Patch/Artifact | Immutable source/head/build/candidate resolver; actual CAS/tamper/conflict/bozuk girdi ret ve artifact readback |
| MOD-008 Bağımsız Verifier | Ayrı servis/kimlik/fixture/candidate izolasyonu qualificationı; gerçek aday koşumu ve current receipt/enrollment readback |
| MOD-009 Acceptance/Release | Gerçek candidate→patch→report→provenance→accept bağları; stale/fake/missing ret ve bağımsız DB readback; release/insan/PROD kapıları ayrı |
| MOD-010 Event/Projection | OfficeEvent/EventEnvelope/typed epoch eşlemesi; actual scoped snapshot/cursor/replay/resync/reload |
| MOD-011 Yönetim/Ofis | Gerçek authenticated HTTP command/readback ve kalıcı UI; görsel/klavye/dar ekran kabulü |
| MOD-012 Katalog/Hafıza | Exact katalog/lisans/provenance pinleri; tenant ACL,promotion,source provenance,revoke/tombstone/readback |
| MOD-013 WorkType | Önce SOFTWARE gerçek ara kabulü; sonra mevcut Research/Spreadsheet/Obligation dallarının schema/oracle/data-rights/locale-TZDB/negatif/reload kabulü |
| MOD-014 Bütçe/Ticari/Dış Etki | Gerçek reservation/UNKNOWN settlement; PH-05 ledger/idempotency/reconciliation; dış ödeme/yayın ve paid fallback ayrı izinli |
| MOD-015 Operasyon/Recovery/Backup | Actual crash/stop/recovery; bağımsız backup/witness,fenced restore,old grant/outbox dirilmeme; ölçülmüş RTO/RPO ve runbook |
| MOD-016 Teslimat/ADR/Kalite | Tam semantik kaynak/AC/TaskSpec izleri, güncel durum/pin/kanıt tutarlılığı, bağımsız review ve reproducible paket/CI |

## İlk akış sonrası kapsam

PH-04 authenticated panel/reload ve ilk13değerlendirmesi; PH-05 recovery/backup/witness ve sınırlı şirket/ticari operasyon; PH-06 katalog/hafıza ve mevcut seçili WorkType dalları kapsamda kalır. İlk çalışan SOFTWARE akışı tam projenin yerine geçmez. Bütün16modülün tam kabulü bu kaynak setinde kanıtlanmış değildir; tek toplam yüzde veya kesin gün tahmini üretilmez.

## Sonraki işin somut tanımı

P0-1/P0-2 için mevcut onaylı kimlik/clock/host/profile kayıtlarının owning native kaynaklarla eşleştirilmesi ve eksik kayıt/adapter listesinin çıkarılması; ardından P0-3/P0-4 gerçek DB/OS implementasyonu. Bu, yalnız bir servis başlatma veya ek test sayısı işi değildir. Onay veya trust root sentetik doldurulmaz.

Bu derleme kaynak değiştirmedi, servis/DB/model başlatmadı ve kabul kapısı yükseltmedi. Yeni mimari karar veya yeni teknik kusur üretilmedi; mevcut açık işlerin güncel önceliklendirmesidir.


## 2026-11-13 — Başlangıç receipt ve yetki adapterleri

[Kaynak/fake-driver raporu](CODEX_YETKI_ADAPTERLERI_20261113.md):DBsiz grant/revoke başarı stubı kaldırıldı; genel issuer açıkça BLOCKED, revoke mevcut CAP-017 Kernel rotasına bağlandı. Dedicated readonly BootstrapReadback ve entry tenant/project/generation/witness kontrolü eklendi. Windows187PASS20SKIP;Linuxuid999 207PASS0SKIP. Gerçek DB/SELECT yetkisi/enrollment/profile/launcher bağları ve native kabul açık; P0-1/P0-3 yalnız kısmi ilerledi. G0OPEN,first13 0/13,tam16MOD/PH00–06 kapsamı korunur.


## 2026-11-13 — PostgreSQL okuyucu mekanizma kanıtı

[Geçici DB raporu](CODEX_POSTGRES_READER_20261113.md):uid999/PostgreSQL18.6 yeni private temp kümede bootstrap reader pozitif/12negatif PASS;actual readonly/repeatable-read ve restart sonrası readback doğrulandı. Stop/küme silme PASS; mevcut DB ve83guarded kaynak kullanılmadı. Minimal SQL fixture/sentetik roller gerçek RLS/enrollment/uygulama kabulü değildir. Ürün kodu değişmedi; önceki22pin aynı;207suite yeniden koşulmadı. Gerçek approved katalog/reader/enrollment/profile ve first13açık;G0OPEN,first13 0/13,tam modül kapanışı yok.


## 2026-11-13 — Native bootstrap readback ACL

[Dar native okuma ve deney raporu](CODEX_NATIVE_READBACK_ACL_20261113.md): SQL084 ve NativeBootstrapReadback eklendi; caller tablo yetkisi almıyor. 84 kaynaklı boş native katalog derleme/ACL PASS; FORCE RLS minimal pozitif witness ve12negatif/restart PASS. Windows192PASS20SKIP;Linux212PASS0SKIP. Gerçek native bootstrap/enrollment/launcher/verifier kabulü açık; G0OPEN,first13 0/13;tam16MOD/PH00–06 kapsamı korunur.


## 2026-11-13 — Root okuyucusu native sürücü düzeltmesi

[Önce/sonra kanıtı ve başlangıç bağımlılıkları](CODEX_ROOT_READER_20261113.md): read_root doğru native UUID kaydını string eşitsizliğinden reddediyordu; SQL text sınırı ve immutable beklenen kayıt snapshotı eklendi. Tam native katalogda sentetik admin insert/commit ve ayrı readback PASS; revoked/compromised/wrong digest ret. Gerçek kimlik/consent/custody/provisioning ACL kanıtı değildir. Linux214PASS0SKIP;Windows194PASS20SKIP;preflight24call0finding. G0OPEN,first13 0/13;tam16MOD/PH00–06 kapsamı korunur.


## 2026-11-13 — Başlangıç izninin güncelliği

[Kontrol bağlantısı ve sınırları](CODEX_CURRENT_WINDOW_20261113.md): SQL085 ve bootstrap_window.py mevcut r56 root/clock kontrolünü dar provisioning API üzerinden erişilebilir yapar. Native missing enrollment/wrong user/internal execute ret ve ACL PASS;gerçek pozitif current root/time kabulü açık. Bu genel runtime/observer yetkisi değildir. Linux221PASS0SKIP;Windows201PASS20SKIP;85kaynak inert assembly. G0OPEN,first13 0/13;tam16MOD/PH00–06 korunur.


## 2026-11-14 — Açılabilir görev ekranı

[Görev ekranı ve gerçek bağlantı sınırı](CODEX_GOREV_EKRANI_20261114.md):127.0.0.1:8766 local UI,iş isteği/kayıt sorgusu,existing Kernel execute/emission adapterı ve ofis gezinmesi hazır. Default gerçek backend bağlı değil;gönderim kapalı. Desktop/mobile browser PASS;mock gönderim/readback native kabul değildir. Windows211PASS20SKIP;Linux231PASS0SKIP. Gerçek DB/session/worker/verifier ve ilk teslim açık;G0OPEN,first13 0/13;tam16MOD/PH00–06 korunur.


## 2026-11-14 — Gerçek bağlantı başlatma yolu

[Pinli HTTP-Kernel başlatıcısı](CODEX_KERNEL_BAGLANTISI_20261114.md) eklendi;native metadata/ACL,unenrolled HTTP403,revoked transport ve superuser ret PASS. Gerçek bağlantı profili/oturum ve Objective commit/readback açık. Windows218PASS20SKIP;Linux238PASS0SKIP. G0OPEN,first13 0/13;tam16MOD kapsamı korunur.


## 2026-11-14 — Mevcut üyelikle oturum açma

[Oturum sınırları](CODEX_OTURUM_SINIRLARI_20261114.md):membership INSERT kaldırıldı;root/context/generation,trusted clock ve exact scope kilidi şartları eklendi. Native sorgu planları/missing root retPASS;gerçek pozitif session kurulumu açık. Bilinen local socketler boş;profile yok;tüm makine taranmadı. Windows225PASS20SKIP;Linux245PASS0SKIP. G0OPEN,first13 0/13;tam16MOD kapsamı korunur.


## 2026-11-14 — Ayrı veritabanı temeli çalışıyor

[Yerel PostgreSQL](CODEX_YEREL_POSTGRES_20261114.md) kuruldu;emptyDB/restart/peer/TCPkapalı doğrulandı. Uygulama şeması/ayrı leastprivilege bağlantı ve başlangıç authority/oturum sonraki iş;SQLguardlar değiştirilmedi. Gerçek Objective/agent/verifier teslimi açık;G0OPEN,first13 0/13;tam16MOD kapsamı korunur.
