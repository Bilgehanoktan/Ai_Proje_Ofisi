# Observer/verifier servis dilimi — kaynak teslimi ve gerçek kabul engelleri

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-12
Kaynak ajan: Codex
Durum: SOURCE_COMPONENTS_IMPLEMENTED_AND_TESTED; ACTUAL_INTEGRATION_BLOCKED; bağımsız review PENDING
Kanıt: evidence/CODEX_SERVICE_20261112_windows_tests.log; evidence/CODEX_SERVICE_20261112_linux_tests.log; evidence/CODEX_SERVICE_20261112_distinct_uid.json; evidence/CODEX_SERVICE_20261112_inventory.json; evidence/CODEX_SERVICE_20261112_preflight.json; evidence/CODEX_SERVICE_20261112_manifest.json.

## TaskSpec ve kapsam

TASK-CODEX-20261112-05; mevcut hedef tasarım §16/27/28; MOD-004/008/009/015/016, PH-02/03 kaynak bağlantıları. REQ/AC/TEST-007/010 alt güven/ölçüm/kabul sınırlarına katkı; tam AC veya modül kabulü değildir. Kullanıcının tamamla talebi bu dilimde servis/IPC ve verifier kodu ile testlerinin uygulanmasını kapsadı; gerçek enrollment, qualification veya insan onayı uydurulmadı.

Allowlist: yeni company_os/peer_rpc.py, runtime_verification.py, supervisor_service.py; yeni tools/probe_peer_rpc_identity.py; yeni tests/unit/test_peer_rpc.py ve test_runtime_verification.py; tests/unit/test_workflow.py; tools/workflow_preflight.py ve test_workflow_preflight.py; config/README.md; bu rapor/takip belgeleri/CODEX_SERVICE_20261112 kanıtları. Mevcut kaynak başlangıç byte yedekleri BACKUP dizininde; yeni dosyalar başlangıçta ABSENT. Önceki devir CODEX_OBSERVER_OLCUM_20261112.md. Tam16MOD/PH00–06 hedefi korunur.

## Uygulanan servis kodu

peer_rpc.py: Linux AF_UNIX/SOCK_SEQPACKET, gerçek SO_PEERCRED ve ayrı non-root UID kontrolü, bounded JSON/paket/deadline, exact operation/request UUID/response eşlemesi, duplicate/nonfinite/extra alan retleri ve SCM_RIGHTS ile tek pidfd aktarımı. İstemci ve servis current peer/scope validatorlarını işlem öncesi/sonrası çağırır. Sabit sekiz operasyon dışında dinamik method/import/pickle/shell yok. Hatalı/truncated paketlerde alınan fdler kapatılır; gönderici fdsi tüketilmez. Timeout/EOF/partialsend belirsizliği no-retry UNKNOWN kalır.

UnixEndpoint, trusted pre-opened server directory fd altındaki server-owned socket slotuna bağlanır; symlink/başka tür, writeable parent veya other-access socket reddedilir. Dizin fdsi final bağlantı yolunu pinler; peer credentials ayrıca doğrulanır. Bu kontroller bağımsız enrollment/native namespace qualification yerine geçmez.

PeerRpcService, supervisor tarafından açılmış listener veya accepted connection üzerinde çalışır. Kalıcı one-shot journal, stop.bind ve verification.run için scope digest'i üstünden handlerdan önce reserve edilir. Aynı işi yeniden çağırmak yeni request UUID ile de tekrar çalıştıramaz. Socket dinleme/exposure veya kalıcı servis kurulumu otomatik yapılmaz. serve metodu request-count/total deadline sınırı ve handler cleanup sağlar.

supervisor_service.py: LaunchObserver/validator ve StopObserver/validator için sabit operasyon handlerları ve Remote* istemciler; pidfd request sahipliği; stop binding ack kaybında cleanup scope korunması; sticky close UNKNOWN; RuntimeVerifier ve receipt revalidation portları. launch observe için service-owned duplicate, stop bind için LinuxStopObserver duplicate kullanılır. service_workflow mevcut PilotWorkflow/Kernel/Broker hattını bu istemcilere bağlar; constructor socket veya süreç başlatmaz.

VerificationReceiptStore: ayrı servis UID'sine ait700dizin/600tek-linkdosyada append-only SQLite yerel kanıt; FULL synchronous commit; exact expected/report eşleşmesi ve tekrar insert ret. Dosya/dizin kimliği/izinleri yeniden kontrol edilir. Bu store kanonik Kernel veya domain writer değildir; yalnız servis cevabının custody/readback kaydıdır. Receipt yeniden doğrulaması current qualification ve peer/scope kontrolü olmadan kabul etmez. Sayısal1, booleanTrue yerine geçmez.

## Verifier değerlendirmesi

runtime_verification.py RuntimeTitleVerifier: exact task/attempt/fence/revision/patch/head/profile/build/AC bağları; immutable candidate resolverdan bounded bytes+digest; qualification BEFORE_LAUNCH/RUNNING/STOPPED; ayrı qualified launcher/session üzerinden READY ve13vakanın gerçek beklenen sonuçlarıyla birebir karşılaştırılması. Adayın PASS, toplam veya checks zarfı doğrulama sonucu sayılmaz. Session finish exact exit0/EOF/stderr sınırı/trailing stdout0 ister; cleanup belirsizliği UNKNOWN ve rapor yok. Koşum öncesi/sonrası qualification olmadan ACTUAL_RUNTIME raporu üretilmez. Aynı UID subprocess fallback eklenmedi; eski run_title_oracle doğrudan runtime ret sınırı korunur.

Bu evaluatorın mevcut pozitif unit testi açık launcher/qualification/session fixtureları kullanır; üretilen ACTUAL_RUNTIME etiketi gerçek OS kabul kanıtı değildir. Gerçek kullanımda injected qualification ve launcherın ayrıca enrolled/independent olarak uygulanıp doğrulanması zorunludur; arbitrary verified=true veya True dönen fixture üretime bağlanamaz.

## Doğrulanan sonuçlar

Windows194test:174PASS20LinuxSKIP,exit0. LinuxUbuntu-E mevcut aipof-dbtest uid999:194PASS0SKIP,exit0. Önceki173teste21yeni test eklendi. Sayılar kaynak/unit/sensör/IPC kapsamıdır; first13 ürün kabulü değildir.

Servis istemcileri→observer→stop bind/recheck→verifier13case→append receipt→remote receipt readback→Kernel accept bağının tek kaynak/fake-driver testi var. Kernel/OS/qualification fixtureları gerçek DB/worker kabulü değildir. Mutant, adayın forged PASS raporu, eksik qualification, changed immutable bytes, nonzero/boolean exit, missing EOF, stderr/trailing output, duplicate one-shot, timeout/no reconnect, revoked peer, malformed packet+fd cleanup ve receipt integerTrue retleri test edildi.

tools/probe_peer_rpc_identity.py ayrı, süreli gerçek IPC mekanizma deneyi yaptı: istemciuid999, serveruid65534; iki uç SO_PEERCRED ile karşı kimliği ölçtü, echo kapsamı eşleşti, helpers stopped. Root yalnız koordinatörün mevcut UIDlere düşürmesi için kullanıldı; iki helper non-root çalıştı. Kullanıcı/grant/DB/namespace/kalıcı servis yaratılmadı. Probe peer/scope validatorları fixturedır; bu deney enrollment veya sandbox qualification değildir. Geçici socket/dizinler temizlendi. Kanıt distinct_uid.json.

Preflight8kaynak/23doğrudan imza/2dinamik atlama/172introspect edilemeyen çağrı/0finding,exit0. Instance methods/dinamik değerler ve exception sınıfları kapsam sınırlamaları korunur. runtime_ready=false.

## Gerçek tamamlanmayı engelleyen mevcut durum

Salt okunur uid999 inventory yeniden alındı: runtime profileJSON yok; cgroup/init.scope ve cgroup root yazılabilirlik ipucu false; trusted clock/profile/signer ve enrolled observer/verifier bağları doğrulanmadı. Gözlenen süreç test/observer ortamıdır; NoNewPrivs0/Seccomp0 değerleri launch edilmiş worker diye sunulmaz. WSL systemd user-session uyarısı tekrar görüldü; onarım iddiası yok.

Bu teslimde gerçek Kernel readback/enrollment adapterleri, immutable artifact resolver, rootless isolated candidate launcher/qualification ve enrolled çalışma profili kurulup doğrulanmadı. Bunlar aşağıdaki entegrasyon sözleşmelerinde explicit bağımlılıktır; onay veya veri icat ederek doldurulmadı. Bu nedenle gerçek SOFTWARE ilk13 kabulü TAMAMLANAMADI. G0OPEN,first13 0/13,insan kabulü yok. Gerçek uygulama workerı/model/DB veya kalıcı verifier servisi başlatılmadı; kaynak-test subprocessleri ve sınırlı IPC helperları çalıştı. GUNCEL/SQL/STATE değiştirilmedi; CALISMA_DURUMU.md eski hash sorunu bu dilimde yeniden koşulmadı:REPORTED_NOT_RETESTED.

## Supervisor entegrasyon sözleşmesi

| Bağ | Gereken somut girdi/kanıt |
|---|---|
| PeerRpcClient/Service peer_validator.validate | Ölçülen peer pid/uid/gid+operation+exact expected için current enrolled OS/source/profile ve Kernel scope kararı; fixtureTrue kabul değildir |
| Linux observer enrollment_reader.validate | Pinli observer profile/enrollment digest ve exact process için current bağımsız authoritative readback |
| Stop authoritative_readback.read | Exact identity ve ayrı workspace_fenced/no_respawn_intent/usage_zero otorite/journal/ledger mutabakatı; cgroup0bunları üretmez |
| Runtime resolver.resolve | Expected task/attempt/patch/headden authoritative immutable candidate bytes/digest; model pathi değil |
| Runtime launcher.open | Enrolled rootless candidate ayrı süreç/namespace/cgroup/FS/fixture sınırları, bounded read_line/write_line/finish/close sessionı; kaynak subprocess adapteri kullanılamaz |
| Qualification validate | BEFORE_LAUNCH,RUNNING,STOPPED,RECEIPT_READBACK için current independent OS/source/build/profile/fixture/custody bağları |
| Session finish | exit_code:int0,stdout_eof:True,stderr_bytes:int0..16384,trailing_stdout_bytes:int0; ayrıca bağımsız STOPPED qualification |
| Servis lifecycle | Supervisor-owned listener/private directory fdleri, ayrıUID, immutable intent journal, receipt custody directory ve bounded serve; otomatik sistem servisi kurulmaz |

Bu tablo yeni mimari/otorite üretmez; mevcut portların actual kabul önkoşullarını somutlaştırır. Tam işletim sisteminin veya mimarinin tamamlandığı iddia edilmez. Açık çalışma; gerçek güven/provisioning kayıtları ve Kernel/OS adapterlerinin bağlanmasıdır, yalnız ek unit-test sayısıyla kapanmaz.

## Pin ve geri dönüş

Byte-exact başlangıç yedekleri, yeni/current kaynak/test/kanıt pinleri manifestte. Yalnız current pin eşleşirse, bağımlılık incelemesiyle kaynak geri dönüşü yapılabilir; concurrent değişiklik overwrite edilmez. Otomatik rollback yapılmadı; grant/fence/epoch geri sarılmadı. Teknik kaynak/IPC testi, bağımsız review, ürün kabulü ve hafıza aktarımı ayrı durumlarda tutuldu.
