# Görev ekranı

Yerel ekran: http://127.0.0.1:8766
Başlatma (Workspace kökünden): `C:\Python314\python.exe -B scripts/development/run.py tasks --port 8766`
Bu komut yalnız ekranı başlatır; DB/oturum/ajan oluşturmaz. Varsayılan durumda gönderim kapalıdır.

## Mevcut Kernel bağlantısı

Güvenilir supervisor aşağıdaki factoryye daha önce onaylanmış bağlantı ve scope referanslarını sağlar:

```python
from company_os.api.http.task_http import create_project_backend, create_server
backend = create_project_backend(
    connect=trusted_connect,
    project_id=enrolled_project_id,
    grant_ids=enrolled_grants_by_operation,
    emission_timeout=approved_emission_timeout,
)
with create_server(port=8766, backend=backend) as server:
    server.serve_forever()
```

Grant map `objectives.create`, `plans.create`, `tasks.create` ve/veya mevcut altı `candidate.r54.*.read` işleminden oluşur. Browser project/grant seçmez. Bearer oturum tokenını native `r54_context_enter` ve emission sırasında tekrar doğrular. Factory grant/session yaratmaz. Gerçek current enrollment/clock/host/profile/worker/verifier şartları ayrıca sağlanmalıdır. Bu factory G0 veya runtime kabulü vermez. Gerçek bağlantı ve anahtarları bu belgeye/depo ayarına yazma.

POST /api/objectives exact ObjectiveCreate sözleşmesini mevcut objectives.create Kernel rotasına gönderir. Bu bir Objective iş isteğidir; tek başına Plan/Task/worker çalıştırmaz. POST /api/details yalnız mevcut native detail read rotalarını kullanır. Sonuç host.emit üzerinden ayrı bağlantıda güncel yetki/snapshot kontrolüyle bounded sockete verilir; WSGI/cache fallbackı yoktur. Ortada kayıp ACK veya emisyon kesintisi varsa istemci yeniden deneme yapmaz; pending request ID sessionStorageda kalır. Request ID dışında token veya goal tarayıcı depolamasına yazılmaz. Belirsiz istek için readback/reconciliation tamamlanmadan yeniden gönderim yapılmamalıdır; bu durumun otomatik çözümü henüz bağlı değildir.

/office önceki kaynak uyumlu ofis önizlemesidir; görev ekranından ulaşılır ve geri dönüş bağlantısı vardır. Yeni görev ekranı ofis tasarımının yerine geçmez. Default loopback sunucu 127.0.0.1 bind eder. Host/Origin ve bounded request/timeout/no-store/CSP uygulanır; secrets veya body loglanmaz. Bu yerel sunucu internete yayınlanmış production deployment değildir.

Kanıt: ../../handover/history/CODEX_GOREV_EKRANI_20261114.md. Tarayıcı testi: `C:\Python314\python.exe -B scripts/verification/check_task_screen.py` (8766 yerel sunucu açıkken). Gönderim ve kayıt pozitif browser senaryoları açıkça mocked transporttur; native ürün kabulü değildir.


## 2026-11-14 — Pinli mevcut bağlantı başlatıcısı

`company_os.api.http.kernel_binding` yeni sınırlı HTTP bağlantı yükleyicisidir;tam runtime yükleyicisi değildir. Profil elle/supervisor tarafından gerçek onaylı referanslarla hazırlanmalıdır;bu görevde gerçek profil oluşturulmadı. Şifre/DSN/token eklenmez. Exact alanlar:

| Alan | Değerin kaynağı |
|---|---|
| version | company.http-kernel-binding/1 |
| canonical_workspace | E:\Projeler\Ai_Proje_Ofisi |
| postgres_service | Supervisorun mevcut libpq service adı |
| database / expected_login | Mevcut yetkili uygulama DB ve login adı |
| socket_directory | PostgreSQL'in exact yerel Unix socket dizini;TCP yok |
| project_id / grant_ids | Mevcut project UUID ve operation→grant UUID eşlemesi;onay üretmez |
| port |1024–65535 local UI portu |
| emission_timeout |Supervisorun onaylı0<süre<=5s gönderim sınırı |

Linux/WSL'deki uygulama ortamında:

```text
python -B scripts/development/run.py kernel --profile ONAYLI_PROFIL_YOLU --sha256 SUPERVISOR_PINI --check-only
python -B scripts/development/run.py kernel --profile ONAYLI_PROFIL_YOLU --sha256 SUPERVISOR_PINI
```

İlk komut metadata kontrolüdür;ikinci komut aynı kontrol geçerse ekran sunucusunu başlatır. SHA256pin belgeden kendiliğinden türetilen yetki değildir;supervisorun güvenilir girdisidir. Her bağlantı tekrar kontrol edilir;native token/grant yetkilendirmesi her işlemde devam eder. Uygulama loginine yeni GRANT vermek veya superuser kullanmak çözüm değildir. Mevcut8766sunucusu açıkken ikinci sunucu aynı porta açılmaz;başarılı kontrol sonrası mevcut sürecin kontrollü değiştirilmesi gerekir. [Kanıt/sınırlar](../../handover/history/CODEX_KERNEL_BAGLANTISI_20261114.md).


## 2026-11-15 — Bağlantı yetenekleri

GET /api/connection `can_create_objective` ve `detail_resources` alanlarını sunucuya bağlı operasyonlardan üretir. Panel salt okunur bağlantıda yeni iş göndermez ve bağlı olmayan kayıt türlerini kapatır. Bu alanlar kullanıcının güncel yetkisini doğrulamaz. Native Kernel her istekte ve sonuç gönderiminde oturumu yeniden denetler. [Adım 4 kontrolü](../../handover/STEP04_HTTP_KERNEL_20261115.md).


## 2026-11-15 — İş isteği, plan, görev ve makbuz

Panel işlem seçicisinden yalnız bağlı constructor seçilebilir. `/api/plans`: request_id, objective_id, expected_revision (proje revizyonu), assumptions, acceptance_criteria; `/api/tasks`: request_id, plan_id, title, role_id, acceptance_criteria, depends_on. Project/grant/tenant/token body alanı eklenmez. Parent/DAG/revision/rol yetkilerini native Kernel denetler. Gönderim DRAFT kaydıdır; READY veya ajan çalışması oluşturmaz.

`/api/receipts` POST: operation (üç constructordan biri), command_id, request_id. Yeni komut göndermez; mevcut r63_constructor_result ile aynı principal/project/operation bağında tanıklı makbuzu okur. request_id, makbuz correlation_id ile eşleşmelidir. Sunucu mevcut grant map üzerinden yetki ve emission kontrolünü yeniden yapar. Sayfa reload sırasında yalnız referansları saklar ve içeriği yeniden sorgulatır. Kaybolan ACK durumunda komut numarası hiç alınamadıysa bağımsız operatör readback gerekir; otomatik yeni gönderim yoktur.

[Bu dilimin kanıtı ve açık sınırları](../../handover/PANEL_WORKFLOW_20261115.md).
