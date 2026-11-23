# Antigravity — kontrol sonrası tam kapsam geliştirme ve görünür sürüm

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Uygulama kökü: E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi
Tarih: 2026-11-10
Durum: HANDOFF_READY / NOT_DISPATCHED

Kök ve uygulama AGENTS.md, mevcut mimari ve son ekler, PLAN.md, UYGULAMA_DURUM_MATRISI.md, CODEX_MATRIS_KONTROL_20261110.md ve aynı adlı evidence JSONunu oku. Önceki ANTIGRAVITY_SIRADAKI_GOREV_20261110.md teknik ayrıntıları korunur; kontrol bulguları güncel ek girdidir.

## Ana hedef ve çalışma biçimi

Mevcut mimarinin 16 modülünün TAMAMI geliştirilecek. PH-00..06 ve modül bağımlılıkları uygulama sırasıdır. İlk gerçek SOFTWARE akışı ve ilk görünür kullanılabilir sürüm ara kilometre taşlarıdır. Sonraki modülleri kapsamdan çıkarma; her modülü ayrı servis veya klasöre dönüştürmek zorunda değilsin.

Bu görev yalnız tablo düzeltme veya verifier onarımıyla bitmez. Envanteri kısa bir düzeltme adımıyla doğrula, ardından mevcut yetkiyle uygulanabilir görev paketlerini kodla ve kanıtla. Gerçek somut engelde aynı izin sorusunu yinelemek yerine eksik önkoşulu göster ve bağımsız kaynak işlerini sürdür. Tek dosyada tek yazıcı, allowlist ve başlangıç hashleri uygula; Codex alanlarını değiştirme. İnsan kabulü veya runtime yetkisi uydurma.

## A — Matris düzeltmesi ve bütün proje kuyruğu

1. Codex F01..F08 bulgularını owning source üzerinden ele al. Gerçek dosya/sembol/hash yaz; bulunmayan fixture ve sembolleri düzelt. Antigravity eski iddialarını yeni tarihli düzeltme kaydıyla bağla; Codex kontrolünü silme.
2. Her modülde ilgili ACnin uygulanan, eksik, bağlanmayan ve test edilmeyen davranışlarını açıkça ayır. SOURCE_STATIC/UNIT/FAKE_DRIVER/SYNTHETIC_NATIVE/ACTUAL_RUNTIME/HUMAN_ACCEPTANCE ayrımı yap. Toplu test PASSini bütün AC setine dağıtma.
3. Kartlardaki bütün görev IDlerini gerçek §28 TaskSpec kayıtlarına bağla: REQ/BR/AC/TEST, canonical allowlist+base hash, bağımlılık, beklenen/negatif sonuç, rollback ve çıkış ölçütü. PH-05/06 ve 16 modülün kalan işleri kuyrukta görünür kalsın.
4. Kanıtta exact komut/exit, redakte stdout/stderr, ortam, source/config/test/fixture manifesti ve tam SHA256 ver. Secret veya .env içeriği kaydetme. A tabanı DOGRULA hatasını neden analizi olmadan manifest yenileyerek gizleme.

## B — Mevcut panelleri görsel olarak denetle

1. Mevcut yeni uygulama presentation kaynaklarını ve daha önceki panel girişlerini kontrollü olarak envanterle. Eski compatibility/ARSIV yalnız referanstır; runtime bağımlılığı yapma.
2. Güvenli yerel görüntüleme yolu varsa mevcut ekranları gerçekten açıp masaüstü ve dar görünümde kontrol et: okunabilirlik, taşma, gezinme, düğme durumu, hata/boş/yükleniyor ekranları, durumların anlaşılır Türkçe sunumu, klavye kullanımı ve temel erişilebilirlik. Görsel ekran görüntülerini kaynak/ortamla bağla.
3. Sunucu yoksa bunu bulgu olarak yaz. Mevcut render fonksiyonunun önizlemesi yapılabiliyorsa sentetik veriyi ekranda açıkça DEMO/FAKE_DRIVER diye etiketle; gerçek DB/worker başarısı gibi sunma. Salt render önizlemesiyle authenticated runtime UI kabulünü ayır.
4. Yalnız statik kaynak okuyup “görsel denetlendi”, fake connection çağırıp “tarayıcı reload/ASGI/WSGI test edildi” deme. Açamadığın ekranın somut giriş/bağımlılık engelini belirt.

## C — İlk görünür sürüm ve ilk gerçek çalışan ürün

İki ara teslimi ayrı takip et:

- **V1 görünür geliştirme paneli:** Mevcut arayüzde gerçek veri bağlıysa onu göster; aksi halde kaynak envanterinden üretilen 16 modül/faz/engel durumlarını tarih ve kanıt sınıfıyla açıkça göster. İşlem düğmeleri gerçek komut yoluna bağlı değilse anlaşılır biçimde devre dışı ve nedenli olsun. Sahte çalışan durum veya uydurma yüzde üretme. Mevcut MOD-011 kapsamında kal; yeni ürün tasarlama.
- **V2 ilk gerçek çalışan ürün:** Yetkili hedef girişi → Objective/Plan/Task kalıcı commit/readback → Qualification/claim/lease/fence → rootless worker/engine/Broker → CAS/immutable Artifact → ayrı güven sınırında verifier → Kernel accept/reject → authenticated ekran → yeniden giriş ve DB restart sonrası kalıcı reload. Her adım actual kanıt ister; first13 otomatik yükselmez.

V1 için bütün projenin bitmesini bekleme. V2ye giden güvenlik ve veri bütünlüğü işlerini sırayla uygula:

1. F03 false-pass için gerçek candidate saldırısını negatif regresyona ekle. Güvenilir test kontrolü ve rapor stateini aday süreçten ayır; input/output şemasını sınırla, okuma sırasında byte cap ve deadline, process-tree/cgroup cleanup uygula. Adayın doğru 13 ID/PASS basması veya oracle global stateini değiştirmesi başarı üretemesin. Baseline FAIL/doğru aday PASS/mutant FAIL ve erken exit/taşma/timeout/bozuk cevap negatiflerini doğrula. Gizli fixture ve signer aday erişiminde olmasın; yalnız kanal veya returncode kontrolüyle yetinme.
2. E2E betiğini gerçek owning APIlere bağla. Statik import eksikleri kanıt JSONunda listeli; bunları dinamik import ve constructor preflight ile DB başlatmadan doğrula. İnceleme statik AST karşılaştırmasıdır; kendi başına constructor/runtime testi değildir. Shim veya sahte yetki ekleme.
3. Mevcut consent ve izin kapsamını kullan; clock policy/enrollment/epoch/sample/current bounds, gerçek identity/custody ve canonical DB yazımı için eksik somut önkoşulları ayır. Aynı kurulum rızasını tekrar isteme. Mevcut bounded DB yaşam döngüsü, exact cleanup ve no-network/resource sınırları korunur.
4. MOD-012 katalog pinleri, MOD-014 kaynak rezervasyonu/UNKNOWN ve MOD-015 güvenli stop/recovery ilk kullanıldıkları yerde bağlanır. Sonraki tam hafıza/ticari/backup/genişleme teslimleri PH-05/06 planında sürer. Paid fallback, genel shell, doğrudan egress veya PROD açma. HSM/dual-custody/ayrı daemon gibi ek zorunlulukları owning karar olmadan üretme.

## D — Görünür sürüm takvimi ve teslim

İlk inceleme sonunda V1 ve V2 için ayrı somut kalan işler/bağımlılıklar/engeller listesi çıkar. Her işte MOD, faz, dosya, test/kabul ve ortam önkoşulunu göster. Süre tahmini yapılabiliyorsa gerçek gözlem, varsayım, belirsizlik ve aralıkla sun; keşif yapılmadan kesin gün verme. Süre tahmini uygulama veya insan kabulü değildir.

Teslimde: 16 modülün güncel dağılımı; tamamlanan gerçek kod değişiklikleri; F01..F08 disposition; açık kusurlar; test ve negatif ham kanıtlar; görsel ekran bulguları; V1/V2 durumu ve kalan yol; PH-05/06 sonraki görevleri; Memory checkpoint ver. Uygulanabilir kaynak işi varken yalnız “plan hazır” ile bırakma. Engellenen runtime aşamasını tamamlandı gösterme. Codex incelemesine REVIEW_REQUIRED olarak sun.


## İkinci kontrol girdisi — 2026-11-10

[CODEX_MATRIS_KONTROL_20261110_02.md](CODEX_MATRIS_KONTROL_20261110_02.md) ve kanıt JSONunu oku. F01..F08 tamamen giderildi iddiası doğrulanmadı. R2-01..06 tam16MOD görevinin güncel girdisidir: gerçek candidate erişim izolasyonu ve oracle/harness pinleri; READY/response/stderr boyunca hard byte/deadline ve tree cleanup; matris/kanıt/TaskSpec tutarlılığı; kaynağa bağlı doğru V1; P0-2 preflight. Mevcut PH05/06 ve V1/V2 geliştirme görevleri sürer. Yalnız rapor/etiketle kusur kapatma; kod ve negatif kanıt üret. Görsel denetim yapılamadıysa NOT_VERIFIED yaz.
