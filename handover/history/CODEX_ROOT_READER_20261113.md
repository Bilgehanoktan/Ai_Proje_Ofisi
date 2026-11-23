# Root enrollment okuyucusu — native sürücü düzeltmesi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-13
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_SYNTHETIC_NATIVE; ACTUAL_PROVISIONING_NOT_VERIFIED

## Sorun ve değişiklik

P0-1/P0-3, MOD-001/MOD-016 kapsamında gerçek başlangıç kaydının bağımsız okunması incelendi. Native SQL016/027 şemasındaki altı UUID alanı psycopg tarafından UUID nesnesi olarak dönüyordu; read_root bunları canonical string girdilerle karşılaştırdığından doğru kayıt ROOT_READBACK_MISMATCH_OR_REVOKED ile reddediliyordu. Yeni geçici PostgreSQL18.6 kümesinde hata yeniden üretildi; salt fake-driver testi bu uyumsuzluğu yakalamamıştı.

company_os/provisioning.py içinde ROOT_READ_QUERY UUID sütunlarını açıkça ::text döndürüyor; diğer alanların native tipleri korunuyor. Parametre bağlama, readonly/repeatable-read, exact alan karşılaştırması ve revoked/compromised ret kuralları korunur. Beklenen kayıt bağlantı açılmadan önce deepcopy ile sabitlenir; geçersiz login DB bağlantısı açmadan reddedilir. Yeni grant, onay, role membership veya SQL migration eklenmedi.

## Kanıt

- evidence/CODEX_ROOT_READER_20261113_reproduce.json: düzeltme öncesi ROOT_READBACK_MISMATCH_OR_REVOKED; private sunucu stop ve küme silme PASS.
- evidence/CODEX_ROOT_READER_20261113_after.json: düzeltme sonrası native root insert/commit ve ayrı bağlantı readback PASS; revoked_at/compromised_at/wrong_digest REJECTED; bağlantılar kapalı. Önceki bootstrap witness/12negatif/restart ve84kaynak katalog ACL deneyleri de PASS. Private küme durduruldu/silindi; mevcut kümeler değişmedi.
- Root deneyi tam84kaynak native katalogda sentetik kayıt ve test adminiyle yapıldı. Verifier açıkça test double; admin RLS bypass eder. Bu, gerçek kimlik/custody/onay veya provisioning ACL kabulü değildir. Native append-only lock kuralı korunur; test satırları yalnız tüm geçici küme silinerek temizlenir.
- İlk denemede test temizliği append-only lock satırını silmeye çalışıp APPEND_ONLY_AUDIT aldı (before.json). Trigger gevşetilmedi; test yaşam döngüsü düzeltildi ve bu başarısız kanıt korundu.
- Windows:214test194PASS20SKIP (windows.log); Linuxuid999:214PASS0SKIP (linux.log).
- workflow preflight: SOURCE_CALLS_COMPATIBLE,24call,0finding. AST kontrolü runtime kabulü değildir.

## Başlangıç bağımlılıkları ve sahip kaynaklar

| Bağımlılık | Sahip kaynak | Açık sınır |
|---|---|---|
| Fiziksel root kaydı ve kilit | sql/016,sql/027; provisioning.enroll_root/read_root | Bağımsız gerçek kimlik/consent/custody verifierı ve onaylı fiziksel DB erişimi gerekir. Runtime rolüne INSERT grant eklenmez. |
| Bootstrap arm ve generation sınırı | sql/016 r55_cp_setup_control_arm;sql/027 r56_root_bounds | Gerçek onaylı root, host/boot/clock ve imzalı manifest/nonce bağları gerekir. |
| İnsan clock policy kararı | sql/032 r57_clock_policy_authority/consents/receipts ve r57_clock_policy_write | Gerçek current authority ve insan consent kaydı gerekir; belge varlığı onay değildir. |
| Bootstrap kalıcı witness | sql/028;sql/084; bootstrap_readback.NativeBootstrapReadback | Dar metadata MATCH güncel yetki/enrollment kanıtı değildir. |
| Host/profile ve supervisor girdileri | observer_profile.py;workflow_trust.py;linux_observer.py | Pinli ölçüm profili, bağımsız current enrollment readback ve qualified OS/launcher bağları açık. |

Tam16modül/PH00–06 kapsamı korunur. Bu düzeltme gerçek çalışan ilk SOFTWARE akışının önkoşulunu onarır; akış kabulü değildir. G0OPEN,first13 0/13; gerçek provisioning/clock/profile/worker/verifier entegrasyonu açık. Sonraki somut iş mevcut authority readback portlarını native enrollment/clock kayıtlarına bağlamak; onay ve anahtarlar sentetik doldurulmaz.
