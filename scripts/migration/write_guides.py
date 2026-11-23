"""Create reviewed layout entry guides; used once before final integrity pins."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write(name, text):
    path=ROOT/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip()+'\n', encoding='utf-8')


def main():
    mapping=json.loads((ROOT/'docs/migration/SOURCE_TO_TARGET.json').read_text('utf-8'))
    if mapping['status']=='COMPLETE_SOURCE_LAYOUT':
        raise RuntimeError('Layout finalized; do not regenerate reviewed guides.')
    write('README.md', '''# AI Proje Ofisi

Canonical workspace: E:\\Projeler\\Ai_Proje_Ofisi

Aktif ürün kaynakları [product/](product/README.md), ortak sözleşmeler [contracts/](contracts/README.md), PostgreSQL kaynakları [database/](database/README.md) altındadır. Klasör geçişi 2026-11-14 kullanıcı kararıyla yapıldı; teknoloji ve tam 16 modül/PH-00–PH-06 kapsamı korunur.

- [Proje ilerlemesi](progress/ILERLEME_TABLOSU.md)
- [Bakım ve değişiklik rehberi](BAKIM_VE_DEGISIKLIK_REHBERI.md)
- [Çalıştırma ve test komutları](docs/developer-guides/CALISTIRMA.md)
- [Mimari giriş](docs/architecture/README.md)
- [Dosya bazlı geçiş eşlemesi](docs/migration/SOURCE_TO_TARGET.json)
- [Geçiş planı ve sınırları](docs/migration/MIGRATION_PLAN.md)
- [Güncel devir](handover/CURRENT.md)

Kökten `C:\\Python314\\python.exe -B scripts/development/run.py tasks --port 8766` ile görev ekranı açılır. Varsayılan gerçek backend bağlı değildir; gönderim kapalıdır.

Kaynak testleri: `C:\\Python314\\python.exe -B scripts/development/run.py verify`. Kaynak bütünlüğü: `C:\\Python314\\python.exe -B scripts/verification/verify_layout.py`.

GUNCEL mevcut A kaynak tabanı ve mimari referansıdır. ARSIV tarihsel kaynaktır. Eski kök ZIP/JSON doğrulama dosyaları tarihsel paket kanıtıdır; yeni ürünün güncel PASS sonucu sayılmaz. GUNCEL/DOGRULA.py ayrı referans kontrolüdür ve önceki hash uyuşmazlığı açıktır.

G0 OPEN; ilk gerçek akış kabulü 0/13. Çalışan ekran veya kaynak testleri gerçek ajan/dosya teslimi ve insan kabulü değildir.''')
    old=(ROOT/'AGENTS.md').read_text('utf-8')
    # Preserve all old architectural rules, replacing only superseded layout facts.
    lines=old.splitlines()
    lines=[line for line in lines if not line.startswith(('- 2026-11-08 kullanıcı kararı:', '- company_os/', '- Test komutu:'))]
    lines[0]='# Güncel kaynak düzeni — 2026-11-14'
    insert='''
- 2026-11-14 kullanıcı kararı: aktif ürün product/ altındadır; önce product/AGENTS.md uygula. Eski AiProjeOfisi kökü emekliye ayrıldı. GUNCEL mevcut A tabanı/mimari referansıdır; ARSIV tarihsel kaynaktır.
- Python: product/backend/company_os; ortak sözleşmeler: contracts/source/python/packages/contracts; bağımsız doğrulayıcı: verifier/src/independent_verifier; SQL: database/sources ve database/assembly/assembly.json.
- Varsayılan kaynak testi: C:\\Python314\\python.exe -B scripts/development/run.py verify. Klasör/hash/import kontrolü: C:\\Python314\\python.exe -B scripts/verification/verify_layout.py. GUNCEL/DOGRULA.py ayrı eski A referans kontrolüdür; bilinen hash hatasını otomatik manifest yenileyerek kapatma.
- İlerleme tek kaynağı progress/ILERLEME_TABLOSU.json; Markdown görünümü scripts/development/run.py progress ile yenilenir. Bakım girişi kök BAKIM_VE_DEGISIKLIK_REHBERI.md.
- Geliştirme veya test yaparken docs/migration/SOURCE_TO_TARGET.json hedef SHA256 ve SOURCE_MANIFEST.json pinlerini anlamlı değişiklikten sonra açıkça gözden geçir; doğrulama aracı pinleri sessizce değiştiremez.
'''
    lines.insert(4,insert)
    write('AGENTS.md','\n'.join(lines))
    product_agents=(ROOT/'product/AGENTS.md').read_text('utf-8')
    product_agents=product_agents.replace('Uygulama kökü: E:\\Projeler\\Ai_Proje_Ofisi\\AiProjeOfisi', 'Uygulama kökü: E:\\Projeler\\Ai_Proje_Ofisi\\product')
    product_agents=product_agents.replace('Kullanıcının 2026-11-08 kararıyla yeni uygulama bu dizinde geliştirilir.', 'Kullanıcının 2026-11-14 geçiş onayıyla ürün kaynakları bu dizinde geliştirilir; eski AiProjeOfisi konumu güncellenmiştir.')
    product_agents=product_agents.replace('`ILERLEME_TABLOSU.json`','`progress/ILERLEME_TABLOSU.json`')
    product_agents=product_agents.replace('Markdown görünümünü uygulama dizininde `C:\\Python314\\python.exe -B -m presentation.progress`', 'Markdown görünümünü workspace kökünde `C:\\Python314\\python.exe -B scripts/development/run.py progress`')
    write('product/AGENTS.md', product_agents)
    write('BAKIM_VE_DEGISIKLIK_REHBERI.md', '''# Bakım ve değişiklik rehberi

Canonical workspace: E:\\Projeler\\Ai_Proje_Ofisi
Son güncelleme: 2026-11-14

Ürün henüz gerçek işi baştan sona teslim etmiş olarak kabul edilmedi. Bu rehber güncel kaynaklara giriş sağlar; tam sürüm geçmişi veya ürün kabulü değildir.

| İhtiyaç | Güncel kaynak |
|---|---|
| Durum, eksik ve sıradaki iş | [İlerleme](progress/ILERLEME_TABLOSU.md) |
| Bağlayıcı mimari ve 16 modül | [Mimari giriş](docs/architecture/README.md) |
| Yeni/eski dosya karşılığı | [Tam eşleme](docs/migration/SOURCE_TO_TARGET.json) |
| Ekranı açma ve test | [Çalıştırma](docs/developer-guides/CALISTIRMA.md) |
| Görev ekranı | [HTML](product/frontend/tasks.html), [JS](product/frontend/tasks.js), [CSS](product/frontend/tasks.css) |
| HTTP/oturum sınırı | [task_http.py](product/backend/company_os/api/http/task_http.py), [kernel_binding.py](product/backend/company_os/api/http/kernel_binding.py) |
| Tek domain writer | [command_host.py](product/backend/company_os/kernel/command_host.py) |
| Başlangıç kimliği ve güvenilir süre | [bootstrap](product/backend/company_os/bootstrap/) |
| Yetkili oturum | [session_provisioning.py](product/backend/company_os/kernel/session_provisioning.py) |
| Ajan/araç/patch bağlantısı | [composition](product/backend/company_os/composition/), [broker](product/backend/company_os/broker/), [workspace](product/backend/company_os/workspace/) |
| Süreç başlatma/IPC/ölçüm | [runtime](product/backend/company_os/runtime/) |
| Bağımsız verifier | [verifier](verifier/README.md) |
| Native kaynaklar | [native](product/backend/native/linux/) |
| Ofis görüntüsü ve kaynağı | [frontend](product/frontend/), [tasarım kaynağı](docs/developer-guides/OFIS_TASARIM_KAYNAKLARI.md) |
| İlerleme görüntüsü | [progress.py](product/backend/company_os/projections/progress.py) |
| SQL sırası ve korumalar | [assembly.json](database/assembly/assembly.json) |
| Yerel DB durum/start/stop | [araç](scripts/database/manage_local_postgres.ps1), [rehber](docs/operations/YEREL_VERITABANI.md) |
| Neden/nasıl taşındı, hangi düzeltmeler var? | [Geçiş raporu](docs/migration/MIGRATION_PLAN.md) |
| Önceki düzeltme kanıtları | [Tarihsel devirler](handover/history/), [ham kanıtlar](evidence/) |

İlgili kaynak değişince uygun test, kanıt ve ilerleme satırı güncellenir; değişmeyen satırlar yeniden test edilmiş sayılmaz. Tahmini yüzde ölçülmüş kabul değildir. Yeni bileşen veya davranış değişirse bu rehber de güncellenir. SOURCE_MANIFEST ve geçiş eşlemesinin hedef pinleri değişikliğin gerekçesiyle birlikte gözden geçirilir; eski source_sha256/historical evidence değiştirilmez.

Klasör geçişi sonrası Windows 248 test/228 başarılı/20 Linux skip; Linux 248 başarılı. Ham koşumlar evidence/runs/layout-migration-20261114 altındadır. Sonraki değişikliklerde bu sonuçlar kendiliğinden güncel sayılmaz. Gerçek profil/kimlik/DB şeması/model/verifier/ilk teslim kabulü ayrı açıktır.''')
    write('product/README.md', '''# Ürün kaynakları

frontend/ mevcut HTML/CSS/JS arayüzüdür. backend/company_os/ Python uygulama paketidir. Teknoloji değiştirilmedi. Önce AGENTS.md ve kök bakım rehberini oku.

Çalıştırma: workspace kökünden scripts/development/run.py. İlerleme progress/ILERLEME_TABLOSU.json içinde; ürün hafızası backend sorumluluğudur. Boş mimari alt alanlar işlev uygulanmış gibi gösterilmez.''')
    guides={
      'contracts/README.md': '# Ortak sözleşmeler\n\nTek asıl kaynak source/python/packages/contracts içindeki Python modelleridir. generated/ altındaki JSON Schema ve OpenAPI mevcut dışa aktarımlardır; TypeScript üretimi henüz uygulanmadı. Paralel elle düzenlenen model kopyası oluşturma. Sözleşme değişikliğinde üretim ve geriye uyumluluk ayrıca kontrol edilir.',
      'verifier/README.md': '# Bağımsız verifier\n\nsrc/independent_verifier kaynak testi yürütücüsünü ve bağımsız doğrulama pipeline kaynaklarını içerir. public-fixtures mevcut kaynak testi örnekleridir; gizli runtime oracle değildir. Ayrı klasör/aynı-UID subprocess gerçek izolasyon sağlamaz. Backend verification istemcileri product/backend/company_os/verification içinde kalır. Runtime enrolled verifier yokken reddedilir; kabulü Kernel kaydeder.',
      'workers/README.md': '# Worker girişleri\n\nBu alan ayrı yürütme girişleri içindir. Mevcut scheduler/claim/dispatch uygulaması backend içindedir; bu geçiş yeni worker servisi kurmadı. Gerektiğinde görev, outbox ve reconciliation girişleri eklenir; iş kuralları burada çoğaltılmaz.',
      'integrations/README.md': '# Entegrasyonlar\n\nİhtiyaç halinde filesystem/browser/MCP/webhook sağlayıcı adapterleri burada yer alır. Geçiş yeni dış sistem bağlantısı kurmadı. Dış etkiler tek Broker ve güncel yetki kontrolünden geçer.',
      'infrastructure/README.md': '# Altyapı\n\nYerel Windows/Linux, servis, izolasyon, ağ, gözlemleme, yedek/kurtarma ve paketleme tanımları bu alanın sorumluluğudur. Mevcut PostgreSQL yönetim aracı scripts/database içindedir. DB data, özel anahtar ve gerçek profil burada tutulmaz. Kubernetes/Terraform zorunlu değildir; geçişte servis kurulmadı.',
      'security/README.md': '# Güvenlik politikaları\n\nThreat model, trust boundary, enrollment/custody/revocation ve incident belgeleri bu alana eklenir. Çalışan güvenlik kodu Kernel/bootstrap/runtime/verifier sahiplerinde kalır. Kanıtlar kök evidence içinde, gerçek sırlar depo dışındadır. Yeni güvenlik kabulü verilmedi.',
      'catalog/README.md': '# Geliştirme kataloğu\n\nsources/MODULE_MAP.json 16 modülün kaynak karşılıklarını gösterir. Dosya/sınıf/fonksiyon/API katalogları gerektiğinde kaynaklardan üretilir; bu geçiş eksiksiz otomatik katalog üreticisi kurmadı. Ürün hafızası veya AI-BRAIN yerine geçmez.',
      'releases/README.md': '# Sürümler\n\nOnaylanmış sürüm manifesti, checksum, sürüm notu ve kabul referansları burada tutulur. Bu klasörün açılması release veya production kabulü değildir. Mevcut eski ZIP paketleri tarihsel kanıt olarak korunur.',
      'examples/README.md': '# Örnekler\n\nİlk SOFTWARE senaryosu MGT-TITLE-NORMALIZATION-01. Producer örneği tests/fixtures/producer/mgt01, açık verifier örnekleri verifier/public-fixtures/mgt01 içindedir; burada ikinci kopya tutulmaz.',
      '.github/README.md': '# GitHub iş akışları\n\nBu workspace için Git deposu/remote bu geçişte oluşturulmadı. CI ve inceleme şablonları gerçek repo/çalıştırıcı kararına göre eklenir. Klasör varlığı etkin CI değildir.',
      'evidence/README.md': '# Kanıtlar\n\nGeçmiş kanıtlar byte-exact taşındı; eski dosya yolları ve hashler tarihsel bağlamdır. Güncel klasör geçişi evidence/runs/layout-migration-20261114 içinde. Kayıtların varlığı teknik iddianın güncel doğruluğunu kanıtlamaz. Sır veya gerçek müşteri verisi ekleme.',
      'ROADMAP.md': '# Geliştirme sırası\n\nTek durum kaynağı progress/ILERLEME_TABLOSU.json. Öncelik: uygulama şeması/başlangıç yetkileri → gerçek oturum → kalıcı Objective → plan/görev/ajan → bağımsız kontrol/teslim/reload. Tam 16 modül/PH-00–PH-06 sürer; ilk SOFTWARE akışı ara hedeftir.',
      'CHANGELOG.md': '# Değişiklikler\n\n## 2026-11-14\n\nKullanıcı onayıyla AiProjeOfisi kaynakları product/contracts/database/verifier ve destek alanlarına taşındı. 440 dosya eşlemesi, geri dönüş ZIPi ve kaynak bütünlük kontrolleri eklendi. Import/HTTP/SQL/WSL başlatıcıları güncellendi. Windows bağlı-olmayan backend 503 yanıtının gövde tüketimi düzeltildi. Ayrıntı docs/migration/MIGRATION_PLAN.md içinde. Ürün kabulü değişmedi.',
      'SECURITY.md': '# Güvenlik\n\nGerçek anahtar, token, parola, DB data ve özel runtime profili depoya eklenmez. Tek Kernel writer ve Broker sınırı, bağımsız verifier ve güncel yetki kontrolü korunur. Şüpheli açıkları herkese açık rapora sırları kopyalayarak bildirme. Bu workspace için yayımlanmış güvenlik iletişim adresi tanımlanmadı.',
      'CONTRIBUTING.md': '# Geliştirme kuralları\n\nAGENTS.md, product/AGENTS.md ve bakım rehberini oku. Yeni teknoloji veya özellik eklemeden mevcut mimariye uy. Uygun kaynak testini, verify_layout kontrolünü ve ilgili ilerleme/kanıt güncellemesini tamamla. İnsan kabulü ve runtime güvenini fixture/test PASS ile yükseltme. Geçmiş kanıt ve source_sha256 değerlerini yeniden yazma.',
    }
    for name,text in guides.items():
        write(name,text)
    write('.env.example', '# Sır içermeyen örnek; uygulama bu dosyayı otomatik yüklemez.\n# Özel profil ve sırlar supervisor tarafından depo dışından sağlanır.')
    write('.gitattributes', '* text=auto\n*.py text eol=lf\n*.md text eol=lf\n*.json text eol=lf\ndatabase/sources/** -text\nverifier/public-fixtures/** -text\ntests/fixtures/** -text\nevidence/** -text\nGUNCEL/** -text\nARSIV/** -text')
    ignore=(ROOT/'.gitignore').read_text('utf-8')
    ignore+='\n.env.*\n!.env.example\n.pytest_cache/\n*.egg-info/\nbuild/\ndist/\nconfig/profiles/private/\n'
    write('.gitignore',ignore)
    write('DOGRULA.bat', '@echo off\ncd /d "%~dp0"\n"C:\\Python314\\python.exe" -B "%~dp0scripts\\development\\run.py" verify\nexit /b %errorlevel%')
    # Old source claims are preserved in before.zip; current mapping reports source
    # presence separately from integration/runtime acceptance.
    modules=ROOT/'catalog/sources/MODULE_MAP.json'
    data=json.loads(modules.read_text('utf-8'))
    data['source']='GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md'
    data['path_base']='CANONICAL_WORKSPACE'
    data['note']='Kaynak eşlemesi; ayrı servis/klasör veya runtime kabulü anlamına gelmez. Güncel ilerleme progress/ILERLEME_TABLOSU.json içindedir.'
    for module in data['modules']:
        raw=module['architecture_source_paths']
        targets=[]
        for row in mapping['files']:
            relative=row['source'].removeprefix('AiProjeOfisi/')
            if relative in raw:
                targets.append(row['target'])
        module['current_source_paths']=sorted(set(targets))
        module['implementation_status']='SOURCE_PARTIAL' if targets else 'TRACKED_IN_PROGRESS_TABLE'
        module['runtime_acceptance']='NOT_VERIFIED'
    write('catalog/sources/MODULE_MAP.json', json.dumps(data,ensure_ascii=False,indent=2))
    write('decisions/DECISION_REGISTER.json', json.dumps({'decisions':[{'id':'ADR-20261114-KLASOR-DUZENI','status':'USER_APPROVED_LAYOUT','path':'adr/ADR-20261114-KLASOR-DUZENI.md'}]},ensure_ascii=False,indent=2))
    progress=ROOT/'progress/ILERLEME_TABLOSU.json'
    data=json.loads(progress.read_text('utf-8'))
    quality=next(a for a in data['areas'] if a['id']=='quality')
    quality['ready']='Yeni kaynak düzeni, importlar ve başlatıcılar doğrulandı. Windows 228 geçti/20 atlandı; Linux 248 geçti.'
    quality['evidence'].append('docs/migration/MIGRATION_PLAN.md')
    quality['evidence_scope']='2026-11-14 yeni konumlardaki kaynak regresyonları: Windows248 test/20 Linux skip, Linux248 başarılı. Gerçek ürün kabulü değildir.'
    write('progress/ILERLEME_TABLOSU.json',json.dumps(data,ensure_ascii=False,indent=2))
    print('Active guides, instructions, decision, module map and quality progress updated')


if __name__=='__main__':
    main()
