# Klasör geçişini geri alma

Başlangıç dosyaları [before.zip](../../evidence/runs/layout-migration-20261114/before.zip) içinde source yollarıyla tutulur. ZIP CRC ve her source SHA256 taşıma öncesinde doğrulandı. Tam kaynak-hedef ve son hashler SOURCE_TO_TARGET.json içindedir.

Yedek ilk uygulamanın 440 dosyasını, ek kök tanı aracını ve AGENTS.md/README.md/.gitignore/PROTOTIP_BASLAT.ps1/PROTOTIP_BASLAT.bat/SOURCE_LOCK.json/GUNCEL_DURUM.json dosyalarını kapsar. Kök DOGRULA.bat önceki byte içeriği yedeklenmedi; geri dönüşte eski GUNCEL/DOGRULA.py komutuna yeniden bağlanmalıdır. Yeni oluşturulan belgeler ve araçlar başlangıç ZIP'inin parçası değildir.

1. Uygulama ve düzenleme yapan ajanları durdur; veritabanı verisini silme veya yeniden kurma.
2. Güncel SOURCE_MANIFEST ve SOURCE_TO_TARGET hedef hashlerini kontrol et. Geçişten sonra değişen dosya varsa üzerine yazma; ayrı incele ve koru.
3. ZIP'i doğrudan workspace üzerine açma. Workspace içinde yeni, boş bir geçici dizine aç; arşiv yollarının bu dizin içinde kaldığını doğrula.
4. Başlangıç hashlerini source_sha256 ile karşılaştır. AiProjeOfisi kaynaklarını ve yedekteki kök giriş dosyalarını yalnız çakışmasız biçimde geri getir.
5. Yeni hedefleri hemen silme. Tek aktif ağaç kararıyla ayrı tarihsel konuma al; güncel manifest/başlatıcı/importları eski düzenle tutarlı hale getir.
6. Eski kaynak testlerini ve başlatıcıyı doğrula. Ürün/DB kabul durumlarını yükseltme.

Bu belge geri alma yöntemidir; fiziksel rollback uygulanmış veya test edilmiş sayılmaz. Runtime verileri, WSL DB dizini ve gerçek sırlar ZIP kapsamına dahil edilmedi.
