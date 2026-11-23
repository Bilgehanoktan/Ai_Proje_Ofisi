# Yerel PostgreSQL temelinin kullanımı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-14
Durum: TARİHSEL TEMEL KURULUM RAPORU; GÜNCEL DB ARTIK BOŞ DEĞİL

## Ne kuruldu?

Ubuntu-E içinde /var/lib/ai-proje-ofisi-local altında ayrı PostgreSQL18örneği ve boş ai_proje_ofisi veritabanı oluşturuldu. İşlem mevcut aipof-dbtest OS kimliği(uid999,gid986) altında çalışır;bu teknik kurulum kimliği ürünün insan sahibi veya uygulama yetkili oturumu değildir. Veri dizini ve socket dizini700;Unix socket700. TCP kapalıdır;port55490 yalnız yerel Unix socket adında kullanılır. Yerel kimlik doğrulaması peer'dır;ayrı şifre üretilmedi. Farklı OS kimliğiyle aynı DB rolüne giriş reddi doğrulandı.

PostgreSQL dağıtımı mevcut /var/lib/ai-proje-ofisi-dbtest/binary altından kullanılır;eski test veritabanının dataları kullanılmaz veya değiştirilmez. Binary SHA256 örnek markerında pinlidir. Bu binary dağıtımını kaldırmak/yükseltmek ayrıca kontrollü bakım gerektirir. Yeni data/socket/log dosyaları eski test kurulumundan ayrıdır.

## Windows'tan kontrol

Workspace kökünden:

```powershell
.\scripts\database\manage_local_postgres.ps1 inspect
.\scripts\database\manage_local_postgres.ps1 stop
.\scripts\database\manage_local_postgres.ps1 start
```

Araç yalnız bu projeye ayrılmış örneği kontrol eder. start veriyi sıfırlamaz;stop veriyi silmez. Windows/WSL yeniden başladıktan sonra otomatik açılma servisi kurulmadı;gerekirse start ve inspect kullanılır. Başka servislerin süreci/klasörü hedeflenmez.

## İlk kurulum ve korumalar

Kaynak: scripts/database/local_postgres.py. prepare yalnız root altında yeni,henüz bulunmayan sabit hedefte özel dizin/marker hazırlar;var olan hedefte overwrite yapmaz. initialize yalnız non-root uid999 ile doğrulanmış marker/binary ve tamamen boş data dizininde initdb yapar. start doğrulanmış örneği açar ve yoksa yalnız boş ai_proje_ofisi DB'sini oluşturur. inspect server ayarı ve gerçek pg_hba_file_rules okumasını yapar. stop yalnız doğrulanmış kendi örneğini durdurur. Recursive silme veya cleanup komutu yoktur. Eski hedefte initialize/prepare tekrar kullanılmaz.

Bu kurulumda vendor initdb çalıştırıldı;uygulamanın85guarded SQL dosyası çalıştırılmadı. company/company_private şemaları0. Role/grant/human session/enrollment/key/model/verifier oluşturulmadı. Yerel DB admin rolü,HTTP uygulama rolü olarak kullanılamaz;mevcut Kernel binding superuserı reddeder.

## Sıradaki işler

1. Mimari şartları karşılayan uygulama şeması kurulum paketini ve ayrı en az yetkili uygulama bağlantısını hazırlamak. Guardları veya kabul durumunu sessizce kaldırma.
2. Bağımsız doğrulanmış başlangıç kimlik/yetki/saat kayıtlarını ve insan oturumunu oluşturmak.
3. HTTP binding üzerinden ilk Objective iş isteğini kaydetmek ve ayrı bağlantıyla kalıcı sonucu okumak.
4. Mevcut Plan/Task/worker/Broker/verifier akışını bağlayıp gerçek dosya teslimini göstermek.

İlk SOFTWARE akışı ara teslimdir;tam16MOD/PH00–PH06 kapsamı devam eder. Bu boş veritabanı,çalışan ürün veya ilk13kabulü değildir. Kanıt: [yerel kurulum raporu](../../handover/history/CODEX_YEREL_POSTGRES_20261114.md).


## 2026-11-14 güncel durum düzeltmesi

Yukarıdaki boş DB/şema yok anlatımı ilk kurulum anına aittir. Son salt okunur sorguda 2 uygulama şeması, 1 Objective, 1 Plan ve 1 süresi dolmuş session var; Task yok. Saat epoch/sample ve host kayıtları yok. Bu durum yetkili uygulama kurulumu kabulü değildir. Güncel kanıt ve sonraki sıra: [uzlaştırma](../../handover/STATE_RECONCILIATION_20261114.md). Eski raporlar değiştirilmeden korunur; DB içeriğine müdahale edilmedi.
