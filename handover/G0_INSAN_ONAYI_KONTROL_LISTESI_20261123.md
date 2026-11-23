# G0 İnsan Onayı ve First13 Kabul Kontrol Listesi

- Tarih: 2026-11-23
- Canonical workspace: `E:\Projeler\Ai_Proje_Ofisi`
- Resmî Durum: **G0: APPROVED_BY_HUMAN (2026-11-23)** | **first13: 13/13 (ACCEPTED)** | **087 canlı PG + R65NativeLauncher MGT-01: PASS**
- Kural: İnsan onayı kullanıcı tarafından 2026-11-23 tarihinde verilmiştir; teknik kanıtlar ve statik bütünlük kontrolleri aşağıda kayıtlıdır.

## Doğrulanmış Teknik Kanıtlar
1. **Kaynak & Layout Bütünlüğü:** `scripts/development/run.py verify` ve `scripts/verification/verify_layout.py` (**PASS**, `failures: []`).
2. **MOD-001 – MOD-010 (İlk Akış `MGT-TITLE-NORMALIZATION-01`):** Yerel WSL PostgreSQL 18.6 değerlendirme kümesinde 086 canlı kurulumu, owner-auth/recovery, saat epoch, HTTP panel Objective/Plan/Task + `/api/receipts`, yerel Ollama (`qwen2.5-coder:3b`), OS subprocess/pidfd + Broker + `PilotSession`, `RuntimeTitleVerifier` (13/13) + `IndependentVerificationPipeline` (`ACCEPTED`) ve PG soğuk restart sonrası 6 `/api/details` readback (`handover/LIVE_FLOW_VERIFICATION_20261120.md`).
3. **MOD-004 (Native C `r65_spawn_linux.c` & cgroup v2 + MGT-01):** `scripts/verification/verify_r65_spawn_native.py` ve `scripts/verification/verify_mgt01_native_launcher.py` (`evidence/runs/mgt01-native-launcher-20261123.json`) ile `gcc -Wall -Wextra -Werror` sıfır uyarı derleme, delegated `cgroup2fs` içinde `clone3(CLONE_INTO_CGROUP|CLONE_PIDFD)` + `seccomp` + `execveat` -> `child_exit_code: 0`, `task_title.py` yama üretimi ve `mgt01.check_title.13cases.v1` **13/13 PASS**.
4. **MOD-015 (Yedek, Restore & Saat Dönemi Kurtarma):** `scripts/verification/verify_disposable_restore.py` (9 tablo özeti eşleşti) ve `scripts/verification/verify_restore_epoch_retirement.py` (eski epoch geçersizleştirme, `bounds`/stale-sample/reopen reddi, taze boot epoch + 2 sample aktivasyonu).
5. **MOD-011 – MOD-014 & 087 Canlı Migration:** `087_MOD012_MOD014_EXTENSIONS_CANDIDATE.sql` `database/assembly/assembly.json` içine 87. migration olarak eklendi; temiz PG 18.6 (`scripts/verification/verify_087_migration_pg.py`) ve canlı PG 18.6 değerlendirme kümesinde (`/var/lib/ai-proje-ofisi-local`, port `55490`, `evidence/runs/migration-087-live-20261123.json`) 4 FORCE RLS tablosu + separation-of-duties CHECK + `disabled_user_triggers: 0` doğrulandı.

## İnsan Onayı Kaydı
- [x] G0 geçiş kapısı onayı — Kullanıcı tarafından 2026-11-23 tarihinde sohbet üzerinden açıkça onaylandı ("ben onayları veriyorum").
- [x] İlk akış (`MGT-TITLE-NORMALIZATION-01`) 13/13 kabul onayı — Kullanıcı tarafından 2026-11-23 tarihinde onaylandı.
- [x] Üretim anahtar/oturum geçişi ve `087` + `r65_spawn_linux.c` canlı hat bağlantısı onayı — Kullanıcı tarafından 2026-11-23 tarihinde onaylandı.

> Not: `verify_layout.py` içindeki tarihsel `G0: OPEN` / `first13: 0/13` statik rapor alanları, ilgili sürüm geçiş betikleri ayrıca güncellenene kadar kaynak bütünlüğü raporu olarak korunur.
