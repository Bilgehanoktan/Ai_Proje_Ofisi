# PostgreSQL bootstrap okuyucu — sınırlı gerçek DB mekanizma deneyi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-13
Kaynak ajan: Codex
Durum: VERIFIED_SYNTHETIC_NATIVE_SQL_FIXTURE; ACTUAL_APPLICATION_INTEGRATION_NOT_RUN
Kanıt: evidence/CODEX_PG_READER_20261113_native.json; evidence/CODEX_PG_READER_20261113_stderr.log; evidence/CODEX_PG_READER_20261113_manifest.json; tools/probe_bootstrap_reader_pg.py.

## TaskSpec

TASK-CODEX-20261113-02; mevcut tasarım §16/27/28; MOD-001/016, PH-01, P0-1/P0-3 reader alt kapsamı. Amaç bootstrap_readback.py sorgu/driver/SELECT privilege/digest/persistent readback davranışını gerçek PostgreSQLde sınamak. Allowlist:yeni tools/probe_bootstrap_reader_pg.py; bu rapor, ilgili takip/backlog ve CODEX_PG_READER_20261113 kanıtları. Ürün/native SQL kaynağı değiştirilmedi. Önceki owning kaynak CODEX_YETKI_ADAPTERLERI_20261113.md ve bootstrap_readback.py. G0/first13/insan kabulü yükseltilmez.

## Neden ayrı deney

Eski bootstrap lifecycle scripti disk imajı mount ve bootstrap yazımı içeriyordu; çalıştırılmadı. Yeni deney mevcut data/socket/disk imajına bağlanmaz. Her koşumda yeni, uniquely created/resolved /tmp/aipof-reader-pg-* dizini, özel data/socket0700 ve uid999 kullanır. Mevcut native83assembly/guardlar çalıştırılmadı, değiştirilmedi veya sökülmedi.

Yalnız sorgunun kullandığı kolonlara sahip minimal SQL contract fixture kuruldu. Bu fixture full schema/constraint/RLS/migration kabulü değildir. Sentetik HUMAN/OWNER metadata gerçek insan enrollmentı değildir. Deney içinde iki geçici DB login rolü oluşturuldu: biri SELECT yetkili, diğeri SELECT yetkisiz. Roller/grantlar yalnız yeni private test kümesindeydi; kümeyle birlikte kaldırıldı. Uygulama/project grant veya gerçek trust root oluşturulmadı.

Local auth yalnız private uid999 dizin/socket içinde TRUST;hostauthREJECT,TCP listen_addresses boş. Bu test ayarı üretim/runtime auth politikası değildir. İşlem/alt süreçlerde CORE0,NOFILE256,AS1GiB;Postgres shared_buffers16MB,max_connections5,max_worker_processes0,max_parallel_workers0 ve finite startup/stop/outer timeout kullanıldı. Kod temizlemeden önce resolved temp parent/prefix kontrol eder; server stop doğrulanmazsa data dizini silinmez.

## Gerçek ölçülen sonuçlar

- PostgreSQL18.6 Ubuntu18.6-0ubuntu0.26.04.1, mevcut özel test binaryleri;psycopg3.3.6;uid999.
- Doğru receipt/command/audit/outbox witness zinciri gerçek query ile MATCH. UUID::text dönüşü ve PostgreSQLjsonb SHA256 ifadesi beklenen pinlerle eşleşti.
- Recording cursor actual PostgreSQL current_setting üzerinden transaction_read_only=on ve transaction_isolation=repeatable read gördü. Bu gözlem ürün adapterinin gerçek BEGINinden sonra, aynı bağlantıda yapıldı; yalnız string kaynak kontrolü değildir.
-12negatif gerçek DBde reddedildi:control generation,owner kind,owner membership,command digest,command payload,audit kind,event digest,event generation,wrong reader login,foreign expected project,missing SELECT privilege,reader INSERT permission.
- Negatif fixture mutasyonları private adminde commit edildi; bağımsız reader bağlantısı sonucu gördü; her mutasyon restore edildi. Bunlar sentetik test metadata commitleridir; uygulama bootstrap commit/enrollment kabulü değildir.
- Son bağımsız readback PASS; kayıtlı reader bağlantılarının tamamı kapandı.
- Aynı özel PostgreSQL kümesi fast restart edildi; yeni reader connection ile result/digest/identity birebir aynı kaldı.
- stop_exit0,private_server_stopped=true,temporary_cluster_removed=true,existing_clusters_touched=false. WSL systemd user-session uyarısı yine görüldü; onarılmadı, test DB sonucuyla karıştırılmadı.

Evidence scope: SYNTHETIC_NATIVE_MINIMAL_SQL_FIXTURE_NOT_ENROLLMENT_OR_FULL_ASSEMBLY;application_acceptance=false. Salt readonly reader MATCH current authorization üretmez.

## Güncellik ve sınırlar

Son207testlik source/fake-driver suite bu dilimde yeniden koşulmadı; ürün kodu/testleri değişmedi. CODEX_AUTHORITY_20261113 manifestindeki22dosya native deney sonrasında yeniden SHA256 ile karşılaştırıldı; fark yok. Bu22pin kontrolü bütün proje için tazelik veya full test iddiası değildir. Son suite kanıtı Windows187PASS20SKIP,Linuxuid999 207PASS0SKIP olarak önceki loglarda korunur.

Gerçek83kaynaklı katalog/RLS/ACL/native clock/current root ve approved reader login üzerinde test edilmedi. Gerçek owner/technical enrollment,full runtime profile,peer/enrollment/fence/journal/ledger current authority adapterleri,immutable resolver,qualified candidate launcher ve ilk SOFTWARE Kernel/DB/OS zinciri açık. config/profiles JSON hâlâ yok. G0OPEN,first13 0/13;tam16MOD/PH00–06 hedefi korunur;tam modül veya insan kabulü yok. GUNCEL CALISMA_DURUMU.md eski hash sorunu bu dilimde yeniden test edilmedi.

## Devam ve geri dönüş

Bootstrap adapterinin minimal SQL/driver/read-only/permission/restart mekanizması artık gerçek PostgreSQL kanıtına sahip. Sonraki owning iş mevcut83kaynaklı katalogda approved SELECT/RLS görünürlüğü ve gerçek root/bootstrap kayıtlarını doğrulamak; ardından current signer/peer/profile readback bağlarını native yetki sınırları içinde uygulamak. Minimal fixture PASS bu gerçek kayıtları onaylamaz.

Yeni test aracı ve kanıt pinleri manifestte. Ürün koduna rollback gerekmedi; otomatik grant/fence/epoch geri sarma yapılmadı. Temizlik yalnız testin yarattığı özel küme/dizine uygulandı. Hafıza yazımı/aktarımı uygulama kabulünden ayrıdır.
