# Native SQL kaynak tabanı

GUNCEL/sql/assembly.json içindeki 83 kaynak SHA256 ile doğrulanarak bu uygulama köküne alındı. Sıra korunur; çalışma anında GUNCEL veya compatibility bağımlılığı yoktur. assembly.json her dosyanın başlangıç ve uyarlanmış hash değerini ayrı tutar.

İlk dar düzeltme: 017 dosyasında r55_cp_clock_epoch_immutable() için CREATE FUNCTION ardından PUBLIC EXECUTE kaldırıldı. Diğer 82 kaynak byte olarak başlangıç kaynağıyla aynıdır. Bu bir kaynak düzeltmesidir; gerçek katalog ACL tekrar testi yapılmadı.

Bu dosyalar çalıştırılabilir migration paketi değildir. DESIGN_ONLY guardları, ROLLBACK sınırları ve automatic_execution=false korunur. Kaynak doğrulama bu engelleri kaldırmaz.

Gerçek registry seed eksikleri (6 finality işlemi ve 3 constructor), policy/mandate/enrollment, gerçek yetkili constructor commit ve ayrı bağlantı readback hâlâ açıktır. Synthetic registry ile yapılmış tarihsel koşullu derleme, gerçek bootstrap yetkisi değildir.

Kaynak kontrolü: `C:\Python314\python.exe -B AiProjeOfisi/tools/verify_source.py` (workspace kökünden).
