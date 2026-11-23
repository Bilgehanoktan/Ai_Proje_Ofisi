# Antigravity uygulama görevi — Codex bağımsız kontrolü

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Uygulama kökü: E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi
Tarih: 2026-11-08
Durum: HANDOFF_READY / NOT_DISPATCHED

AI Proje Ofisi'nin mevcut mimarisine göre ilk güvenli gerçek yazılım akışını tamamla. Yeni büyük tasarım döngüsü, departman veya görsel genişleme açma. Kapsam: İş kaydı → yetkili Attempt/Qualification/lease → izole worker → Broker → immutable Artifact → bağımsız verifier → Kernel kabul/ret → minimum arayüz ve kalıcı reload. Kullanıcı şirket sahibinin kendisi olduğunu ve yerel kuruluma izin verdiğini açıkça belirtti; config/owner-installation-consent.json mevcut. Aynı izni tekrar isteme. Bu onay G0 kapanışı, sahte kimlik kanıtı, paid/PROD veya dış iletişim yetkisi değildir.

## Önce oku

### Mimari belgelerin tam yolları ve önceliği

- Kısa ana mimari giriş ve mevcut A kararları: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v0.16.2-r68.md`
- Ayrıntılı hedef tasarımın ana referansı: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\hedef-mimari-v1\PROJE_TASARIM_DOKUMANI.md`. §1/5/26/36 ve sondaki 8 Kasım eklerini birlikte oku; baştaki eski özetlerle yetinme. REVIEW_REQUIRED durumu korunur; bütün öneriler kesinleşmiş karar veya runtime izni değildir.
- Uygulama fazları: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\hedef-mimari-v1\UYGULAMA_YOL_HARITASI.md`
- Seçici A/B kararları: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\hedef-mimari-v1\ENTEGRASYON_KARAR_MATRISI.md`
- Gereksinim–modül–kural–kabul–test izleri: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\hedef-mimari-v1\GEREKSINIM_IZLENEBILIRLIK.md`
- Açık karar ve kanıt borçları: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\hedef-mimari-v1\MIMARI_ACIK_KONULAR.md`
- Kaynak dosya rehberi: `E:\Projeler\Ai_Proje_Ofisi\GUNCEL\dokumanlar\KAYNAK_REHBERI.md`
- Yeni uygulamanın güncel sırası: `E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi\PLAN.md`
- Yeni uygulamanın 16 modül eşlemesi: `E:\Projeler\Ai_Proje_Ofisi\AiProjeOfisi\module-map.json`

Öncelik: güncel kullanıcı kararları ve AGENTS.md → mevcut A'nın bağlayıcı kararları → ilgili güncel owning-source/sözleşme ve gerçek kanıt → hedef tasarımın ilgili aday kararları. Çelişkide sessizce seçim yapma; kapsamı ve dayanağı belirt. `GUNCEL\STATE.json` mevcut A sürümünü tanımlar; yeni uygulamanın tamamlanma durumunu tanımlamaz. Ana mimari ve ayrıntılı tasarım GUNCEL altında, yeni uygulama geliştirmesi AiProjeOfisi altında kalır. ARSIV ve compatibility güncel mimari otoritesi veya runtime bağımlılığı değildir.

1. Kök AGENTS.md ve AiProjeOfisi/AGENTS.md.
2. GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md; özellikle §12,15,16,22,26,27,29,30,35,36 ve 8 Kasım ekleri.
3. AiProjeOfisi/PLAN.md ve evidence/SESSION_INTEGRATION_20261108.json, BOOTSTRAP_INTEGRATION_20261108.json.
4. GUNCEL/dokumanlar/hedef-mimari-v1/inceleme/SONRAKI_ADIMLAR_v1/07_DB_DILIMI.md, 08_WORKER.md, 09_VERIFIER.md, 10_UI.md.

Aktif yeni geliştirme AiProjeOfisi/ altında. GUNCEL referans tabanıdır. compatibility/ ve ARSIV runtime bağımlılığı olamaz. Çalışmaya başlamadan dosya/hash ve mevcut çalışan servisleri kontrol et; diğer ajanın eşzamanlı değişikliğini ezme.

## Mevcut durum — yeniden doğrula

83 SQL kaynağı yeni kökte; registry 48 tanımla native derlenmiş. Clock trigger PUBLIC EXECUTE kaldırılması gerçek katalogda gözlendi. Kaynak dosyaları inert DESIGN_ONLY guard ve ROLLBACK sınırlarını korur. Ayrı disposable deney kopyaları açık farklarla kullanıldı; bunları production loader sayma.

Sentetik root/test transport koşulunda gerçek bootstrap arm→consume→COMMIT ve ayrı bağlantıdan receipt/Objective/Plan/audit/outbox/grant/receipt-command witness her biri1 doğrulandı. Hatalı HMAC ret ve replay yeni grant üretmeme testleri geçti. Gerçek kullanıcı kurulumu kabulü değildir.

Session yazıcısı company_os/session_provisioning.py: hash-only token, mevcut bootstrap/human bağları, authority locks ve SESSION epoch/head, audit; yeni grant yok. Gerçek sentetik DB commit/ayrı readback kanıtı evidence/NATIVE_CLOCK_TRIAL_3ee41cd3.json. İlk gerçek context_enter sonucu BLOCKED_TIME_DEPENDENCY: proje clock epoch/sample enrollment eksik. Native SYNC tek başına yeterli değil. Policy uygunluğu henüz bu kapının ötesinde doğrulanmadı.

Son Windows kaynak koşumu77test:73PASS4LinuxSKIP. Daha önce Linux75PASS0SKIP; son iki session testinin Linux koşumu ayrıca doğrulanmalı. Bu sayılar first13 kabulü değildir. G0 OPEN; first13 0/13. implementation_status.json bazı eski iç özetleri koruyor; en yeni açık kapsamlı receiptleri esas al, hepsini aynı güncel durum sanma.

WSL Ubuntu-E; .runtime/kernel-linux314 mevcut Pydantic2.14.0 ortamı. Disposable DB kullanıcı aipof-dbtest uid999; private depolama /var/lib/ai-proje-ofisi-dbtest/storage-1g.ext4 ve storage mountpoint. Var olan kurulumu yeniden oluşturma. Deney scriptlerini incelemeden çalıştırma. Mevcut commit deneyinin şema/rol önkontrolü ve cleanup kapsamını özellikle doğrula.

## İş sırası

1. company_os/provisioning.py, consent_binding.py, secret_adapter.py, bootstrap_protocol.py, bootstrap_transaction.py ve session_provisioning.py akışını birlikte denetle. Eksik gerçek trust/identity/key custody bağlantılarını belirt ve mimariye uygun uygula. User declaration/hash'i bağımsız kimlik kanıtı gibi sunma.
2. Öncelikle BLOCKED_TIME_DEPENDENCY sebebini owning-source üzerinden çöz: clock host/policy/signer enrollment, epoch ve sample writer/current bounds zinciri. SYNС/UNKNOWN, boot/generation ve expiry koşullarını gevşetme, clock health fonksiyonunu stub yapma. Test sonucu kendi yetkisini üretmesin.
3. Mevcut policy/bootstrap/session/grant yollarını tamamla. Onaysız policy digest veya uydurma grant ekleme. Sonra gerçek yetkili Objective→Plan→Task commit ve ayrı connection readback; scope, revision, receipt, audit ve outbox bağlarını doğrula.
4. Qualification, fresh claim/lease, rootless Linux controller/engine ve Broker'ı bağla. Mevcut kaynakları yeniden yazmak yerine eksik bağlantıları uygula. Model/engine/toolchain seçimini gerçek pin ve qualification ile doğrula; otomatik paid fallback yok.
5. MGT-TITLE-NORMALIZATION-01 için gerçek worker çıktısı, immutable artifact, producer'dan ayrı verifier identity/process/key/profile, seal/provenance ve Kernel kabul/ret zinciri. Reference dosyasını worker çıktısı gibi sunma. Oracle13 vaka ile first13 uçtan uca aşamasını karıştırma.
6. Minimum authenticated UI/readback ve reload. Yetkiyi UI vermez; committed gerçek veriyi göster. Sahte LIVE/success, demo veya bellek içi kayıtla kalıcılık iddiası yok.
7. Yetkisiz scope, eski lease/fence, replay, revoke, yanlış artifact/manifest, commit ack kaybı, crash ve restart negatiflerini çalıştır. UNKNOWN sonucunda otomatik OS/komut tekrarını açma.

## Çalışma biçimi ve kabul

Kapsamlı uygulama yap; her küçük test grubundan sonra kullanıcıya devam onayı sormak için durma. Yeni tasarım incelemesi somut kod/test/engelleyici karara bağlansın. Gerçek engel varsa tam kaynak, exception ve gereken dış karar/kanıtı belirt; guard bypass veya sahte PASS üretme. G0 ve gerçek insan kabulünü otomatik kapatma. Kod kabulü ayrı, gerçek ortam kabulü ayrı.

Her native deneyde bounded kaynaklar, finite timeout, private data/socket, no-network ve non-root profil korunur; yalnız bu deneye ait süreç/şema/roller temizlenir. Var olan nesne varsa overwrite/drop ile devam etme. Kalıcı test verisini yanlışlıkla üretim verisi sayma. Anahtar/token/secret içeriklerini rapora veya sohbete koyma.

## Codex'e teslim

- Değişen dosyalar ve her değişikliğin nedeni.
- Çalıştırılan exact komutlar, exit kodları, PASS/FAIL/SKIP ve kanıt sınıfı.
- Sentetik/fake-driver/native/gerçek owner enrollment/insan kabulü ayrımı.
- Kaynak/build/fixture/attempt/fence ve receipt/audit/outbox bağları.
- İlk13 aşamanın her biri için kanıt veya açık engel; otomatik toplu PASS yok.
- Açık kalan işler ve gerçek ortamın son durumu; temizlenen/kalan servisler ve test verileri.
- AI-BRAIN checkpoint/outbox yolu ve transfer durumu.

Teslimi Codex bağımsız olarak diff, kaynak sözleşmeleri ve uygun tekrar testleriyle kontrol edecek. Antigravity raporu tek başına teknik kanıt değildir. Codex/Antigravity ajan incelemesi de ürünün runtime bağımsız verifier'ı veya insan G0 makamı yerine geçmez.
