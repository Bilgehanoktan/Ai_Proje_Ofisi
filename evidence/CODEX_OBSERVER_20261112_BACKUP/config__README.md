# Ortam profilleri

Mimari §27 uyarınca profiles/ sır içermeyen ortam profillerine ayrılmıştır. SOURCE_ONLY, DISPOSABLE_TEST ve ISOLATED_DEV ayrı tutulur. Henüz runtime yükleyicisi yoktur.

Gerçek profilde host/boot/generation, toolchain/model digest, kaynak limitleri, network/fs allowlist, clock, grant/lease, deadline/queue, signer/verifier enrollment ve stop/recovery sorumlusu doğrulanmalıdır. Eksik değer sınırsız veya sıfır varsayılamaz. Profil varlığı runtime izni değildir. Kimlik bilgileri, token, anahtar ve bağlantı sırları burada saklanmaz.
