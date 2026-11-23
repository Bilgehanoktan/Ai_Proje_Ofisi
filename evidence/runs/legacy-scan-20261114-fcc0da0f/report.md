# Legacy scan — 2026-11-14

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi

Aktif kodda 127 Python dosyası tarandı. Doğrulanmış eski import: 0; eski köke doğrudan string yol: 0. Klasör/hash/import kontrolü: PASS. Kaynaklar değiştirilmedi.

## Açık bulgular

### LEG-001 — P2 — BROKEN_CURRENT_COMMAND
Kaynak: `database/README.md:11`

Kaynak kontrolü komutu kaldırılan AiProjeOfisi/tools/verify_source.py yolunu kullanıyor.

Öneri: scripts/development/run.py verify komutuna güncelle.

### LEG-002 — P2 — STALE_MAINTENANCE_PATHS
Kaynak: `config/README.md:14`

tools/probe_peer_rpc_identity.py ve presentation/kernel_binding.py yolları güncel kökte yok.

Öneri: scripts/verification/probe_peer_rpc_identity.py ve product/backend/company_os/api/http/kernel_binding.py yollarını kullan.

### LEG-003 — P2 — STALE_CURRENT_VALIDATION_POINTER
Kaynak: `GUNCEL_DURUM.json:15`

effective_source_root=product olduğu halde current_validation=GUNCEL/VERIFICATION.json; eski A kanıtı güncel ürün doğrulaması sanılabilir.

Öneri: A referans doğrulamasını ayrı alanla koru; güncel doğrulama alanını güncel koşum kanıtına bağla.

### LEG-004 — P2 — LIVE_PROJECTION_OF_HISTORICAL_STATUS
Kaynak: `product/backend/company_os/projections/preview_generator.py:14`

Üretici tarihsel matris kartlarının ilk eşleşen durumlarını okuyor; yeniden üretilen HTML halen 85 PASS ve tools/disposable_e2e_workflow_trial.py bilgisi içeriyor. Dosya kalıntısı değil; /office için de kullanılan üretici davranışı.

Öneri: Güncel ilerleme/katalog bilgisini kaynak olarak kullan veya tarihsel kart görünümünü açıkça tarihsel olarak etiketle; eski kanıtları yeniden yazma.

### LEG-005 — P2 — MOVED_PLAN_WITH_BROKEN_LINKS
Kaynak: `docs/implementation-plan/PLAN.md:10`

Tarihli plan eski uygulama kökünü anlatıyor; yeni konumuna göre 17 Markdown bağlantısı çözülemiyor.

Öneri: Tarihsel metni koruyarak konum/devir notu ekle; bağları eşlemeyle düzelt veya belgeyi açıkça tarihsel devir olarak ayır.

### LEG-006 — P3 — AMBIGUOUS_REFERENCE_TOOL_PATH
Kaynak: `AGENTS.md:16`

tools/refresh_source.py --docs workspace kökünde yok; gerçek A referans aracı GUNCEL/tools/refresh_source.py altında.

Öneri: A referansına ait komutun konumunu ve çalışma dizinini açık yaz; mevcut hash hatasını körlemesine manifest yenileyerek kapatma.

## Kapsam sınırı

- GUNCEL/ARSIV içeriği genel olarak taranmadı; referans ve tarihsel kaynak olarak korundu.
- Ham evidence/handover geçmişi ve migration source mapping eski yolları bilerek içerir; aktif bağımlılık sayılmadı.
- Çalışan süreçler, Windows Task Scheduler, gizli profiller, runtime verisi ve mevcut paket kurulumları taranmadı.
- Uygulama test grubu yeniden çalıştırılmadı; verify_layout bağımsız yeniden çalıştırıldı.

G0 OPEN; first13 0/13. Bu tarama gerçek çalışma/kabul kanıtı değildir.

İki company_os.composition adayı mevcut pakete çözülür; eski düz modül bağımlılığı değildir. Ham adaylar JSON raporunda korunur.
