# Güvenilir başlangıç ve yetki adapterleri — kaynak dilimi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-13
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_FAKE_DRIVER; native DB integration NOT_RUN; bağımsız review PENDING
Kanıt: evidence/CODEX_AUTHORITY_20261113_windows_tests.log; evidence/CODEX_AUTHORITY_20261113_linux_tests.log; evidence/CODEX_AUTHORITY_20261113_preflight.json; evidence/CODEX_AUTHORITY_20261113_manifest.json.

## TaskSpec

TASK-CODEX-20261113-01; mevcut tasarım §16/27/28; MOD-001/009/016, PH-01, P0-1/P0-3 başlangıç alt kapsamı. AC/TEST-004/012 güven ve current scope sınırlarına katkı; tam AC veya modül kapanışı değildir. Allowlist: company_os/provisioning.py; yeni bootstrap_readback.py; tools/disposable_e2e_workflow_trial.py ve workflow_preflight.py; yeni tests/unit/test_authority_adapters.py; tests/unit/test_workflow.py ve test_workflow_preflight.py; bu rapor/takip/backlog ve CODEX_AUTHORITY_20261113 kanıtları. Mevcut kaynakların byte-exact başlangıçları BACKUP dizininde. Tam16MOD/PH00–06 kapsamı korunur.

## Doğrulanan kusur

provision_project_grant yalnız SimpleNamespace(grant_id=...) döndürüyordu; revoke_project_grant yalnız target_grant_id/revoked=True döndürüyordu. DB command/commit/readback yoktu. Böylece API çağrısı authority etkisi olmuş gibi sonuç verebiliyordu. Bu yardımcıların canlı bir grant bypassı yaptığı gösterilmedi; aktif E2E girişinde çağrı bulunmadı, eski trial yedeğinde importları var. Yine de gelecekte bağlanacak provisioning için somut yanlış başarı riskiydi.

Genel issuer için bağlı approved native writer yok; helper artık ENROLLED_NATIVE_GRANT_WRITER_REQUIRED ile reddeder ve caller connectionını tüketmez. Mevcut bootstrapın sınırlı initial-grant native yolu korunur. Key/role/grant yaratılmadı; yeni delegation politikası veya SQL issuer icat edilmedi. Genel grant writer bağlantısı açık kalır.

## Uygulanan revoke bağlantısı

revoke_project_grant mevcut078_R64_REVOKE_FINALITY.sql ve CommandHost CAP-017.revoke rotasına bağlandı. Exact tenant/project/target/correlation UUID,PROJECT auth scope,revision0..JS-safe sınır,reason enum,idempotency ve dışarıdan authoritative PG-jsonb revocation_scope_digest gerekir. Eski eksik girdiler DB komutundan önce reddedilir. Python JSON hashinden PG scope digest üretilmez.

Geçerli girdide CommandHost transaction/finality/COMMIT/close sahibidir. Dönen private envelope için SUCCEEDED receipt,target,result operation/status,revision+1,scope digest,descendant membership vecommand/revocation receipt eşleşmesi zorunludur. Commit ack kaybında UnknownCommitOutcome korunur; post-commit result farkı ProvisioningOutcomeUnknown olur; otomatik retry/ikinci revoke yok. Sonuç revoked=True veya current emission/OS-stop onayı diye sunulmaz. Self-revoke pre-cut snapshot korunur; HTTP emit için mevcut ayrı current guard gerekir.

## BootstrapReadback adapteri

Yeni bootstrap_readback.py, r57 replay-witness owning koşullarından parametrik SELECT kullanır. Yeni dedicated bağlantıda REPEATABLE READ READ ONLY, bounded statement/lock/idle timeouts ve exact DB session_user kontrolü vardır. Beklenen installation/generation/tenant/project/human/command ve digestler dışarıdan pinlenir. UUID kolonları::text seçilerek gerçek psycopg UUID/str dönüşü farkı önlenir.

Sorgu consumed control generation/tenant/project/human bağlarını; HUMAN/OWNER membership;SUCCEEDED trusted_setup.consume r56 command/result/payload;COMMIT_CUT final proof;PG-jsonb result digest;InstallationBootstrapped audit ve exact outbox/project_sequence/writer_generation/event digest tanıklarını eşleştirir. Missing/duplicate/foreign/changed kayıt ret; sonuç yalnız EXACT_COMMITTED_WITNESS_MATCH,authorization NOT_VERIFIED,new_grants0. Current root/clock/session authority veya owner identity enrollmentı bu snapshotla kanıtlanmış sayılmaz. Bootstrap consume/yazıcı çağrılmaz.

Reader mevcut yetkili SELECT görünürlüğü olan maintenance/provisioning login ister. RLS/ACL atlanmaz ve yeni read grant verilmez; gerçek DB login görünürlüğü ayrıca bağlanmalıdır. İstisnalar driver/connection detayları sızdırılmadan sabit hataya çevrilir. Rollback veya close hatası başarıya dönüşmez. BootstrapReadback.__call__ supervisor read_bootstrap portuna uyar.

E2E girişi artık installation/human yanında exact generation(int),committed-witness sınıfı ve pilot signer tenant/worker project bağını ister. Eski iki alanlı metadata veya yanlış tenant/project dispatch öncesinde reddedilir. Reader MATCH yeni grant veya G0 yetkisi üretmez; sonraki Kernel command scope kontrolleri zorunludur.

## Doğrulama

Windows207test:187PASS20LinuxSKIP,exit0. LinuxUbuntu-E aipof-dbtest uid999:207PASS0SKIP,exit0. Önceki194teste13yeni kaynak/fake-driver davranış testi eklendi. Native PostgreSQL sorgu çalıştırması, gerçek grant/revoke,root provisioning veya ürün E2E bu dilimde yapılmadı.

Negatifler: eski issuer sahte başarı, eksik/malformed revoke inputs,wrong scope,commit ack kaybı,post-commit payload farkı;bootstrap missing/duplicate/malformed/wrong tenant/digest/login/nonidle/autocommit/timeout;driver connection/cleanup hata redaksiyonu;mutable expected pin koruması;entry legacy witness/tenant/project/bool generation reddi. Native SQL semantics sahte driverla fiziksel kabul edilmiş sayılmaz.

Preflight10kaynak/24doğrudan imza/2dinamik atlama/183introspect edilemeyen çağrı/0finding,exit0. Instance-method/dinamik value kapsam sınırı korunur;runtime_ready=false. WSL systemd user-session uyarısı tekrar görüldü; onarım iddiası yok.

## Açıklar ve devam

Bu P0-1/P0-3 kısmi ilerlemesidir. Gerçek approved bootstrap/read login vecurrent enrollment/clock/host/profile kayıtları;genel authorized grant writer/delegation;peer/enrollment/fence/journal/ledger authority adapterleri;immutable candidate resolver;qualified isolated launcher/runtime profile ve gerçek Kernel/DB/OS kabulü açık kalır. Yeni okuyucu bu bağımlılıkların hepsini yerine getirmiş sayılmaz. GUNCEL/SQL/STATE değiştirilmedi; eski CALISMA_DURUMU.md hash hatası yeniden koşulmadı:REPORTED_NOT_RETESTED.

G0OPEN,first13 0/13;tam modül veya insan kabulü yok. Sonraki owning iş, BootstrapReadback SELECT görünürlüğünü ve mevcut onaylı root/bootstrap kayıtlarını gerçek kontrollü DB ortamında eşleştirmek; ardından current enrollment/profile/peer readback adapterlerini aynı somutlıkta bağlamak. Synthetic kayıt veya True fixture ile açıklar kapatılmaz.

Byte yedekleri ve current manifest pinleri saklandı. Current pin değişmişse overwrite rollback yapılmaz. Otomatik rollback/DB-epoch-grant geri sarma yapılmadı. Hafıza aktarımı uygulama testinden ayrıdır.
