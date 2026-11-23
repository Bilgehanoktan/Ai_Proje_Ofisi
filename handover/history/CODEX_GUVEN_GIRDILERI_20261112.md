# E2E güven girdileri uygulama dilimi


## 2026-11-12 — E2E güven girdileri bağlantısı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-12
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_TEST; bağımsız kabul PENDING; runtime NOT_RUN
Kanıt: evidence/CODEX_TRUST_20261112_tests.log; evidence/CODEX_TRUST_20261112_preflight.json; evidence/CODEX_TRUST_20261112_manifest.json.

TASK-CODEX-20261112-01; MOD-001/004/015/016, PH-00/02 güven girdisi alt dilimi; hedef tasarım §16 ve BR-001. Tam16MOD/PH00–06 hedefi korunur.

E2E betiğinin belge içeriğinden kendi consent SHA256 pinini türetmesi kaldırıldı. company_os/workflow_trust.py mevcut consent_binding ve secret_adapter arayüzlerine bağlandı: supervisor sağladığı pin/human/workspace/root ve directory fd/name/owner uid gerekir. Onay eşleşmesi enrollment yetkisi veya bağımsız kimlik doğrulaması değildir. Betiğin sabit test anahtarı üretimi, path ile secret okuması ve enrolled dizini cleanup sırasında silmesi kaldırıldı. Güven kontrolü DB bağlantısından önce yapılır; bootstrap installation/human ile root bağı ayrıca karşılaştırılır. Supervisor provisioning/enrollment uygulanmış sayılmaz.

129 test çalıştı:125PASS,4LinuxSKIP; exit0. Yeni dört test; exact port aktarımı, pin/human/workspace ve değiştirilmiş belge retleri, path bypass/anahtar hatasında ret ve gerçek main gövdesinde DB öncesi ret. Anahtar okuma pozitif testi mock; gerçek Linux custody kabulü değildir. Preflight42doğrudan çağrı/1dinamik atlama/15uyuşmazlık,exit2. Önceki17uyuşmazlıktan consent/secret çağrıları owning arayüzlerine taşındı; dinamik atlama sayısı önceki1de kaldı. Bu sayı yalnız AST imza kapsamıdır.

GUNCEL/DOGRULA.py bugün yeniden koşuldu: exit1, dokumanlar/hedef-mimari-v1/CALISMA_DURUMU.md SHA256 assertion hatası sürüyor. Eski baseline/manifest değiştirilmedi. G0OPEN,first13 0/13; DB/model/servis başlatılmadı.

Sıradaki iş: kalan15çağrı ve custom CommandHostRuntimePort katmanını canonical PilotSession/Kernel/launcher/verifier portlarına taşımak. Gerçek enrolled profile/signer/lease/source/OS kanıtı uydurulmaz. Bağımsız review ve fiziksel zincir açık. Bu dilim tam modül kapanışı değildir.
