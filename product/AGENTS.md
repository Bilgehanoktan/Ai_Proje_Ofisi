# Uygulama çalışma alanı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi

Uygulama kökü: E:\Projeler\Ai_Proje_Ofisi\product



Kullanıcının 2026-11-14 geçiş onayıyla ürün kaynakları bu dizinde geliştirilir; eski AiProjeOfisi konumu güncellenmiştir. Üst dizindeki GUNCEL kaynak konumu kuralının bu yeni uygulama için istisnasıdır. GUNCEL mevcut kaynak ve mimari referansıdır; otomatik taşınmaz.

Türkçe iletişim kullan. Mimari dayanak ../GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md §12, §15, §16, §26 ve §27.

Mevcut tasarımı uygula; yalnız somut kod/test engelinde karar incelemesine dön. İlk akış SOFTWARE MGT-TITLE-NORMALIZATION-01 ve tanımlı MOD-001–MOD-016 çerçevesidir. Kapsam dışı yeni özellik veya departman ekleme.

Kernel kanonik domain writer; Broker dosya/araç etkisi sınırı; verifier ayrı kimlik ve süreç; presentation salt okunur görünüm ve yetkili command istemcisidir.

GUNCEL/compatibility ve ARSIV runtime bağımlılığı olamaz. Kaynak uyarlarken ilgili contracts/SQL/import zincirini birlikte incele; kör kopyalama veya sys.path ile eski ağaca bağlama yapma.

Producer ve verifier fixtureları ayrı tutulur; klasör ayrımı gerçek izolasyon kanıtı değildir. Sırları veya gerçek müşteri verisini depoya koyma.

G0 OPEN; runtime NOT_RUN; first13 0/13. Klasör veya statik test başarısı runtime izni/kabulü değildir.



## Kullanıcının sürekli ilerleme tablosu isteği — 2026-11-14



Her anlamlı geliştirmede `progress/ILERLEME_TABLOSU.json` içindeki ilgili alanları güncelle; ne çalışıyor, ne eksik ve sıradaki iş sade Türkçeyle yazılsın. Ön yüz, arka uç, güvenlik ve diğer başlıklar tüm 16 modül/PH-00–PH-06 kapsamını korur. Kanıtı ve ilgili satırın kontrol tarihini ekle; değişmeyen alanları yeniden doğrulanmış gösterme. Test sayısını ürün tamamlanması veya tahmini yüzdeye dönüştürme. Nihai arayüz ile geçici görev ekranını ayır. Ürün hafızasını AI-BRAIN ajan notlarıyla karıştırma.



Tek sade takip kaynağı bu JSON'dur; Markdown görünümünü workspace kökünde `C:\Python314\python.exe -B scripts/development/run.py progress` ile yenile. Tarayıcıdaki `/progress` aynı kaynaktan okunur; arka planda otomatik güncelleme iddia edilmez. Ayrıntılı `UYGULAMA_DURUM_MATRISI.md` ve tarihsel kanıtlar korunur. Kullanıcıya ilerlemeyi bu sade tablodan anlat.





## Bakım erişimi — 2026-11-14



Anlamlı değişikliklerde neyin neden/nasıl değiştiği, ilgili dosyalar, uygun kontrol ve açık sınırlar erişilebilir kayıtta tutulur. Kullanıcının bakım başlangıç noktası `BAKIM_VE_DEGISIKLIK_REHBERI.md` dosyasıdır; önemli yeni bileşen, yol veya davranış değişince bu rehberi de güncelle. Belgeyi güncel kod ve kanıta bağla; belgenin varlığını teknik doğruluk veya tam sürüm geçmişi sayma.





## Kullanıcının tahmini yüzde isteği — 2026-11-14



Kullanıcı açıkça tahmini de olsa yüzde eklenmesini istedi. Sade tabloda alan bazlı kaba geliştirme tahmini gösterilir; ölçülmüş tamamlanma veya gerçek runtime kabulü gibi sunulmaz. İlk sürüm14alanın eşit ağırlıklı tahmin ortalamasını en yakın5puana yuvarlar;zaman/efor ağırlıklı değildir. Tahminin dayanağını ve belirsizlik aralığını koru;test sayısını yüzdeye çevirme. Gerçek ilk akış kabulünü ayrı göster. Yeni kanıt gelirse tahmin düşebilir;eski tahmini teknik gerçek sayma.



## Sıradaki işleri her zaman belirt — 2026-11-14



Kullanıcının açık isteği: her ilerleme yanıtının sonunda sıradaki somut işleri sade Türkçeyle söyle. Güncel sırayı ve sonraki adımları progress/ILERLEME_TABLOSU.json ve handover/NEXT_STEP.md üzerinden oku. Bu adımlar tam 16 modül kapsamının yerine geçmez. Tamamlanmamış adımı tamamlandı deme; aynı genel engeli tekrar etmek yerine son doğrulanmış durumu ve somut kalan işi belirt.



## Ajanlar arası güncel durum ve kanıt — 2026-11-14

Durum yanıtında önce progress/ILERLEME_TABLOSU.json ve kanıtlarını oku. Canlı AI-BRAIN kartı ile kaynak raporu çelişiyorsa eski kaydı güncel durum sayma; ilgili canlı readback veya son çalışma kanıtıyla çöz. DB satır varlığı ile yetkili kökeni ayır. Kaynak ajan iddiası REPORTED_NOT_RETESTED; bağımsız gözlem VERIFIED olarak kaydedilir. Önemli kalıcı DB/oturum/iş kaydı değişikliği de anlamlı kilometre taşıdır; yalnız kod veya karar değişmemesi Memory: UNCHANGED gerekçesi olamaz. İlgili ilerleme satırı, kanıt raporu ve yetkili ortak hafıza kaydı birlikte güncellenir; aktarım ayrıca doğrulanır. Son uzlaştırma ve kontroller: handover/STATE_RECONCILIATION_20261114.md, handover/LIVE_FLOW_VERIFICATION_20261120.md ve handover/G0_INSAN_ONAYI_KONTROL_LISTESI_20261123.md. Trigger kapatma veya append-only kanıtın süresini elle uzatma ürün kabul yolu değildir.


## Ortak temiz kod kuralı — 2026-11-14

Kullanıcı talimatı: Codex ve Antigravity her yeni/değiştirilen kodda [ortak kod kalitesi kurallarını](../docs/developer-guides/KOD_KALITESI_KURALLARI.md) uygular. Açık ve okunabilir kod, güvenli hata/kaynak yönetimi, doğrulanan bağımlılıklar, mimari sınırlar ve uygun test/kanıt zorunludur. Kuralların yazılması formatter/lint/tip kontrolü veya CI kurulduğu anlamına gelmez; eksik otomatik kontrolleri açık bildir. Mevcut açık ajan oturumlarının bu dosyayı kendiliğinden yeniden yüklediğini varsayma.
