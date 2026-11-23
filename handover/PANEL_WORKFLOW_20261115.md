# Panel → Kernel geliştirme dilimi — 2026-11-15

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-15
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_TESTS_AND_READ_ONLY_DB; LIVE_PANEL_MUTATION_NOT_VERIFIED
Kanıt: evidence/runs/panel-workflow-20261115/database-audit.json; evidence/runs/browser-1300435f/TASK_SCREEN_20261114_browser.json; tests/unit/test_task_http.py; tests/unit/test_host_guards.py; tests/unit/test_kernel_binding.py

## Uygulanan bağlantılar

- HTTP POST /api/plans ve /api/tasks, mevcut PlanCreate/TaskCreate sözleşmeleriyle yalnız sunucuya bağlı project/grant üzerinden mevcut plans.create/tasks.create native rotalarına gider. Tarayıcı proje/yetki seçemez. Taslak kaydı worker başlatmaz.
- Panel üç kayıt türünü, üst kayıt referanslarını, plan revizyonunu, rolü, kabul ölçütlerini ve görev bağımlılıklarını sunar. Yalnız profilin bağlı operasyonları açılır; gerçek yetki her istekte native Kernel tarafından denetlenir.
- POST /api/receipts operation+command_id+request_id alır. command_host.execute read_command_id yolunda mevcut r63_constructor_result çağrılır; constructor tekrar çalıştırılmaz. Native fonksiyon principal/project/operation ve audit/outbox tanıklarını denetler. Request correlation ayrıca eşleştirilir; sonuç ayrı bağlantıda güncel emission kontrolünden geçer.
- Panel reload sonrası yalnız komut/istek/operasyon referanslarını saklar; makbuz içeriği güncel kabul edilmez ve yeniden sorgulanır. Token veya iş içeriği depolanmaz. Belirsiz isteğin kilidi yalnız aynı operasyon/isteğe ait başarılı readback ile açılır. Komut numarası hiç alınamadıysa operatörün bağımsız bulması gerekir; request_id ile otomatik lookup henüz yoktur.
- command_host.emit validation/serialization sırasında BEGIN öncesi hata verirse bağlantı artık finally ile kapanır. Revocation kontrolü başarısızsa byte gönderilmez; belirsiz sonuçta otomatik resend yoktur.
- plans/tasks-only profillerinde de r63_constructor_result ACL metadata kontrolü zorunludur. Mevcut gerçek SQL, rol, trigger, oturum veya yetki değiştirilmedi.

## Bağımsız mevcut DB gözlemi

15 Kasım salt okunur snapshot: PostgreSQL18.6; 2 Objective, 2 Plan, 3 Task, 2 Attempt, 1 verification_run, 1 acceptance_record; 32 session satırından geçerli/iptal edilmemiş olan 0; process_runs ve tool_requests 0; kapalı user trigger yok. Kayıt sayımı yetkili köken/model/izolasyon kabulü değildir. Signer enrollment ve operation_permissions tablolarında RLS false gözlenir; bu metadata tek başına açık veya hata sonucu olarak yorumlanmadı. Önceki pilot anlatımı otomatik tam ürün kabulüne yükseltilmedi.

## Doğrulama

Linux Python3.14: 261 test başarılı, skip0. Windows Python3.14: 261 test/241 başarılı/20 platform skip. Genişletilmiş browser masaüstü/dar ekran, readonly capability, unknown ACK reload/no-resubmit, makbuz, escaped kayıt, plan/görev formları ve yeniden makbuz okuma PASS; pageerror yok. Tarayıcı pozitif gönderimler mock, Kernel/HTTP testleri DB-API doubles kullanır. Üç değişen üretim Python dosyası Ruff PASS. Son layout ve test logları evidence/runs/panel-workflow-20261115 altında tutulur. Hedef pinler yalnız bu dilimde değişen dosyalarda açık güncellenir; tarihsel source_sha256 korunur.

## Açık iş ve sınır

Adım4 tam canlı kabulü hâlâ açık: mevcut güven kökünden desteklenen provisioning ile geçerli oturum ve onaylı en-az-yetkili HTTP bağlantısı sağlanmalı; panelden Objective/Plan/Task pozitif ve expired/revoked/wrong-scope negatifleri gerçek PostgreSQL ile kanıtlanmalı. Ardından görev READY/scheduler, rootless worker, ücretsiz yerel model ve Broker→gerçek patch→bağımsız verifier zinciri tamamlanmalı. Bu çalışma grant/session veya insan kabulü üretmedi. G0 OPEN, first13 0/13; tam16MOD/PH00–06 korunur. Önceki STEP04_HTTP_KERNEL_20261115.md bu dilimin başlangıç durumudur.

Son tarayıcı kontrolünde belirsiz istek için başarısız makbuz okuması kilidi korudu; eşleşen makbuz yeni constructor çağrısı olmadan kilidi açtı. Son Linux suite sırasında değişen tarayıcı test betiğinin pini nedeniyle layout FAIL verdi; testlerin kendisi 261/261 geçti. Pinler açıkça gözden geçirilerek ayrı son layout ile doğrulandı; ham ilk sonuç saklandı.
