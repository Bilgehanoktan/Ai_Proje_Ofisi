# AI Proje Ofisi — Üretim İşletim ve Operasyon Rehberi

- Canonical workspace: `E:\Projeler\Ai_Proje_Ofisi`
- Son güncelleme: 2026-11-23
- Kapsam: PostgreSQL 18.6 (`001..087`), `OWNER_AUTH` anahtar/oturum rotasyonu, `r65_spawn_linux.c` cgroup v2 delegasyonu, `AutonomousWorkerDaemon` ve yedek/kurtarma.

## 1. Veritabanı Kurulumu ve Migration Sırası (`001..087`)
- Resmî sıralama ve SHA256 pinleri: `database/assembly/assembly.json`.
- Tüm kaynak SQL dosyaları (`database/sources/001..087`) güvenlik gereği `DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED` / `ROLLBACK;` ile inert tutulur; otomatik çalışma kapalıdır.
- Temiz kurulum doğrulaması:
  ```bash
  PYTHONPATH=. python3 -B scripts/verification/verify_087_migration_pg.py
  ```
- Beklenen sonuç: 4 yeni `087` tablosu (`catalog_entries`, `memory_promotions`, `work_template_validations`, `external_effect_ledger`) `FORCE ROW LEVEL SECURITY` aktif, `disabled_user_triggers = 0`, E0 tabloları değişmez.

## 2. Native C Başlatıcı (`r65_spawn_linux.c`) ve cgroup v2 Delegasyonu
- Derleme (sıfır uyarı zorunlu):
  ```bash
  gcc -Wall -Wextra -Werror -O2 -shared -fPIC \
    -o /opt/aipof/lib/r65_spawn_linux.so \
    product/backend/native/linux/r65_spawn_linux.c
  ```
- Non-root servis kullanıcısı için delegated cgroup v2 leaf oluşturun ve servis PID'ini ortak ata cgroup içine yerleştirin.
- Doğrulama:
  ```bash
  AIPOF_CGROUP_PATH=/sys/fs/cgroup/aipof_eval/worker \
    python3 -B scripts/verification/verify_mgt01_native_launcher.py
  ```

## 3. Yedekleme, Restore ve Saat Dönemi Kurtarma (MOD-015)
1. Fiziksel yedek: `pg_basebackup` + `pg_verifybackup`.
2. Restore sonrası **eski saat dönemi (`clock_epoch`) geçersizleştirilir**, eski oturumlar ve stale örnekler reddedilir, yeni `host_boot_id` ile taze saat dönemi ve en az 2 örnek aktive edilir.
3. Tatbikat betikleri:
   - `scripts/verification/verify_disposable_restore.py`
   - `scripts/verification/verify_restore_epoch_retirement.py`

## 4. `OWNER_AUTH` Anahtar & Oturum Rotasyonu
- Gizli anahtar materyali veritabanı dışında `0600` izinli dizinde saklanır; hiçbir sır depoya veya loglara yazılmaz.
- Oturum iptali/rotasyonu `086_APPLICATION_OWNER_AUTH_RECOVERY_V1.sql` fonksiyonları (`REVOKE_SESSION`, `RECOVER_ROTATE_SESSIONS`) ile least-privilege `aipof_owner_auth` rolünden çalıştırılır.

## 5. Otonom Worker Daemon ve Canlı API Uçları
- Otonom döngü: `company_os.runtime.worker_daemon.AutonomousWorkerDaemon` (`max_consecutive_errors` devre kesici ile fail-closed durur).
- Salt-okunur tenant-scoped API uçları (`company_os.api.http.app.make_wsgi_app`):
  - `GET /api/status`
  - `GET /api/work-types`
  - `GET /api/events?tenant_id=<uuid>` (SSE)
  - `GET /api/catalog?tenant_id=<uuid>`
  - `GET /api/memory-promotions?tenant_id=<uuid>`
  - `GET /api/external-effects?tenant_id=<uuid>`

## 001–088 geçici PostgreSQL kontrolü

24 Kasım 2026 koşusunda `scripts/verification/verify_087_migration_pg.py` pinli 001–088 assembly sırasını geçici Linux PostgreSQL kümesinde rollback ile uyguladı. 087 için dört, 088 için iki FORCE RLS tablosu ve 087 görev ayrılığı kısıtı doğrulandı. Kalıcı temiz kurulum ve 087 → 088 yükseltme provası açık.
