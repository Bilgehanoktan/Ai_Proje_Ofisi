# Veri koruyan Owner-Auth / Recovery yaşam döngüsü ve kaynak bütünlüğü — 2026-11-20

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-20
Kaynak ajan: Antigravity
Durum: VERIFIED_SOURCE_TESTS_AND_PG18_ROLLBACK_COMPILE; LIVE_ENROLLMENT_AND_MIGRATION_NOT_AUTHORIZED
Kanıt: evidence/runs/owner-auth-recovery-20261120/pg18-rollback-compile-audit.json; evidence/runs/owner-auth-recovery-20261120/native-login-denial.json; evidence/runs/owner-auth-recovery-20261120/readiness-before.json; evidence/runs/owner-auth-recovery-20261120/readiness-after.json; evidence/runs/owner-auth-recovery-20261120/verify-windows.log; evidence/runs/owner-auth-recovery-20261120/verify-linux.log

## Uygulanan değişiklikler

1. **Kaynak bütünlüğü regresyonu onarıldı:**
   - Manifest dışı sahte `InteractiveDemoBackend` içeren `scripts/serve_persistent.py` silinmeden SHA256 (`f287d165fe238ce41110185928d856716286e598a891286b02be5ad6211b149d`) kaydıyla `.runtime/trials/retired-demo-20261120/serve_persistent.py.retired` altına taşındı.
   - Eksik `scripts/serve_standalone.py`, `scripts/serve_configured_ui.py` ile birebir aynı byte içeriği (`7ab3fabd02cc3ca731cfbc7254cf2bee7c7c086711499025e06a1d7dcf799b59`) ile geri yüklendi.
2. **Inert native owner-auth/recovery SQL kaynağı (`database/sources/086_APPLICATION_OWNER_AUTH_RECOVERY_V1.sql`):**
   - `DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED` ve `ROLLBACK;` guard'larıyla inert tutuldu; `database/assembly/assembly.json` 86. sıraya eklendi.
   - Mevcut tüketilmiş tenant verilerini korur; ilk bootstrap/root penceresine (`r56_root_bounds`, `bootstrap_receipts.e0_valid_until`) veya `clock_timestamp()` fallback'ine dayanmaz. Canlı proje saatine (`company_private.r55_cp_clock_current_bounds`) ve `company.signer_enrollments` (`purpose='OWNER_AUTH'`) + `company_private.r58_key_material` (`purpose='OWNER_AUTH'`) + `r55_cp_hmac_sha256` + `r55_cp_tag_equal` doğrulamasına bağlanır.
   - Üç dar rol (`company_owner_auth_owner_v1`, `company_owner_auth_readback_v1`, `company_owner_auth_transport_v1`), append-only + `FORCE RLS` + immutability trigger'lı `company_private.owner_auth_receipts_v1` tablosu ve `owner_auth_execute_v1` / `owner_auth_receipt_readback_v1` (`SECURITY DEFINER SET search_path=pg_catalog`) tanımlandı.
   - Desteklenen işlemler: `ISSUE_SESSION`, `REVOKE_SESSION`, `RECOVER_ROTATE_SESSIONS` (tüm açık owner oturumlarını kapatıp `authority_scope_heads` `epoch+1, revision+1` artırarak yeni oturum açma). Hiçbir `project_grants`, `memberships` veya `bootstrap_receipts` yazma izni içermez.
3. **Python supervisor adapteri (`product/backend/company_os/kernel/owner_auth.py`) ve kurulum tanısı (`scripts/database/audit_local_state.py`):**
   - `issue_committed_owner_auth_v1`, `read_owner_auth_receipt_v1` ve `owner_auth_tag` eklendi: exact least-privilege non-superuser login kontrolü, `SERIALIZABLE` write + commit + ayrı bağlantıda `REPEATABLE READ READ ONLY` independent witness readback, lost-ACK durumunda `ProvisioningOutcomeUnknown` (asla otomatik retry yok) ve zero-plaintext token/key sınırı.
   - `audit_local_state.py` içine salt okunur `owner_auth_readiness` eklendi ve `doctor --summary` çıktısına bağlandı.

## Gerçek PostgreSQL 18.6 ve kaynak doğrulaması

- **PostgreSQL 18.6 rollback-only compile & runtime probu (`pg18-rollback-compile-audit.json`):** `status=PASS`. Transaction içinde `086` eksiksiz derlendi (`tables 72->73->72`, `roles 19->22->19`, `functions 151->153->151`, `sessions 33`, `grants 14`), `FORCE RLS`, immutability trigger (`O`), `SECURITY DEFINER`/`search_path=pg_catalog`/`REVOKE FROM PUBLIC`, superuser çağrı reddi (`OWNER_AUTH_TRANSPORT_REQUIRED`), geçici least-privilege transport probuyla 9-tablo readback (`OWNER_AUTH_READBACK_WITNESS_MISMATCH`) ve execute context reddi (`OWNER_AUTH_CONTEXT_MISMATCH`) doğrulandı; rollback sonrası tüm nesnelerin tamamen temizlendiği ve `readiness-before.json` ile `readiness-after.json` çıktılarının özdeş olduğu kanıtlandı.
- **Native unsafe-login denial (`native-login-denial.json`):** Mevcut privileged `aipof-dbtest` ile `issue_committed_owner_auth_v1` çağrısı `EXACT_LEAST_PRIVILEGE_OWNER_AUTH_LOGIN_REQUIRED` ile reddedildi (`session_delta=0`, `grant_delta=0`).
- **Birim/SQL testleri ve statik kapılar:** `tests/unit/test_owner_auth.py`, `tests/unit/test_installation_readiness.py` ve `tests/security/test_sql_source.py` güncellendi; Ruff (`check` + `format --check`), Mypy 1.10 (`owner_auth.py` + `session_provisioning.py`) ve Windows + Linux `run.py verify` + `verify_layout.py` doğrulandı.

## Açık sınırlar (tamamlanmamış kabul)

- Canlı PostgreSQL'de `086` kurulumu (G0 sonrası yetkili migration), `OWNER_AUTH` signer/key enrollment'ı, canlı proje saat epoch aktivasyonu ve gerçek least-privilege transport rolüyle pozitif owner session/recovery kabulü **henüz çalıştırılmadı**.
- Ardından onaylı HTTP/Kernel profiliyle panelden kalıcı `Objective`/`Plan`/`Task` oluşturma ve bağımsız readback, READY/scheduler, rootless worker + ücretsiz yerel model ve bağımsız verifier/acceptance zinciri açıktır. `G0 OPEN`, `first13 0/13`, tam 16 modül / PH-00–PH-06 kapsamı korunur.
