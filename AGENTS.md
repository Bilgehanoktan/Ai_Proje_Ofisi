# Güncel kaynak düzeni — 2026-11-14

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi


- 2026-11-14 kullanıcı kararı: aktif ürün product/ altındadır; önce product/AGENTS.md uygula. Eski AiProjeOfisi kökü emekliye ayrıldı. GUNCEL mevcut A tabanı/mimari referansıdır; ARSIV tarihsel kaynaktır.
- Python: product/backend/company_os; ortak sözleşmeler: contracts/source/python/packages/contracts; bağımsız doğrulayıcı: verifier/src/independent_verifier; SQL: database/sources ve database/assembly/assembly.json.
- Varsayılan kaynak testi: C:\Python314\python.exe -B scripts/development/run.py verify. Klasör/hash/import kontrolü: C:\Python314\python.exe -B scripts/verification/verify_layout.py. GUNCEL/DOGRULA.py ayrı eski A referans kontrolüdür; bilinen hash hatasını otomatik manifest yenileyerek kapatma.
- İlerleme tek kaynağı progress/ILERLEME_TABLOSU.json; Markdown görünümü scripts/development/run.py progress ile yenilenir. Bakım girişi kök BAKIM_VE_DEGISIKLIK_REHBERI.md.
- Geliştirme veya test yaparken docs/migration/SOURCE_TO_TARGET.json hedef SHA256 ve SOURCE_MANIFEST.json pinlerini anlamlı değişiklikten sonra açıkça gözden geçir; doğrulama aracı pinleri sessizce değiştiremez.

- ARSIV/ tarihsel kanıttır; aktif kaynak veya güncel PASS sayma.
- GUNCEL/compatibility/ yalnız kapalı regresyon/tasarım fixture ağacıdır. Eski yayın betiklerini çalıştırma.
- G0 OPEN; runtime NOT_RUN; ilk TEST 0/13. İnsan onayı veya native kabul üretme.
- Eski klasörleri ya da arşivi tekrar güncel kod bağımlılığına dönüştürme.
- Projenin görünen adı AI Proje Ofisi'dir. Ana belge ve TXT adında sürüm zorunludur: AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v{architecture_version}-r{revision}.md/.txt. STATE.json sürümü değişince tools/refresh_source.py --docs bu adı ve paket içi bağlantıları günceller; kök giriş bağlantılarını da güncel tut.
- Ana belge kısa mimari girişidir: güncel tasarım, kararlar, kabul sınırları ve kaynak bağlantıları içerir. Geçmiş tam belgeleri ve kaynak kodlarını belgeye gömme. Tam geçmiş ARSIV içinde kayıpsız korunur. Metin şablonu GUNCEL/dokumanlar/ANA_MIMARI_KAYNAK.md, bağlantılı kaynak listesi KAYNAK_REHBERI.md dosyasıdır.


## Ortak temiz kod kuralı — 2026-11-14

Kullanıcı talimatı: Codex ve Antigravity her yeni/değiştirilen kodda [ortak kod kalitesi kurallarını](docs/developer-guides/KOD_KALITESI_KURALLARI.md) uygular. Açık ve okunabilir kod, güvenli hata/kaynak yönetimi, doğrulanan bağımlılıklar, mimari sınırlar ve uygun test/kanıt zorunludur. Kuralların yazılması formatter/lint/tip kontrolü veya CI kurulduğu anlamına gelmez; eksik otomatik kontrolleri açık bildir. Mevcut açık ajan oturumlarının bu dosyayı kendiliğinden yeniden yüklediğini varsayma.
