# Güncel bootstrap penceresi — native kontrol bağlantısı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-13
Kaynak ajan: Codex
Durum: SOURCE_AND_NATIVE_NEGATIVE_VERIFIED; ACTUAL_POSITIVE_NOT_VERIFIED

## Sade durum

Ne çalışıyor: uygulamanın mevcut native başlangıç geçerlilik kontrolünü çağıracağı bağlantı hazır; kayıtsız kurulum ve yanlış kullanıcıyla yapılan çağrılar gerçek PostgreSQL denemesinde duruyor.
Ne eksik: gerçek onaylı kurulumun bu kontrolden başarıyla geçmesi ve görev çalıştırma zincirine bağlanması. Sistem bu çalışmayla gerçek iş yapmaya başlamadı.
Ürüne katkı: başlangıç kaydının yalnız varlığına güvenmek yerine iptal, host reboot ve süre sınırlarını mevcut güvenilir native kontrol üzerinden sorgulayabilme.

## Mimari ve uygulama

MOD-001/MOD-016, P0-1/P0-3 kısmi ilerleme. Dayanak mevcut SQL027 r56_root_bounds: root revoke/compromise, tek insan/custodian, manifest/nonce/enrollment/boot/clock policy, gerçek Linux local SYNC observation, monotonic boottime ve konservatif UTC sınırlarını kontrol eder. Bu çekirdek değiştirilmedi; Python saatine veya sentetik SYNC durumuna fallback eklenmedi.

SQL085 bootstrap_window_readback_v1 mevcut r56_root_bounds fonksiyonunu exact provisioning session_user sınırından çağırır. Installation/generation/enrollment digest/host boot ve ARMED veya CONSUMED kontrolü ekler; dönen generation/boot tekrar karşılaştırılır. Mevcut NOLOGIN company_bootstrap_functions_r56 ownerı kullanılır, search_path pg_catalog, PUBLIC execute kapalıdır. Çağırana dahili fonksiyon, tablo yetkisi, rol üyeliği veya yazma yetkisi açılmaz. Sonuç BOOTSTRAP_WINDOW_ONLY_NOT_RUNTIME ve new_grants=0 taşır. Bu API observer/worker/runtime enrollment validatorının tamamı değildir.

company_os/bootstrap_window.py dedicated idle bağlantıda bounded repeatable-read transaction açar; backend/xid/login ve exact dönen alanları/pinleri doğrular. r56 root kontrolü FOR SHARE kilidi kullandığı için READ ONLY transaction kullanılamaz. DML veya commit yapmaz; her durumda rollback ve close uygular. Sonuç çağrı anındaki bootstrap pencere kanıtıdır; cache edilebilir kalıcı yetki tokenı değildir ve sonraki yazıcının native tekrar kontrolünün yerine geçmez. Mevcut bootstrap arm/consume zaten kendi native kontrolünü yapar; bu görevde onların yerine farklı bir doğrulama konmadı.

Önceki84SQL dosyası değişmedi; assembly85. Guardlar, ROLLBACK ve automatic_execution=false korunur. GUNCEL kaynakları değişmedi. Native kaynak kurulumu yalnız yeni özel geçici kümede hash kontrollü bellekte türetilmiş test kopyalarıyla yapılır; migration/deployment değildir.

## Kanıt ve sınır

- evidence/CODEX_CURRENT_WINDOW_20261113_native.json: PASS;85kaynak native katalog derlendi. Mevcut provisioning rolü altında missing enrollment reddi; yanlış session_user reddi; callerın dahili r56_root_bounds fonksiyonuna erişiminin reddi ve native owner/ACL/search_path kontrolü PASS.
- Önceki root driver sentetik pozitif/negatif, minimal bootstrap witness12negatif ve restart testleri de aynı yeni kümede PASS. Bunlar SQL085 için gerçek pozitif current authorization kanıtı değildir.
- Native SQL085 pozitif current root/time deneyinin önkoşulu gerçek onaylı root/arm/clock kayıtlarıdır; bu önkoşullar sentetik onayla kapatılmadı. Yeni istemcinin pozitif protocol/binding/timeout/cleanup davranışı fake-driver testidir.
- Windows221test201PASS20SKIP;Linuxuid999221PASS0SKIP. workflow preflight24call0finding; yeni standalone API preflight default çağrı listesinin parçası değildir, doğrudan unit/native kaynak testleriyle kapsanır.
- Private PostgreSQL durduruldu ve geçici küme silindi. Mevcut kümelere dokunulmadı. Native kaynak hashleri ve diğer kanıtlar manifestte pinlidir.

## Sıradaki iş

Gerçek onaylı root/arm/clock kurulum girdilerini mevcut writerlarla eşleştirip SQL085 pozitif kontrolünü bağımsız doğrulamak; ardından host/profile/observer enrollment authority portlarını ayrı owning kayıtlara bağlamak. Bootstrap geçerliliği genel runtime yetkisi gibi kullanılmaz. Tam16modül/PH00–06 kapsamı korunur; G0OPEN,first13 0/13; insan/runtime kabulü üretilmedi.
