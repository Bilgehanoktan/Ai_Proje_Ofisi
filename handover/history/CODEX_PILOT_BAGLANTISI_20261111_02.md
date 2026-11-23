# Kanonik pilot bağlantısı — ikinci uygulama dilimi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-11
Kaynak ajan: Codex
Durum: SOURCE_AND_FAKE_DRIVER_VERIFIED; ayrı bağımsız inceleme ve gerçek runtime kabulü açık
Kanıt: evidence/CODEX_PILOT_20261111_02_FINAL_CHECK.json; pytest_FINAL.log; preflight_FINAL.log; kaynak manifesti.

## Uygulanan bağlantı

Mevcut `company_os/composition.py` içindeki `PilotSession` tek composition kökü olarak geliştirildi. Mimari dayanak hedef tasarım §12, §15 MOD-004..007/015, §16 port tablosu ve BR-006..010'dur. Yeni servis, provider, domain writer veya runtime ağacı eklenmedi.

Kaynak akışı: explicit worker/controller auth → üç controller signer → exact EngineBinding ve watchdog identity → ProducerOutputAdapter → Broker → ToolKernel/effect transaction → PatchReceiptRecorder → current EngineReplyGuard → bounded cevap → stop request/cleanup. Domain yazıları CommandHost, dosya etkisi Broker üzerinden kalır.

`PilotSession.from_launch_observation` mevcut LinuxLauncher çıktısındaki parent stdin/stdout/stderr uçlarını `PipeTransport.from_observation` üzerinden bu akışa bağlar. Beklenen host boot ID, cgroup inode, pozitif PID, ayrı pidfd/pipe descriptorları ve lease host bağı kontrol edilir. Constructor imzası pipe devrinden önce kontrol edilir; bilinmeyen/eksik argüman transferred descriptor sızıntısına yol açmamalıdır.

Bu giriş trusted supervisor portudur. Metadata eşleşmesi enrollment veya exec attestasyonu değildir; `CREATED_NOT_EXEC_ATTESTED` yükseltilmez. Üç pipe'ın sahipliği transfer edilir; pidfd bağımsız gözlem için çağıranda kalır. Metadata ret durumunda stop istenir; pipe sahipliği devredilmediği için özgün descriptorların kapatılması çağıranın sorumluluğundadır. Gerçek Linux çağrısı bu tur çalıştırılmadı; descriptor transferi fake portla sınandı.

## Scope, lease ve yaşam döngüsü

- `EngineBinding` yeniden validate edilir; `model_copy/model_construct` kaynaklı geçersiz bindinge güvenilmez.
- İki auth aynı task/project/attempt/fence ve ATTEMPT resource'a bağlanır. Tenant alanı verilmişse signer tenantıyla eşleşir. Controller signer issuerları ve üç ayrı key ID kontrol edilir. Worker/controller token ve grantlerinin doğrudan tekrar kullanımı reddedilir. Bu alan farkları gerçek bağımsız principal veya key custody kanıtı değildir; native current authority kontrolleri gereklidir.
- Auth ve binding kopyalanır; çağıranın sonradan auth sözlüğünü değiştirmesi kurulmuş port scope'unu değiştirmez.
- Lease `process_id/attempt_id/fencing_epoch` ile eşleşir; identity değişimi veya expiry okuma/etki öncesinde reddedilir. Zaman uzatımı yeni bir timer ile uydurulmaz; mevcut enrolled watchdog nesnesi kullanılır.
- Constructor sonrası başarısızlıkta ve çalışma sonunda stop/transport/executor temizliği uygulanır. Başarısız stop sonraki çağrıda sessiz başarıya dönüşmez. Tek session tekrar çalıştırılamaz; belirsiz etki otomatik tekrar edilmez.
- `CgroupStopRequest` kısmi/başarısız kill yazımını kalıcı UNKNOWN gerektiren yerel duruma geçirir. Başarılı kill isteği bağımsız quiescence veya budget settlement sayılmaz. Bu davranış mock OS portlarıyla test edildi, cgroup enforcement kabulü verilmedi.

## Commit sonrası patch teslimi

`PatchReceiptRecorder` bir kez kullanılır. Gerçek native `r58_patch_receipt` dönüşündeki `patch_id`, `attestation`, `result_head`, `patch_digest` alanları signed effect/receipt kimliğiyle karşılaştırılır. Owning SQL kaynağı `sql/040_R58_PATCH_ACCEPTANCE_NATIVE.sql:26` incelendi; SQL değiştirilmedi.

`confirmed` ancak CommandHost commit-confirmed cevabı doğrulanınca doldurulur. Lost commit acknowledgement, bozuk head/digest veya ikinci kayıt denemesi başarı üretemez. `PilotSession.run()` tek frame için yalnız `PATCH_RECORDED_STOP_AND_VERIFY_REQUIRED` ve doğrulanmış receipt ile sonuç döndürür. Sonuç exact task/attempt/fence/process/engine kimliklerini ve receipt kopyasını taşır. Bu kopya yeni otorite deposu değildir; downstream işlem current canonical readback yapmak zorundadır.

Sonuç alanları `verification=NOT_RUN`, `quiescence=NOT_OBSERVED` olarak kalır. Bağımsız verifier/acceptance veya stop settlement bu kaynaktan otomatik türetilmez.

## Doğrulama ve sınırlar

`C:\Python314\python.exe -B -m pytest AiProjeOfisi/tests -q -rs`: **exit0, 121 PASS, 4 SKIP, 112 subtest PASS**, 8.04 s. Önceki paket 104 PASS/4 SKIP idi; fark 17 yeni composition/handoff/stop testidir. Test sayısı mimari AC sayısı değildir.

Yeni entegrasyon testlerinde gerçek composition, producer, Broker, kernel adapter, patch recorder ve emission guard Python kodu birlikte çalışır. DB-API fake, Linux executor yerine portable fixture ve transport yerine test portu kullanılır. Dosya etkisi yalnız geçici fixture üzerindedir; gerçek PostgreSQL, Linux namespace/cgroup, model, enrollment veya provider çalıştırılmadı.

Pozitif kanıt: parçalı model çıktısı → proposal staging → consume/effect transaction → COMMIT → patch receipt COMMIT → current reply guard → cevap → stop/cleanup; tek dosya yazımı, tek patch kaydı ve exact receipt dönüşü. Etki okuması ile etki yazımı aynı fake transaction bağlantısındadır.

Negatif kanıtlar: effect/patch commit onayı kaybında sıfır cevap ve yeniden dosya etkisi yok; commit sonrası revoke durumunda sıfır cevap; yanlış receipt headi; yanlış task/project/fence veya aynı session/grant; expired/changed lease; setup hatası; stop hatasının tekrarda sessiz başarı olmaması; cancel-before-run; yanlış launcher host/cgroup/alias FD; handoff öncesi Python argument hatası. Cleanup ownership testlerinde tek close/stop istenir.

Dört SKIP önceki engine socketpair/FIFO ve iki Linux secret-adapter testidir. Gözlenen Windows Python3.14.3/Pydantic2.12.5 ortamı, requirements2.14.0 hedef ortam qualificationı değildir.

`workflow_preflight.py` final koşumu exit2/BLOCKED: 43 doğrudan çağrı, 17 uyumsuzluk. Eski `disposable_e2e_workflow_trial.py` yeni composition akışına henüz bütünüyle uyarlanmadı. Yeni bağlantı ve fake-driver testi bu 17 kusurun kapandığı anlamına gelmez. Wrapperın ortam kurmadan ret koşulu korunur.

`GUNCEL/DOGRULA.py` bu dilimde yeniden koşulmadı; önceki paketteki CALISMA_DURUMU.md hash uyuşmazlığı açık, REPORTED_NOT_RETESTED. GUNCEL/STATE/SQL/manifest ve gerçek DB değiştirilmedi. G0 OPEN, runtime NOT_RUN, first13 0/13.

## TaskSpec — TASK-CODEX-20261111-04

| Alan | Kapsam |
|---|---|
| Amaç | Mevcut launcher→composition→engine/Broker→patch/receipt→stop bağlantısını exact scope ve belirsizlik sınırlarıyla kaynakta uygulamak |
| MOD / faz | MOD-004/005/006/007/015/016; PH-02/03 kaynak hazırlığı |
| REQ / BR / AC / TEST | REQ/BR/AC/TEST-006..010, ayrıca 022/027 stop/recovery alt sınırları; tam AC seti kabulü yok |
| Girdi / owning source | Hedef tasarım §16; composition, engine/broker/kernel/patch portları; r58_patch_receipt SQL dönüşü |
| Allowlist | company_os/composition.py, company_os/patch_pipeline.py, tests/unit/test_pipeline.py; yeni tests/unit/test_composition.py; PLAN.md, UYGULAMA_DURUM_MATRISI.md, bu rapor ve CODEX_PILOT_20261111_02 önekli kanıtlar |
| Önkoşul | Supervisor sağladığı exact auth/signer/binding/directory fd/source ölçümü/watchdog/stop portları; gerçek enrollment/qualification ayrı |
| Başlangıç / bitiş pinleri | evidence/CODEX_PILOT_20261111_02_BASE.json ve MANIFEST.json; yeni test dosyası başlangıçta ABSENT |
| Çıkış | Pozitif chain + commit/revoke/lease/cleanup negatifleri kaynak/fake-driver PASS; gerçek OS/DB/verifier kabulü açık |
| Rollback | Değişen mevcut dosyaların byte-exact .before yedekleri BACKUP dizininde. Her dosya için mevcut son pin değişmemişse baseline byte ve hashle restore edilebilir; concurrent değişiklikte overwrite yapılmaz. Yeni dosya bağımlılıkları denetlenmeden kaldırılmaz. Otomatik rollback çalıştırılmadı; DB/grant/epoch geri sarılmaz. |
| Bağımsız review | PENDING; yazarın kaynak testi ayrı bağımsız ajan veya insan kabulü değildir |

## Mevcut planda devam

Bu dilim MOD-004..007/015'in seçili kaynak bağlantısıdır; tam16MOD/PH00–06 hedefi korunur. MOD-008'in gerçek ayrı OS kimliği/fixture izolasyonu ve enrolled receipt validatorı açık. MOD-010/011 authenticated UI/reload, PH-05 restore/ticari kayıt ve PH-06 katalog/hafıza/WorkType dalları kapsamda kalır.

Sıradaki uygulama eski E2E betiğinin custom runtime katmanını bu canonical composition portlarıyla değiştirmek ve güncel Kernel command/result sözleşmelerine taşımaktır. Trusted profile, actual source snapshot/head, launch/engine binding ve signer enrollment verileri uydurulmaz. Yeni `from_launch_observation` girişi bu geçişte kullanılabilir; gerçek Linux/DB koşumu ancak kendi önkoşulları ve kanıtıyla değerlendirilir.
