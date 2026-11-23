# Adım 4 — HTTP/Kernel bağlantısı, 2026-11-15

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-15
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_TEST_BOUNDARY; LIVE_DATABASE_HTTP_NOT_VERIFIED
Kanıt: tests/unit/test_task_http.py; evidence/runs/browser-68a914a1/TASK_SCREEN_20261114_browser.json

## Değişiklik

/api/connection yalnız yapılandırılmış objectives.create ve detail-read yeteneklerini bildirir. Bunlar kullanıcı yetkisi veya çalışma kabulü değildir; native context/emission kontrolleri sürer. Salt okunur bağlantıda gönderim kapalıdır; yalnız bağlı kayıt türleri seçilebilir. Bearer veya grant kimlikleri bu yanıta eklenmedi.

Yeni test gerçek loopback HTTP + KernelTaskBackend + command_host.execute/emit zincirini DB-API test bağlantısıyla yürütür: tek constructor çağrısı, kararlı idempotency anahtarı, commit sonrası ayrı bağlantıda yeniden yetki/emission kontrolü ve sonuç makbuzu doğrulandı. DB sınırı test doubles kullanır; canlı PostgreSQL veya kalıcılık kanıtı değildir. Diğer yeni test read-only/create-only yapılandırmasını doğrular.

## Kontroller ve sınırlar

251 test: 231 başarılı, 20 platform testi atlandı. Tarayıcı: masaüstü/dar ekran, salt okunur bağlantı, belirsiz sonuç sonrası tekrar göndermeme, makbuz ve escaped detail PASS; pageerror yok. Pozitif gönderim ve kayıt tarayıcı senaryoları mock transport kullanır. task_http.py Ruff kontrolü başarılı. İlgili hedef pinleri açıkça güncellendi; tarihsel source_sha256 değişmedi.

Onaylı canlı HTTP bağlantı profili bulunmadığı için gerçek DB oturumu/komutu çalıştırılmadı. Yeni grant/session/profile üretilmedi. Adım 4 bütünü tamamlanmadı: onaylı Linux libpq service/profile ile mevcut kernel başlatıcısını çalıştırmak, panelden kalıcı Objective ve ayrı readback kanıtını almak, belirsiz komut reconciliation akışını bağlamak gerekiyor. G0 OPEN; first13 0/13 korunur. Tam 16 modül/PH-00–06 kapsamı değişmedi.
