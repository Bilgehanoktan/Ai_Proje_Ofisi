# Owner oturumu ve kurulum tanısı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-15

## Durumu kontrol et

Workspace kökünden `C:\Python314\python.exe -B scripts/development/run.py doctor --summary` çalıştır. Araç Windows'tan mevcut WSL ortamına gider; DB'yi/servisi başlatmaz, kullanıcı veya grant oluşturmaz. `unexpired_unrevoked` yalnız expiry/revocation sayımıdır. Root ve bootstrap kontrolleri ayrı değerlendirilir. `DIAGNOSTIC_ONLY_NOT_NATIVE_AUTHORIZATION` yetki kararı değildir.

Root/boottime/wall window kapalıysa mevcut native işlem başarısız kalmalıdır. Aynı bootstrap'ı tekrar çalıştırmak normal oturum yenileme değildir; fresh-tenant gerektiren kurulum akışını mevcut tenant üzerine uygulama. Genel root expiry UPDATE, trigger kapatma, RLS gevşetme veya admin oturumuyla ürün yürütme kullanma.

## Supervisor bağlantısı

`company_os.kernel.session_provisioning.issue_committed_owner_session` önceden yetkilendirilmiş provisioning bağlantısı, installation_id, dışarıda güvenli tutulan token ve exact expected_login alır. Bu fonksiyon HTTP login endpointi değildir; bağımsız insan kimliği/custody verifierı veya grant issuer değildir.

Native root/clock/OWNER şartları geçerliyse transaction içinde session yazar, commit eder ve ayrı bağlantıdan token hash, generation, expiry, principal/tenant ve SESSION lock bağını doğrular. Sonuç token içermez. `ProvisioningOutcomeUnknown` durumunda otomatik tekrar çağırma; bağımsız readback/reconciliation yap. Credential teslimini güvenilir supervisorun mevcut secret custody mekanizması yürütür.

## Paneli başlat

`scripts/development/run.py kernel --profile ONAYLI_PROFIL --sha256 DIS_PIN --check-only` metadata kontrolüdür. Aynı komut --check-only olmadan mevcut gerçek Kernel backendini başlatır. Legacy `scripts/serve_configured_ui.py` ve `scripts/serve_standalone.py` de aynı gerçek profil yoluna yönlenir. Default `tasks` sunucusu gönderimi kapalı açılır. Çalışan servis değiştirildiyse /api/connection yanıtını yeniden kontrol et; diskteki dosyanın düzelmesi eski demo sürecini dönüştürmez.

[Kaynak, test ve açık yaşam döngüsü sınırları](../../handover/TRUSTED_SESSION_20261115.md).

## Post-bootstrap owner-auth ve recovery (v1)

Tarih: 2026-11-20

- `database/sources/086_APPLICATION_OWNER_AUTH_RECOVERY_V1.sql` (`DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED`) mevcut tüketilmiş tenant üzerinde root/bootstrap penceresine (`r56_root_bounds`, `e0_valid_until`) bağımlı olmadan canlı proje saatine (`r55_cp_clock_current_bounds`) ve `OWNER_AUTH` signer/key enrollment'ına dayanan oturum açma (`ISSUE_SESSION`), tekil iptal (`REVOKE_SESSION`) ve tüm açık owner oturumlarını döndürerek kurtarma (`RECOVER_ROTATE_SESSIONS`) yaşam döngüsünü tanımlar.
- `product/backend/company_os/kernel/owner_auth.py` içindeki `issue_committed_owner_auth_v1` ve `read_owner_auth_receipt_v1` yalnızca önceden yetkilendirilmiş non-superuser/non-bypassrls/non-createrole transport bağlantısı kabul eder; plaintext token/signing_key SQL argümanlarına veya dönüşlere girmez; lost ACK durumunda `ProvisioningOutcomeUnknown` üretir ve otomatik retry yapmaz.
- `doctor --summary` içindeki `owner_auth_readiness` bölümü `086` kurulu mu, aktif `OWNER_AUTH` signer ve clock epoch sayısı kaç adet sorularını salt okunur gösterir (`DIAGNOSTIC_ONLY_NOT_NATIVE_AUTHORIZATION`).
- Ayrıntı ve PG18 rollback kanıtı: [Owner-auth / recovery raporu](../../handover/OWNER_AUTH_RECOVERY_20261120.md).
- Canlı değerlendirme kümesi (WSL `Ubuntu-E`, PostgreSQL `18.6`, `aipof_owner_auth` / `aipof_http_kernel` least-privilege `peer map=aipof_local`) üzerinde `086` kurulumu, saat epoch aktivasyonu, `OWNER_AUTH` signer enrollment, pozitif/negatif oturum açma/iptal/kurtarma döndürme, HTTP panel `Objective`/`Plan`/`Task` yazımı ve soğuk PG yeniden başlatması sonrası `/api/details` readback doğrulaması: [Canlı doğrulama raporu](../../handover/LIVE_FLOW_VERIFICATION_20261120.md) ve ham kanıtlar (`evidence/runs/live-flow-20261120/`). Bu değerlendirme `G0 OPEN` ve `first13 0/13` sınırını değiştirmez.
