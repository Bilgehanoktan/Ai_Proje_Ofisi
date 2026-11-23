# Klasör geçişi — 2026-11-14

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi

Kullanıcı 2026-11-14 tarihinde önerilen product/contracts/database/workers/verifier düzenini uygulama yetkisi verdi. Bu değişiklik teknoloji veya ürün kapsamı değişikliği değildir. Tam 16 modül/PH-00–PH-06 korunur; G0 OPEN, first13 0/13.

| Bölüm | Yapılan işlem | Kontrol |
|---|---|---|
| 1 — Envanter | 440 dosya için source→target ve başlangıç SHA256; 85 cache/yer tutucu ayrı | before.zip yeniden açılıp her kayıt doğrulandı |
| 2 — Destek kaynakları | Kanıt, takip, yapılandırma ve tarihsel raporlar ayrıldı | Taşıma sırasında kaynak/hedef SHA256 eşleşmesi |
| 3 — Ürün kaynakları | Python, sözleşme, native, SQL, test ve araç kaynakları taşındı | Importlar güncellendi; eski ağaca runtime loader yok |
| 4 — Bağlantılar | HTTP statik dosyaları, ilerleme, SQL assembly ve Windows/WSL başlatıcıları düzeltildi | Windows ve Linux kaynak regresyonları; HTTP ekran kontrolleri |
| 5 — Kapanış | Bakım rehberi, ilerleme, kaynak manifesti, devir ve karar kaydı güncellendi | verify_layout.py ve readback |

İlk uygulama440dosyasına kök check_adjtimex.py tanı aracı da eklenerek toplam441kaynak eşlendi. Ayrıntılı son sonuçlar [VALIDATION.md](VALIDATION.md) içindedir.

Dosya bazlı tam eşleme: [SOURCE_TO_TARGET.json](SOURCE_TO_TARGET.json). Python sembol yolları: [MODULE_MOVES.json](MODULE_MOVES.json).

## Korunan kaynaklar

- GUNCEL mimari/A tabanı referansıdır; bu geçişte topluca taşınmadı. Mimari giriş docs/architecture/README.md üzerinden erişilir.
- ARSIV tarihsel kaynaktır. Mevcut arşiv yeniden yazılmadı. Eski uygulamanın yalnız cache ve yer tutucuları ayrı bir alt dizinde korunur.
- Ham evidence ve geçmiş devir raporları byte-exact taşındı. İçlerindeki eski yol/hash/test sayıları tarihsel iddialardır; güncel durum diye kullanılmaz.
- config/owner-installation-consent.json tarihsel yetki kaydıdır; uygulama kökü alanı sessizce değiştirilmedi ve yeniden yetki üretmedi.
- database/sources altındaki 85 SQL dosyasının byte/hash/sırası ve automatic_execution=false korundu. Gerçek DB şeması uygulanmadı.
- Gizli oracle veya gerçek anahtar eklenmedi. verifier/public-fixtures yalnız mevcut kaynak testi örnekleridir.

## Dar ek düzeltmeler

- Aynı r65_spawn_linux.c kaynağının LF/CRLF kopyaları farklı hash taşıyordu. Native kopya kanonik kaldı; eski company_os varyantı source-variants altında byte-exact korundu. Aynı hashli clock C kopyası tek hedefte birleştirildi; iki kaynak da rollback ZIP içinde bulunur.
- Pydantic manifesti 2.14.0 bildirirken çalıştırılan ortam 2.12.5 idi. Kaynak testleriyle doğrulanan 2.12.5 kaydedildi; DB opsiyonel bağımlılığı mevcut psycopg 3.3.4 olarak tanımlandı. Yeni paket kurulmadı.
- Backend bağlı değilken HTTP gövdesini okumadan bağlantı kapatma Windows'ta 503 yerine WinError 10053 üretebildi. Aynı hata yanıtından önce yalnız tek Content-Length ve sınırlı gövde süre sınırı içinde tüketilir. Yetki veya backend oluşturulmaz.

## Kabul sınırı

Bu geçiş dosya düzeni ve kaynak regresyonu doğrulamasıdır. Linux testlerinin geçmesi gerçek enrolled ajan/verifier, model inference, görev teslimi veya insan kabulü değildir. GUNCEL/DOGRULA.py eski CALISMA_DURUMU.md hash uyuşmazlığı ayrı açık bulgudur; yeni manifest bu eski sonucu PASS'e çevirmez.
