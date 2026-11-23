# Linux observer ölçüm ve pinli alt profil dilimi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-12
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_BOUNDED_LINUX_SENSOR; bağımsız review PENDING; tam runtime NOT_RUN
Kanıt: evidence/CODEX_OBSERVER_20261112_windows_tests.log; evidence/CODEX_OBSERVER_20261112_linux_tests.log; evidence/CODEX_OBSERVER_20261112_preflight.json; evidence/CODEX_OBSERVER_20261112_manifest.json.

## TaskSpec ve kapsam

TASK-CODEX-20261112-04; mevcut tasarım §16/27/28, MOD-004/008/015/016 ve PH-02/03 seçili ölçüm/izolasyon/cleanup sınırları. REQ-007/010, AC-007/010 ve TEST-007/010 için kısmi kaynak katkısı; bütün AC veya modül kabulü değildir. Allowlist: yeni company_os/observer_profile.py ve linux_observer.py; company_os/workflow.py; tools/workflow_preflight.py; config/README.md; yeni tests/unit/test_linux_observer.py; tests/unit/test_workflow.py ve test_workflow_preflight.py; bu rapor, ilgili takip belgeleri ve CODEX_OBSERVER_20261112 önekli kanıtlar. Başlangıç mevcut dosya byte yedekleri BACKUP dizininde; yeni dosyalar başlangıçta ABSENT.

Tam16MOD/PH00–06 hedefi korunur. Yeni bağımsız karar, izin/grant/SQL veya varsayılan enrollment üretilmedi. Önceki devir CODEX_LINUX_SUPERVISOR_20261112.md.

## Uygulanan davranışlar

observer_profile.py, dışarıdan trusted supervisor tarafından verilen SHA256 pinine/canonical workspace'e bağlı, bounded ve strict JSON ölçüm alt profilini okur. Kendi içeriğinden pin türetip güvenmez. Eksik/tekrar/bilinmeyen alan, root UID, observer ile worker/controller UID aliası, worker-host namespace aliası, root/bozuk cgroup yolu, sınırsız/bozuk kaynak limitleri ve bozuk digest/boot kimliği reddedilir. Bu alt profil tam runtime konfigürasyonu değildir; gerçek profil JSON veya onay kaydı oluşturulmadı. Native/source/enrollment digest alanları expected pinlerdir; yalnız dosyada bulunmaları gerçek enrollment veya native filter doğruluğu kanıtı değildir.

LinuxProcReader actual pidfd türü/PID bağı ve exit durumunu, bounded /proc stat/status/ns/cgroup/fd ve executable ölçümlerini okur. starttime comm içindeki boşluk/parantezlerden bağımsız ayrıştırılır; işlem/executable değişimi veya exit reddedilir. Runtime ölçümü sealed native ELF ister; ordinary executable yalnız açık require_sealed=False envanter testinde ölçülebilir ve LaunchObserver tarafından kabul edilemez. CapEff/Prm/Inh/Amb, NoNewPrivs, Seccomp, UIDler ve descriptor seti ölçülür. Seccomp mode2, tek başına exact filtre veya isolation qualification kanıtı değildir.

LinuxCgroupReader gerçek CGROUP2_SUPER_MAGIC kontrol eder; normal dizindeki sahte dosyalar cgroup sayılamaz. Bounded resource limits/cgroup.procs/events okunur.

LinuxLaunchObserver profile-bound observer OS UID/boot/boottime, namespace/executable/UID/capability/stdio ve dedicated cgroup/limit/process ölçümlerini karşılaştırır; cgroup değişimi ve profil expiry yeniden kontrol edilir. Üretilen process_identity_digest ve isolation_digest ölçüm bağlarıdır; bağımsız runtime qualification değildir.

LinuxLaunchObservationValidator ölçümü yeniden alıp karşılaştırır; ayrıca ölçüm öncesi/sonrası current enrollment/profile readback adapterini ister. Bu readback implementasyonu gerçek enrolled otoriteyle hâlâ bağlanmamıştır; fixture true sonucu authority değildir.

LinuxStopObserver, callbackteki exact process identity digest ile eşleşen live pidfd'yi bind eder ve bağımsız duplicate handle tutar; başka exited pidfd yeterli değildir. EXITED için pidfd exit ve empty cgroup birlikte gerekir. Workspace fence, no-respawn intent ve usage-zero cgroup boşluğundan türetilmez; authoritative readback portundan ayrı alınır. Bu otorite/journal/ledger readback portunun fiziksel implementasyonu ve ayrı OS servis/IPC bağı açıktır. Validator stop ölçümünü ve enrollmentı yeniden kontrol eder. Close belirsizliğinde sticky UNKNOWN/no-retry korunur.

PilotWorkflow callback sonrasında, engine çalıştırılmadan önce bind portunu çağırır. Final cleanup observer duplicate pidfd'sini ve supervisor parent handlelarını ayrı yönetir. Bağımsız observer close hatasında parent cleanup yine denenir; kabul yazılmış olsa bile cleanup hatası sessiz başarı veya retry olarak sunulmaz.

## Kanıt ve sınırlar

Windows173test:162PASS11LinuxSKIP,exit0. LinuxUbuntu-E mevcut aipof-dbtest uid999:173PASS0SKIP,exit0. Önceki158testten15yeni test;13profile/observer/sensor ve2workflow bağlantı/cleanup testi. Ürün/ilk13 kabul sayacı değildir.

Yeni pozitif workflow testi somut observer/validator sınıflarını kanonik activation/reconciliation/pipeline zincirine bağlar; proc/cgroup/context/enrollment/readback/DB/OS fixturelarıyla yapılır. Ayrı OS kimliği veya gerçek enrollment iddia edilmez.

Linux sensör testi bounded /bin/sleep kaynak-test alt sürecinin actual /proc metadata/pidfd PID bağı ve exit durumunu ölçer; ordinary executable'ın qualified varsayılan yoldan reddini doğrular. Alt süreç terminate/wait ve pidfd close ile temizlenir. Ayrı bir test normal dizinin cgroup taklidini reddeder. Bu testler üretim workerı, bağımsız verifier, güvenli sandbox veya native agent launch kabulü değildir.

Negatifler: profile pin/scope/alan/UID/namespace/limit, revoked/missing enrollment, ölçüm sırasında enrollment değişimi, process starttime/UID/namespace/executable/seal/capability/stdio farkı, cgroup race/extra process/limit, expired/reboot context, foreign pidfd identity, eksik fence/ledger ve duplicate close belirsizliği.

Preflight5kaynak dosyası/9doğrudan imza/2dinamik atlama/92introspect edilemeyen çağrı/0finding,exit0. Introspect edilemeyenlerin ağırlığı exception sınıflarıdır; instance-method/values AST kapsamı dışındadır. runtime_ready=false. Bu payda önceki preflight ile aynı değildir.

GUNCEL/SQL/STATE ve gerçek runtime config değiştirilmedi. Eski GUNCEL CALISMA_DURUMU.md hash hatası bu dilimde yeniden koşulmadı:REPORTED_NOT_RETESTED. WSL systemd user-session uyarısı tekrar görüldü; onarım/kabul iddiası yok. Gerçek DB/model/uygulama workerı veya verifier servisi başlatılmadı; mevcut SOURCE_TEST subprocessleri ve sınırlı sleep probe çalıştı.

## Açık işler ve geri dönüş

Ölçüm katmanı ve alt profil okuyucusu uygulandı. Tam rootless ortam profili/qualification, ayrı OS servis/IPC ve pidfd transferi, current enrollment readback, authoritative fence/journal/ledger readback, bağımsız hidden-fixture runtime verifier/receipt validator ve gerçek Kernel/DB/OS zinciri hâlâ açıktır. run_title_oracle runtime ret sınırı değiştirilmedi. G0OPEN,first13 0/13,insan kabulü yok; tam modül kapanışı sayılmaz. İlk SOFTWARE akışı ara teslimdir; tam mimari hedefinin yerine geçmez.

Sıradaki teknik parça ayrı OS observer/verifier servis-IPC ve current enrollment/readback portlarını owning native sözleşmelerle bağlamaktır; sentetik profil veya doğrulanmamış verified=true ile açıklar kapatılmaz.

Byte-exact başlangıç yedekleri ve current SHA256 manifesti saklandı. Geri dönüş yalnız current pin aynıysa ve bağımlılıklar kontrol edilerek yapılabilir; concurrent değişiklik overwrite edilmez. Otomatik rollback/DB-epoch-grant geri sarma yapılmadı.
