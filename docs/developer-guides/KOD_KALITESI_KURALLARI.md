# Codex ve Antigravity için ortak kod kalitesi kuralları

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-14
Kaynak ajan: Codex; kullanıcı açık talimatı
Durum: USER_APPROVED_POLICY; AUTOMATED_ENFORCEMENT_NOT_IMPLEMENTED

Bu kurallar bu workspace içinde çalışan Codex ve Antigravity için geçerlidir. Mevcut 16 modül/PH-00–PH-06 mimarisi ve Kernel/Broker/verifier sınırları korunur.

1. Yeni ve değiştirilen kodda açıklayıcı isimler, açık kontrol akışı ve tek sorumluluk kullan. Bir satıra birden fazla bağımsız işlem sıkıştırma. Gereksiz soyutlama, kullanılmayan kod ve kopya mantık ekleme. Yorum kararın nedenini açıklasın.
2. Dış girdileri sözleşmelerle doğrula; kritik API ve modül sınırlarında tip açıklamaları kullan. Hataları yutup başarı döndürme; uygun hata türü ve güvenli açıklama kullan. Any, ignore veya lint istisnasıyla denetimi susturmak gerekiyorsa dar kapsam ve gerekçe belirt.
3. DB transaction, bağlantı, dosya ve süreç yaşam döngülerini açık yönet. Hata durumunda rollback/cleanup uygula. Sırları, oturum materyalini veya gerçek profilleri kaynak koda ve loga yazma. Tanı araçları varsayılan olarak salt okunur ve en az veri çıktılı olsun.
4. Kernel tek domain writer, Broker araç/dosya etkisi sınırı, verifier bağımsız süreç/kimlik olarak kalır. GUNCEL, ARSIV ve compatibility aktif runtime bağımlılığı olamaz. Trigger kapatma veya append-only kanıtı elle değiştirerek kontrol geçme ürün kabul yolu değildir.
5. Desteklenen ve ihtiyaca uygun bağımlılık seç. Sırf yeni diye framework ekleme veya yeniden yazım yapma. Sürüm güncellemesinde resmi uyumluluk/güvenlik bilgisi, Windows/Linux desteği, lisans, test ve geri dönüşü değerlendir. Bağımlılık tanımlarını tutarlı ve kurulumu tekrarlanabilir tut.
6. Mevcut formatter/lint/tip kontrolü kuruluysa kapsamına uygun kontrolleri çalıştır; yeni hata bırakma. Bu araçlar henüz yoksa kontrol yapıldı deme; eksik kalite kapısını raporla. Kurulum görevinde Python için Ruff ve uygun tek tip denetleyici değerlendirilip sürüm/kuralları doğrulanacak. Bu belge bu araçları kurmuş veya CI etkinleştirmiş sayılmaz.
7. Davranış, refactor, biçimlendirme ve bağımlılık yükseltmesini incelenebilir parçalara ayır. Depo genelinde kör otomatik düzeltme yapma. Uygun mevcut testleri çalıştır; önemli davranış/hata düzeltmelerine anlamlı regresyon testi ekle. Basit biçim değişikliği için uygulamayı tekrar eden test üretme.
8. Eski kodun tamamını bir anda temizlemek zorunlu değildir; değiştirilen kapsamda kaliteyi düşürme. Eşzamanlı ajan değişikliklerini koru; hedefi yazmadan hemen önce yeniden oku ve çatışmada overwrite yapma.
9. SOURCE_TO_TARGET hedef hashlerini ve SOURCE_MANIFEST pinlerini yalnız incelenen değişiklik için açıkça güncelle. Tarihsel source_sha256 pinlerini koru. Doğrulayıcı pinleri sessizce yenilemez; ilgisiz manifest dışı dosyayı onaylanmış gibi ekleme.
10. Tamamlama raporunda ne/neden değiştiğini, gerçekten çalıştırılan kontrolleri, sonuçları ve açık sınırları belirt. İlgili bakım belgesi/ilerleme satırını anlamlı değişimde güncelle. Kalıcı önemli bulguyu yetkili ortak hafızaya kaydet ve yeniden oku. Statik kalite veya test PASS, runtime/G0/insan kabulü değildir.

## Mevcut doğrulama girişleri

- C:\Python314\python.exe -B scripts/development/run.py verify
- C:\Python314\python.exe -B scripts/verification/verify_layout.py

Bunlar mevcut kaynak/test/bütünlük kontrolleridir; henüz kurulmamış formatter/lint/tip/CI kontrollerinin yerine geçtikleri iddia edilmez. Sonraki somut iş otomatik kalite kapılarını kurmak ve mevcut sorunları davranışı koruyan küçük değişikliklerle azaltmaktır.
