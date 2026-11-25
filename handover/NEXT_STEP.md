# Sıradaki işler

23 Kasım [kabul kaydı](G0_INSAN_ONAYI_KONTROL_LISTESI_20261123.md) G0 insan onayını ve MGT-01 için 13/13 kabulü; 24–25 Kasım canlı doğrulamaları ise 328/328 birim/güvenlik testini, `verify_layout.py` PASS sonucunu, canlı Ollama (`qwen2.5-coder:3b`, `repeat_penalty=1.15`) + gerçek Broker (`workspace.read`) + Windows Edge `RESEARCH` uçtan uca koşusunu, en az yetkili `aipof_research_readback` servisiyle görev/proje/deneme kapsamlı native Kernel DB `workspace.read` makbuz geri okumasını (`verifier/src/independent_verifier/research_readback.py`, `verify_backup_restore_and_queue_pg.py`), en az yetkili `aipof_catalog_087` servisi üzerinde çoklu tenant katalog yük testini (`10×20=200` izole PG ve `5×20=100` canlı PG, `0` sızıntı), izole PostgreSQL 18.6 üzerinde `001–087` kalıcı kurulumu + `087 → 088` yükseltmesi ve soğuk restart readback'ini (`verify_087_migration_pg.py`), iki ayrı tarayıcı oturumuyla `088` proje ayrımını (`200` vs `403 AGENT_INSTANCE_SCOPE_DENIED`) ve canlı Ollama üzerinde `EXP-01` baz/pilot rol kartı karşılaştırması ile gerçek `.xlsx` (`SPREADSHEET`) ve `OBLIGATION` belge akışlarını (`3/3 ACCEPTED`) belgeliyor.

1. Uzak üretim dağıtımı yapılacaksa hedef SSH host takma adını ve izinli harici HTTPS domain listesini belirleyip `docs/operations/PRODUCTION_RUNBOOK.md` adımlarını hedef üretim Linux sunucusunda uygula.
2. Doğrulanmış yerel commit'i uzak GitHub deposuna (`origin/main`) gönderip `.github/workflows/ci.yml` hattının uzak Linux runner üzerinde yeşil geçtiğini teyit et.
3. MOD-001–MOD-016 ve PH-00–PH-06 durumunu `progress/ILERLEME_TABLOSU.json` üzerinden kanıtıyla izle.

GUNCEL/DOGRULA.py içindeki eski CALISMA_DURUMU.md hash uyuşmazlığı ayrı açık bakım bulgusudur; manifesti körlemesine yenileyerek kapatma.
