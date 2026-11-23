# Ortam profilleri

Mimari §27 uyarınca profiles/ sır içermeyen ortam profillerine ayrılmıştır. SOURCE_ONLY, DISPOSABLE_TEST ve ISOLATED_DEV ayrı tutulur. Tam runtime yükleyicisi henüz yoktur.

Gerçek profilde host/boot/generation, toolchain/model digest, kaynak limitleri, network/fs allowlist, clock, grant/lease, deadline/queue, signer/verifier enrollment ve stop/recovery sorumlusu doğrulanmalıdır. Eksik değer sınırsız veya sıfır varsayılamaz. Profil varlığı runtime izni değildir. Kimlik bilgileri, token, anahtar ve bağlantı sırları burada saklanmaz.

2026-11-12: `company_os/observer_profile.py`, Linux ölçüm alt profilini dışarıdan sağlanan exact SHA256 pini ve canonical workspace ile yükler. Bu alt profil tam runtime profili veya enrollment değildir. JSON içinden türetilen kendi pini güven kaynağı olarak kullanılmaz; bilinmeyen/eksik/tekrar alanlar, root UID, observer/producer-controller UID eşleşmesi, host namespace eşleşmesi ve sınırsız kaynak limiti reddedilir. Gerçek profil değerleri veya onay kaydı oluşturulmadı.

`company_os/linux_observer.py` mevcut LaunchActivation ve ProcessReconciler portları için başlama/durma ölçümleri sağlar. Validator ayrıca bağımsız güncel enrollment/profile readback adapterini ister; profil dosyası veya ölçüm digest'i bu kontrolün yerine geçmez. Stop observer pidfd'yi süreç hâlâ çalışırken bind eder; başka bir exited pidfd yeterli değildir. Cgroup boşluğu workspace fence/no-respawn journal/ledger mutabakatı diye yorumlanmaz; bunlar yetkili readback portundan alınır. Bu portların ayrı OS kimliğiyle çalışan servis/IPC bağları ve gerçek enrolled verifier hâlâ açık.


2026-11-12 servis dilimi: `peer_rpc.py` Linux AF_UNIX/SOCK_SEQPACKET, SO_PEERCRED, SCM_RIGHTS, paket/deadline sınırları ve kalıcı one-shot intent denetimini; `supervisor_service.py` sabit observer/verifier operasyonlarını, private append-only yerel rapor deposunu ve `service_workflow` bağlantısını sağlar. `runtime_verification.py` 13 vakayı serviste değerlendirir; adayın PASS/total iddiasını kullanmaz. Exit code, EOF, stderr/trailing-output ve cleanup/qualification kontrolü olmadan rapor üretmez. Otomatik reconnect, same-UID subprocess fallback, key/grant üretimi veya servis kurulumu yoktur.

Gerçek çalıştırma için supervisor; önceden açılmış private directory/listener fdlerini, ayrı non-root UIDleri, current peer/enrollment/scope validatorlarını, immutable candidate resolverı, qualified isolated candidate launcherı ve mevcut Kernel otorite readbacklerini sağlamalıdır. Servis kurucuları bunları onaylamaz veya icat etmez. `tools/probe_peer_rpc_identity.py` yalnız mevcut uid999/65534 altında süreli test alt süreçleriyle peer kimlik mekanizmasını sınar; gerçek enrollment/namespace/uygulama kabulü değildir. Gerçek runtime profil JSON hâlâ oluşturulmadı.


2026-11-14: `presentation/kernel_binding.py` yalnız HTTP→mevcut Kernel için pinli,sır içermeyen local socket/service scope referanslarını yükler ve catalog/ACL precheck yapar. Tam runtime/profile,enrollment,clock veya worker qualification değildir. Gerçek profil oluşturulmadı. [Çalıştırma ve exact alanlar](../docs/developer-guides/TASK_SCREEN.md).
