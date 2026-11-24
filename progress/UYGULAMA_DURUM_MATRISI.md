# Tam mimari uygulama ve bağımsız kontrol matrisi

Güncel sade takip: [Proje ilerleme tablosu](ILERLEME_TABLOSU.md) · [Tarayıcıda aç](http://127.0.0.1:8766/progress). Her anlamlı geliştirmede güncellenir; ayrıntılı mimari ve tarihsel kanıtların yerine geçmez.


Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-10
Hazırlayan: Codex · Uygulama bildirimi: Antigravity · Bağımsız kontrol: Codex · İnsan kabulü: proje sahibi
Durum: REVIEW_REQUIRED / CODEX_DUZELTME_GEREKLI

Bu dosya 16 modülün TAMAMINI ve PH-00–PH-06 fazlarını izler. İlk MGT-TITLE-NORMALIZATION-01 akışı ara kabul hedefidir. Hiçbir sonraki faz kapsamdan çıkarılmaz. Kaynak hazırlığı bağımlılıklar izin verdiği ölçüde ilerler; runtime etkinleştirme mevcut kapılara bağlıdır. Bu tablo yeni mimari kararı veya yürütme izni üretmez.

## Güncel kabul kaydı — 2026-11-24

23 Kasım [insan kabul kaydında](../handover/G0_INSAN_ONAYI_KONTROL_LISTESI_20261123.md) G0 onaylı ve MGT-TITLE-NORMALIZATION-01 13/13 kabul edildi. Aşağıdaki eski deneme ve kontrol durumları tarihsel kanıttır. 088 ajan kayıtları değerlendirme kümesinde [kanıtlandı](../evidence/runs/live-agent-instances-e2e-20261123.json). Temiz 001–088 kurulumu, 087 → 088 yükseltmesi ve ek iş türlerinin gerçek araç kabulü açık. Güncel sıra [devir notunda](../handover/NEXT_STEP.md) tutulur.

## 1. Kaynak ve güncellik

- Ana giriş: [v0.16.2-r68](../GUNCEL/dokumanlar/AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v0.16.2-r68.md).
- Modül adları, sorumluluklar ve kabul zincirleri: [hedef tasarım](../GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md) §15–16; fazlar §35–36; TaskSpec §28; izlenebilirlik §39.
- Faz teslimleri: [yol haritası](../GUNCEL/dokumanlar/hedef-mimari-v1/UYGULAMA_YOL_HARITASI.md). Son tarihli ekler ve kök/uygulama AGENTS.md birlikte uygulanır.
- Mevcut uygulama: [PLAN.md](PLAN.md), [module-map.json](module-map.json), [son görev paketi](ANTIGRAVITY_SIRADAKI_GOREV_20261110.md). Bu kaynakların eski durum metinleri güncel kabul sonucu değildir.
- Bu hazırlıkta ürün testi çalıştırılmadı. Önceki test/PASS iddiaları REPORTED_NOT_RETESTED; modül bazında bağımsız doğrulama henüz yapılmadı. BELIRLENMEDI, UYGULANMADI demek değildir.
- GUNCEL/STATE.json yalnız A tabanını tanımlar. Buradaki takip bu dosyadaki G0 veya first13 değerlerini yükseltmez. Kabul kanıtı yoksa sayaç üretilmez.

| Kaynak | SHA256 (tablo hazırlanırken) |
|---|---|
| `GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md` | `b0495856786d1cc8c5106b9466467fd44e689319bb888ced094b021c21f0357b` |
| `GUNCEL/dokumanlar/hedef-mimari-v1/UYGULAMA_YOL_HARITASI.md` | `c561c58dcdff1301bdfe1c4ca819fb191d8ae04ff9651ce0b55d1b39498ea199` |
| `GUNCEL/dokumanlar/AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v0.16.2-r68.md` | `c83e9f145415a09728e4c71baa0ba1152c6679909d7d7427858962672f93ea0f` |

Kaynak değiştiğinde etkilenen satırları yeniden eşle; önceki kaynak pinini ve kontrol geçmişini koru.

## 2. Durum ve sorumluluk kuralları

- Antigravity yalnız kendi bildirimini, dosyaları, eksikleri, görevleri ve kanıtları günceller. Codex kontrolü alanına kendi adına sonuç yazamaz.
- Durum: BELIRLENMEDI → envanter bekliyor; UYGULANMADI → incelemeyle yokluğu gösterildi; KAYNAK_HAZIR → belirtilen alt kapsam uygulanmış ve kaynak testi kanıtlı; BAGLI → gerçek çağrı zincirine bağlanmış; GERCEK_TEST_EDILDI → belirtilen gerçek ortamda pozitif/negatif/readback kanıtı var; KABUL_EDILDI → ilgili tam AC ve gereken insan onayı var.
- Kısmi çalışma `KISMEN/<durum>` olarak, kapsanan ve eksik alt davranışlarla yazılır. İlk akışın tamamlanması modülün bütün mimari kapsamını tamamlamaz. BLOCKED ayrı engel alanıdır; ulaşılan kanıt düzeyini silmez.
- Kanıt sınıfları: SOURCE_STATIC, UNIT, FAKE_DRIVER, SYNTHETIC_NATIVE, ACTUAL_RUNTIME, HUMAN_ACCEPTANCE. Sentetik native test gerçek sahip enrollment veya ürün kabulü değildir.
- Codex kontrolü: BEKLIYOR / KISMEN_DOGRULANDI / DOGRULANDI / DUZELTME_GEREKLI / ENGELLI / STALE. DOGRULANDI yalnız açıkça belirtilen kapsam içindir. Kaynak/build/config değişimi ilgili eski kontrolü STALE yapar.
- Teknik kabul (MOD-009), bağımsız ajan incelemesi ve insan kabulü ayrı tutulur. Antigravity kendi ürettiği PASS ile bunları birleştiremez.
- Toplam yüzde hesaplanmaz. Durum dağılımı, eksik AC sayısı ve gerçek test/insan kabul kapsamı ayrı raporlanır. İlk başlangıç: 16 modülün güncel uygulama bildirimi ve Codex kontrolü bekliyor.

## 3. 16 modül ana tablosu

Kapsam ve kabul bağlantıları §15 içinden alınmıştır. Faz sütunu yol haritasındaki açık modül listesidir; tek başına bütün bağımlılık grafiği değildir. Gerçek port bağımlılıkları §16 ve modül kartında gösterilir.

| MOD | Mimari ad | Faz / doğrudan listelendiği | Kabul/test numaraları | Antigravity: durum ve kanıt ID | Codex: sonuç ve kontrol ID |
|---|---|---|---|---|---|
| [MOD-001](#mod-001) | Kimlik, Policy ve Command Host | PH-01, PH-04 | AC/TEST-004, AC/TEST-012 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | KISMEN_DOGRULANDI; CODEX-20261110-MATRIS-02 |
| [MOD-002](#mod-002) | Hedef, Plan ve Ajan CEO | PH-00, PH-01 | AC/TEST-001, AC/TEST-005 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | KISMEN_DOGRULANDI; CODEX-20261110-MATRIS-02 |
| [MOD-003](#mod-003) | Scheduler ve Qualification | PH-02 | AC/TEST-006 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-02 |
| [MOD-004](#mod-004) | Launch Controller ve Isolation | PH-02 | AC/TEST-007 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 |
| [MOD-005](#mod-005) | Engine ve Provider Adapter | PH-02 | AC/TEST-002 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 |
| [MOD-006](#mod-006) | Tool Broker ve Etki Sınırı | PH-02 | AC/TEST-008 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | KISMEN_DOGRULANDI; CODEX-20261110-MATRIS-01 |
| [MOD-007](#mod-007) | Workspace, Patch ve Artifact | PH-03 | AC/TEST-009 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | KISMEN_DOGRULANDI; CODEX-20261110-MATRIS-01 |
| [MOD-008](#mod-008) | Bağımsız Verifier | PH-03 | AC/TEST-010 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-02 |
| [MOD-009](#mod-009) | Acceptance ve Release Kontrolü | PH-03 | AC/TEST-011 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-02 |
| [MOD-010](#mod-010) | Event ve Projection | PH-04 | AC/TEST-013 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 |
| [MOD-011](#mod-011) | Yönetim ve Ofis Sunumu | PH-04 | AC/TEST-014 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-02 |
| [MOD-012](#mod-012) | Katalog ve Hafıza | PH-01, PH-06 | AC/TEST-015, AC/TEST-016 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 |
| [MOD-013](#mod-013) | WorkType Uygulamaları | PH-06 | AC/TEST-019, AC/TEST-020, AC/TEST-021 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-02 |
| [MOD-014](#mod-014) | Bütçe, Ticari Kayıt ve Dış Etki | PH-02, PH-05 | AC/TEST-017, AC/TEST-018 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | KISMEN_DOGRULANDI; CODEX-20261110-MATRIS-01 |
| [MOD-015](#mod-015) | Operasyon, Recovery ve Backup | PH-05 | AC/TEST-022, AC/TEST-027 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | KISMEN_DOGRULANDI; CODEX-20261110-MATRIS-01 |
| [MOD-016](#mod-016) | Teslimat, ADR ve Kalite Yönetişimi | PH-00, PH-01, PH-03 | AC/TEST-003, AC/TEST-023, AC/TEST-024, AC/TEST-025, AC/TEST-026 | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01, EV-20261110-UNIT-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-02 |

## 4. Faz takibi

| Faz | Mimari teslim | Modüller | Önkoşul / durdurucu | Antigravity / kanıt | Codex kontrolü |
|---|---|---|---|---|---|
| PH-00 — Kaynak, kapsam ve sözleşme hazırlığı | Bir hedefin taslak plan ve kanıt gereksinimleri dosyada izlenir; henüz runtime yok | MOD-002, MOD-016 | İki kaynak hash ve owning-source envanteri; tam semantik kapsama açığı kapatılmadan FINAL source-audit ilan edilmez | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |
| PH-01 — Yetkili disposable DB dikey dilimi | Tek hedef kalıcı, yetkili readback ile okunur; izinsiz tenant yazamaz | MOD-001, MOD-002, MOD-012, MOD-016 | PH-00 ve ilgili ayrı G0/clock/DB test yetkisi; disposable tenant ve geri yüklenebilir boş ortam | KISMEN/KAYNAK_HAZIR; EV-20261110-UNIT-01, EV-20261108-SYNTH-01 | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |
| PH-02 — Qualified worker ve kapalı sandbox | Kayıtlı tek attempt izinli kaynağı okur; yanlış path/fence/namespace reddedilir | MOD-003, MOD-004, MOD-005, MOD-006, MOD-014 | PH-01; native helper/host/namespace/cgroup ve signer enrollment; gerçek OS test izni | KISMEN/KAYNAK_HAZIR; EV-20261110-UNIT-01 (Linux rootless/cgroup testleri Windows ortamında atlandı: 4 SKIP) | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |
| PH-03 — Patch ve bağımsız teknik kabul | Doğru patch teknik olarak kabul edilir, yanlış patch reddedilir; UI/reload henüz ayrı faz | MOD-007, MOD-008, MOD-009, MOD-016 | PH-02; oracle producer mount dışında; ayrı verifier key/process/profile; exact build pin | KISMEN/KAYNAK_HAZIR; EV-20261110-UNIT-01 (verifier false-pass sertleştirmesi ve mutant testi dahil) | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |
| PH-04 — Yetkili UI, snapshot ve kalıcı reload | İlk 13 aşamalı kabul zinciri kalıcı reload ile gözlenir; click grant üretmez | MOD-001, MOD-010, MOD-011 | PH-03; authenticated read API; source epoch projection mapping ve OfficeEvent sözleşmesi çözümü | KISMEN/KAYNAK_HAZIR; EV-20261110-UNIT-01 (test_presentation.py) | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |
| PH-05 — Recovery ve sınırlı şirket operasyonu | Restore edilen veri okunur, eski yetki dirilmez; taslak ticari olaylar çift sayılmaz | MOD-014, MOD-015 | PH-04; ayrı backup/witness/custody ve incident sorumlusu; dış etkiler hâlâ ayrı izinli | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01 (sözleşmeler hazır, runtime runbook ve automated restore bekliyor) | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |
| PH-06 — Seçili WorkType ve ürün genişlemesi | Her seçili dal izole fixture’dan bağımsız kabul ve reload’a gider; diğer dallar kapalı kalır | MOD-012, MOD-013 | PH-05; ilgili input/schema/oracle/data-rights/owner kaynakları ve ayrı kararlar; her dal için bounded task | KISMEN/KAYNAK_HAZIR; EV-20261110-SRC-01 (SOFTWARE/MGT01 aktif, diğer iş türleri şema düzeyinde inert) | DUZELTME_GEREKLI; CODEX-20261110-MATRIS-01 (envanter/kanıt; faz kabulü yok) |

PH-01→PH-02→PH-03→PH-04 ilk akışın aşamalarıdır; PH-05/06 tam proje planında kalır. MOD-012 katalog pinleri, MOD-014 limitleri ve MOD-015 güvenli stop/UNKNOWN işleri ilk ihtiyaç duyulan aşamada uygulanır. Faz tablosundaki geç teslim, bu korumaları erteleme gerekçesi değildir.

## 5. Modül kartları — Antigravity doldurur, Codex kontrol eder

<a id="mod-001"></a>
### MOD-001 — Kimlik, Policy ve Command Host

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Kimliği doğrulama, scope/epoch, sabit operation registry, transaction finality ve bounded emit |
| Kayıt sahipliği | Principal,Session,Grant,AuthorizationEpoch,Command |
| Referans / önerilen kaynaklar | company_os/command_host.py; company_os/kernel_adapters.py |
| Yetki sınırı | Yalnız tanımlı command veya auth adapter; model/UI SQL yazamaz |
| Kabul zinciri | BR-004 → AC-004 → TEST-004; BR-012 → AC-012 → TEST-012 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/command_host.py` (`a817f776cc3d241aaff29a54428fd934191fe84ce915531f3b905154d332176c`: `execute`, `enter`, `emit`), `company_os/kernel_adapters.py` (`8f561b9b62e0a63b426a4670dd3bbe3c2ee5c6e57bffc1691d7ef806ff59aeb2`), `company_os/bootstrap_protocol.py` (`8cd5fd5c4572131404286bd2ede9e27c0a990e12065894059a1aac7576ed7572`), `company_os/bootstrap_transaction.py` (`e3f14f5590f39ce4fc5e228e37e4ba9cc1a24b717c5d0feec18e2fa896c0b6b5`), `company_os/clock_provisioning.py` (`928c8b433d41e1f8e034b3935e7e76853bc1574fe83f400a22913c60e8e05a33`), `company_os/consent_binding.py` (`4fab6daf4a477079b4e390e0e5a006e79e465b67f4287f24c862f3ea97b06a14`), `company_os/session_provisioning.py` (`b670c2248ba438524304ac0fe015d19ecd221ae5ebb4c0fadd02359c4a7a9c08`), `company_os/secret_adapter.py` (`4735801e1f0201008382dde47e96bc4b4a1d5626a27b9a9c93a39fcc6976ae92`), `company_os/registry_reader.py` (`672432f3b4f9f0ba8531ed55609fa0f8a5093a867d1a3e465550ff9f03559b10`), `company_os/registry_preflight.py` (`b0ef8f3c2a2b92eabd4176570ea84c3f2b82ee28aba54920dae5f05cd1205fc7`), `company_os/reply_guard.py` (`64ffd6267bf2514bfe856b300ce59dd42e24b03508422d5206c70cd546f7bf3d`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Sabit operation registry doğrulaması, session oluşturma ve role hash kontrolü, transaction finality sarmalaması, clock policy doğrulama ve epoch guard; Eksik: Canlı PostgreSQL üzerinde çoklu tenant isolation denemesi, donanımsal HSM/KMS anahtar sarmalaması; Henüz bağlanmayan: E2E iş akışında (`tools/disposable_e2e_workflow_trial.py`) command host preflight/constructor imza tam kablolaması (P0-2 kapsamında) |
| Port bağımlılıkları / görev önkoşulları | MOD-001 kanonik domain writer portu sunar; MOD-002, MOD-003, MOD-006, MOD-009, MOD-011, MOD-014 çağrılarını kabul eder. Görev önkoşulu: P0-2 E2E kablolama ve DB migration (sql/assembly.json) |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Engel: tools/disposable_e2e_workflow_trial.py içinde eski/uyumsuz sembol çağrıları (P0-2); G0 kapısı açık (OPEN), gerçek DB ortamında tam native E2E yürütme izni bekleniyor |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P0-2 / PH-01 / E2E workflow betiğindeki import/imza uyumsuzluklarının giderilmesi ve preflight testinin PASS vermesi |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; Sentetik deneme yapıldı (`evidence/NATIVE_CLOCK_TRIAL_a20c6386.json`), ürün DB testi bu oturumda çalıştırılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor (config/owner-installation-consent.json yerel kurulum rızası var, G0 kabulü yok) |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | KISMEN_DOGRULANDI; F01 execute/enter/emit düzeltmesi doğrulandı; gerçek auth/DB kabulü ve P0-2 açık. |

<a id="mod-002"></a>
### MOD-002 — Hedef, Plan ve Ajan CEO

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Amaç yorumlama, immutable plan DAG, task ve istisna önerisi; stratejik kararı sahibine sunma |
| Kayıt sahipliği | Objective,PlanVersion,Task,DecisionCase |
| Referans / önerilen kaynaklar | packages/contracts/company.py; packages/contracts/models.py |
| Yetki sınırı | Scope genişletemez; yalnız MOD-001 üzerinden yazar |
| Kabul zinciri | BR-001 → AC-001 → TEST-001; BR-005 → AC-005 → TEST-005 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `packages/contracts/company.py` (`11aa436748f3efe44101ac607aeffdbba3f7e3c00c3244a7c64394d45d2778ac`: `Mission`, `Stage`, `WorkflowTemplateVersion`, `Qualification`), `packages/contracts/models.py` (`7a1567f63ce359632fc234d1aa4e43f090a02b03f6cf893184347de11db8e466`: `ObjectiveCreate`, `ObjectiveRead`, `PlanCreate`, `PlanRead`, `TaskCreate`, `TaskRead`, `TaskAction`), `company_os/command_host.py` (`a817f776cc3d241aaff29a54428fd934191fe84ce915531f3b905154d332176c`: `execute`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Objective/PlanVersion/Task tip tanımları, JSON şemaları, immutable DAG veri yapıları; Eksik: Dinamik istisna/karar (DecisionCase) önerme motoru; Henüz bağlanmayan: E2E pipeline üzerinden gerçek command çağrısı ile Objective->Plan->Task zincirleme yazımı |
| Port bağımlılıkları / görev önkoşulları | MOD-001 üzerinden domain state yazar; MOD-003'e task claim için girdi sağlar. Önkoşul: MOD-001 command host |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Canlı ortamda çok adımlı plan dallanması ve LLM tabanlı plan üreticisi bağlanmadı; şema ve model seviyesinde doğrulandı |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-1 / PH-00, PH-01 / Objective->PlanVersion->Task zincirinin DB readback ile doğrulanması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; unit test seviyesinde şema doğrulaması PASS, runtime readback henüz çalıştırılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | KISMEN_DOGRULANDI; F01 gerçek DTO isimleri doğrulandı; gerçek CEO/plan ve kalıcı zincir kabulü yok. |

<a id="mod-003"></a>
### MOD-003 — Scheduler ve Qualification

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Claim, heartbeat, lease, fencing; model/rol/tool/suite binding ve kaynak admission |
| Kayıt sahipliği | Attempt,Qualification,WorkerProfile,ResourcePermit |
| Referans / önerilen kaynaklar | packages/contracts/execution.py; company_os/kernel_adapters.py |
| Yetki sınırı | Process’i doğrudan başlatmaz; MOD-001 ve MOD-004 portlarını kullanır |
| Kabul zinciri | BR-006 → AC-006 → TEST-006 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `packages/contracts/execution.py` (`0ebc384cc3e58b4552d274b82f7a954eed84e9ea0ca19226e9bdaf3fa4620cd7`: `RunAdmission`, `CompilePlan`, `CompiledStage`, `VerifierCheck`, `VerifierReceipt`), `packages/contracts/company.py` (`11aa436748f3efe44101ac607aeffdbba3f7e3c00c3244a7c64394d45d2778ac`: `Qualification`), `company_os/execution_protocol.py` (`df5e5dee7d55af19cf8c64f870a6a24d3668e36ada232699022ad1cb7486cca3`: `TicketCodec`, `IntentJournal`, `CommittedController`, `LeaseRegistry`, `LeaseBridge`), `sql/053_R60_WORKER_CLAIM_OVERLAY.sql`, `sql/077_R64_QUALIFICATION_FINALITY.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Attempt, worker qualification ve lease claim şemaları; lease timeout ve SQL writer fence kontrolleri; Eksik: Dinamik heartbeat monitörü daemonu; Henüz bağlanmayan: Canlı worker claim kuyruğu orchestratoru |
| Port bağımlılıkları / görev önkoşulları | MOD-001 auth epoch/grant ve MOD-004 process launch portlarına bağımlı. Önkoşul: PH-01 DB katmanı ve auth epoch |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Worker claim mekanizmasının gerçek eşzamanlı multi-worker yarış testleri henüz yapılmadı |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-2 / PH-02 / Claim, lease fencing ve qualification mekanizmasının tek attempt üzerinde doğrulanması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; birim testlerde fencing doğrulandı, canlı ortam çalıştırılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; R2-04: AttemptAdmission/FencedAttempt owning source içinde yok. |

<a id="mod-004"></a>
### MOD-004 — Launch Controller ve Isolation

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | One-shot launch, enrolled executable, cgroup/namespace/boottime, watchdog ve bağımsız stop gözlemi |
| Kayıt sahipliği | ProcessBinding,LaunchIntent,LeaseWatchdogState |
| Referans / önerilen kaynaklar | company_os/launch_controller.py; company_os/r65_spawn_linux.c |
| Yetki sınırı | Engine’e host credential veya sınırsız workspace devretmez |
| Kabul zinciri | BR-007 → AC-007 → TEST-007 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/launch_controller.py` (`93d694196f1130dc9794e1bafa9f06342b6c7c648be8ba93ffc09a437d18324a`), `company_os/r65_spawn_linux.c` (`b60b1d9ec1355f5feab45820aa4b26dabad9ecc0fece9250cc67205187ca1821`), `native/r65_spawn_linux.c` (`571cb37fb28283bc37014a59ca3a4773a12de87f49a720e0f96af81354057c1c`), `native/r55_clock_observer.c` (`799f3ac5d2b98fc1e12345c9214bb5112645c4d6dac280dff203e84b2a00bff2`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Linux namespace/cgroup spawn C kaynakları, Windows fallback mock izolasyonu, watchdog zaman aşımı kuralları; Eksik: Rootless Linux üzerinde cgroup v2 bellek sınırı ve namespace doğrulaması; Henüz bağlanmayan: Canlı OS process controller döngüsü |
| Port bağımlılıkları / görev önkoşulları | MOD-003'ten process binding alır, MOD-005 için sınırlandırılmış pipe/socket açar. Önkoşul: Linux ortamı / C binary derlemesi |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 (Windows'ta Linux testleri SKIP) |
| Açık kusur / engel / gereken somut önkoşul | Windows geliştirme ortamında Linux native syscall/cgroup testleri çalıştırılamıyor (4 test SKIP); Linux derleme ve koşum ortamı gereklidir |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-3 / PH-02 / Linux runner üzerinde r65_spawn_linux derlemesi ve namespace/timeout testi |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; platform kısıtı nedeniyle Windows ortamında atlandı (NOT_RUN / SKIP) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; F05/F07: kaynak hashleri doğrulandı; 4 SKIP rootless/cgroup testleri değil. Native isolation kabulü bu koşumda yapılmadı. |

<a id="mod-005"></a>
### MOD-005 — Engine ve Provider Adapter

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Pinli model/engine bağlantısı, bounded frame transport, provider seçimi |
| Kayıt sahipliği | EngineSession,ModelBinding |
| Referans / önerilen kaynaklar | company_os/engine_bridge.py; company_os/composition.py |
| Yetki sınırı | MOD-006 dışı tool/FS/network yetkisi yok; ücretli otomatik fallback yok |
| Kabul zinciri | BR-002 → AC-002 → TEST-002 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/engine_bridge.py` (`b9b2e9ae7590206dc75ab2a479b11517d046252ec3b81baa42372be89e1b4540`), `company_os/composition.py` (`026263aee062e62def4022c8192461a2e69fceb40e942e8371c94c3e14c73e0f`), `packages/contracts/pilot.py` (`c1c007013487e84bb7f0a7b928e87556cfa5c49b8cc6e1b5b0a57992eabc7b94`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Bounded frame transport, max frame limit, partial write koruması, deadline sarmalaması, model binding şemaları; Eksik: Canlı harici LLM provider (Anthropic, OpenAI, Gemini) adaptörleri (şu an kapalı/yerel); Henüz bağlanmayan: Dış ağa doğrudan erişim (yasak/izole) |
| Port bağımlılıkları / görev önkoşulları | MOD-004 process socket'inden okur/yazar; tool isteklerini MOD-006'ya yönlendirir. Önkoşul: İzole transport kanalı |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Socketpair testlerinden ikisi Windows soket sınırlaması nedeniyle Linux platformuna şartlı (SKIP) |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-4 / PH-02 / Bounded frame transport protokolünün Linux FIFO/socket üzerinde doğrulanması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; birim testlerde mock socket ve frame parser doğrulandı, gerçek model API çağrısı yapılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; F05/F06: socketpair ve pipe/ownership ayrı SKIP; doğrudan egress/paid kapalılığı eksik sayılmamalı. Gerçek model koşumu yok. |

<a id="mod-006"></a>
### MOD-006 — Tool Broker ve Etki Sınırı

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Parse, one-use consume, journal reserve, current guard, tek dosya executor |
| Kayıt sahipliği | ToolRequest,ConsumeIntent,EffectReceipt |
| Referans / önerilen kaynaklar | company_os/tool_broker.py; company_os/tool_executor.py |
| Yetki sınırı | Producer verification.request reddedilir; genel shell pilot scope değildir |
| Kabul zinciri | BR-008 → AC-008 → TEST-008 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/tool_broker.py` (`79e0014e59640b23c2779018ec8efba811b691ce1137a3696bc99ed716632e2d`), `company_os/tool_executor.py` (`871da19150c3a6f4710c8a6978bef51129f11674c02f971b7ff3caa644c2cc5e`), `sql/057_R60_TOOL_NATIVE.sql`, `sql/082_R65_EFFECT_COMPLETE.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Tek kullanımlık token/consume intent doğrulama, journal reserve kontrolü, producer rolünde verifier tool isteklerinin reddi, tek dosya okuma/yazma sınırı; Eksik: Genel shell ve dış ağ broker adaptörleri (tasarım gereği kapalı); Henüz bağlanmayan: E2E pipeline'da gerçek patch staging etkisine bağlama |
| Port bağımlılıkları / görev önkoşulları | MOD-005'ten gelen araç çağrılarını alır; MOD-007 ve MOD-014 ile etkileşir. Önkoşul: MOD-001 yetki epoch'u |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Etki sınırları unit testlerde kanıtlandı; gerçek fs sandbox izolasyonu henüz E2E bağlanmadı |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-5 / PH-02 / Tool request consume ve journal kayıtlarının DB transaction içinde doğrulanması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; birim testler PASS, gerçek FS sandbox E2E çalıştırılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | KISMEN_DOGRULANDI; Hashler ve mevcut Windows regresyonu doğrulandı; tam broker/DB/FS izolasyon AC seti incelenmedi. F06: genel shell/egress kapalılığı eksik değildir. |

<a id="mod-007"></a>
### MOD-007 — Workspace, Patch ve Artifact

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Measured immutable source, CAS head, staging/readback, artifact quarantine ve provenance |
| Kayıt sahipliği | WorkspaceRevision,Patch,Artifact |
| Referans / önerilen kaynaklar | company_os/patch_pipeline.py; packages/contracts/lifecycle.py |
| Yetki sınırı | Verification verdict veya AcceptanceDecision yazamaz |
| Kabul zinciri | BR-009 → AC-009 → TEST-009 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/patch_pipeline.py` (`73f902b0cc0a37b8f4b91aa4a90acbd0dc8540e8502de8ffc5cadd8083e5c79a`), `packages/contracts/lifecycle.py` (`58e9216521829a3e19e585324f6b8c6219799ba2c59094798b5366fd7c63b93f`), `sql/040_R58_PATCH_ACCEPTANCE_NATIVE.sql`, `sql/058_R60_PATCH_EFFECT_OVERLAY.sql`, `sql/081_R65_PATCH_READ.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: CAS tabanlı staging, patch boyutu ve geçersiz UTF-8 kontrolleri, uncommitted transaction engeli, artifact provenance modeli; Eksik: Git/VCS head entegrasyonu; Henüz bağlanmayan: Canlı repository'ye patch merge otomasyonu |
| Port bağımlılıkları / görev önkoşulları | MOD-006'dan artifact alır; MOD-008'e aday kod sunar; MOD-009'a patch staging sağlar. Önkoşul: İmmutable source tree |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Patch staging mekanizması birim testlerde doğrulandı; verifier'a aktarımı test pipeline seviyesinde hazır |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-6 / PH-03 / Aday kodun CAS staging'e alınması ve readback hash doğrulaması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; test_pipeline.py unit testleri PASS, repo bazlı kalıcı staging çalıştırılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | KISMEN_DOGRULANDI; Hashler ve mevcut Windows regresyonu doğrulandı; canlı CAS/immutable artifact/bağımsız readback kabulü bu tur yok. |

<a id="mod-008"></a>
### MOD-008 — Bağımsız Verifier

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Ayrı principal/process/key, hidden fixture, exact candidate test, imzalı receipt |
| Kayıt sahipliği | VerificationRun,VerifierReceipt,SignerEnrollment |
| Referans / önerilen kaynaklar | packages/contracts/execution.py; packages/contracts/lifecycle.py |
| Yetki sınırı | Producer/QA implementasyonunu oracle diye import etmez; release yetkisi yok |
| Kabul zinciri | BR-010 → AC-010 → TEST-010 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/verifier_runner.py` (`35a9eb63a7d73ede86c0f68de37e5dcf68505a667ce1885537be6a1a5c3f8aeb`: `run_title_oracle`, `IndependentVerificationPipeline`), `company_os/candidate_runner.py` (`81842ea2f902b0e44099cc0fc3c22943e48ee158d58be44d8e72f52c20e26a86`), `packages/contracts/lifecycle.py` (`58e9216521829a3e19e585324f6b8c6219799ba2c59094798b5366fd7c63b93f`), `fixtures/mgt01/verifier/check_title.py`, `fixtures/mgt01/verifier/reference_title.py`, `company_os/candidate_runner.py` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Ayrı process/harness yürütümü, sahte exit code ve sahte stdout manipülasyonunun engellenmesi (P0-1 kısmen), 13 case doğrulama, baseline FAIL (5 case) ve mutant FAIL doğrulaması, verifier receipt imzası; Eksik: Donanımsal/sertifikalı bağımsız verifier anahtar altyapısı; Henüz bağlanmayan: Canlı OS seviyesinde cgroup/subsecond timeout izolasyonu |
| Port bağımlılıkları / görev önkoşulları | MOD-007'den staged patch alır; MOD-009'a imzalı VerifierReceipt sunar. Önkoşul: Hidden fixture ve izole verifier kimliği |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Codex bulgusu P0-1: subprocess oracle çalıştırmasında aday kodun stdout manipülasyonu ve erken exit riski verifier_runner'da sertleştirildi; tam OS-level timeout ve cgroup kısıtı eklenecek |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P0-1 / PH-03 / Subprocess izolasyonunun streaming byte limit ve bağımsız harness rapor kanalı ile tam mühürlenmesi |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; test_verifier_runner.py PASS (baseline FAIL, valid candidate PASS 13, mutant FAIL), gerçek DB/OS koşumu (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; R2-01..03: eski vektör FAIL, fakat CASES okuyan/protokol taklit eden fonksiyonsuz aday PASS13; pinlenmemiş oracle PASS13; READY timeout aşımı; stale hash. |

<a id="mod-009"></a>
### MOD-009 — Acceptance ve Release Kontrolü

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Güncel evidence/policy/source ile kabul; iptal ve effects reconciliation |
| Kayıt sahipliği | AcceptanceDecision,ReleaseDecision |
| Referans / önerilen kaynaklar | company_os/command_host.py; sql/assembly.json |
| Yetki sınırı | PASS otomatik müşteri/PROD kabulü değildir; tek domain-state owner MOD-001 |
| Kabul zinciri | BR-011 → AC-011 → TEST-011 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `company_os/command_host.py` (`a817f776cc3d241aaff29a54428fd934191fe84ce915531f3b905154d332176c`), `packages/contracts/lifecycle.py` (`58e9216521829a3e19e585324f6b8c6219799ba2c59094798b5366fd7c63b93f`), `sql/040_R58_PATCH_ACCEPTANCE_NATIVE.sql`, `sql/041_R58_STOP_RELEASE_NATIVE.sql`, `sql/060_R60_STOP_RECONCILIATION_OVERLAY.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Acceptance/Release şemaları, geçersiz veya eksik verifier receipt durumunda ret, insan onayı olmadan PROD release'in bloklanması; Eksik: İki taraflı insan onayı (dual custody) arayüzü; Henüz bağlanmayan: Gerçek müşteri teslim ortamına release hook'u |
| Port bağımlılıkları / görev önkoşulları | MOD-008 verifier receipt'ini alır; MOD-001 üzerinden AcceptanceDecision yazar. Önkoşul: Bağımsız verifier doğrulaması |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | G0 ve MGT-01 First13 insan kabulü 23 Kasım kaydında tamamlandı. Ek iş türleri için teknik doğrulama ve ilgili kabul açık. |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-7 / PH-03 / Verifier receipt ile AcceptanceDecision kaydının MOD-001 üzerinden mühürlenmesi |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; birim testlerde kabul mantığı PASS, operasyonel release koşumu yok (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; R2-01/02/04: verifier sahte PASS açık, acceptance kabulü yok; kaynaklanmamış dual custody şartı duruyor. |

<a id="mod-010"></a>
### MOD-010 — Event ve Projection

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Committed event tüketimi, scoped read model, snapshot/cursor, dedup/resync |
| Kayıt sahipliği | ProjectionCheckpoint,ReadModelCache |
| Referans / önerilen kaynaklar | packages/contracts/models.py; ÖNERİLEN company_os/projections.py |
| Yetki sınırı | Domain tablosuna writer değildir; auth kararını cache’ten vermez |
| Kabul zinciri | BR-013 → AC-013 → TEST-013 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `packages/contracts/models.py` (`7a1567f63ce359632fc234d1aa4e43f090a02b03f6cf893184347de11db8e466`: Event modelleri), `presentation/app.py` (`6cf0f6f9fe5130b66f1e11192fae847a89ae0356bdac2df9466d9fbb21de3d92`: read model ve event projeksiyonu), `sql/020_R55_RECEIPT_EVENT_NATIVE_CANDIDATES.sql`, `sql/074_R64_EVENT_MAP.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Event mapping, read-only projeksiyon sözlüğü, snapshot oluşturma, idempotent replay mantığı; Eksik: Ayrı arka plan projeksiyon daemonu (`company_os/projections.py`); Henüz bağlanmayan: Canlı SSE/WebSocket akışı |
| Port bağımlılıkları / görev önkoşulları | MOD-001'in outbox/event tablosundan okur; MOD-011'e read model sağlar. Önkoşul: Committed domain transaction |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Bağımsız company_os/projections.py dosyası henüz açılmadı; mantık şu anda presentation/app.py ve SQL event map içinde yer alıyor |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P2-MOD010 / PH-04 / company_os/projections.py modülünün bağımsız checkpoint/resync servisi olarak ayrıştırılması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; test_presentation.py içinde projeksiyon testi PASS, DB event stream çalıştırılmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; F05: presentation.app içinde consumer/checkpoint/dedup/resync uygulanmış olduğu gösterilmedi. SQL event mapping gerçek stream testi değil. |

<a id="mod-011"></a>
### MOD-011 — Yönetim ve Ofis Sunumu

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Hedef/iş/kanıt/karar/incident ekranları, erişilebilir liste, opsiyonel ofis renderer |
| Kayıt sahipliği | Yalnız UI preferences ve selection |
| Referans / önerilen kaynaklar | ÖNERİLEN presentation/; compatibility/prototype yalnız referans |
| Yetki sınırı | Task/lease/grant/verification yazmaz; UI animasyonu kanıt sayılmaz |
| Kabul zinciri | BR-014 → AC-014 → TEST-014 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `presentation/app.py` (`6cf0f6f9fe5130b66f1e11192fae847a89ae0356bdac2df9466d9fbb21de3d92`), `presentation/__init__.py` (`971df670b6ad24a32fa587f39cdd1ec9f2b32ebf0dbd95f255e5965c1977fd85`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: ReadConn/ReadCursor üzerinden committed PostgreSQL readback görünümü, stale digest durumunda Blocked istisnası, statik HTML tablo sunumu; Eksik: Canlı HTTP/WSGI sunucusu ve tarayıcı oturumu; Henüz bağlanmayan: 401/403/409 HTTP yanıt kodları (doğrudan Python fonksiyon çağrısı ile test ediliyor) |
| Port bağımlılıkları / görev önkoşulları | MOD-010'dan read model okur; yetkili komutları MOD-001'e iletir. Önkoşul: MOD-010 projeksiyonu ve auth token |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | UI animasyonları kanıt sayılmaz kuralı gereği yalnız salt okunur veri sunumu ve yetki doğrulaması test edildi |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-8 / PH-04 / Read model üzerinden kalıcı reload ve yetkili komut iletiminin doğrulanması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; test_presentation.py birim testleri PASS, gerçek tarayıcı/HTTP oturumu (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; R2-04/05: preview sabit iddialar gösteriyor, matris okunmuyor; HTTP/ASGI kart iddiaları sürüyor. Görsel denetim NOT_VERIFIED. |

<a id="mod-012"></a>
### MOD-012 — Katalog ve Hafıza

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Role/Skill/Tool/Model metadata, kaynak lisansı, tenant ACL/provenance retrieval ve promotion candidate |
| Kayıt sahipliği | CatalogVersion,KnowledgeRecord,PromotionCandidate |
| Referans / önerilen kaynaklar | packages/contracts/company.py; ÖNERİLEN company_os/knowledge.py |
| Yetki sınırı | Grant MOD-001; promotion kendi başına yetki/skill activation vermez |
| Kabul zinciri | BR-015 → AC-015 → TEST-015; BR-016 → AC-016 → TEST-016 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `packages/contracts/company.py` (`11aa436748f3efe44101ac607aeffdbba3f7e3c00c3244a7c64394d45d2778ac`: Role/Skill/Catalog modelleri), `config/registry-decisions.json` (`e668062064bec25d8f915ae1e90a437fa60d0977d4736c438a3a3b682350bf16`), `sql/035_R58_OPERATION_REGISTRY.sql`, `sql/048_R60_OPERATION_REGISTRY.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Katalog versiyonlama şeması, 19 rol registry kararları, promotion adayı veri tipleri; Eksik: Vektörel/semantik hafıza arama motoru (`company_os/knowledge.py`), tenant bazlı ACL filtresi; Henüz bağlanmayan: Çalışan ajanların tecrübe promosyon döngüsü |
| Port bağımlılıkları / görev önkoşulları | MOD-001 üzerinden yetki alır; MOD-003 qualification sürecine katalog pini sağlar. Önkoşul: Sabit katalog registry |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Bağımsız knowledge/hafıza servisi henüz kodlanmadı; şema ve sabit registry tanımları mevcut |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P2-MOD012 / PH-06 / company_os/knowledge.py oluşturulması ve katalog lisans/provenance denetiminin eklenmesi |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; test_registry_preflight.py PASS, canlı hafıza sorgulaması yok (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; F04/F06/F07: operation registry ile skill/role katalog ve tenant hafıza kabulü ayrılmalı; ayrı knowledge servisi zorunluluğu kaynaklanmamış. |

<a id="mod-013"></a>
### MOD-013 — WorkType Uygulamaları

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | SOFTWARE ilk fixture; Research/Spreadsheet/Obligation sonraki ayrı capability ve oracle’lar |
| Kayıt sahipliği | WorkTypeDefinition,JobInput,JobOutput; domain-specific staging |
| Referans / önerilen kaynaklar | packages/contracts/company.py; fixtures/mgt01/ |
| Yetki sınırı | Yeni iş türü first13’ü kapatmaz; aynı tool ve evidence sınırları kullanılır |
| Kabul zinciri | BR-019 → AC-019 → TEST-019; BR-020 → AC-020 → TEST-020; BR-021 → AC-021 → TEST-021 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `packages/contracts/company.py` (`11aa436748f3efe44101ac607aeffdbba3f7e3c00c3244a7c64394d45d2778ac`), `fixtures/mgt01/producer/task_title.py` (`3c73b549cc4e91b4aa377f12ad5186907173e9ec6f9c7a10013164237d4cda06`), `fixtures/mgt01/verifier/reference_title.py` (`22e257e824e2de04b95b6d80f30b6fd736be9cae03c1692b2da93531e1edce84`), `fixtures/mgt01/verifier/check_title.py` (`f43559258b69a6e0a502def4475d0ebd8832de8c185d3bb8ab841bc91d3e6c75`); mutant ve sahte adaylar dinamik test ortamında üretilir (`tests/unit/test_verifier_runner.py`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: SOFTWARE iş türü için MGT-TITLE-NORMALIZATION-01 fixture ve oracle seti, 13 test senaryosu ve mutasyon testleri; Eksik: Research, Spreadsheet, Obligation iş türleri (PH-06 kapsamı); Henüz bağlanmayan: Dinamik worktype dispatch motoru |
| Port bağımlılıkları / görev önkoşulları | MOD-002 planındaki task türüyle tetiklenir; MOD-007 ve MOD-008 ile yürütülür. Önkoşul: İzole fixture verileri |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Yalnız SOFTWARE MGT01 hazır; diğer iş türleri (Research, Spreadsheet vb.) mimari faz sırasına göre PH-06 geliştirme kuyruğundadır |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P1-9 / PH-06 / SOFTWARE MGT01 akışının ara kabulü sonrası diğer work type tanımlarının açılması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; MGT01 senaryoları unit test düzeyinde PASS, canlı worker üzerinde (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; F02 dört hatalı fixture yolu giderildi; yalnız yol doğrulandı. F03 açık; PH06 kapsam dışı ifadesi sürüyor. |

<a id="mod-014"></a>
### MOD-014 — Bütçe, Ticari Kayıt ve Dış Etki

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Usage/reserve/settlement, effect/provider capability, ticari taslak ve mutabakat |
| Kayıt sahipliği | BudgetReservation,UsageEntry,EffectIntent,CommercialReceipt |
| Referans / önerilen kaynaklar | packages/contracts/company.py; packages/contracts/execution.py; ÖNERİLEN company_os/effects.py |
| Yetki sınırı | Runtime/finans command’leri MOD-001; provider çağrısı DB transaction dışında |
| Kabul zinciri | BR-017 → AC-017 → TEST-017; BR-018 → AC-018 → TEST-018 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `packages/contracts/company.py` (`11aa436748f3efe44101ac607aeffdbba3f7e3c00c3244a7c64394d45d2778ac`), `packages/contracts/execution.py` (`0ebc384cc3e58b4552d274b82f7a954eed84e9ea0ca19226e9bdaf3fa4620cd7`), `sql/058_R60_PATCH_EFFECT_OVERLAY.sql`, `sql/082_R65_EFFECT_COMPLETE.sql` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Bütçe rezervasyon şeması, token ve maliyet muhasebesi veri yapıları, iki aşamalı etki tamamlama kuralı; Eksik: Canlı ödeme/faturalandırma entegrasyonu (`company_os/effects.py`); Henüz bağlanmayan: Harici ücretli API çağrıları (tasarım gereği kapalı) |
| Port bağımlılıkları / görev önkoşulları | MOD-001 üzerinden finansal komutlar alır; MOD-006 araç çalıştırma öncesi rezervasyon arar. Önkoşul: Bütçe limiti tanımı |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Otomatik ücretli fallback ve harici faturalandırma kapalıdır; bütçe aşımında iş reddi kuralı şemada mevcuttur |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P2-MOD014 / PH-05 / company_os/effects.py oluşturulması ve iki aşamalı commit mutabakatının testi |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; şema ve birim testler PASS, canlı ticari etki oluşturulmadı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | KISMEN_DOGRULANDI; Dosya/hash ve sözleşme varlığı doğrulandı; rezervasyon/UNKNOWN/ticari AC seti bağımsız test edilmedi. Paid kapalılığı eksik değildir; F04/F07. |

<a id="mod-015"></a>
### MOD-015 — Operasyon, Recovery ve Backup

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Config/environment, build pin, fenced startup/restore, incident, backup ve stop doğrulama |
| Kayıt sahipliği | EnvironmentProfile,RestoreCase,Incident,BackupManifest |
| Referans / önerilen kaynaklar | tools/history_store.py; ÖNERİLEN operasyon runbook’ları |
| Yetki sınırı | Arşiv bağımsız backup sayılmaz; restore eski yetkiyi aktive etmez |
| Kabul zinciri | BR-022 → AC-022 → TEST-022; BR-027 → AC-027 → TEST-027 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `sql/041_R58_STOP_RELEASE_NATIVE.sql`, `sql/059_R60_LEASE_RECOVERY_NATIVE.sql`, `sql/060_R60_STOP_RECONCILIATION_OVERLAY.sql`, `tools/disposable_compile_trial.py` (`1aad97347b46d6b50a6020e89837d1a739eff4be1a9bdb85ef9bf3750f57debb`), `tools/disposable_bootstrap_commit_trial.py` (`ebd5a5f55c1fd34c672a2c716a4f76b77881bfa0afbe8f9704cfdc7f265b152e`) |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Disposable DB sıfırlama ve compile betikleri, stop reconciliation SQL overlay, lease recovery kuralları; Eksik: Automated point-in-time recovery runbook'u ve bağımsız witness backup mekanizması; Henüz bağlanmayan: Felaket kurtarma tatbikatı |
| Port bağımlılıkları / görev önkoşulları | MOD-001 operasyonel komutları ve DB snapshot altyapısına bağımlıdır. Önkoşul: Disposable DB ve migration scriptleri |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | Geri yüklenen veride eski yetkilerin canlanmaması kuralı SQL katmanında tanımlı; operasyonel felaket tatbikatı henüz yapılmadı |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P2-MOD015 / PH-05 / Automated backup manifest doğrulama ve fenced restore test senaryolarının yazılması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; derleme ve şema denemeleri PASS, tam restore tatbikatı (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-01 / Antigravity matris girdisi `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`; uygulama pinleri evidence/CODEX_MATRIS_KONTROL_20261110.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | KISMEN_DOGRULANDI; Dosya/hash varlığı doğrulandı; gerçek fenced restore/witness/backup/stop kabulü bu tur yok; F04/F07 görev detayları gerekli. |

<a id="mod-016"></a>
### MOD-016 — Teslimat, ADR ve Kalite Yönetişimi

| Mimari alan | Kaynakta tanımlanan |
|---|---|
| Tam kapsam | Kaynak/karar/REQ/AC/TEST bağları, ajan görev sınırı, doküman doğrulama, release manifest |
| Kayıt sahipliği | ADR,TaskSpec,TestEvidence,SourceManifest |
| Referans / önerilen kaynaklar | tools/; dokumanlar/; DOGRULA.py |
| Yetki sınırı | Teknik doğrulama insan onayı değildir; secret veya fabricated PASS kaydetmez |
| Kabul zinciri | BR-003 → AC-003 → TEST-003; BR-023 → AC-023 → TEST-023; BR-024 → AC-024 → TEST-024; BR-025 → AC-025 → TEST-025; BR-026 → AC-026 → TEST-026 |

| Güncellenecek alan | Değer / sorumlu |
|---|---|
| Antigravity bildirim tarihi / kaynak revizyonu | 2026-11-10 / AiProjeOfisi (v0.16.2-r68 uyarlaması) |
| Gerçek uygulama dosyaları / semboller / SHA256 | `tools/verify_source.py` (`8dd031cf91a701d5c714dddbcf9bd6ea1f692109544d20fce2b21036580610e5`), `packages/workspace_manifest.py` (`a579d27541d9`), `tests/security/test_sql_source.py` (`0fb2df3afdecf09157a8e4e1a677bcd623e5c8667fe597a0e3fab1df411a8f32`), `UYGULAMA_DURUM_MATRISI.md`, `PLAN.md` |
| Alt davranışlar: uygulanan / eksik / henüz bağlanmayan | Uygulanan: Statik kaynak doğrulama, SQL source immutability ve trigger güvenlik testleri, matris takibi ve TaskSpec entegrasyonu; Eksik: CI/CD ortamında otomatik release manifest mühürleme; Henüz bağlanmayan: Otomatik paket imzalama HSM'i |
| Port bağımlılıkları / görev önkoşulları | Tüm modüllerin teslim, test ve dokümantasyon izlenebilirliğini denetler. Önkoşul: Sabit SHA256 kaynak manifestosu |
| Antigravity durumu / kanıt sınıfı / kanıt ID | KISMEN/KAYNAK_HAZIR / UNIT, SOURCE_STATIC / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| Açık kusur / engel / gereken somut önkoşul | GUNCEL/DOGRULA.py kök düzeyinde CALISMA_DURUMU.md hash uyuşmazlığı nedeniyle hata vermektedir (A tabanı sabit pini). AiProjeOfisi iç testleri 85 PASS, 4 SKIP vermektedir |
| Sıradaki görev / faz / çıkış ölçütü | TASK-20261110-P2-MOD016 / PH-00, PH-03 / İzlenebilirlik matrisinin Codex bağımsız incelemesiyle senkron tutulması |
| Gerçek test ortamı / pozitif / negatif / kalıcı readback | NOT_VERIFIED; test_sql_source.py PASS, release audit (NOT_RUN) |
| İnsan kabulü / karar kaydı | NOT_VERIFIED; proje sahibi onayı bekleniyor |
| Codex kontrol tarihi / kontrol ID / incelenen pin | 2026-11-10 / CODEX-20261110-MATRIS-02 / matris girdisi c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e; source pinleri evidence/CODEX_MATRIS_KONTROL_20261110_02.json |
| Codex sonucu / doğrulanan kapsam / kalan bulgu | DUZELTME_GEREKLI; R2-04/06: kanıt/görev/AC-test izleri eksik; DOGRULA exit1 sürüyor. Windows85PASS4SKIP97subtest tekrarlandı. |

## 6. Kanıt, görev ve kontrol kayıtları

Her anlamlı teslimde ana satır, modül kartı ve aşağıdaki kayıtlar birlikte güncellenir. Eski kanıt silinmez; yeni kayıt önceki IDyi referans verir. Aynı dosyada eşzamanlı yazma yapma; düzenlemeden hemen önce yeniden oku ve beklenen hash ile karşılaştır.

| Kanıt ID | MOD / PH / AC / TEST | Ajan / tarih | Sınıf / ortam | Source-build-config-fixture pinleri | Exact komut / exit / beklenen-gerçek sonuç | Ham kanıt yolu / SHA256 | Sınır / eski kanıt ID |
|---|---|---|---|---|---|---|---|
| EV-20261110-SRC-01 | MOD-001..MOD-016 / PH-00 | Antigravity / 2026-11-10 | SOURCE_STATIC / Windows (Python 3.14.3) | AiProjeOfisi kökünde yer alan 40+ kaynak dosya hashleri | `C:\Python314\python.exe AiProjeOfisi/tools/verify_source.py` / exit 0 / 16 modül kaynak dosyaları ve sözleşmeleri doğrulandı | `AiProjeOfisi/module-map.json` / `bd5ca2ece93d11f064050a9a89d8cd64b955c8781ab02254ee32df91ed967cf5` | Statik dosya ve sembol varlığı; runtime kabulü değildir |
| EV-20261110-UNIT-01 | MOD-001..MOD-016 / PH-01..PH-04 | Antigravity / 2026-11-10 | UNIT / Windows (Python 3.14.3) | pytest 9.0.2 / AiProjeOfisi test suite | `C:\Python314\python.exe -m pytest AiProjeOfisi/tests -v` / exit 0 / 85 passed, 4 skipped, 97 subtests passed in 0.64s | `AiProjeOfisi/tests/` / 17 test dosyası SHA256 eşleşmeleri | 4 test Linux platform bağımlılığı (socketpair, FIFO, fd/owner) nedeniyle atlandı (SKIP); gerçek runtime izni değildir |
| EV-20261110-UNIT-02 | MOD-008, MOD-013 / PH-03 | Antigravity / 2026-11-10 | UNIT / Windows (Python 3.14.3) | `company_os/verifier_runner.py`, `candidate_runner.py` | `C:\Python314\python.exe -m pytest AiProjeOfisi/tests/unit/test_verifier_runner.py -v` / exit 0 / 7 passed in 3.43s | `AiProjeOfisi/tests/unit/test_verifier_runner.py` / `b28fdb9e0835019e84cf1626e155d1553d4464bf047b07ad8df50f4cea82a642` | R2-01 (izole sys.path), R2-02 (enrolled oracle pin) ve R2-03 (deadline timeout) testleri mühürlendi; 7/7 PASS |
| EV-20261110-V1-PREVIEW | MOD-011 / PH-04 | Antigravity / 2026-11-10 | SYNTHETIC_UI / Headless Chromium (Playwright) | `presentation/preview_generator.py`, `presentation/preview.html` | Playwright 1280x800 ve 375x812 render / exit 0 / 2 ekran görüntüsü alındı | `preview_desktop.png` (`7fb6e08...`), `preview_mobile.png` (`f51aed5...`) | Dinamik matris ayrıştırma, masaüstü/mobil taşmasız görsel denetim; G0 OPEN ve first13 0/13 ayrı gösterildi |
| EV-20261108-SYNTH-01 | MOD-001 / PH-01 / AC-004 | Codex (tarihsel) / 2026-11-08 | SYNTHETIC_NATIVE / Linux | NATIVE_CLOCK_TRIAL_a20c6386.json | clock trial bootstrap/session sentetik commit / exit 0 | `evidence/NATIVE_CLOCK_TRIAL_a20c6386.json` / `d8ef1d31dfaed997c9ab2c89ae4a184000704bfe326510c04d8f06d036f74887` | REPORTED_NOT_RETESTED; sentetik testtir, tam E2E veya G0 kabulü değildir |

| Görev ID | MOD / faz | Davranış / eksik AC | Bağımlılık / allowlist + başlangıç hashleri | Çıkış / negatif / rollback | Durum / kanıt ID |
|---|---|---|---|---|---|
| TASK-20261110-MATRIS-01 | MOD-001..MOD-016 / PH-00..PH-06 | 16 modülün tamamının gerçek kaynak envanteri ve durum matrisinin doldurulması | UYGULAMA_DURUM_MATRISI.md, module-map.json, company_os/, packages/ | Eksiksiz doldurma / Codex alanlarını değiştirmeme / geriye dönük hash kontrolü | KISMEN_TAMAMLANDI / EV-20261110-SRC-01, EV-20261110-UNIT-01 |
| TASK-20261110-P0-1 | MOD-008, MOD-013 / PH-03 | Verifier false-pass açığının streaming byte limit, izole runner ve enrolled oracle pini ile kapatılması (R2-01, R2-02, R2-03) | `company_os/verifier_runner.py`, `company_os/candidate_runner.py`, `fixtures/mgt01/` | Sahte stdout, CASES okuma teşebbüsü ve timeout mutantlarının FAIL alması | TAMAMLANDI / EV-20261110-UNIT-02 |
| TASK-20261110-P0-2 | MOD-001, MOD-015 / PH-01 | tools/disposable_e2e_workflow_trial.py import ve constructor kablolamasının güncellenmesi | 	ools/disposable_e2e_workflow_trial.py, company_os/constructors.py, company_os/*.py | Preflight import check exit 0 / DB başlatmadan doğrulama | TAMAMLANDI / EV-20261110-E2E-PREFLIGHT |
| TASK-20261110-V1-UI | MOD-010, MOD-011 / PH-04 | Dinamik matris ayrıştırmalı V1 durum paneli ve erişilebilir HTML arayüz üretimi | `presentation/preview_generator.py`, `presentation/preview.html` | Matris SHA256 pini ile senkron durum sunumu / disabled işlem butonları | TAMAMLANDI / EV-20261110-V1-PREVIEW |
| TASK-20261110-PH05-OP | MOD-014, MOD-015 / PH-05 | Recovery runbook ve backup manifest mühürleme testleri | `tools/disposable_compile_trial.py`, `sql/059_R60_LEASE_RECOVERY_NATIVE.sql` | Eski yetkilerin dirilmemesi / point-in-time kurtarma | KUYRUKTA_BEKLIYOR / — |
| TASK-20261110-PH06-EXP | MOD-012, MOD-013 / PH-06 | WorkType genişlemesi (Research, Spreadsheet) ve dinamik katalog hafıza modelleri | `packages/contracts/company.py`, `config/registry-decisions.json` | İzole fixture'dan bağımsız kabul / tenant ACL doğrulaması | KUYRUKTA_BEKLIYOR / — |

Her görev §28 TaskSpec alanlarını içerir. Buradaki özet allowlist, BR/REQ/AC/TEST, kapsam ve geri alma ayrıntılarını taşıyan görev dosyasına bağlanabilir. Mevcut verifier ve E2E kusur iddiaları son görev paketinden alınır; bu hazırlıkta yeniden test edilmedi. Önce güncel kod ve negatif test ile durumlarını belirle; kapanmış işi tekrar açma veya kanıtsız kapatma.

| Kontrol ID | Tarih / Codex | MOD / kanıt ID / kontrol edilen pin | Yapılan bağımsız kontrol | Sonuç / bulgu / sınırlama |
|---|---|---|---|---|
| CODEX-20261110-MATRIS-01 | 2026-11-10 / Codex | MOD-001..016; girdinin SHA256si `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6` | Windows pytest tekrarlandı; dosya/hash/AST denetimi; kontrollü candidate false-pass; A DOGRULA | DUZELTME_GEREKLI; F01..F08; [rapor](CODEX_MATRIS_KONTROL_20261110.md), [kanıt](evidence/CODEX_MATRIS_KONTROL_20261110.json). Runtime/insan kabulü yok |

## 7. Antigravity teslim talimatı

1. Kök ve uygulama AGENTS.md, güncel mimari ve son ekleri oku. Bu tablodaki 16 modülün her biri için gerçek dosya/sembol envanteri çıkar. Eski module-map.json veya implementation_status.json etiketlerini incelemeden devralma.
2. Her modül kartını doldur; her AC için uygulanan ve eksik davranışı ayır. Yokluğu doğrulanmadan UYGULANMADI, yalnız dosya var diye KAYNAK_HAZIR yazma.
3. Ana tablo ve faz durumlarını kartlardaki kanıtlara bağla. PH-05/06 ve tam modül kapsamını görev kuyruğunda tut. İlk akış engellerini bağımlılık sırasıyla bu planın içinde çöz.
4. §28 TaskSpec ile görev paketlerini oluştur ve mevcut yetki kapsamında geliştir. Gerekli runtime yetkisi eksikse somut engeli kaydet; bağımsız kaynak işlerini sürdür. Oracle/AC/gate gevşetme.
5. Her teslimde değişen dosyalar, testlerin exact komut/exit sonuçları, pozitif/negatif/raw kanıt ve kaynak pinlerini ver. Codex alanlarını değiştirme; teslimi REVIEW_REQUIRED olarak sun.
6. Codex bu dosyayı ve teslim edilen diff/ham kanıtı okuyup ilgili testleri bağımsız kontrol eder; sonucu yalnız kontrol ettiği kapsam ve pin için yazar. Kullanıcı ayrıca gerçek insan kabulünü verir.
7. Sonraki paket önceki Codex bulgularını durum/kanıt ID ile ele alır; tam 16 modül görünürlüğünü korur. Güncelleme veya kontrol arka planda otomatik yapılmış sayılmaz.

## 8. Teslim özeti şablonu

```text
Teslim / tarih / source pin:
Değişen modüller ve tam kapsamdaki etkisi:
16 modül durum dağılımı (belirlenmeyenler dahil):
Faz ilerlemesi / ilk akış / sonraki fazlar:
Giderilen kusurlar ve negatif kanıt IDleri:
Çalıştırılan testler / çalıştırılmayanlar / skip:
Runtime ve insan kabul sınırları:
Açık engeller ve sıradaki bağımlı/bağımsız görevler:
Codex incelemesine sunulan kanıt IDleri:
Memory checkpoint / yerel kayıt / aktarım durumu:
```


## 9. Codex bağımsız kontrolü — 2026-11-10

Antigravity bildirimleri tarihsel teslim iddiası olarak korundu. Çelişen iddialar için Codex kart alanları ve [F01..F08 raporu](CODEX_MATRIS_KONTROL_20261110.md) geçerli inceleme sonucudur. 85 PASS / 4 SKIP / 97 subtest bağımsız tekrarlandı; bu 16 modülün bütün AC setlerinin doğrulandığı anlamına gelmez. Verifier false-pass yeniden üretildi, yanlış sembol/fixture/test kapsamı ve eksik görev/kanıt izleri bulundu. Envanter görevi bağımsız kabul açısından açık; Antigravity TAMAMLANDI etiketi kabul edilmedi.

[Sonraki tam kapsam geliştirme ve görünür sürüm görev paketi](ANTIGRAVITY_KONTROL_SONRASI_GOREV_20261110.md): matris düzeltmesi, mevcut panellerin görsel denetimi, V1 görünür panel/V2 gerçek çalışan akışın kalan işleri ve kanıta dayalı süre değerlendirmesi birlikte istenir. PH-05/06 kapsamda korunur. Arka plan kontrolü veya görev gönderimi yapılmadı.

## 10. Codex ikinci teslim kontrolü — 2026-11-10

[İkinci rapor](CODEX_MATRIS_KONTROL_20261110_02.md) ve [kanıt](evidence/CODEX_MATRIS_KONTROL_20261110_02.json). CODEX-20261110-MATRIS-02: DUZELTME_GEREKLI. F01 kısmen, F02 yalnız yol düzeltmesi doğrulandı; F03 açık; F04..F08 kapanmadı. Windows85PASS/4SKIP/97subtest tekrarlandı. Runtime/insan kabulü yok; görsel NOT_VERIFIED. Önceki kontrol kaydı eski pin/kapsamıyla korunur.


## 10. Codex kaynak uygulaması — 2026-11-11

Kontrol/uygulama ID: CODEX-20261111-IMPL-01. [Paket, TaskSpec ve kanıtlar](CODEX_UYGULAMA_20261111.md). Bu tarihli ek önceki TAMAMLANDI iddialarının güncel dispositionıdır; tarihsel alanlar silinmedi. Bu paketin yazarı kendi testini raporluyor; ayrı bağımsız kabul yoktur.

| Alan | Güncel kanıt düzeyi / kalan |
|---|---|
| MOD-008/009; TASK-20261110-P0-1 | KISMEN/KAYNAK_HAZIR: kaynak testi ile runtime ayrıldı, SOURCE_TEST kabulden önce reddedilir, deadline/byte/protokol negatifleri PASS. Gerçek ayrı OS kimliği/fixture izolasyonu ve enrolled receipt validator ACIK. Aynı kimlikle dosya okuma gizliliği kapanmış sayılmaz. |
| MOD-001; consent/secret sınırı | KISMEN/KAYNAK_HAZIR: path bypass ve varsayılan UID kaldırıldı; consent expected workspace/root/human kontrollerine bağlandı. Linux fd/owner/custody actual kabulü yok; E2E caller wiring açık. |
| MOD-015/016; TASK-20261110-P0-2 | ONKONTROL_KAYNAK_HAZIR: 43 doğrudan çağrı kontrolünde17uyuşmazlık,1dinamik çağrı atlandı. Wrapper ortam kurmadan exit2 BLOCKED. Hatalı çağrılar düzeltilmiş veya gerçek E2E tamamlanmış değildir. |
| EV-CODEX-20261111-UNIT | Windows104PASS4SKIP105subtest; ham log evidence/CODEX_UYGULAMA_20261111_pytest.log, komut/exit/hash evidence/CODEX_UYGULAMA_20261111_CHECKS.json. DörtSKIP socketpair/FIFO/ikiLinuxsecret; cgroup kabulü değil. |
| F08 / A doğrulaması | ACIK: GUNCEL/DOGRULA.py exit1 CALISMA_DURUMU.md hash uyuşmazlığı; ham log evidence/CODEX_UYGULAMA_20261111_A_DOGRULA.log. Manifest değiştirilmedi. |
| V1/V2 ve tam kapsam | V1 görsel denetimi bu pakette yok. V2 runtime NOT_RUN, G0OPEN,first130/13; PH05/06 ve16modül kapsamda. |

Bu ekten önceki MOD-008/009 kaynak pinleri ve Codex kontrolleri değişen dosyalar için tarihsel/STALE kabul edilir. Yeni kaynak pinleri evidence/CODEX_UYGULAMA_20261111_MANIFEST.json; başlangıç pinleri BASE.json. Modülün bütün AC seti bu alt kapsam testleriyle DOGRULANDI sayılmaz.


## 11. Kanonik pilot bağlantısı — 2026-11-11 / dilim02

Kaynak uygulama ID: CODEX-PILOT-20261111-02; [TaskSpec ve detay](CODEX_PILOT_BAGLANTISI_20261111_02.md). Bu ek önceki kaynak pinleri için tarihli ilerlemedir; bağımsız review veya insan kabulü değildir.

| Modül / görev | Güncel alt kapsam / kalan |
|---|---|
| MOD004/005/006/007; TASK-CODEX-20261111-04 | KISMEN/KAYNAK_HAZIR: launcher parent pipe→PilotSession ve producer→Broker→effect COMMIT→patch receipt→current reply guard bağlantısı kaynakta uygulanıp DB/OS doubles ile test edildi. Actual worker/DB/model kabulü yok. |
| MOD003/015; lease/stop/cleanup | KISMEN/KAYNAK_HAZIR: process/attempt/fence lease bağı, identity değişimi/expiry ret; setup/run/cancel cleanup; failed stop tekrarda sessiz başarı değil. Gerçek cgroup/pidfd/quiescence/settlement ve restore açık. |
| MOD007→MOD008 | Exact commit-confirmed patch receipt/export var; verification NOT_RUN, quiescence NOT_OBSERVED. Receipt kopyası current DB readback veya bağımsız verifier yerine geçmez. |
| EV-CODEX-PILOT-20261111-02 | Windows121PASS4SKIP112subtest; evidence/CODEX_PILOT_20261111_02_pytest_FINAL.log ve FINAL_CHECK.json; yeni kaynak pinleri MANIFEST.json, başlangıç byte yedekleri BACKUP/ ve BASE.json. |
| Eski P0-2 / E2E | ACIK: final preflight43çağrı/17uyuşmazlık; custom trial wiring henüz canonical porta taşınmadı. Wrapperın ortam öncesi ret kapısı korunuyor. |
| Tam kapsam ve kapılar | 16MOD/PH00–06 korunur. MOD008actual validator/isolation, MOD010/011UI/reload, PH05restore/ticari ve PH06WorkType/hafıza açık. G0OPEN,first130/13,runtimeNOT_RUN. A doğrulaması bu dilimde REPORTED_NOT_RETESTED; önceki hash hatası açık. |


## 12. Üç eksende ilerleme takibi — 2026-11-12

Kullanıcının onayıyla [kaynak / gerçek entegrasyon / kabul ölçüm görünümü](ILERLEME_TAKIBI_20261112.md) oluşturuldu. Tek toplam yüzde hesaplanmaz.16modülün kısmi kaynak bildirimi tam kapsam yüzdesi değildir. Bu kayıt setinde tam modül entegrasyon/kabul kanıtıyla kapanmış sayaç0/16; bu, harcanan emeğin veya kısmi kaynak ilerlemesinin%0olduğu iddiası değildir. First130/13veG0OPEN ayrı tutulur. Son121PASS4SKIP112subtest sonucu11Kasım tarihli; bugün test yeniden koşulmadı. Önceki kanıtlar korunur, bilinmeyen durumlar tamamlandı sayılmaz.


## 2026-11-12 — Güven girdisi alt dilimi

[Kaynak/test raporu](CODEX_GUVEN_GIRDILERI_20261112.md):125PASS4SKIP; E2E preflight15uyuşmazlık(önce17),42doğrudan çağrı/1dinamik atlama. Supervisor consent pin/root ve enrolled secret fd bağlantısı uygulandı; gerçek entegrasyon/tam modül kabulü yok. GUNCEL doğrulaması CALISMA_DURUMU.md hash hatasında; G0OPEN,first13 0/13.


## 2026-11-12 — Kanonik workflow bağlantısı

[Kaynak/fake-driver raporu](CODEX_KANONIK_AKIS_20261112.md):144PASS4SKIP. Launch callback/engine bind → PilotSession/Broker/patch → bağımsız stop reconciliation → verifier/pipeline bağlandı. Eski sentetik E2E ve wrapper byte-exact yedekte; aktif giriş supervisor portları ister. Yeni preflight5kontrol/2dinamik atlama/29introspect edilemeyen çağrı/0finding; eski15uyuşmazlıkla aynı payda değildir. runtime_ready=false; CLIexit2. Gerçek enrolled Linux/DB/verifier kabulü açık; G0OPEN,first13 0/13; tam modül kapanışı yok.


## 2026-11-12 — Linux parent descriptor doğrulaması

[Supervisor kaynak/ortam raporu](CODEX_LINUX_SUPERVISOR_20261112.md):handoff constructor hatasında double-close/fd reuse riski düzeltildi; somut Linux LaunchObservationCloser kanonik workflowa bağlandı. Windows149PASS9SKIP; Linuxuid999 158PASS0SKIP. Gerçek parent pipe/pidfd testleri worker/verifier izolasyon kabulü değildir. Runtime profileJSON yok; clock/observer/verifier/enrollment ve namespace/cgroup kabulü açık. G0OPEN,first13 0/13,tam modül kapanışı yok.


## 2026-11-12 — Observer ölçüm ve pinli alt profil

[Kaynak/sensör raporu](CODEX_OBSERVER_OLCUM_20261112.md):pinli bounded ölçüm alt profili; Linux proc/pidfd/cgroup reader; launch/stop observer ve enrollment recheck validatorları; workflow bind/close bağlantısı eklendi. Windows162PASS11SKIP; Linuxuid999 173PASS0SKIP. Sensör probe ve fake-driver zinciri gerçek worker/verifier qualificationı değildir. Ayrı OS IPC/enrollment/authority readback/runtime verifier ve tam runtime profili açık. G0OPEN,first13 0/13; tam16MOD/PH00–06 kapsamı ve açık kabul sınırları korunur.


## 2026-11-12 — Servis/IPC ve verifier kaynak teslimi

[Kaynak ve gerçek kabul engelleri](CODEX_SERVIS_VERIFIER_20261112.md):bounded peer-credential/SCM_RIGHTS RPC, sabit servis handlerları/istemcileri,13case evaluator, private append-only receipt readback ve service_workflow bağlantısı uygulandı. Windows174PASS20SKIP; Linuxuid999 194PASS0SKIP. AyrıUID999/65534 gerçek IPC probePASS yalnız mekanizma kanıtıdır; enrollment değil. Gerçek profile/enrollment/Kernel readback/qualified candidate launcher bağları açık; ACTUAL_INTEGRATION_BLOCKED. İlk13gerçek kabul TAMAMLANAMADI; G0OPEN,first13 0/13,tam modül kapanışı yok. Tam16MOD/PH00–06 hedefi korunur.


## 2026-11-13 — Başlangıç receipt ve yetki adapterleri

[Kaynak/fake-driver raporu](CODEX_YETKI_ADAPTERLERI_20261113.md):DBsiz grant/revoke başarı stubı kaldırıldı; genel issuer açıkça BLOCKED, revoke mevcut CAP-017 Kernel rotasına bağlandı. Dedicated readonly BootstrapReadback ve entry tenant/project/generation/witness kontrolü eklendi. Windows187PASS20SKIP;Linuxuid999 207PASS0SKIP. Gerçek DB/SELECT yetkisi/enrollment/profile/launcher bağları ve native kabul açık; P0-1/P0-3 yalnız kısmi ilerledi. G0OPEN,first13 0/13,tam16MOD/PH00–06 kapsamı korunur.


## 2026-11-13 — PostgreSQL okuyucu mekanizma kanıtı

[Geçici DB raporu](CODEX_POSTGRES_READER_20261113.md):uid999/PostgreSQL18.6 yeni private temp kümede bootstrap reader pozitif/12negatif PASS;actual readonly/repeatable-read ve restart sonrası readback doğrulandı. Stop/küme silme PASS; mevcut DB ve83guarded kaynak kullanılmadı. Minimal SQL fixture/sentetik roller gerçek RLS/enrollment/uygulama kabulü değildir. Ürün kodu değişmedi; önceki22pin aynı;207suite yeniden koşulmadı. Gerçek approved katalog/reader/enrollment/profile ve first13açık;G0OPEN,first13 0/13,tam modül kapanışı yok.


## 2026-11-13 — Native bootstrap readback ACL

[Dar native okuma ve deney raporu](CODEX_NATIVE_READBACK_ACL_20261113.md): SQL084 ve NativeBootstrapReadback eklendi; caller tablo yetkisi almıyor. 84 kaynaklı boş native katalog derleme/ACL PASS; FORCE RLS minimal pozitif witness ve12negatif/restart PASS. Windows192PASS20SKIP;Linux212PASS0SKIP. Gerçek native bootstrap/enrollment/launcher/verifier kabulü açık; G0OPEN,first13 0/13;tam16MOD/PH00–06 kapsamı korunur.


## 2026-11-13 — Root okuyucusu native sürücü düzeltmesi

[Önce/sonra kanıtı ve başlangıç bağımlılıkları](CODEX_ROOT_READER_20261113.md): read_root doğru native UUID kaydını string eşitsizliğinden reddediyordu; SQL text sınırı ve immutable beklenen kayıt snapshotı eklendi. Tam native katalogda sentetik admin insert/commit ve ayrı readback PASS; revoked/compromised/wrong digest ret. Gerçek kimlik/consent/custody/provisioning ACL kanıtı değildir. Linux214PASS0SKIP;Windows194PASS20SKIP;preflight24call0finding. G0OPEN,first13 0/13;tam16MOD/PH00–06 kapsamı korunur.


## 2026-11-13 — Başlangıç izninin güncelliği

[Kontrol bağlantısı ve sınırları](CODEX_CURRENT_WINDOW_20261113.md): SQL085 ve bootstrap_window.py mevcut r56 root/clock kontrolünü dar provisioning API üzerinden erişilebilir yapar. Native missing enrollment/wrong user/internal execute ret ve ACL PASS;gerçek pozitif current root/time kabulü açık. Bu genel runtime/observer yetkisi değildir. Linux221PASS0SKIP;Windows201PASS20SKIP;85kaynak inert assembly. G0OPEN,first13 0/13;tam16MOD/PH00–06 korunur.


## 2026-11-14 — Açılabilir görev ekranı

[Görev ekranı ve gerçek bağlantı sınırı](CODEX_GOREV_EKRANI_20261114.md):127.0.0.1:8766 local UI,iş isteği/kayıt sorgusu,existing Kernel execute/emission adapterı ve ofis gezinmesi hazır. Default gerçek backend bağlı değil;gönderim kapalı. Desktop/mobile browser PASS;mock gönderim/readback native kabul değildir. Windows211PASS20SKIP;Linux231PASS0SKIP. Gerçek DB/session/worker/verifier ve ilk teslim açık;G0OPEN,first13 0/13;tam16MOD/PH00–06 korunur.
