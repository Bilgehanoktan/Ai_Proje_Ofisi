# Ayrı yerel PostgreSQL temeli kuruldu

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-14
Kaynak ajan: Codex
Durum: VERIFIED_PERSISTENT_LOCAL_DATABASE_FOUNDATION; APPLICATION_SCHEMA_NOT_INSTALLED

## Kullanıcı açısından

Ne çalışıyor: Önceden boş olduğu doğrulanan ayrı hedefte PostgreSQL18ve boş ai_proje_ofisi veritabanı kuruldu,başlatıldı ve ayrı bağlantıyla okundu. Durdur/başlat sonrası aynı database OID korundu. TCP kapalı;yerel peer erişimi/700socket gerçek katalog ve farklı OS kullanıcı denemesiyle doğrulandı.
Ne eksik: Uygulama tabloları,ayrı uygulama bağlantısı,başlangıç enrollment/clock/grant ve kullanıcı oturumu yok. Panel henüz gerçek iş kaydetmiyor;ajan/dosya teslimi çalıştırılmadı.
Katkı: Gerçek kurulum sırasının veritabanı temeli artık yalnız hazırlanmış kod değil,mevcut çalışan ayrı yerel altyapıdır. Tam veritabanı/ürün kurulum adımı tamamlanmadı.

## Yapılan işlem

Önce root salt-okunur metadata kontrolü:/var/lib/ai-proje-ofisi-local yok,resolve aynı,symlinkfalse;mevcut OS hesabıuid999/gid986 ve PostgreSQLbinary var. Sonra kullanıcı tarafından onaylanan yerel kurulum kapsamında yeni hedef hazırlandı. Mevcut testdata taşınmadı,değiştirilmedi veya silinmedi. Yeni dizinler700,marker600vebinarysha pinli.

Non-root uid999 altında initdb --auth-local=peer --auth-host=reject ile boş cluster oluşturuldu. Kaynak limitleri küçük shared_buffers16MB,max_connections8,worker0,WAL64/32MB ve bounded statement/lock/idle timeout olarak ayarlandı. PostgreSQL yalnız /var/lib/ai-proje-ofisi-local/socket altında55490Unix socket açar,TCP dinlemez. CREATE DATABASE yalnız dedicated örnekteki boş ai_proje_ofisi DBsi içindir. SQL assembly,migration,role/session/grant/enrollment yazıcısı çalıştırılmadı.

Yeni tools/local_postgres.py açık prepare/initialize/start/inspect/stop adımlarını sunar;mevcut hedefi overwrite veya reinitialize etmez,her kontrolte exact path/marker/owner/mode/binaryhash doğrular. tools/manage_local_postgres.ps1 yalnız inspect/start/stop için kolay giriş sağlar. Ayrıntı:YEREL_VERITABANI.md.

## Kanıt

- LOCAL_POSTGRES_20261114_start.json: LOCAL_POSTGRES_RUNNING,application_schema_count0,sessionfalse,taskfalse.
- LOCAL_POSTGRES_20261114_restart.json: inspect→stop→start→inspect PASS,database_oid_preservedtrue. Yeni data korunuyor;uygulama iş verisi oluşturulmadı.
- LOCAL_POSTGRES_20261114_readback.json: ayrı son okumada TCPfalse,peerpolicyreadbacktrue,700socket,companyşemaları0. peer/passfile ayarı sonrası da doğrulandı;genel pgpass/sır dosyası okunmaz. İlk bağlantıda /dev/null passfile uyarısı vardı;explicit bulunmayan ve varlığı reddedilen özel NO_PASSWORD_FILE referansına geçildi,sır dosyası yaratılmadı.
- LOCAL_POSTGRES_20261114_peer_denial.json: farklı OS kullanıcısıyla aynı DB loginine peer retPASS.
- LOCAL_POSTGRES_20261114_source_guard.json:85uygulama SQL hashinin tamamı assembly ile eşleşir,automatic_executionfalse;GUNCEL G0OPEN/runtimeNOT_RUN değişmedi.
- Windows248test228PASS20SKIP;Linux248PASS0SKIP. Yeni3overwrite/reinitialize/marker sınırı testiPASS. Son küçük passfile referansı düzeltmesi ayrıca gerçek readback/peer deneyiyle sınandı;genel suite bu küçük değişiklikten sonra tekrar koşulmadı.

## Kabul sınırı ve devir

Bu örnek kalıcı data dizininde bırakıldı;önceki disposable /tmp kümelerinden farklı olarak silinmedi. PostgreSQL şu gözlemde çalışıyor. WSL/Windows yeniden başlatılması veya shutdown sonrası otomatik açılış garantisi yok;boot servisi oluşturulmadı. Durum sorgusu ve start/stop rehberde. Yedek/restore/RTO/RPO henüz doğrulanmadı.

Uygulama SQL kaynakları DESIGN_ONLY/ROLLBACK sınırlarını korur. Sadece PostgreSQLin çalışması G0 kapanması,enrollment,Kernel veya runtime kabulü değildir. DBadmin uygulama loginine dönüştürülmez. Gerçekilk13hala0/13,tam16MOD/PH00–PH06 kapsamı korunur.

İlerleme tablosu actual boş yerel DB altyapısına göre güncellendi. Kaba tahmin veritabanı45→50,operasyon25→35;eşit alan ağırlıklı yuvarlanmış genel tahmin~%30. Bu ölçülmüş efor/tamamlanma değildir. Sıradaki somut işler:uygulama şeması ve least-privilege connection,başlangıç authority/oturum,ilk kalıcı Objective,sonra agent/verifier/dosya teslimi.
