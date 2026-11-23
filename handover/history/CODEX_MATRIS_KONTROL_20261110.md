# Codex — Antigravity matris teslimi bağımsız kontrolü

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-10
Kaynak ajan: Codex
Kontrol ID: CODEX-20261110-MATRIS-01
Durum: DUZELTME_GEREKLI; uygulama veya insan kabulü değildir

İncelenen Antigravity matris SHA256: `fa65b274bbb884df02459cc64e25b1f71c7afa6dfec0872f9cfbf125750c7de6`.
Makine kaydı: [CODEX_MATRIS_KONTROL_20261110.json](evidence/CODEX_MATRIS_KONTROL_20261110.json).

## Doğrulananlar

- `C:\Python314\python.exe -B -m pytest AiProjeOfisi/tests -v -rs`: exit 0; 85 passed, 4 skipped, 97 subtests passed. Bu, Windows kaynak/birim regresyonudur; modüllerin bütün AC setlerini veya gerçek zinciri doğrulamaz.
- 16 modül ve 7 faz tabloda mevcut. Kaynak kartlarındaki dosya hash önekleri mevcut dosyalarla eşleşiyor. MOD-013 dışındaki listelenen dosya yolları mevcut. Kısaltılmış hashler tam SHA256 yerine geçmez.
- Teslim anında Codex alanları BEKLIYOR olarak korunmuş. Kapsam PH-05/06 dahil görünür; insan kabulü yükseltilmemiş.

## Bulgular

### F01 — Gerçek kaynak sembolleri yerine olmayan isimler yazılmış

MOD-001: `command_host.py` içinde `CommandHost` ve `execute_command` yok; gerçek giriş `execute`. MOD-002: `company.py` içinde `ObjectiveSpec`, `PlanSpec`, `TaskSpec`; `models.py` içinde `Objective`, `PlanVersion`, `Task`, `DecisionCase` adlı üst düzey tanımlar yok. Gerçek DTOlar arasında `ObjectiveCreate`, `ObjectiveRead`, `PlanCreate`, `PlanRead`, `TaskCreate`, `TaskRead` var. MOD-003: `execution.py` içinde `AttemptSpec`, `QualificationSpec`, `WorkerProfileSpec` yok; `Qualification` company.py içinde, diğer ilişkili sözleşmeler gerçek owning source ile eşlenmeli. AST üzerinden kontrol edildi. Dosya hashinin tutması sembol ve davranış iddiasını doğrulamıyor.

### F02 — MOD-013 dört bulunmayan fixture dosyasına dayanıyor

`fixtures/mgt01/oracle_mgt01.py`, `candidate_valid.py`, `candidate_mutant.py`, `baseline_candidate.py` mevcut değil. Gerçek dosyalar `fixtures/mgt01/producer/task_title.py`, `fixtures/mgt01/verifier/check_title.py`, `fixtures/mgt01/verifier/reference_title.py`. Mutant mevcut testte geçici dizinde üretiliyor (`tests/unit/test_verifier_runner.py`); kalıcı dosyaymış gibi listelenemez.

### F03 — Verifier false-pass hâlâ yeniden üretilebiliyor

Gerçek `check_title.py` değiştirilmeden, `normalize_title` tanımlamayan aday dosya beklenen 13 case ID için PASS JSON yazıp `os._exit(0)` ile çıkınca `run_title_oracle` **PASS / 13 / 13** döndürdü. Kontrollü aday geçici dizinde oluşturuldu ve kaldırıldı; DB/model/anahtar/acceptance çalıştırılmadı. Yeniden üretim girdisi, rapor ve kaynak pinleri JSON kanıtında var.

Mevcut negatif test, değiştirilmiş oracle ve yanlış case IDlerini reddediyor; doğru IDlerle aday kaynaklı sahte raporu reddetmiyor. Aday ve trusted oracle aynı çocuk süreçte çalışıyor, stdout ortak. `capture_output=True` ardından uzunluk kontrolü okuma sırasında bellek/byte sınırı değildir. MOD-008 ve PH-03 içindeki sertleştirme ifadeleri bu açığın kapandığını göstermiyor. Güvenilir harness test kararlarını adayın erişemediği sınırda üretmeli; ayrı kanal tek başına yeterli değildir.

### F04 — Test/ham kanıt ve modül kabul eşlemesi yetersiz

`EV-20261110-SRC-01` komutu `python -c "..."`; tekrar çalıştırılabilir tam komut yok. `module-map.json` dosyası AST/semantik envanter çıktısı değildir. `EV-20261110-UNIT-01` bir dizini ham koşum kaydı olarak gösteriyor; stdout/stderr ve kaynak/test manifesti yok. Test sonucu bağımsız tekrarlandı ancak bütün 16 modülde UNIT etiketinin aynı IDyle kullanılması, her ACnin sınandığı anlamına gelmez. Her AC için test/fonksiyon ve eksik davranış bağı kurulmalı. TEST-001..027 mimari kimlikleri pytest case sayısıyla karıştırılmamalı.

### F05 — Arayüz/projection ve SKIP açıklamaları gerçek test kapsamını aşıyor

`presentation/app.py` Python okuma istemcisi ve HTML üreten fonksiyonlar içeriyor. `test_presentation.py`, `ReadConn`/`ReadCursor` sahteleri ile doğrudan fonksiyon çağırıyor. ASGI/WSGI runner, HTTP 401/403/409, tarayıcı reload, gerçek DB restart/readback veya erişilebilirlik denetimi bu testlerle kanıtlanmıyor. `Blocked` exception HTTP durum kodu değildir. Ayrı projection consumer/checkpoint/dedup/resync davranışının `presentation/app.py` içinde mevcut olduğu gösterilmedi.

Dört SKIP: socketpair, `test_actual_pipes_and_ownership_transfer`, iki secret fd/owner/mode testi. Bunlar rootless namespace/cgroup kabul testleri değil. Teslimdeki `test_select_loop_nonblocking_and_partial_line_drain` adı bu koşumun atlanan testi değil. Linux native kabul ayrıca gerekir.

### F06 — Eksik uygulamayla kapalı yetki yüzeyi karıştırılmış

Genel shell, dış ağa doğrudan erişim ve ücretli fallback kapalılığı hata/eksik olarak açılmamalı. MOD-001/008/016 HSM, MOD-009 dual custody ve MOD-012 ayrı knowledge servisi yeni zorunlu teslim olarak owning karar/REQ olmadan dayatılmamalı. Tek insan sahipliği korunmalı. Bir modülün önerilen dosyasının yokluğu ayrı servis gerektirmez. MOD-013 diğer WorkType dalları tam proje kapsamında; “PH-06'ya kadar kapsam dışı” yerine “PH-06 uygulama sırasını bekliyor” yazılmalı. Yerel kurulum rızası varken genel “izin bekleniyor” yerine eksik somut yetki/enrollment/ortam kanıtı gösterilmeli.

### F07 — Sonraki görevler ve AC kapsamı tam izlenebilir değil

Kartlarda P1-1..P1-9 ve P2-MOD* IDleri var; görev tablosunda yalnız MATRIS-01/P0-1/P0-2 var. §28 TaskSpec dosyaları veya tam görev alanlarına bağlantı verilmemiş. MOD-012/014/015 ilk akış korumaları ile sonraki tam kapsam işleri ayrılmalı. “Envanter eksiksiz TAMAMLANDI” yerine bu bulgular kapanana kadar REVIEW_REQUIRED kullanılmalı.

### F08 — A kaynak doğrulaması gerçekten başarısız

`C:\Python314\python.exe -B GUNCEL/DOGRULA.py`: exit 1, `AssertionError: dokumanlar/hedef-mimari-v1/CALISMA_DURUMU.md`. Fail açık tutulmalı. Hashi sırf PASS almak için yenileme; önce farkın owning kaynağı ve nedenini incele. Yeni uygulama testlerinin geçmesi bu A tabanı hatasını kapatmıyor.

## Sonuç ve inceleme sınırı

Envanter başlangıç olarak yararlı; **eksiksiz ve bağımsız doğrulanmış teslim olarak kabul edilmedi**. Codex alanları bu rapora bağlandı. Dosya/hash doğrulaması, AST sembol denetimi, Windows regresyonu ve kontrollü false-pass yeniden üretimi yapıldı. Tüm SQL semantiği, Linux/native/DB E2E, model çıktısı, görsel panel ve insan kabulü bu incelemede çalıştırılmadı. G0/first13 durumu yükseltilmedi.

Sonraki paket: [Antigravity — kontrol sonrası tam kapsam geliştirme ve görünür sürüm](ANTIGRAVITY_KONTROL_SONRASI_GOREV_20261110.md).
