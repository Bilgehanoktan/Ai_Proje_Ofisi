# AI Proje Ofisi — uygulama temeli

Bakım için ilk giriş: [Bakım ve değişiklik rehberi](BAKIM_VE_DEGISIKLIK_REHBERI.md).


Güncel sade takip: [Proje ilerleme tablosu](ILERLEME_TABLOSU.md) · [Tarayıcıda aç](http://127.0.0.1:8766/progress). Her anlamlı geliştirmede güncellenir; ayrıntılı mimari ve tarihsel kanıtların yerine geçmez.


2026-11-14 görünür giriş: AiProjeOfisi dizininden `C:\Python314\python.exe -B -m presentation.task_http --port 8766`; [Görevler](http://127.0.0.1:8766). Ekran ve Kernel HTTP adapteri hazır; varsayılan gerçek görev bağlantısı yok, gönderim kapalıdır. Gerçek ajan/dosya teslimi henüz doğrulanmadı. [Bağlantı ve çalıştırma](presentation/TASK_SCREEN.md), [kanıt ve açık işler](CODEX_GOREV_EKRANI_20261114.md). Aşağıdaki eski tarihli test/durum sayıları tarihsel kayıttır.


Bu klasör yeni uygulamanın geliştirme köküdür. Mimari: [hedef tasarım](../GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md). Yapı §26'dan uyarlanmıştır; native C kaynakları için native/ ayrılmıştır. Mevcut kaynaklar taşınmamıştır; uygulama aktarımı parça parça sürmektedir.

- company_os/: command, scheduler, process, engine, broker, artifact, verifier ve projection uygulamaları.
- packages/contracts/: sürümlü DTO ve predicate sözleşmeleri; DB/provider/UI bağımlılığı içermez.
- sql/: sıralı native kaynaklar ve açık migration planı; 83 kaynaklı inert assembly mevcut; native kabul açık.
- native/: Linux process ve clock yardımcıları; ayrı compile/OS kabulü gerekir.
- fixtures/mgt01/: producer girdisi ve bağımsız verifier oracle için ayrı alanlar.
- presentation/: yetkili command istemcisi ve scope kontrollü sonuç görünümü.
- tests/: unit, contracts, integration, security ve e2e ayrımı.
- evidence/: koşuma bağlı manifest ve kanıtlar; sır deposu değildir.
- tools/: geliştirme ve kaynak doğrulama araçları.

[Uygulama sırası](PLAN.md) ve [kaynak pini](architecture-source.json).
Güncel durum SOURCE_ONLY / SQL_AND_COMMAND_HOST_ADAPTED. Servis veya model başlatılmaz.

- config/profiles/: sır içermeyen ortam profilleri için ayrılmış alan.
- [Modül eşlemesi](module-map.json): mimari §15 içindeki 16 modülün kaynak dosya karşılığı; her modül ayrı klasör veya servis gerektirmez.

SQL assembly ve yerel kaynak kontrolü hazır; bağımlılık/paketleme manifestosu, CI ve runtime girişleri henüz hazırlanmadı. Mimari belgeler GUNCEL/dokumanlar konumundan referans alınır.

2026-11-08: 83 SQL kaynağı pinlenerek alındı; clock trigger PUBLIC EXECUTE kaynak düzeltmesi ve 2 kaynak testi hazır. Eski kaynakta regresyon EXPECTED_FAIL. Gerçek DB ACL doğrulaması yapılmadı.

Command Host yeni kökte bağımsızdır. `C:\Python314\python.exe -B AiProjeOfisi/tools/verify_source.py` workspace kökünden 2 SQL kaynak + 11 fake-driver testini çalıştırır. Toplam 13 test, first13 uçtan uca kabul sayacı değildir. Registry seed boşlukları evidence/registry_seed_gap.json içinde kayıtlıdır.

Son kaynak koşumu: 54 PASS, 2 Linux SKIP. Worker/engine/broker/patch/contracts/native kaynakları yeni kökte; gerçek DB/OS/verifier/UI kabulü tamamlanmadı. [Güncel durum](evidence/implementation_status.json).


Tam proje takibi: [16 modül, fazlar ve bağımsız kontrol matrisi](UYGULAMA_DURUM_MATRISI.md). Antigravity bildirimi, Codex kontrolü ve insan kabulü ayrı tutulur.
