# Ortam profilleri

Mimari §27 uyarınca profiles/ sır içermeyen ortam profillerine ayrılmıştır. SOURCE_ONLY, DISPOSABLE_TEST ve ISOLATED_DEV ayrı tutulur. Tam runtime yükleyicisi henüz yoktur.

Gerçek profilde host/boot/generation, toolchain/model digest, kaynak limitleri, network/fs allowlist, clock, grant/lease, deadline/queue, signer/verifier enrollment ve stop/recovery sorumlusu doğrulanmalıdır. Eksik değer sınırsız veya sıfır varsayılamaz. Profil varlığı runtime izni değildir. Kimlik bilgileri, token, anahtar ve bağlantı sırları burada saklanmaz.

2026-11-12: `company_os/observer_profile.py`, Linux ölçüm alt profilini dışarıdan sağlanan exact SHA256 pini ve canonical workspace ile yükler. Bu alt profil tam runtime profili veya enrollment değildir. JSON içinden türetilen kendi pini güven kaynağı olarak kullanılmaz; bilinmeyen/eksik/tekrar alanlar, root UID, observer/producer-controller UID eşleşmesi, host namespace eşleşmesi ve sınırsız kaynak limiti reddedilir. Gerçek profil değerleri veya onay kaydı oluşturulmadı.

`company_os/linux_observer.py` mevcut LaunchActivation ve ProcessReconciler portları için başlama/durma ölçümleri sağlar. Validator ayrıca bağımsız güncel enrollment/profile readback adapterini ister; profil dosyası veya ölçüm digest'i bu kontrolün yerine geçmez. Stop observer pidfd'yi süreç hâlâ çalışırken bind eder; başka bir exited pidfd yeterli değildir. Cgroup boşluğu workspace fence/no-respawn journal/ledger mutabakatı diye yorumlanmaz; bunlar yetkili readback portundan alınır. Bu portların ayrı OS kimliğiyle çalışan servis/IPC bağları ve gerçek enrolled verifier hâlâ açık.
