# Antigravity — sıradaki uygulama paketi ve tam mimari takip
Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Uygulama kökü: E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi
Tarih: 2026-11-10
Durum: HANDOFF_READY / NOT_DISPATCHED

Kullanıcı hedefi mevcut mimarinin TAMAMINI uygulamaktır. İlk gerçek SOFTWARE akışı yalnız ara entegrasyon/kabul teslimidir; tam kapsamın yerine geçmez. Yeni mimari tasarlama, mevcut modülleri daraltma veya ilk akıştan sonraki fazları iş listesinden çıkarma. Kod değişiklikleri yeni uygulama kökünde yapılır. Önce iki AGENTS.md ve mevcut devir promptunu oku.

## Mimari otorite ve mevcut sonuç

Ana giriş: E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v0.16.2-r68.md
Ayrıntılı hedef ve son ekler: E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\hedef-mimari-v1\PROJE_TASARIM_DOKUMANI.md
Faz/iz kayıtları: aynı dizindeki UYGULAMA_YOL_HARITASI.md, GEREKSINIM_IZLENEBILIRLIK.md, MIMARI_ACIK_KONULAR.md ve inceleme/SONRAKI_ADIMLAR_v1/07_DB_DILIMI.md..12_GENISLEME.md.
Uygulama planı: E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi\PLAN.md;16MOD:module-map.json.
Kullanıcının şirket sahipliği ve yerel kurulum izni config/owner-installation-consent.json içinde;aynı izni tekrar sorma. İzin bağımsız kimlik veya G0 kabulü değildir. Güvenlik kapılarını stub/bypass etme;paid/PROD/dış iletişim açma.

Codex 2026-11-10 bağımsız kaynak koşumu89test85PASS4LinuxSKIP. Teslimin Linux89PASS iddiası bu incelemede yeniden koşturulmadı. NATIVE_CLOCK_TRIAL_a20c6386.json bootstrap/session sentetik commit/readback/cleanup sonucu taşıyor;clock eksikliğinde ret devam ediyor. Tam nativeE2E sonucu değildir. first13 0/13,G0OPEN.

Yapılmış işleri tekrar yapma: clock explicitpolicy ve explicit source_sync_state kontrolleri kaynakta mevcut;cleanup bootstrap_applied/exact19role listesine bağlanmış;PG18/psycopg3 uyarlamaları var. Bunların tüm native davranışlarının kabulü hâlâ ayrıca gerekir.

## P0 — Önce bu iki gerçek eksikliği kodla ve kapat

1. VERIFIER FALSE-PASS: Beklenen13case ID ve exit0 kontrolü tek başına yeterli değil. run_title_oracle'ın subprocessinde candidate import edilirken candidate stdouta beklenen13PASS yazıp os._exit(0) yapabiliyor. normalize_title bile olmayan bu candidate Codex denemesinde PASS13 aldı. Trusted verifier test kontrolü ile aday kod yürütmesini ayrı güven sınırlarına al. Adayın çıktı kanalı oracle verdict/rapor kanalı olarak kullanılmasın. Güvenilir harness test girdilerini yönetmeli, aday yalnız sınırlı çağrı sonuçları üretebilmeli;aday trusted report state/expected results/signing key'e erişememeli. Yalnız bir returncode/JSON kontrolü veya fonksiyon adının kaynakta aranması çözüm değildir. Timeout, child/cgroup cleanup ve çıktı byte sınırı okuma sırasında uygulanmalı;capture_output tamamlandıktan sonra len kontrolü bellek sınırı değildir.

Regresyonlar: exit7/sahteID;exit0/beklenenID/sahte13PASS;candidate os._exit(0) ile erken çıkış;oracle globalstate manipülasyonu;bozuk/duplicate/eksikcase;çıktı taşması;timeout;normal baseline FAIL/doğru candidate PASS/mutant FAIL. Bu fixtureların worker çıktısı veya actual model kabulü olmadığını belirt.

2. E2E KABLOLAMA: tools/disposable_e2e_workflow_trial.py hâlâ verify_owner_installation_consent,constructors,PumpLimits,SpawnPlan,ProvisioningContext,read_secret_bytes vb olmayan importlar içeriyor. Sembolleri eşleme raporunda saymak değil,gerçek çağrı noktalarını owning APIlere uyarla. Shim ile olmayan authority veya sahte başarılı sonuç üretme. Mevcut command_host.execute,OwnerConsentBinding,ProofSigner/DbScope/DeliveryGuard,PilotSession,read_enrolled_key imzalarını kullan. Tüm importları ve constructor imzalarını DB başlatmadan preflight ile doğrula.

PostgreSQL pg_ctl start/harness/stop aynı bounded systemd yaşam döngüsünde tutulmalı;ayrı run_dbtest(pg_ctl start) transient processin ölmesine neden olabilir. Tek birimin içindeki subprocess psqller aynı network/socket namespaceini kullanmalı. Başlamadan temiz baseline/pin/uid/mount/source sahipliği;yalnız denemenin oluşturduğu exactnesneleri cleanup et. Başarısız preflight mevcut veriyi silemez. Başlatamadığın DByi veya başka çalışmanın mountunu durdurma/ayırma. Check/finallyhatasağlamsakayıt,timeoutvecleanupfailingressi test et. 512MiB/swap0/finiteCPU/pids/no-network/readonlysystem/privatewritabledata sınırlarını koru.

## P1 — Çalışan ilk native zinciri tamamla

P0 sonrası model/host/signerdigest/enrollment ve actual policy koşullarını owning source üzerinden doğrula. Önce clock policy→host/signer enrollment→epoch→sample→current bounds positive ve UNKNOWN/wrongboot/stalesample/forgedproof negatifleri. BLOCKED_TIME_DEPENDENCY ret testi clock activation PASS değildir.

Ardından sırasıyla:
- gerçek yetkili Objective→Plan→Task ve ayrıconnectionreceipt/revision/audit/outbox readback;
- Qualification,freshclaim/lease/fence,rootlessLinuxlaunch veengineboundchannel;
- Broker/CAS/immutableArtifact ve gerçek worker çıktısı;
- ayrıidentity/process/key/profile bağımsızverifier→seal/provenance→Kernelaccept/reject;
- minimum authenticatedUI ve DBrestart/yenidengiriş/reload.

Kaynakta bulunmayan bir privilege,policy veya portu gerçekten uygulaman gerekiyorsa açıkça kaynak/dayanak ve diff ile belirt. Identity/consent/hash/custody'yi eşitleme. Gerçek engelde komut,exit,owningsource ve eksik önkoşulu kaydet;aynı incelemeyi her tur yeniden anlatıp ilerlemesiz teslim yapma. Tek doğrulanmış engel varsa bağımsız yapılabilen sonraki uygulama işlerini sürdür.

## P2 — Tam mimari görünürlüğü ve sonraki fazlar

Bu teslimde16MODtamamının durumunu gösteren UYGULAMA_DURUM_MATRISI.md oluştur/güncelle. Her satırda MOD/ad,owningsource,gerçekuygulamadosyaları,bağımlılıklar,kanıt ve durum olsun:UYGULANMADI/KAYNAK_HAZIR/BAGLI/GERCEK_TEST_EDILDI/KABUL_EDILDI. Farklıkanıtsınıflarını tekPASS'e birleştirme.

Tüm proje planında MOD001..016korunsun:Kernel/identity;CEO/hedefplan;Scheduler/Qualification;Launch/isolation;Engine/provider;Broker;Workspace/Artifact;Verifier;Acceptance/release;Event/projection;Yönetim/ofis;Katalog/hafıza;WorkType;Bütçe/ticari/etkiler;Recovery/backup;Kalite/teslimyönetişimi. İlkakışsonrası mevcut11Yönetim/12Genişleme kartlarına ve PH05/PH06bağımlılıklarına göre kalan modülleri sırala. İlkakış uğruna vizyonu küçültme;ilkakış kapanmadan gelişmişofis veya yeniworktype ile kapsamı dağıtma.

## Codex teslimi

Değişendosyalar,exactkomut/exit/testsonuçları,source/build/fixture/digest/attempt/fence bağları,rawreceiptleri,negatifvakalari veortamsondurumunu sun. Code/unit/fake/syntheticnative/actualownerenrollment/insankabulü ayrı. İlk13aşamanın her biri için kanıt veya eksik;otomatik topluPASS/G0kapanışı yok. Koddan bağımsız doğrulanmış olana gerçektestetiketi ver. Kapanışta AI-BRAIN checkpoint uygula;yerelyazma/transfer ayrımını koru. Antigravity aracı Codex'in bağımsız kontrolünü kendisi yapmış gibi kaynakajanetiketi kullanmasın.


## 2026-11-10 — Matris hazır; ilk teslimde doldur

P2 içindeki matris oluşturma işi Codex tarafından yapıldı: [UYGULAMA_DURUM_MATRISI.md](UYGULAMA_DURUM_MATRISI.md). İlk teslimin başlangıcında 16 modülün tamamı için envanter ve eksikleri doldur; bunu yalnız P0/P1 sonrasına erteleme. Ardından mevcut faz ve bağımlılıklara göre geliştir, her teslimde güncelle. Codex kontrol alanlarını doldurma. Bu ek önceki teknik bulguların yeniden test edildiği veya runtime kabulü verildiği anlamına gelmez.


## 2026-11-10 — Matris bağımsız kontrolü ve sonraki paket

[Codex kontrolü](CODEX_MATRIS_KONTROL_20261110.md): DUZELTME_GEREKLI; 85 PASS/4 SKIP doğrulandı, F01..F08 açık. [Sonraki görev](ANTIGRAVITY_KONTROL_SONRASI_GOREV_20261110.md) tam 16 modül planını, panel görsel incelemesini ve V1/V2 görünür sürüm teslimlerini birlikte kapsar. NOT_DISPATCHED; ürün kabulü değildir.
