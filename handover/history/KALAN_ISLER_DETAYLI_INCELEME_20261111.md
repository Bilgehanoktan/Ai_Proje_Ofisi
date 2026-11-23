# Kalan işlerin ayrıntılı incelemesi — 2026-11-11

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-11
Kaynak ajan: Codex
Durum: REVIEW_REQUIRED; kaynak ve sınırlı yerel deney incelemesi. Ürün/insan kabulü değildir.
Kanıt: evidence/KALAN_ISLER_INCELEME_20261111.json; aşağıdaki komut çıktıları ve doğrudan kaynak incelemesi.

## 1. Sonuç ve inceleme sınırı

Tam hedef mevcut mimarinin 16 modülü ve PH-00–PH-06 fazlarıdır. İlk SOFTWARE akışı ara teslimdir. Kapsam daraltılmadı. Yeni uygulama kökü AiProjeOfisi/, mimari referans GUNCEL/; compatibility/ ve ARSIV/ ürün runtime bağımlılığı yapılmadı.

Kaynakta önemli parçalar bulunuyor; bütün modülleri UYGULANMADI saymak yanlış. Bununla birlikte modül kartları tam davranış kabulünü kanıtlamıyor. Bu inceleme hiçbir modülü KABUL_EDILDI düzeyine yükseltmiyor. G0 OPEN ve first13 0/13 korunur. Toplam tamamlanma yüzdesi üretilemez: işlerin ağırlıkları ve AC bazlı kapanış kanıtları yok.

En acil iki teknik sorun verifier güven sınırı ve E2E API kablolamasıdır. Birim testler başarılıyken bu iki alanın açık kalabildiği doğrudan gösterildi. Ayrıca A kaynak bütünlüğü kontrolü başarısız ve durum/kanıt kayıtları güncel kodla tam uyumlu değil.

İnceleme kaynak kod değiştirmedi. Yeni rapor ve kanıt dosyaları oluşturuldu. PostgreSQL, Linux worker, model, gerçek enrollment veya PROD çalıştırılmadı. Tarayıcı/görsel/erişilebilirlik kabulü yapılmadı. Mevcut screenshot dosyalarının varlığı gözlendi; içerik, kaynak pini ve çekim koşulları bağımsız doğrulanmadı. Git metaverisi bulunmadığından commit/branch tabanlı karşılaştırma yapılamadı; seçili dosyalar SHA256 ile kaydedildi.

## 2. Bugün bağımsız doğrulananlar

| Kontrol | Sonuç | Ne kanıtlar / sınır |
|---|---|---|
| `C:\Python314\python.exe -B -m pytest AiProjeOfisi/tests -q -rs` | exit0; 89 passed, 4 skipped, 97 subtests passed; 4.23 s | Windows kaynak/birim/fake-driver ve yerel subprocess davranışları. Tüm mimari AC veya gerçek Linux kabulü değil. |
| `C:\Python314\python.exe -B GUNCEL/DOGRULA.py` | exit1; `AssertionError: dokumanlar/hedef-mimari-v1/CALISMA_DURUMU.md` | A tabanı bütünlük doğrulaması tamamlanmıyor. Öncesinde koşan testlerin hepsine toplu FAIL denmez; komutun bütünü PASS değildir. |
| E2E yerel `from ... import ...` AST denetimi | Eksik isim 0 | Önceki eksik import listesi artık aynı haliyle geçerli değil. Bu sonuç constructor/method/return uyumu değil. |
| E2E `inspect.signature(...).bind(...)` | Dört çağrı uyumsuz; ayrıca `LinuxLauncher.launch` yok | DB/worker başlatmadan mevcut API uyuşmazlıkları doğrulandı. |
| Panel modül ayrıştırıcısı | 16 modül okundu | Önceki sabit liste kusuru için kaynak ilerlemesi var; paneldeki iddiaların teknik doğruluğu ayrıca denetlenmeli. |
| Yeni false-pass adayı | PASS, 13/13 | `normalize_title` tanımlamayan aday kaynak dosyasındaki CASES verisini okuyup protokolü taklit etti. Kritik açık sürüyor. |
| READY deadline deneyi | Limit 0.1 s, aday beklemesi 0.5 s, dönüş 0.565 s | Deadline bloklayan okumayı zamanında kesmiyor. Nihai FAIL dönmesi süre sınırının uygulandığını kanıtlamıyor. |

Dört SKIP: engine socketpair denemesi, Linux FIFO/selectors ve iki secret-adapter Linux fd/owner/mode kontrolü. Bunları dört rootless/cgroup testi diye adlandırmak yanlış. Bugünkü koşum gerçek namespace/cgroup izolasyonunu doğrulamadı.

Yeni negatif deneylerde test alt sürecine UTF-8 I/O ayarı ve 3 saniyelik dış kill watchdog uygulandı. Bu, deneyin güvenli sınırıdır; ürünün kendi timeout mekanizmasının başarısı değildir. İlk ek deney sonuç üretmeden kesildi; onun üzerinden teknik sonuç çıkarılmadı. Kanıt JSONu tamamlanan sınırlı deneyleri içerir.

## 3. Kritik bulgular ve kapanış ölçütleri

### K01 — P1: Verifier beklenen cevapları adaydan gizlemiyor

Kaynak: `company_os/verifier_runner.py:30,98`; `company_os/candidate_runner.py:25`.

`sys.path` temizliği ve `cwd` değişikliği dosya erişim yetkisini değiştirmiyor. Yeni aday `__main__.__file__` üzerinden `candidate_runner.py` konumunu buldu, komşu `verifier_runner.py` dosyasını doğrudan okuyup CASES ifadesini değerlendirdi. Hiç `normalize_title` tanımlamadan READY ve cevap protokolünü taklit ederek 13/13 aldı. Tekrarlanabilir aday metni ve rapor JSON kanıtında mevcut.

Mevcut negatif test import yoluyla CASES erişimini deniyor. İmport bağımlılığı bozulunca test PASS olabiliyor; dosyayı okuyarak aynı bilgiye erişim sınanmıyor. Sonuç: TASK-20261110-P0-1 için TAMAMLANDI ve “mühürlendi” iddiası geçerli değil.

Kalan iş: producer/candidate için gerçek OS erişim sınırı; fixture, harness, rapor statei ve signer erişiminin ayrılması; yalnız sınırlı giriş/çıkış portu. Test doubles ve demo koşumu kabul yolundan ayrılmalı. Kapanış: bu aday reddedilmeli, reference PASS/baseline FAIL/mutant FAIL korunmalı; gerçek uid/mount/process sınırı ve kaynak/build pinleri kanıtlanmalı. Sadece aday metnini filtrelemek çözüm değildir.

### K02 — P1: Timeout, stderr ve süreç ağacı sınırları tamamlanmamış

Kaynak: `company_os/verifier_runner.py:49–69,98–125`; test: `tests/unit/test_verifier_runner.py:281`.

`stream.read(1)` bloklayan pipe okumasıdır. Önündeki zaman kontrolü okuma sırasında çalışmaz. 0.1 saniyelik READY sınırıyla 0.5 saniye uyuyan adaydan 0.565 saniyede dönüldü. Mevcut test 3 saniye uyuyan adaya 4 saniyeden kısa dönüşü yeterli görüyor; 2 saniyelik READY sınırını doğrulamıyor. stderr PIPE açılıyor ama tüketilmiyor. Temizlik doğrudan child terminate/kill/wait yapıyor; süreç ağacı/cgroup kapanışı kanıtlanmış değil.

Kalan iş: READY dahil deadline kontrollü gerçek non-blocking/bounded binary okuma; stdout ve stderr birlikte sınırlandırma; toplam süre/bayt sınırı ve process-tree cleanup. Kapanış: newline göndermeyen, stderr dolduran, geciken ve child bırakan sınırlı negatiflerde üst süre ve artık süreç yokluğu doğrulanmalı. Sınırsız hang/flood deneyi bu incelemede çalıştırılmadı.

### K03 — P1: Importlar düzelmiş, E2E constructor ve sonuç sözleşmeleri hâlâ uyumsuz

Kaynak: `tools/disposable_e2e_workflow_trial.py:2033,2043,2188,2215–2242`; owning APIler `launch_controller.py`, `engine_bridge.py`, `reply_guard.py`.

| Betikteki kullanım | Güncel API / somut fark |
|---|---|
| `LinuxLauncher(so_path)` | 10 zorunlu argüman var; ilk eksik `library_digest`. |
| `launcher.launch(consume_ticket, plan)` | `launch` metodu yok; mevcut API `spawn(self,t)`. |
| `EngineReplyGuard(rt_port)` | Yalnız keyword `scope,binding` kabul ediyor. |
| `PipeTransport(read_fd=...,write_fd=...)` | `stdout_fd,stdin_fd,stderr_fd` bekliyor. |
| `EnginePump(runtime=...,limits=...,tenant_id=...,...)` | `emission_guard,stop_request,lease_remaining,timeout` bekliyor; verilen sözleşme farklı. |
| `pump_result.frames_processed/halted_reason` | Mevcut `run()` dönüşleri dict; `frames,outcome` anahtarları kullanıyor. |

İlk dört constructor için side-effect üretmeyen signature bind TypeError doğrulandı; method yokluğu da doğrulandı. Dönüş uyuşmazlığı kaynak incelemesidir. `PumpLimits` ve `SpawnPlan` isimlerinin eklenmesi mevcut çalışan sınıflarla entegrasyonu tamamlamıyor. Launcher probe hatası genel `except` içinde not edilip devam edebiliyor; bypass edilmiş probe gerçek izolasyon kabulü sayılmamalı.

Kalan iş: betiği owning portlara uyarlamak; required guard, scope, lease, manifest ve descriptor bağlarını sağlamak; constructor, method ve result schema preflightını DB açmadan çalıştırmak. Kapanış: yalnız import0 değil, bütün giriş/çıkış sözleşmelerinin uyumu ve ardından yetkili sınırlı gerçek pozitif/negatif koşum. TASK-20261110-P0-2 TAMAMLANDI iddiası kabul edilemez.

### K04 — P1: Sonradan eklenen yardımcılar güvenli owning davranışı taşımıyor

Kaynak: `company_os/secret_adapter.py:52`; `company_os/consent_binding.py:58`.

`read_enrolled_key` Linux fd, owner, 0700 directory, 0400 regular file, 32 byte ve no-follow kontrolleri yapıyor. Yeni `read_secret_bytes` ise str/Path gelince doğrudan `Path.read_bytes()` ile bu kontrolleri atlıyor; E2E betiği path kullanıyor. Bu yardımcıyla enrollment/custody doğrulanmış sayılamaz. `owner_uid or 999` ayrıca açıkça verilen 0 değerini de değiştirir.

`verify_owner_installation_consent` aldığı `expected_human_id` değerini kullanmıyor; yalnız hash eşitliği ve JSON parse yapıyor. Eski `OwnerConsentBinding.check` içindeki workspace/statement/duplicate-key/root bağlarını taşımıyor. `authority_granted=False` dönmesi önemli sınırdır: burada doğrudan yetki elde edildiği iddia edilmiyor. Ancak fonksiyon adına dayanarak identity/consent doğrulandı denemez.

Kalan iş: shim yerine mevcut enrolled-key ve consent binding sınırlarını kullanmak; gerekliyse test-only fixture yolunu açık ayırmak. Kapanış: yanlış owner/mode/length/symlink ve yanlış insan/workspace/duplicate-key/pin negatifleri. Bu incelemede gerçek anahtar veya onay belgesi içeriği okunmadı.

### K05 — P2: Oracle pini ilerleme, tam harness/build pin doğrulaması açık

Kaynak: `company_os/verifier_runner.py:72–82,250`.

Varsayılan yolda exact oracle SHA256 reddi eklenmiş; eski içerik-parçası dalı kaldırılmış. Önceki R2-02 aynı haliyle tekrar edilmemeli. Ancak yürütülen CASES mantığı oracle dosyasında değil verifier runner içinde; oracle hashini kontrol etmek bu mantığı tek başına pinlemez. `allow_unpinned_oracle=True` için ayrı güvenilir test bağlamı şartı görünmüyor. Ürün wiringinde bu yolun açıldığı bu incelemede gösterilmedi.

Kalan iş: trusted manifestten harness/candidate runner/profile/build pin doğrulaması; test-only bypassın üretim girişinde kapalı olması. `seal_and_accept` girişindeki outcome/passed kontrolü tek başına rapor–candidate–patch–head kimlik bağının doğrulanması değildir; tam zincirin bağımsız testi gerekir.

### K06 — P2: Panel kaynak matrise bağlanmış; gerçek ürün readback UI yolu hâlâ ayrı

Kaynak: `presentation/preview_generator.py:16,69`; `presentation/app.py:42,82,201–240`.

Panel artık matris içeriğini okuyor ve SHA256 gösteriyor. 16 modül ayrıştırıldı; WSGI server kaynağı da mevcut. “Sunucu yok” veya “bütün durumlar sabit” eski bulgularını aynen taşımak yanlış.

Bununla birlikte WSGI `/`, `/preview`, `/api/status` yolları matris önizlemesi sunuyor; `AuthenticatedReadbackApp` domain okuma sınıfını gerçek HTTP oturumuna bağlamıyor. Domain iş verisi için auth, 401/403/409, yetkili command, snapshot/cursor/resync ve restart sonrası reload henüz kanıtlı değil. Altı detay okuması ayrı command çağrıları; tek atomik workflow snapshot tutarlılığı ayrıca incelenmeli, gözlenmiş tutarsızlık iddia edilmiyor.

Kalan iş: V1'de kaynak tarihini, kanıt sınıfını, güncel açık bulguları ve birbirinden ayrı G0/first13 göstergelerini doğru sunmak; V2'de gerçek authorized DB readback ve command akışını HTTP katmanına bağlamak. Screenshot varlığı visual acceptance değildir; masaüstü/dar ekran/klavye/boş-hata-yükleniyor durumları bağımsız denetlenmeli.

### K07 — P2: Durum, görev ve kanıt kayıtları hâlâ çelişiyor

`module-map.json` 16 modülün tümünde `NOT_IMPLEMENTED` tutuyor; matris tümünü kısmi kaynak hazır gösteriyor. README ve implementation_status.json eski test sayıları ve tarihler taşıyor. Kaynak pinleri ve eski Codex yorumları tarihsel kapsamlarıyla korunmalı; değişmiş dosyaların önceki kontrolü güncel doğrulama gibi sunulmamalı.

Görev tablosu üçten altı satıra çıkmış; fakat modül kartlarındaki P1-1..P1-9 ve P2 görevlerinin tamamı gerçek §28 TaskSpec kayıtlarına bağlı değil. EV-20261110-UNIT-02/V1-PREVIEW eklenmiş; önceki “yok” bulgusu kısmen giderilmiş. EV-20261110-E2E-PREFLIGHT görevde referanslı, kanıt tablosunda ayrıntısı yok. Kısaltılmış screenshot hashleri ve test dizini referansı tam raw log/manifest yerine geçmez.

Kalan iş: görev→REQ/BR/AC/TEST→exact kaynak/config/fixture→komut/log→independent review zinciri. Her görev için somut allowlist, base hash, negatif, rollback ve çıkış ölçütü. HSM, iki ayrı insan onayı veya ayrı daemon gibi source tarafından zorunlu tutulmayan ek gereksinimler iş kuyruğuna kendiliğinden eklenmemeli.

### K08 — P2: A kaynak bütünlüğü doğrulaması başarısız

Bugünkü DOGRULA koşumu CALISMA_DURUMU.md pininde exit1 verdi; beklenen ve gerçek hash kanıt JSONunda. Kalan iş dosyanın hangi yetkili belge değişikliğiyle ayrıştığını belirlemek, ardından owning manifest üretim süreciyle gerekçeli düzeltme ve tam doğrulama. Sadece manifest hashini güncellemek kök neden veya kabul kanıtı değildir. Burada manifest değiştirilmedi; başka mismatch olmadığı iddia edilmedi.

## 4. On altı modül için kalan işler

Aşağıdaki “mevcut” alanı kaynakta görülen alt kapsamı özetler; tüm modülün acceptance sonucu değildir. AC/TEST numaraları tasarım/matris eşlemesidir; pytest test sayısıyla karıştırılmaz.

| Modül / faz / AC-TEST | Mevcut dayanak | Kalan somut teslim ve kapanış kanıtı |
|---|---|---|
| MOD-001 Kimlik/Policy/Command / PH-01,04 / 004,012 | command_host, provisioning, session, registry/clock kaynakları | Güvenilir enrollment/consent/key yolu; current clock/policy/session/grant bağları; yetkili create/readback, wrong-scope ve revoked ret; HTTP auth bağlantısı. K03/K04 öncelikli. |
| MOD-002 Hedef/Plan/CEO / PH-00,01 / 001,005 | DTOlar, constructor, plan/task kaynakları | Objective→immutable Plan→Task READY kalıcı zinciri; DAG/tekrar istek/rollback; ajan CEO plan ve DecisionCase önerisini yetki genişletmeden bağlama. Gerçek model/plan kalite kabulü ayrı. |
| MOD-003 Scheduler/Qualification / PH-02 / 006 | Qualification, admission, lease/fence/claim kaynakları | Exact model/rol/tool/suite/catalog/resource tuple; çift claim, stale fence, lease expiry, heartbeat, revoke; admission sonrası gerçek worker binding readback. |
| MOD-004 Launch/Isolation / PH-02 / 007 | LinuxLauncher, native spawn, watchdog | Pinli binary ve rootless uid/cgroup/namespace/fd bağları; gerçek spawn/stop; timeout/crash/revoke ve bağımsız ölüm gözlemi. K03 giderilmeden E2E probe kabulü yok. |
| MOD-005 Engine/Provider / PH-02 / 002 | FrameBuffer, transport, EnginePump, reply guard | Pump API kablolaması; local/free-default exact model pinli tek görev; Linux pipe/socket, partial frame/deadline/EOF negatifleri. Ücretli sağlayıcı açmak ilk teslimin şartı değil. |
| MOD-006 Broker/Etki / PH-02 / 008 | broker, executor, journal kaynakları | DB consume→execute→receipt atomik sınırları; izinli tek dosya, yanlış path/egress/replay/revoke/crash; UNKNOWN reconciliation; gerçek OS enforcement. |
| MOD-007 Workspace/Patch/Artifact / PH-03 / 009 | CAS/staging/patch/provenance kaynakları | Exact immutable head/base/build bağları; artifact readback hash; bozuk UTF-8/oversize/tamper/conflict ret; verifier'a değişmez aday aktarımı. Genel otomatik merge ilk kabulün yerine geçmez. |
| MOD-008 Verifier / PH-03 / 010 | runner, 13 case, signer/pipeline | K01/K02/K05; gerçek candidate erişim sınırı, güvenilir harness/report/fixture/key ayrımı; doğru/yanlış/sahte aday negatifleri ve tüm kaynak pinleri. |
| MOD-009 Acceptance/Release / PH-03 / 011 | native final seal/provenance/accept yolları | candidate→patch→head→profile→report→evidence→accept bağları ve ayrı kimlikler; stale/missing/fake receipt reddi; ayrı DB readback. Technical accept, insan kabulü ve PROD farklı kapılar. |
| MOD-010 Event/Projection / PH-04 / 013 | SQL event map, read-model parçaları | OfficeEvent/EventEnvelope alan ve typed epoch eşlemesi; authorized snapshot cutover/cursor/replay/resync/gap/revoke; restart sonrası tutarlı read model. Ayrı servis açmak kendiliğinden zorunlu değil. |
| MOD-011 Yönetim/Ofis / PH-04 / 014 | dinamik V1 generator, WSGI preview, readback sınıfı | V1 doğru kanıt/durum ve görsel denetim; V2 gerçek oturum/HTTP command/readback/reload; narrow ekran ve hata/boş/yükleniyor/klavye kanıtları. Geniş Office görünümü gerçek domain kanıtından ayrı. |
| MOD-012 Katalog/Hafıza / PH-01,06 / 015,016 | katalog/registry sözleşmeleri | İlk akışta exact katalog/lisans/provenance pinleri; sonra tenant ACL, promotion onayı, source provenance, revoke/tombstone/readback. Vektör DB veya ayrı knowledge servisi source kararı olmadan zorunlu değil. |
| MOD-013 WorkType / PH-06 / 019,020,021 | SOFTWARE MGT01 fixture/oracle | Önce SOFTWARE gerçek zincir ara kabulü; sonra Research/Spreadsheet/Obligation seçili dalına göre schema/oracle/data rights/locale-TZDB/provenance/negative/reload. Bu dallar kapsamda, etkinleşmeleri fazlı. |
| MOD-014 Bütçe/Ticari/Dış etki / PH-02,05 / 017,018 | reservation/accounting/effect sözleşmeleri | İlk attempt'te kaynak bütçesi ve UNKNOWN rezervasyon/settlement; PH-05 sentetik ledger duplicate/idempotency/reconciliation. Gerçek ödeme/fatura/paid fallback ayrı izinli; kapalı olmak hata değil. |
| MOD-015 Operasyon/Recovery / PH-05 / 022,027 | disposable lifecycle ve stop/recovery SQL | Bounded stop/crash/UNKNOWN temizliği; bağımsız medya backup/witness, fenced restore, eski grant/outbox dirilmeme; ölçülmüş RTO/RPO ve recovery runbook. Aynı disk arşivi backup kabulü değil. |
| MOD-016 Teslimat/ADR/Kalite / PH-00,01,03 / 003,023–026 | doğrulayıcılar, matris, kısmi kanıtlar | K07/K08; tüm TaskSpec ve AC-test bağları; pinli source/build/config/fixture/log manifesti; bağımsız review ve reproducible paket/CI. Donanım imzalayıcı eklemek kendiliğinden şart değil. |

## 5. Tasarım borcu: kod işlerinden ayrı açık tutulmalı

Eski KALAN_ISLER_20261107.md tek başına güncel backlog değildir. Sonraki owning belgeler (özellikle MIMARI_ACIKLARI_TAMAMLAMA_v1.md ve yol haritasının ekleri) aday teknik yönleri ilerletmiş; “karar bekliyor” disposition sayısı 0 olarak kaydedilmiş. Bu 14 operational OPEN kaydının kapandığı veya full-source semantik kabul verildiği anlamına gelmiyor.

| Açık grup | Kalan doğrulama | Bağlandığı işler |
|---|---|---|
| OPEN-001 | A/B owning-source kararlarının bağımsız semantik ratifikasyonu; A91/370 aile/REQ izleri | PH-00, MOD-016; bütün modüllere toplu PASS dağıtma. |
| OPEN-002,014 | Gerçek executable consumer/converter, field-loss/roundtrip ve migration/deployment envanteri | MOD-001/002/010/016; reader-first/shadowvalidate/fence/readback/rollback. |
| OPEN-003 | LIVE epoch/freshness/snapshot/cursor/SSE uygulama kanıtı | MOD-010/011; belge fixtureları gerçek stream değil. |
| OPEN-004,007,010 | DB/OS/model/host/resource ve işyükü/SLO gerçek kanıtları | PH-01–04; kesin performans/gün taahhüdü üretilemez. |
| OPEN-005,008,009 | Gerçek enrollment/custody, uygulanabilir insan yetkisi ve restore-dışı witness | MOD-001/008/009/015; tek-insan kararı korunmalı. |
| OPEN-006 | Koşullu PASS/required/slot, exact receipt, zaman/iptal ve negatif oracle enforcement | MOD-003/008/009/016. |
| OPEN-011–013 | Ticari ölçüm/izin, veri-hukuk/lisans ve seçili WorkType kaynakları | PH-05/06; ayrı dal bazlı aktivasyon ve kabul. |

Sentetik bootstrap/session commit ve ayrı readback raporları mevcut. En yeni görülen NATIVE_CLOCK_TRIAL_5d9ba3d2.json da sentetik bootstrap/session kapsamında; kaynak iddiası REPORTED_NOT_RETESTED. Bunlar yok sayılmamalı; gerçek owner login/enrollment, worker, model, bağımsız verifier veya tam E2E kabulüne yükseltilmemeli.

## 6. Bağımlılık sırasıyla uygulanabilir iş paketleri

Bu bölüm inceleme sonucudur; kaynak değişikliği, yeni enrollment veya dış etki yürütme kararı değildir. Mevcut TaskSpec kayıtlarıyla birleştirilmeli, paralel ikinci backlog yaratılmamalı.

| Sıra | Paket | Bağımlılık / kapanış |
|---|---|---|
| 1 | Verifier güven sınırı ve deadline onarımı | K01/K02/K05 negatifleri; sahte PASS artık mümkün olmamalı. PH-01 kaynak işlerinden bağımsız ilerleyebilir. |
| 2 | E2E owning API preflight ve güvenli yardımcılar | K03/K04; DB açmadan imza/metod/return schema uyumu ve bypass negatifleri. İsim eklemekle bitmez. |
| 3 | Kanıt ve A bütünlük düzeltmesi | K07/K08; kaynak değişikliği gerekçesi, tam log/manifest, bütün kart görev bağlantıları. 1–2 ile bağımsız hazırlanabilir. |
| 4 | PH-01 yetkili DB dikey dilimi | Gerçek identity/clock/policy/session önkoşulları; Objective/Plan/Task READY commit + ayrı readback; scope/rollback/idempotency/revoke negatifleri. |
| 5 | PH-02 qualification→worker→engine→broker | 4 + exact Linux/model/resource profile; çift claim/stale fence/path/timeout/crash; bağımsız stop. |
| 6 | PH-03 artifact→verifier→Kernel accept/reject | 1 + 5; aynı source/build chain üzerinde doğru patch kabulü ve mutant/sahte receipt reddi. |
| 7 | PH-04 authenticated UI ve kalıcı reload | 6; gerçek HTTP oturumu, authorization, snapshot/cursor/resync; yeniden giriş ve DB restart sonrası readback. İlk 13 zincir ve insan kapıları burada ayrı değerlendirilir. |
| 8 | PH-05 operasyon ve sentetik ticari akış | 7; fenced restore/old-grant negatifleri, backup/witness, duplicate/UNKNOWN reconciliation. |
| 9 | PH-06 katalog/hafıza ve seçili WorkType | 8 ve dal önkoşulları; source rights/schema/oracle/ACL/tombstone ve bağımsız dal kabulü. |

V1 görünür geliştirme paneli için 7. paketi beklemek gerekmiyor: dinamik kaynak mevcut; K07 ile doğru durum/kanıt sunumu ve bağımsız görsel denetim ayrı, erken teslim olabilir. V2 ilk gerçek çalışan akış 4→5→6→7 yolunu ve 1–2 güvenlik düzeltmelerini gerektiriyor. PH-05/06 tam hedefin devamıdır.

Kesin süre verilmedi. Linux/cgroup/model/enrollment/clock hazırlığı ve ilk gerçek wiring deneyi yapılmadan önceki 3–5 / 8–14 gün aralıkları doğrulanmış takvim sayılamaz. Sonraki süre değerlendirmesi paket bazlı gerçekleşen emek, ortam beklemesi ve yeniden test ölçümleriyle yapılmalı.

## 7. Teslim kanıtının biçimi

Her pakette şu kayıtlar birlikte bulunmalı: TaskSpec ve REQ/BR/AC/TEST; canonical allowlist ve başlangıç SHA256; exact source/build/config/fixture pinleri; ortam ve gerçek komut/exit; beklenen-gözlenen pozitif/negatif sonuç; redakte ham log; bağımsız readback; cleanup/rollback; bağımsız review; gereken insan kabulü. UNIT, FAKE_DRIVER, SYNTHETIC_NATIVE, ACTUAL_RUNTIME ve HUMAN_ACCEPTANCE ayrı yazılmalı.

Bir dosyanın/screenshotın varlığı, bir testin PASS olması veya rapor digestinin hesaplanması tek başına diğer kanıt sınıflarını sağlamaz. Bu rapor mevcut Antigravity/Codex tarihsel alanlarını değiştirmez; yeni 2026-11-11 inceleme katmanıdır.
