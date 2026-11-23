# İlk görünür görev ekranı — 2026-11-14

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-14
Kaynak ajan: Codex
Durum: VERIFIED_LOCAL_UI_AND_SOURCE_ADAPTER; REAL_TASK_EXECUTION_BLOCKED

## Kullanıcı açısından

Ne çalışıyor: Yerel görev ekranı açılıyor. İş isteği formu, dört aşamalı istek/ajan/kontrol/teslim görünümü, kayıt sorgulama alanı ve mevcut sanal ofis önizlemesine geçiş var. Mobil ve masaüstü tarayıcıda doğrulandı. Gerçek altyapı bağlı değilken durum açıkça söyleniyor ve gönderim kapalı.
Ne eksik: Onaylı gerçek DB/oturum ve worker/verifier zinciri. Bu görevde gerçek bir yazılım işi verilmedi, ajan çalışmadı, dosya teslim edilmedi. Ekranın hazır olması çalışan ürün kabulü sayılmaz.
Katkı: Kullanıcıya yalnız rapor yerine açılabilir görev giriş yüzeyi ve mevcut Kernel rotalarına kaynak düzeyinde bağlı bir HTTP adapteri sunuldu.

## Mimari uyumu ve kod

MOD-002/MOD-010/MOD-011/MOD-016 kısmi ilerleme, PH-04 görünürlük ile ilk SOFTWARE ara akışına hazırlık. Tam16modül/PH00–06 hedefi korunur. presentation/task_http.py yeni local loopback HTTP sunucusudur; mevcut app.py salt-okunur WSGI önizlemesi korunur. Ofis geometrisi/pixel-art kaynak tasarımı değiştirilmedi; /office aynı generatorı çalıştırır, inline script/style için exact CSP hashleri kullanılır.

KernelTaskBackend/create_project_backend yalnız supervisorun sağladığı connection ve existing project/grant refs üzerinden çalışır. Browser kendi proje/grant/SQL rotasını seçemez. İş isteği ObjectiveCreate sözleşmesiyle objectives.create native constructorına bağlanır; bu Objective'den kendiliğinden Plan/Task/claim veya worker üretmez. Ayrı detail sorgusu mevcut candidate.r54 native read rotalarına TASK scope ile gider.

Sonuçlar command_host.emit üzerinden ayrı dedicated bağlantı, tekrar context enter ve parça başına emission snapshot kontrolüyle bounded sockete gönderilir. JSON sonucun WSGI veya bellekteki sahte göreve doğrudan bırakılması yoktur. Commit ACK kaybı409; native deny403; yapılandırılmamış backend503. Emisyon başladıktan sonra hata olursa bağlantı kapanır; ikinci sonuç veya otomatik resend yoktur. Sahip kaynak execute/emit değişmedi.

İstemci yalnız request IDyi sessionStorageda saklar; goal ve token saklanmaz. Belirsiz sonuç sayfa yenilemeyle yeni idempotency key üretip tekrar gönderilmez. Böyle bir pending isteğin gerçek reconciliation ekranı henüz bağlı değildir; engel gizlenmez. Kayıt sorgusu sonucu sade durum metniyle gösterilir; ham kayıt yalnız isteğe bağlı ayrıntıdadır. Gelen metin textContent ile yazılır.

## Doğrulama

- Windows231test211PASS20SKIP;Linuxuid999231PASS0SKIP. Ham loglar evidence/TASK_SCREEN_20261114_windows.log ve linux.log.
- Native DB veya gerçek model/ajan bu çalışmada başlatılmadı.
- evidence/TASK_SCREEN_20261114_browser.json: Chromium PASS. Canlı unconfigured ekran,1440px masaüstü/390px mobil overflow ve görsel kontrol; ofis tab/rol seçimi ve iki yönlü gezinme PASS.
- Mock transport: unknown commit→reload→no resubmit; receipt≠agent execution; sade kayıt metni ve HTML enjeksiyonu çalıştırmama PASS. Bu senaryolar test doublesıdır, gerçek görev kabulü değildir. Browser page error0.
- Desktop/mobile PNGler canlı unconfigured ekrandır; fake başarılı görev ekran görüntüsü üretilmedi.
- HTTP testleri loopback üzerinde gerçek request/response, Host/Origin ret,503default,409unknown ve partial emission no retry davranışını sınar; Kernel positive tests fake-driver/mocktür. Loopback sandbox WinError10013 verdi; izinli yürütmede aynı testler geçti, ürün kuralı gevşetilmedi.
- İlk browser denemesinde gizli tab selectorı, ikinci denemede CSP unsafe-eval kullanan test beklemesi düzeltildi; CSP gevşetilmedi. Son browser koşumu PASS.

## Çalıştırma ve açık bağımlılıklar

Sunucu bu oturumda http://127.0.0.1:8766 adresinde başlatıldı. Oturum kapanması veya süreç sonlandırılması sonrası kalıcılık garanti edilmez; yeniden başlatma komutu presentation/TASK_SCREEN.md içindedir. Varsayılan backend=None; dummy DB/oturum/model üretilmez.

config/profiles altında yalnız .gitkeep var; config/README tam runtime loader/enrollment/qualified launcher önkoşullarının açık olduğunu söylüyor. Bu kaynak incelemesi tüm makinede approved runtime olmadığını kanıtlamaz; bu çalışma alanında kullanılabilir yapılandırılmış profil doğrulanmadı. owner-installation-consent.json kullanıcı kurulum iznini kaydeder; independent enrollment/custody/clock authority yerine geçirilmedi.

Sıradaki somut iş gerçek onaylı DB/session bağlantısını factoryye sağlamak ve bir Objective kaydını native kalıcı readback ile doğrulamak; sonra mevcut CEO/Plan/Task/worker/Broker/verifier akışını bağlamak. İlk uçtan uca teslim tamamlanmadı. G0OPEN,first13 0/13; hiçbir modülün tam entegrasyon/insan kabulü bu ekranla kapatılmadı.
