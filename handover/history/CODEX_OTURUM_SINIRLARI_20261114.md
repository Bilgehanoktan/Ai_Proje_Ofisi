# Oturum hazırlığı ve mevcut rol sınırları

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-14
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_NATIVE_PLAN_NEGATIVE; REAL_SETUP_NOT_VERIFIED

## Sade sonuç

Ne çalışıyor: Oturum açma kodu artık rol eklemiyor;yalnız mevcut rolü kullanıyor. Başlangıç kaydının güncel nesli,iptali ve güvenilir saat kontrolü korunuyor;rol/kimlik/proje kilidi veya süre belirsizse yazma başlamadan duruyor.
Ne eksik: Gerçek kurulum ve yetkili oturum doğrulanmadı;panelden gerçek iş kaydı oluşturulmadı. Bu çalışma kurulumun tamamlandığı veya ajanın çalıştığı anlamına gelmez.
Katkı: Gerçek oturum oluşturulurken yanlışlıkla yeni yetki ekleme ve eski başlangıç kaydıyla devam etme yolları daraltıldı.

## Kurulum gözlemi

Kaynakların zaten kullandığı /var/lib/ai-proje-ofisi-dbtest altındaki iki socket dizini boş;iki bilinen data yerinde postmaster.pid yok;standart /var/run/postgresql yok. İlk uid999 listeleme izinsizdi;ortamın onay mekanizmasıyla root altında yalnız bu yolların ad/varlık metadata kontrolü yapıldı. İçerik/secret okunmadı,servis başlatılmadı,mevcut DB değiştirilmedi. Tüm makinede başka kurulum yoktur sonucu çıkarılmaz.

Beklenen config/profiles/http-kernel-binding.json yok. Kullanıcı kurulumun daha önce yapılıp yapılmadığını bilmediğini belirtti;kendisinden şifre/anahtar istenmedi. Bu yüzden gerçek approved enrollment/session varmış gibi devam edilmedi. Ayrıntı:evidence/SESSION_GUARDS_20261114_setup_observation.json.

## Neden ve nasıl değişti?

Önceki issue_principal_session bir oturum talebinde company.memberships INSERT ... ON CONFLICT DO NOTHING yapıyordu;mevcut membership rolünün istenen rolle eşleşmesi zorunlu değildi. Bu trusted physical setup fonksiyonudur;bu bulgu dışarıdan istismar edilmiş bir güvenlik olayı iddiası değildir. Rol atamasıyla oturum oluşturmanın birbirine karışması giderildi. Değişiklik öncesi regression kanıtı:before.log.

company_os/session_provisioning.py:

- Membership yazımı kaldırıldı. Owner mevcut HUMAN+OWNER,technical principal mevcut kind+role eşleşmesi gerektirir. Yeni session yeni grant veya membership üretmez.
- Native r56_root_bounds sonucu installation/generation/hostboot ve aynı DB backend/transaction/login bağlarıyla exact doğrulanır. Python veya SQL wall-clock fallbackı kullanılmaz.
- Receipt/control mevcut generation ve CONSUMED durumu,canonical bootstrap command principal/project/operation/revision/digest ile bağlanır.
- Süre trusted UTC lower+TTL ile hesaplanır;upper sınırı tamamen expiry öncesinde kalmalı. Yetki kilitleri alındıktan sonra native root/time yeniden okunur;generation veya boot değişirse ret.
- Tenant/project scope kilitlerinin rank ve identity_key alanları exact doğrulanır. Kilitli son okumaya membership/control de dahil edilir.
- Caller transaction/commit ve bağımsız fiziksel kimlik/custody doğrulamasını yönetmeye devam eder. Hata durumunda tüm transaction rollback edilmelidir. Bu fonksiyon HTTP login endpointi değildir. Token yalnız hash olarak SQLye gider;çıktıda token yoktur.

Bu uyumluluk değişikliği bilinçlidir:principal için gereken membership daha önce bağımsız yetkili writer tarafından oluşturulmuş olmalıdır. Oturum açma membership eksikliğini kendiliğinden tamamlamaz.

## Kanıt ve sınırlar

- Önceki davranış:SESSION_GUARDS_20261114_before.log içindeki no-membership-write testi FAIL;düzeltme sonrası aynı davranış kontrolü PASS.
- Yeni11session protokol testi:mevcut rol/kimlik şartı,token hash,no membership write,yanlış root/context/generation,expiry,lock identity ve lock sonrası current clock kontrolü PASS. Pozitif session senaryoları typed fake-driver testidir;gerçek enrollment değildir.
- Native deney:85kaynaklı yeni private PostgreSQL18.6 katalogda owner/principal normal veFOR SHARE sorgularının EXPLAIN planı PASS. EXPLAIN ANALYZE kullanılmadı;plan kontrolü yetkili pozitif session oluşturulduğunu kanıtlamaz.
- Native root bulunmayan gerçek session çağrısı ROOT_TRUST_ANCHOR_NOT_ENROLLED ile reddedildi;sessions/memberships0/0. Clock/root fonksiyonu taklit edilmedi veya değiştirilmedi. Private küme stop/silmePASS;mevcut kümeler değişmedi. Önceki native HTTP/root/witness/restart deneyleri aynı fixturedaPASS.
- Windows245test225PASS20SKIP;Linuxuid999245PASS0SKIP. Ham kanıtlar SESSION_GUARDS_20261114_windows.log,linux.log,native.json.

## Sonraki adım

Gerçek local DB kurulumu ve bağımsız onaylı enrollment/custody/clock girişleri hazırlanıp doğrulanmalı;mevcut85guarded SQL dosyası otomatik migrationa çevrilmez. Sonrasında mevcut üyelikle gerçek oturum,HTTP binding,ilk Objective commit ve ayrı kalıcı readback yapılmalı. Bu işte bunlar tamamlanmadı. G0OPEN,first13 0/13;tüm16MOD/PH00–06 kapsamı korunur. Sade tablo ve bakım rehberi güncellendi;tahmini yüzdeler bu hata düzeltmesi nedeniyle yükseltilmedi.
