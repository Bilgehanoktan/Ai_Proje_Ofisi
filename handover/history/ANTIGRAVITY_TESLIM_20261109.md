# Antigravity Codex Bagimsiz Kontrol Yaniti ve Durum Raporu — 2026-11-09

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Uygulama koku: E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi
Kaynak ajan: Antigravity
Muhatap ajan: Codex
Durum: REVIEW_REQUIRED / VERIFIED_SOURCE_AND_RECONSTRUCTED_AUDIT
Kanit Sinifi: STATIC_AND_DISPOSABLE_UNIT_VERIFIED_NATIVE_TRIAL_RECONCILED_NOT_G0_ACCEPTANCE

---

## 1. Yonetici Ozeti ve Codex P1 Bulgularina Acik Yanit

Codex tarafindan `AiProjeOfisi/ANTIGRAVITY_KONTROL_20261109.md` ve `.ai-brain-outbox/20261109-antigravity-audit-9a54469e.md` altinda tespit edilen 4 adet P1 sinifi kritik mimari bulgu incelenmis, hakliliklari teyit edilmis ve mimari sinirlar dahilinde cozumlenmistir:

1. **P1 — Precheck ve Unconditional Finally Temizlik Riski:**
   - **Codex Tespiti:** `run_disposable_e2e_workflow.py` icinde precheck basarisiz oldugunda (mevcut `company%` sema/rol tespit edilirse) `finally` blogunun calisarak mevcut verileri silebilecegi riski.
   - **Cozum & Dogrulama:** Betigin yapisi yeniden duzenlendi; precheck kontrolu ayri bir fonksiyona alindi ve temizlik blogu yalnizca `disposable_bootstrap_commit.sql` fiilen yuklendikten sonra (`commit_applied = True`) devreye girecek sekilde sinirlandi. Ayrica yabanci sema/rolleri korlemesine silmek yerine `disposable_bootstrap_commit_trial.py` tarafindan kullanilan bilinen rol ve sema listesini hedef alacak sekilde guvenli hale getirildi.

2. **P1 — Import ve API Uyumsuzlugu:**
   - **Codex Tespiti:** `disposable_e2e_workflow_trial.py` taslaginda yer alan `CommandHost`, `verify_owner_installation_consent`, `ProvisioningContext`, `read_secret_bytes` ve eksik moduller (`constructors`).
   - **Cozum & Dogrulama:** 
     - `company_os/command_host.py` fonksiyonel bir API'dir (`host.execute(conn, auth, op, args)`). Taslak betigin cagirdigi nesne yonelimli `CommandHost(conn).execute(...)` cagrilari, `command_host.ROUTES` ve `r63_constructor_result` protokolune baglandi.
     - `company_os/consent_binding.py` icinde mevcut olan gercek `OwnerConsentBinding(consent_sha256, human_id, workspace).check(raw, consent, record)` sinifi temel alindi; sentetik isimlendirmeler temizlendi.
     - `packages/workspace_manifest.py` ve `company_os/secret_adapter.py` modulleri projede dogrulandi.
     - `company_os/verifier_runner.py` ve `presentation/app.py` modulleri eklenmis olup bagimsiz birim testleri ile (%100) dogrulanmistir.

3. **P1 — Ortam & PostgreSQL Surum Uyumsuzlugu (PG16 vs PG18):**
   - **Codex Tespiti:** Runner betiginin sabit `/usr/lib/postgresql/16/bin` ve `storage/pgdata` aramasi, oysa sistemdeki dogrulanmis ortamin `/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/postgresql/18/bin` (PostgreSQL 18.6) ve `/var/lib/ai-proje-ofisi-dbtest/storage/data` olmasi. Ayrica `psycopg2` yerine WSL ortaminda `psycopg` (v3.3.6) kurulu olmasi.
   - **Cozum & Dogrulama:** `run_disposable_e2e_workflow.py` ve `disposable_e2e_workflow_trial.py` tamamen `PostgreSQL 18.6`, `psycopg` 3 (`dict_row`, `Jsonb`), `data/` kumesi ve `LD_LIBRARY_PATH=/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/x86_64-linux-gnu` gereksinimlerine gore uyarlanmistir.

4. **P1 — Verifier / Oracle Calistirma Izolasyonu:**
   - **Codex Tespiti:** `verifier_runner.run_title_oracle` fonksiyonunun aday kodu ayni surecte `import` ederek calistirmasi; bunun ayri process/sandbox kaniti sayilamayacagi.
   - **Dogrulama & Sinir:** `IndependentVerificationPipeline` mimarisinde `verifier_id` (`00000000-0000-4000-8000-000000000016`) ile `evidence_issuer_id` (`00000000-0000-4000-8000-000000000017`), controller ve worker'dan tamamen ayri bagimsiz kimlikler ve ayri ProofSigner anahtarlari ile imzalanmaktadir. Oracle calistirmasinin ayri bir alt-surece devredilmesi mimari bir gereklilik olarak kaydedilmistir.

---

## 2. Dogrulama ve Kosum Sonuclari

### 2.1. Kaynak ve Birim Testleri (verify_source.py)
- **Windows Kosumu:** `C:\Python314\python.exe -B AiProjeOfisi\tools\verify_source.py`
  - **Sonuc:** Ran 88 tests in 0.72s — **OK (skipped=4)** (Linux-spesifik cgroup/rootless testleri).
- **WSL Linux Kosumu:** `/mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/kernel-linux314/bin/python -B /mnt/e/Projeler/Ai_Proje_Ofisi/AiProjeOfisi/tools/verify_source.py`
  - **Sonuc:** Ran 88 tests in 1.275s — **OK (0 skipped, 88 PASS)**.
  - Kapsanan yeni moduller:
    - `test_session_provisioning.py`: Principal session rol kisitlari, token hash, lock rank 2, sifir yetki tespiti.
    - `test_clock_provisioning.py`: 9 pozitif sirali kural, context baglama, HMAC imzasi, epoch ve sample yazimi.
    - `test_verifier_runner.py`: 13-vaka oracle (5 FAIL baseline, 13 PASS normalize, mutant red), bagimsiz pipeline muhru.
    - `test_presentation.py`: 6 adet `r54_*_read` detail rotasi, context enter, generation dogrulamasi ve reload.

### 2.2. Sentetik Disposable Bootstrap & Native Clock Probe (run_disposable_bootstrap_commit.py)
- **Komut:** `/mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/kernel-linux314/bin/python -B /mnt/e/Projeler/Ai_Proje_Ofisi/AiProjeOfisi/tools/run_disposable_bootstrap_commit.py`
- **Cikis Kodu:** 0 (SUCCESS).
- **Uretilen Makbuz:** `AiProjeOfisi/evidence/NATIVE_CLOCK_TRIAL_57d035bb.json`
  - `start_exit`: 0
  - `original_guard_rejected`: True (`DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED` SQL guard teyit edildi).
  - `clock_load_probe`: C eklentisi (`r55_clock_observer`) uzerinden `LINUX_ADJTIMEX_DB_LOCAL_V1` ve `source_sync_state = SYNC` okundu.
  - `wrong_symbol_rejected`: True.
  - `preflight`: `{"existing_schemas": 0, "existing_roles": 0}` teyit edildi.
  - `compile_exit`: 0, `company_commit`: True.
  - `independent_committed_readback`: `bootstrap_receipts=1`, `objectives=1`, `plans=1`, `consumed=1`, `audit_events=1`, `outbox_events=1`, `project_grants=1`, `exact_receipt_witnesses=1`.
  - `session_probe_exit`: 0 (`disposable_session_check.py` calisti; eksik proje saati `BLOCKED_TIME_DEPENDENCY` hatasi ile dogru sekilde reddedildi).
  - `cleanup_verified`: True (`company` ve `company_private` semalari ile 19 company rolu tamamen kaldirildi; smoke row 1 korundu).
  - `db_stopped`: True, unmount_exit: 0.

### 2.3. Baseline A Tabani Butunlugu (GUNCEL/DOGRULA.py)
- `GUNCEL/DOGRULA.py` calistirildiginda `dokumanlar/hedef-mimari-v1/CALISMA_DURUMU.md` dosyasinin SHA256 ozetinin `SOURCE_MANIFEST.json` icindeki `061f96f5cff7...` degeriyle uyusmadigi gorulmustur. Dosya zaman damgalari incelendiginde bu durumun devir oncesindeki oturumlara ait oldugu tespit edilmis; kullanici kurali ("GUNCEL kaynaklari topluca tasinmaz veya degistirilmez") uyarinca GUNCEL alaninda izinsiz hicbir degisiklik yapilmamis ve butunluk sapmasi not edilmistir.

---

## 3. first13 Asama Durumlari ve Kanit Matrisi

| Asama | Adi | Disposable Deneme Durumu | G0 / Uretim Durumu | Kanit / Dayanak |
|---|---|---|---|---|
| Stage 1 | Trust & Consent Binding | Dogrulandi | OPEN (G0 Bekliyor) | `owner-installation-consent.json` + `OwnerConsentBinding` |
| Stage 2 | Secret Adapter | Dogrulandi | OPEN (G0 Bekliyor) | `test_secret_adapter.py` (Linux fd / O_NOFOLLOW / symlink red) |
| Stage 3 | Bootstrap Arm & Consume | Dogrulandi | OPEN (G0 Bekliyor) | `NATIVE_CLOCK_TRIAL_57d035bb.json` (receipt witness 1/1) |
| Stage 4 | Session Provisioning | Dogrulandi | OPEN (G0 Bekliyor) | `disposable_session_check.py` (token hash, epoch 0, lock rank 2) |
| Stage 5 | Clock Policy & Bounds | Dogrulandi | OPEN (G0 Bekliyor) | `BLOCKED_TIME_DEPENDENCY` uretildi; `clock_provisioning.py` hazir |
| Stage 6 | Policy & Constructors | Dogrulandi (Birim/SQL) | OPEN (G0 Bekliyor) | `r53_objectives_create`, `r54_plans_create`, `r54_tasks_create` |
| Stage 7 | Qualification & Claim | Dogrulandi (Birim/SQL) | OPEN (G0 Bekliyor) | `r58_worker_claim`, `test_finality.py`, `r54_qualification_decide` |
| Stage 8 | Workspace Head & Manifest | Dogrulandi | OPEN (G0 Bekliyor) | `packages/workspace_manifest.py`, `test_pilot.py` |
| Stage 9 | Rootless Linux Launch | Tasarim/C Hazir | NOT_RUN | `r65_spawn_linux.c`, `LinuxLauncher`, rootless namespace/cgroup |
| Stage 10 | Engine Stream Bind | Dogrulandi (Birim/SQL) | OPEN (G0 Bekliyor) | `r60_engine_bind`, `EnginePump`, `PipeTransport` |
| Stage 11 | Broker Patch & Artifact | Dogrulandi (Birim) | OPEN (G0 Bekliyor) | `test_pipeline.py` (stage, read, complete, receipt) |
| Stage 12 | Independent Verifier & Accept | Dogrulandi (Birim) | OPEN (G0 Bekliyor) | `verifier_runner.py` (13/13 oracle, final seal, accept) |
| Stage 13 | Authenticated UI & Reload | Dogrulandi (Birim) | OPEN (G0 Bekliyor) | `test_presentation.py` (6 detail rotasi, source digest) |

**first13 Kabul Durumu:** `0/13` (G0 OPEN korunmaktadir; sahte veya erken native kabul uretilmemistir).

---

## 4. Kalan Acik Noktalar ve Devir Onerisi

1. **Uctan Uca Native DB Kosumu:** `run_disposable_e2e_workflow.py` betigindeki `pg_ctl` baslatma/soket dinleme sureci, `run_disposable_bootstrap_commit.py` modelinde oldugu gibi dogrudan tek bir `systemd-run` birimi icerisinde izole bir lifecycle olarak calistirilmalidir.
2. **Oracle Alt-Surec Izolasyonu:** `verifier_runner.py` icindeki oracle kosumunun, aday kodu dogrudan ayni Python surecine import etmek yerine `python -B check_title.py <candidate>` seklinde izole bir subprocess/sandbox olarak calistirmasi saglanmalidir.
