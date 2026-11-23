# AI Proje Ofisi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi

Aktif ürün kaynakları [product/](product/README.md), ortak sözleşmeler [contracts/](contracts/README.md), PostgreSQL kaynakları [database/](database/README.md) altındadır. Klasör geçişi 2026-11-14 kullanıcı kararıyla yapıldı; teknoloji ve tam 16 modül/PH-00–PH-06 kapsamı korunur.

- [Proje ilerlemesi](progress/ILERLEME_TABLOSU.md)
- [Bakım ve değişiklik rehberi](BAKIM_VE_DEGISIKLIK_REHBERI.md)
- [Çalıştırma ve test komutları](docs/developer-guides/CALISTIRMA.md)
- [Mimari giriş](docs/architecture/README.md)
- [Dosya bazlı geçiş eşlemesi](docs/migration/SOURCE_TO_TARGET.json)
- [Geçiş planı ve sınırları](docs/migration/MIGRATION_PLAN.md)
- [Güncel devir](handover/CURRENT.md)

Kökten `C:\Python314\python.exe -B scripts/development/run.py tasks --port 8766` ile görev ekranı açılır. Varsayılan gerçek backend bağlı değildir; gönderim kapalıdır.

Kaynak testleri: `C:\Python314\python.exe -B scripts/development/run.py verify`. Kaynak bütünlüğü: `C:\Python314\python.exe -B scripts/verification/verify_layout.py`.

GUNCEL mevcut A kaynak tabanı ve mimari referansıdır. ARSIV tarihsel kaynaktır. Eski kök ZIP/JSON doğrulama dosyaları tarihsel paket kanıtıdır; yeni ürünün güncel PASS sonucu sayılmaz. GUNCEL/DOGRULA.py ayrı referans kontrolüdür ve önceki hash uyuşmazlığı açıktır.

G0 OPEN; ilk gerçek akış kabulü 0/13. Çalışan ekran veya kaynak testleri gerçek ajan/dosya teslimi ve insan kabulü değildir.
