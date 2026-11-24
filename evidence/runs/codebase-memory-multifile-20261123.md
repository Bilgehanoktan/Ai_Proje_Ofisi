# Codebase Memory çok dosyalı inceleme denemesi

23 Kasım 2026 · Codex · Statik kaynak incelemesi

İnceleme görevi, ofis görev formundan gelen isteğin HTTP girişini ve worker yürütmesini takip etmek, `EXP-01` için katalog okumasının ve Ollama çağrısının yerini bulmaktı. Karşılaştırmada güncel çalışma ağacında `rg` ve kaynak okuma ile yalnız ürün arka ucunu kapsayan Codebase Memory `fast` indeksi kullanıldı. İndeks 739 düğüm ve 3378 ilişki bildirdi.

| Kontrol | Kaynak araması | Kod grafiği |
|---|---|---|
| HTTP girişi ve başlatıcıdaki callback | `app.py` ve `start_office_local.py` üzerinde doğrudan doğrulandı | Başlatıcı indeks kapsamı dışındaydı |
| Worker ve çalışma adımları | Kurucuya geçirilen üç callback ve daemon çağrıları okundu | `AutonomousWorkerDaemon.run_once` çağrısı claim, execute ve verify ilişkilerini tek sorguda gösterdi |
| Katalog ve model | `LiveOfficeTaskRunner._execute_task`, `Extensions087Store.list_catalog_entries` ve `OllamaClient.generate` kaynakta doğrulandı | İki çağrıyı ikinci adımda gösterdi |
| Bağlantı çözümleme | `Extensions087Store` bağlantısı kurucudan verilen `connect` callback'idir | Derinlik iki sorgusu `IntentJournal.connect` ilişkisini de gösterdi. Kaynak bu atfı desteklemiyor |

Grafik çağrı zincirini hızlıca daralttı ve çalışma ağacındaki pilot kodunu görebildi. Bu çalışmada süre karşılaştırması, token tasarrufu, görev çözüm kalitesi ve ürün entegrasyonu ölçülmedi. Sonuç tek statik inceleme göreviyle sınırlı.
