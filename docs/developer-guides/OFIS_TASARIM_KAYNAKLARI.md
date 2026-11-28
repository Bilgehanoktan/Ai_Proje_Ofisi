# Ofis görünümü — kaynak eşleme ve uygulama sınırı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-11
Kaynak ajan: Codex
Durum: SOURCE_ALIGNED_PREVIEW; VISUAL_ACCEPTANCE_NOT_VERIFIED

## Kaynak ve uyarlama

- `GUNCEL/dokumanlar/hedef-mimari-v1/kaynaklar/B_v135.md` §v134-02: büyük merkez ofis, sol navigasyon, üst bağlam ve sağ operasyon paneli.
- Aynı kaynak §v134-03: Research / Orchestrator / Engineer üst sıra; pasif rezerv / briefing-giriş / QA alt sıra. Research ve Engineer yarı açık, QA ayrışmış yarı kapalı. Dört örnek figür; rezervde ajan yok, kat portali pasif.
- §v134-04: özgün pixel-art, hedef Phaser 2.5D, sunucu kaynaklı durum; görsel seçim yetki değildir.
- §v134-05: Aktivite / Ajanlar / Onaylar / Seçili Bağlam. Agent Detail yedi sekmesi ayrı sözleşmedir; bu prototipte uygulanmadı.
- `GUNCEL/dokumanlar/hedef-mimari-v1/ENTEGRASYON_KARAR_MATRISI.md` DEC-014..017, DEC-297..301: B tarihsel görsel kararları A runtime/kabulü sayılmaz; geometri dondurulmaz.
- `PROJE_TASARIM_DOKUMANI.md` BR-014: DEMO/UNVERIFIED görünür, kanıtsız WORKING/VERIFIED yok.

## Bu sürüm

`dashboard.html` kabuk, `office-preview.js` özgün prosedürel Canvas çizimi ve seçim kontrolleri, `preview_generator.py` yerel matrisi ve scripti tek HTML önizlemeye yerleştirir. Eski runtime ağacına import, asset veya paket bağımlılığı eklenmedi. Önceki serbest oda yerleşimi esas alınmaz.

Duvar yüksekliği, önden görülen mobilya, pixel figür ve katman sırası görsel derinlik sağlar. Bu, Phaser entegrasyonu veya tam Office Engine değildir. Çalışma animasyonu yok; canlı snapshot/SSE/lease/proof bağlı değil. Rol seçimi örnek bağlamı değiştirir; sahte agent_instance_id/run_id üretilmez.

UI kontrolleri: dört sekme, ok tuşları/Home/End ile sekme seçimi, örnek rol seçimi ve eşdeğer rol listesi, %75–150 yakınlaştırma, CSS büyütme ve Escape ile geri dönme. Mobilde sahne kendi bölgesinde yatay kaydırılır.

Özgün çizimler kodla oluşturulur; üçüncü taraf sprite/texture/font indirilmedi. Ticari release için gereken asset bundle/provenance ve layout registry bu önizlemeyle tamamlanmış sayılmaz.

## Doğrulama

- Mevcut `test_presentation.py`: 3 test OK.
- `node --check presentation/office-preview.js`: exit 0.
- Tarayıcı aracı file URL erişimini engelledi; localhost bağlantısı zaman aşımına uğradı.
- Yerel Playwright kontrolü sonuçlanmadı; görsel, mobil ve etkileşim kabulü doğrulanmadı. `check_office_preview.py` tekrar çalıştırılabilir kontrol betiğidir.
- Eski `preview_desktop.png` ve `preview_mobile.png` bu görünümün kanıtı değildir.

G0 OPEN; First13 0/13; insan kabulü üretilmedi.


## 2026-11-14 konum güncellemesi

Ofis kabuğu product/frontend/office/scenes/dashboard.html; script product/frontend/office/engine/office-preview.js; üretici product/backend/company_os/projections/preview_generator.py. Eski dosya adları yukarıda tarihsel tasarım kanıtıdır. Geçiş yeni görsel tasarım veya canlı ajan kabulü değildir.

## 2026-11-28 DEC-28C / DEC-017 / MOD-011 mimari hizalama güncellemesi

- Canlı modüler giriş (`product/frontend/office/modules/main.js`, `office-canvas.js`, `phaser-scene.js`, `panels.js`) ve salt-okunur `GET /api/office-architecture` (`product/backend/company_os/projections/office_layout.py`) ile `F1-DEC28C` taslak kat planı (`F1-RSCH`, `F1-ORCH`, `F1-ENG`, `F1-COR`, kapalı `F1-EXP`, `F1-BRIEF`, `F1-QA`, kapı eşikleri ve kapalı üst kat portali), yerel Phaser 3.90.0 karakter seçim konturu, renk+simge durum rozetleri (`●/◆/△/○`), `Hareket Azalt` (`reduced-motion`), sahne durum filtresi, `Seçiliye Odaklan`, sol menü kanonik KPI özeti, `087` Rol/Beceri/Model kataloğu ve `DEC-017` 7 sekmeli salt-okunur `Agent Detail` görünümü eklendi. Görsel şema veya beceri pini yetki (`grant`) üretmez; geometri dondurulmuş (frozen) sayılmaz.
