# Native bootstrap readback ve ACL — 2026-11-13

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Durum: VERIFIED_SOURCE_AND_SYNTHETIC_NATIVE; ACTUAL_INTEGRATION_BLOCKED
Kapsam: MOD-001/MOD-016, PH-01; P0-1/P0-3 kısmi ilerleme. Tam 16 modül/PH-00–PH-06 hedefi korunur.

Doğrudan SELECT okuyucusunun native RLS/context sınırına uygun dar yol eklendi: sql/084_APPLICATION_BOOTSTRAP_READBACK_V1.sql ve NativeBootstrapReadback. Fonksiyon yalnız mevcut company_provisioning_runtime_r55 session_user kimliğine exact bootstrap metadata döndürür. NOLOGIN/NOBYPASSRLS owner, sütun bazında SELECT, sabit search_path, PUBLIC EXECUTE iptali ve eksik provisioning rolünde güvenli ret uygulanır. Çağırana tablo SELECT, owner üyeliği veya yazma yetkisi verilmez. Sonuç authorization=NOT_VERIFIED, new_grants=0 taşır; güncel yetki kanıtı değildir.

83 önceki SQL kaynağı bu görevde değişmedi; uygulama assembly 84 dosyadır. DESIGN_ONLY guardları, son ROLLBACK ve automatic_execution=false korunur. Otomatik migration yapılmadı.

## Doğrulama

- Windows: 212 test, 192 PASS/20 SKIP; Linux uid999: 212 PASS/0 SKIP.
- evidence/CODEX_NATIVE_ACL_20261113_attempt02.json: PASS. PostgreSQL 18.6 yeni özel /tmp kümesi; TCP kapalı, socket 0700. Özgün guardın reddi doğrulandı. Hash kontrollü 84 kaynağın yalnız bellekte türetilmiş fixture kopyaları derlendi. Tam native katalogda projects/grants/bootstrap sayıları 0/0/0; fonksiyon ACL/owner/read-only erişim ve boş witness reddi doğrulandı.
- Pozitif kayıt, 12 negatif ve restart sonrası readback: aynı fonksiyon + FORCE RLS uygulanmış minimal yansıtılmış şema üzerinde PASS. Bu bölüm tam native bootstrap üretimi değildir.
- Private sunucu durduruldu, geçici küme silindi; mevcut kümelere dokunulmadı.
- İlk fixture denemesi guard sayısı uyumsuzluğunda güvenli durdu; evidence/CODEX_NATIVE_ACL_20261113_trial.json korunur. 050 kaynağındaki üç guard açıkça ele alınarak ikinci deneme geçti.

## Açık işler

Gerçek onaylı provisioning/enrollment, registry seed, güncel owner/clock/profile doğrulaması, qualified launcher/worker ve bağımsız verifier bağları açık. Tam native şemada yetkili bootstrap commit ve bağımsız readback henüz doğrulanmadı. Sonraki adım bu kurulum bağımlılıklarını mevcut kaynaklarla eşleyip eksik güvenilir adapterleri tamamlamaktır. G0 OPEN; first13 0/13; insan veya runtime kabulü üretilmedi. GUNCEL/DOGRULA.py tarihsel hash sorunu bu görevde tekrar sınanmadı.
