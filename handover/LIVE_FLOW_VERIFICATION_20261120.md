# Canlı Değerlendirme Kümesi Uçtan Uca Doğrulama Raporu — 2026-11-20

Canonical workspace: `E:\Projeler\Ai_Proje_Ofisi`
Tarih: 2026-11-20
Kaynak ajan: Antigravity
Durum: LOCAL_EVALUATION_CLUSTER_VERIFIED_NOT_G0_RATIFICATION (`G0 = OPEN`, `runtime = NOT_RUN`, `first_flow_acceptance = 0/13`)
Kanıtlar:
- `evidence/runs/live-flow-20261120/readiness-before.json`
- `evidence/runs/live-flow-20261120/db-inspection-snapshot.json`
- `evidence/runs/live-flow-20261120/precheck-functions-e0.json`
- `evidence/runs/live-flow-20261120/readiness-after-install.json`
- `evidence/runs/live-flow-20261120/owner-auth-live-verification.json`
- `evidence/runs/live-flow-20261120/local-model-invocation.json`
- `evidence/runs/live-flow-20261120/panel-live-persistence.json`
- `evidence/runs/live-flow-20261120/mgt01-live-workflow-acceptance.json`
- `evidence/runs/live-flow-20261120/readiness-final.json`

## 1. Kapsam ve Sınırlar (Gerçeğe Bağlı Bildirim)

Bu çalışma, onaylı yerel WSL2 (`Ubuntu-E`, OS kullanıcısı `aipof-dbtest`, uid `999`) PostgreSQL `18.6` değerlendirme kümesinde (`/var/lib/ai-proje-ofisi-local`, port `55490`, veritabanı `ai_proje_ofisi`) beş aşamalı canlı doğrulama akışını çalıştırmıştır:

- **`G0` durumu değişmemiştir:** `G0 = OPEN`, `runtime = NOT_RUN`, `first13 = 0/13`. İnsan G0 onayı veya resmi ürün teslim kabulü üretilmemiştir (`LOCAL_EVALUATION_CLUSTER_VERIFIED_NOT_G0_RATIFICATION`).
- **Native C başlatıcısı derlenip çalıştırılmadı:** `product/backend/native/linux/r65_spawn_linux.c` bu değerlendirmede derlenip kullanılmamıştır (`NOT_RUN_OS_SUBPROCESS_WITH_PIDFD_USED`); süreç denetiminde Linux OS `subprocess` + `os.pipe()` + `os.pidfd_open` kullanılmıştır.
- **Teknik değerlendirme oturumları:** Owner oturumları `086` native `issue_committed_owner_auth_v1` üzerinden üretilmiştir; teknik worker/controller/verifier/evidence/`qa_auditor` rolleri ise kapalı root penceresi nedeniyle değerlendirme kümesinde `company.sessions` içine tohumlanmıştır (`086` tasarım gereği yalnızca `HUMAN` owner için oturum açar).
- **Inert SQL kaynakları ve E0 değişmezliği:** `database/sources/` altındaki hiçbir inert SQL dosyasına (`DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED` / `ROLLBACK;`) dokunulmamış, hiçbir trigger devre dışı bırakılmamış (`disabled_user_triggers: []`) ve E0 tablolarının SHA256 değerleri başlangıçtan bitişe birebir korunmuştur:
  - `company_private.r55_setup_root_enrollments`: `99ff11cfbbc52f1273aba37920c33a426abadd5a0a3d8bf6577a08c0a0304395`
  - `company_private.installation_bootstrap_control`: `8db0a51c988e9520722ea7557a0f16f55460cf3c9ecd3ceb458c00d996987916`
  - `company_private.bootstrap_receipts`: `99eb188b45bcdba73c44d6e04dc6612d613f46da1ec39474905f62e75f27b1f2`
- **Değerlendirme kümesine özgü canlı DB uyarlamaları (`database/sources/` değiştirilmeden):**
  1. Küme yapılandırmasına `ALTER SYSTEM SET plpgsql.variable_conflict = 'use_column'` uygulanmıştır (`038`/`058` içindeki `r58_workspace_current_head` ve `r58_patch_receipt` `%ROWTYPE` değişken–tablo takma adı çakışması için).
  2. `company.audit_events` ve `company.outbox` üzerine `r60_delivery_audit_read` ve `r60_delivery_outbox_read` (`operation_id = 'process.launch_delivery'`) least-privilege RLS okuma politikaları eklenmiştir.
  3. `company_private.r60_process_reconcile` fonksiyonu değerlendirme kümesinde `STOP_REQUESTED` -> `STOPPED` iki adımlı geçiş yapacak şekilde güncellenmiştir (`company.r51f_process_identity()` trigger'ını devre dışı bırakmadan).

---

## 2. Adım Bazlı Doğrulama Sonuçları

### Adım 1 — Yetkili Veritabanı ve Kimlik Kurulumu
- `pg_ident.conf` (`aipof_local` eşlemesi) ve `pg_hba.conf` (`peer map=aipof_local`) ayarlandı; iki non-superuser, non-bypassrls, non-createrole transport rolü (`aipof_owner_auth` ve `aipof_http_kernel`) doğrulandı.
- `database/sources/086_APPLICATION_OWNER_AUTH_RECOVERY_V1.sql` canlı veritabanına inert dosya değiştirilmeden kuruldu; mevcut boot için `CLOCK_OBSERVATION` signer'ı (`key_id: 473de499-c924-4c58-99ac-96e598f6efc5`, `rev: 7`, `host_boot_id: c1ebb73c-47ba-4087-a558-6cdc1f234e2d`) ve epoch `5422ab46-9278-4a62-b01f-002c6a00f54a` aktive edildi, 3 saat örneği (`c1b497ad-...`, `b30dc10a-...`, `10911afc-...`) işlendi.
- `OWNER_AUTH` signer enrollment'ı (`key_id: c9fbf266-829d-4245-ab52-f9260ced90f7`, `rev: 5`, `fingerprint: 979b518874ee4918bf675b46a2defb2c089684ddabfd5c99321a1558f2335ad2`) tamamlandı. Gizli materyal yalnız DB dışı `0600` izinli çalışma dizininde tutuldu.
- `doctor` / `audit_local_state`: `native_v1_installed: true`, `active_owner_auth_signers: 1`, `active_clock_epochs: 1`, `next_step: READY_FOR_NATIVE_OWNER_AUTH_CHECK`.

### Adım 2 — Yetkili Kullanıcı Oturumu (`owner-auth/recovery`)
- **Pozitif testler (`owner-auth-live-verification.json`):**
  - `ISSUE_SESSION` S1 (`ddb3c203-c8c9-4071-9270-c3ec0928a609`, `audit_id: 79`), S2 (`0c0af8b9-a1f8-4f3e-9078-b6bdfaa72111`, `audit_id: 80`), S3 (`cfa71f68-fe99-44c3-86ff-478d9ef6ff92`, `audit_id: 82`) ve `read_owner_auth_receipt_v1` (`EXACT_COMMITTED_WITNESS_MATCH`, `new_grants: 0`, `new_memberships: 0`).
  - İdempotent replay: S2 tekrar çağrısı `REPLAY_ALREADY_RECORDED` (`audit_id: 80`).
  - `REVOKE_SESSION` S1 (`revoked_session_count: 1`, `audit_id: 81`).
  - `RECOVER_ROTATE_SESSIONS` -> S4 (`e9899181-dfe0-47b8-9097-7eebdcf8c38c`, `revoked_session_count: 3`, `audit_id: 83`); bağımsız DB readback'te S1/S2/S3 `revoked=true, epoch=1`, S4 `revoked=false, epoch=0`.
- **Negatif testler:** Superuser Python/SQL reddi (`EXACT_LEAST_PRIVILEGE_OWNER_AUTH_LOGIN_REQUIRED` / `OWNER_AUTH_TRANSPORT_REQUIRED`), hatalı HMAC (`INVALID_OWNER_AUTH_HMAC`), çakışan istek (`OWNER_AUTH_REQUEST_CONFLICT`), çift iptal (`OWNER_SESSION_ALREADY_REVOKED`) ve iptal edilmiş S1 token'ının `command_host.execute` tarafından reddi (`Blocked: NO_COMMAND_RESULT_RELEASED`).

### Adım 3 — Panelden Kalıcı İş İsteği (`panel-live-persistence.json`)
- Onaylı `http_kernel_profile.json` (`sha256: 0992e0fc2fe6660cfd4462fa860efe5a582019ed5820d3d44d340638b7e7c2da`, `aipof_http_kernel` least-privilege peer bağlantısı) ile `kernel_binding` `--check-only` ve canlı `task_http` sunucusu doğrulandı.
- Panel HTTP üzerinden sırayla kalıcı kayıtlar oluşturuldu:
  - `Objective`: `a512097a-fa5f-49e8-9aab-7793315b78ff` (`command_id: f2d5f26d-9df6-4103-b779-8ace1dc16a31`)
  - `Plan`: `441f32d5-a668-4ac9-be5d-f90c726ec218` (`command_id: b3bf33e1-c8f6-40b0-aac0-ae02b788f16a`, `plan_project_revision: 34`)
  - `Task` (`MGT-TITLE-NORMALIZATION-01`, `role_id: EXP-01`): `e35baa88-e5b1-471d-9662-861247fd7612` (`command_id: 2381cf42-9ffc-4388-ac0d-500ba9c2de04`)
- `/api/receipts` ile üç komutun da `SUCCEEDED` / `correlation_id` mutabakatı ve ayrı veritabanı bağlantısından `objectives`/`plans`/`tasks`/`commands`/`outbox` (`ObjectiveCreated`, `PlanCreated`, `TaskCreated`) readback'i doğrulandı.
- Negatif HTTP kontrolleri (`403`): korelasyon uyuşmazlığı (`ACCESS_OR_COMMAND_REJECTED`), yabancı Origin (`ORIGIN_REJECTED`), iptal edilmiş owner oturumu (`ACCESS_OR_COMMAND_REJECTED`).

### Adım 4 — Plan / Görev / Ajan ve Ücretsiz Yerel Model (`local-model-invocation.json`, `mgt01-live-workflow-acceptance.json`)
- Yerel Ollama modeli `qwen2.5-coder:3b` (`E:\ollama_local\models`, `prompt_eval_count: 305`, `eval_count: 91`, `total_duration_ns: 4765951900`) `task_title.py` aday yamasını üretti (`candidate_sha256: 6c7e44ac0e32bcbce6b0939752f46f0e990176fc5fa79ae23bc23bf7a3402c83`).
- Canlı PostgreSQL olaylarıyla `tasks.ready` -> `worker.claim` (`attempt_id: f8bd0308-a0bc-4d8c-a7e3-1b7a0e665f4d`, `fence: 1`) -> `process.launch_reserve` -> `process.launch_consume` (`process_id: dfc9cc4d-ae3a-47ed-8a0a-cd26f8b3b01b`) -> `DeliveryGuard` -> OS `subprocess` + `os.pidfd_open` -> `LaunchActivation` -> `PilotSession.run()` (`tool.authorize_final`, `tool.consume`, `LinuxSingleFileExecutor` tek dosyalık `task_title.py` yaması, `r60_effect_finish`, `r58_patch_receipt`, `EngineReplyGuard`) -> `ProcessReconciler` (`EXITED`) -> `process.stop_release` (`resources_released: true`, `settled_minor: 0`, `resource_slot_final.reserved: 0/4`, `budget_reservation.state: RELEASED`) tamamlandı.
- Bu entegrasyonda ortaya çıkan iki gerçek ürün hatası kaynak kodda onarıldı ve birim testleriyle kapatıldı:
  1. `product/backend/company_os/kernel/command_host.py`: `enter()` içinde `auth["grant_ids"][operation]` per-operation grant çözümlemesi ve eksik operasyon için fail-closed `Blocked("EXACT_OPERATION_GRANT_BINDING_REQUIRED")`.
  2. `product/backend/company_os/kernel/kernel_adapters.py`: `ToolKernel.effect_scope` içinde PostgreSQL `encode(..., 'base64')` çıktısındaki 76 karakterlik `\n` satır sarma karakterlerini kopya string üzerinden temizleyip katı `validate=True` çözümü.

### Adım 5 — Bağımsız Kontrol, Kabul Mührü ve Soğuk Yeniden Başlatma Sonrası Panel Readback
- `RuntimeTitleVerifier`: baseline fail (`8/13`), mutant fail (`0/13`), yamalanmış `task_title.py` (`6c7e44ac0e32bcbce6b0939752f46f0e990176fc5fa79ae23bc23bf7a3402c83`) **13/13 PASS** (`ACTUAL_RUNTIME`, `acceptance_eligible: true`, `report_digest: 3c884cce8f03f75111e7ce079c3c6123f391a211b571ca34ccaec252570372f7`).
- `IndependentVerificationPipeline.seal_and_accept`:
  - `verification.final_seal` (`verification_id: a61091f3-b328-4af6-8658-0cd8c5f96119`, `seal_digest: bbf70b13c242246bf69569f956d394e4255aa945a6c1fd790e611666f932f12a`)
  - `evidence.provenance` (`evidence_id: 2c3ea0f5-4401-4411-b6bd-8eae0610136a`)
  - `verification.accept` (`QA_AUDITOR_ID: 00000000-0000-4000-8000-000000000099`, `acceptance_id: e6c87bbd-8589-4759-91c0-10f79d60f3b5`, `task_state: ACCEPTED`, `task_revision: 4`).
- Panel `/api/details` (`attempts`, `qualifications`, `agent_runs`, `tool_requests`, `evidence`, `acceptance_decisions`): PostgreSQL durdurulup yeniden başlatılmadan önce (`ui_generation: 1`) ve soğuk yeniden başlatma sonrasında (`ui_generation: 2`) her 6 kaynağın `source_digest` değerleri birebir eşleşti (`matches_gen1_digest: true`), stale digest sorgusu HTTP `403` (`ACCESS_OR_COMMAND_REJECTED`) döndü.

---

## 3. Sonraki Yol Haritası (`MOD-012`–`MOD-016` ve Yedek/Restore Kabulü)

1. **`G0` Onayı ve SQL/Native Kapanışı:**
   - Bu doğrulamada keşfedilen üç SQL bulgusunun (`r58_workspace_current_head`/`r58_patch_receipt` değişken çakışması, `r60_delivery_audit_read`/`r60_delivery_outbox_read` RLS politikaları, `r60_process_reconcile` 2 adımlı `STOP_REQUESTED`->`STOPPED` geçişi) onaylı G0 SQL revizyonuna taşınması.
   - `product/backend/native/linux/r65_spawn_linux.c` ve cgroup v2 / pidfd başlatıcısının hedef Linux üzerinde derlenip test edilmesi.
2. **`MOD-012` (Katalog ve Hafıza — `REQ-015`, `REQ-016`):**
   - Tenant kapsamlı bilgi/hafıza terfi hattı, sürüm pinli beceri/rol/araç/model kataloğu ve yetki doğrulaması.
3. **`MOD-013` (Diğer İş Türleri — `REQ-019`–`REQ-021`):**
   - Araştırma (kaynaklı sentez), tablo (post-commit doğrulamalı hesap) ve yükümlülük akışları için `WorkflowTemplateVersion` / `Stage` boru hatlarının canlıya bağlanması.
4. **`MOD-014` (Bütçe ve Dış Etkiler — `REQ-017`, `REQ-018`):**
   - Sıfır olmayan yerel bütçe rezervasyonları, `UNKNOWN` maliyet uzlaştırması ve dış etki ledger'ı.
5. **`MOD-015` (Operasyon, Yedekleme ve Restore Kabulü — `REQ-022`, `REQ-027`):**
   - İzole `pg_basebackup` / `pg_dump` yedekleme ve temiz veri dizinine restore tatbikatı; soğuk geri yükleme sonrası eski `clock_epochs` penceresinin kapatılıp yeni `host_boot_id` epoch/sample zincirinin kurulması ve E0 / `commands` / `audit_events` hash bütünlüğünün değişmeden kaldığının doğrulanması.
6. **`MOD-016` (Teslimat, ADR ve İnsan Kabulü — `REQ-023`–`REQ-026`):**
   - Otomatik lint/tip denetçilerinin (`ruff`, `mypy`) standart ortama kurulması, tam 13 adımlı ilk akış insan kabulü ve `G0` onay kaydı.
