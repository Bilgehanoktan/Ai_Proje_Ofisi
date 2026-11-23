# Klasör geçişi doğrulaması — 2026-11-14

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi

| Kontrol | Sonuç ve sınır |
|---|---|
| Başlangıç kaynak koşumu | Windows 248 test, 228 başarılı, 20 Linux SKIP |
| İlk uygulama envanteri | 440 dosya için başlangıç SHA256 ve hedef eşlemesi; 85 cache/yer tutucu ayrı |
| Kök tanı aracı | check_adjtimex.py ek eşlemeyle scripts/database içine alındı; toplam 441 kaynak eşlemesi |
| Son Windows kaynak koşumu | 249 test, 229 başarılı, 20 Linux SKIP |
| Son Linux kaynak koşumu | Mevcut Ubuntu-E, non-root aipof-dbtest ortamında 249 testin tamamı başarılı |
| Yeni HTTP regresyonu | Taşınan JS/CSS dosyaları doğru MIME ile sunulur; backend kaynak yolu HTTP ile sunulmaz |
| Tarayıcı | Yeni geçici sunucuda desktop/mobile, ofis gezinmesi ve scriptler PASS; sayfa hatası yok |
| Mock tarayıcı akışları | Belirsiz commit sonrası tekrar göndermeme, kayıt gösterimi ve metin kaçış kontrolü PASS; gerçek iş kaydı değildir |
| SQL | 85 kaynak hash/sıra/ROLLBACK/DESIGN_ONLY koruması kaynak testinde doğrulandı; DB'ye uygulanmadı |
| Ortak modeller | Pydantic 2.12.5 Windows ortamıyla kaynak testleri; yeni paket kurulmadı |
| Tarihsel kanıtlar | Eşlemedeki ham evidence/devir kayıtları başlangıç hashleriyle korunur |

Ham son koşumlar:

- [Windows](../../evidence/runs/layout-migration-20261114/windows-tests-final.txt)
- [Linux](../../evidence/runs/layout-migration-20261114/linux-tests.txt)
- [Tarayıcı raporu](../../evidence/runs/browser-b13066e1/TASK_SCREEN_20261114_browser.json)
- [Mobil görünüm](../../evidence/runs/browser-b13066e1/TASK_SCREEN_20261114_mobile.png)
- [Klasör/hash/import kontrolü](../../evidence/runs/layout-migration-20261114/layout-validation.json)

İlk kısıtlı test koşumlarında WinError 10013; ayrı izin alanındaki sunucuya tarayıcı erişiminde timeout gözlendi. Son tarayıcı koşumu sunucu ve tarayıcıyı aynı geçici izinli test yürütmesinde kurup sonunda kapattı. Bunlar ayrı ortam sonuçlarıdır; başarısız ilk denemeler gizlenmedi.

Windows'ta okunmamış HTTP gövdesiyle bağlantı kapanması 503 yerine WinError 10053 üretebildi; sınırlı ve belirsiz olmayan gövde tüketimiyle düzeltildi. Yetki denetimi veya kapalı backend durumu atlanmadı.

Eski AiProjeOfisi dizininin tamamını yeniden adlandırma başka süreç kullanımından reddedildi. İçindeki 85 cache/yer tutucu dosyası tek tek, kapsamı kontrol edilerek ARSIV/layout-migration-20261114/generated-old-tree içine taşındı; eski dizinde kaynak dosyası kalmadı. Boş dizinler kilitli olabilir; başka ajan veya kullanıcı süreci durdurulmadı.

G0 OPEN; first13 0/13. Gerçek DB şeması, gerçek kimlik/oturum, model inference, bağımsız enrolled verifier ve gerçek dosya teslimi kabulü verilmedi. Eski GUNCEL doğrulayıcısındaki CALISMA_DURUMU.md hash sorunu ayrı açık bulgudur.
