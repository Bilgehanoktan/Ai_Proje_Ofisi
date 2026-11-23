# Mevcut Kernel bağlantısıyla görev ekranını başlatma

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-14
Kaynak ajan: Codex
Durum: SOURCE_AND_SYNTHETIC_NATIVE_PRECHECK_VERIFIED; REAL_OBJECTIVE_WRITE_BLOCKED

## Sade sonuç

Ne çalışıyor: Ekranı mevcut PostgreSQL'e bağlayacak denetimli başlatıcı hazır. Beklenen veritabanı/kullanıcı/socket ve gerekli native fonksiyonlara erişim kontrol ediliyor. Geçerli oturum olmadan gönderilen iş isteği gerçek native PostgreSQL'de kaydedilmeden reddedildi.
Ne eksik: Çalışma alanında kullanılabilir onaylı HTTP bağlantı profili ve gerçek oturum doğrulanmadı. Panelden gerçek Objective oluşturulmadı,ajan çalışmadı,dosya teslim edilmedi.
Katkı: Ekran artık yalnız Python içinden callback verilerek değil, dışarıdan pinli gerçek bağlantı ayarıyla denetimli başlatılabilir. Bu genel runtime kurulumu veya kabulü değildir.

## Uygulama

presentation/kernel_binding.py mevcut create_project_backend/connect arayüzüne bağlanır. Exact SHA256-pinli,bounded,tekrar anahtarsız ve sır içermeyen company.http-kernel-binding/1 belgesini yükler. Canonical workspace,service/db/login,sabit local Unix socket,project ve mevcut grant referansları,port ve emisyon süresi doğrulanır. Pin bütünlük bağını sağlar;belge tek başına yetki vermez. Şifre/token/DSN belgeye alınmaz;bağlantı sırrı supervisorun libpq service/custody yapılandırmasında kalır.

Her yeni bağlantıda readonly/repeatable-read bounded metadata kontrolü yapılır. Session/current user ve database exact eşleşmeli;recovery node,superuser,BYPASSRLS veya CREATEROLE login reddedilir. Gerekli existing native fonksiyonların varlığı ve EXECUTE erişimi sorgulanır. Başarılı kontrol rollback ile dedicated idle bağlantıyı mevcut command_hosta bırakır;başarısızlıkta bağlantı kapatılır. Migration,role,grant,session,proje veya veritabanı oluşturulmaz;TCP fallback yoktur. Bağlantı hataları ham DSN/sır içeriğiyle gösterilmez.

Bu sınırlı HTTP bağlantı ayarı tam mimari runtime profili değildir;host/model/observer/verifier qualificationın yerine geçmez. Metadata precheck kullanıcı tokenını veya grantın current kapsamını onaylamaz. r54_context_enter ve emisyon kontrolü her işlemde mevcut owning otorite olarak kalır. Kaynak/katalog isimlerinin varlığı tam katalog attestationı değildir.

## Doğrulama

- Windows238test218PASS20SKIP;Linuxuid999238PASS0SKIP. evidence/KERNEL_BINDING_20261114_windows.log ve linux.log.
- evidence/KERNEL_BINDING_20261114_native.json: PASS. Yeni private uid999 PostgreSQL18.6 kümesinde85hash-pinli native kaynak test kopyası derlendi. Sentetik non-superuser transport üyeliğiyle6existing fonksiyon için gerçek catalog/ACL precheck PASS;rollback sonrası IDLE.
- Gerçek loopback HTTP→Kernel yolu sahte/hiç kayıtlı olmayan session tokenıyla403 döndü. company.commands sayısı0 kaldı. Transport üyeliği geri alınınca yeni bağlantı reddedildi;superuser app bağlantısı da reddedildi. Sentetik fixture rol/membership gerçek enrollment değildir;pozitif yetkili Objective deneyi yapılmadı.
- Önceki native root/witness/12negatif/restart kontrolleri aynı geçici kümede PASS. Stop/küme silme PASS;mevcut kümelere dokunulmadı. SQL kaynakları ve guardları değiştirilmedi.
- CLI --check-only, mevcut olmayan config/profiles/http-kernel-binding.json için güvenli BLOCKED/exit2 verdi;sunucu/DB oluşturulmadı. Kanıt: missing_profile.json. Bu kontrol tüm bilgisayarda başka onaylı profil olmadığını kanıtlamaz.

## Sıradaki iş ve takip

Onaylı mevcut service/db/login/socket/project/grant eşlemesi ile gerçek session sağlandığında --check-only kontrolü,sonra gerçek Objective commit ve bağımsız readback yapılmalı. Kurulum izni, bağımsız kimlik/enrollment/clock/custody kanıtına dönüştürülmez. G0OPEN,first13 0/13;tam16MOD/PH00–06 kapsamı korunur.

Backend tahmini40→45,kurulum/operasyon20→25 olarak kaba değerlendirme güncellendi;eşit ağırlıklı genel özet en yakın5puanla hâlâ yaklaşık%25. Bu ölçülmüş tamamlanma değildir. Sadece test sayısı arttığı için yüzdeler değişmedi;değişiklik yeni gerçek bağlantı başlatma kabiliyetine dayanır. Diğer alanlar yeniden doğrulanmış sayılmadı.
