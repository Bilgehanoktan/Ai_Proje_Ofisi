# Mimariye göre uygulama — ilk güvenlik ve önkontrol paketi

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-11
Kaynak ajan: Codex
Durum: IMPLEMENTED_SOURCE_AND_UNIT; bağımsız review ve gerçek Linux/DB/model kabulü açık
Kanıt: evidence/CODEX_UYGULAMA_20261111_CHECKS.json, aynı önekli ham loglar ve kaynak manifesti.

## Kapsam ve dayanak

Kullanıcının “kontrol et ve mimariye göre yapmaya başla” talimatıyla kaynak uygulaması başlatıldı. Dayanak PROJE_TASARIM_DOKUMANI.md §12, MOD-008/009, BR-010, §16 portları ve §28 görev sözleşmesidir. Önceki KALAN_ISLER_DETAYLI_INCELEME_20261111.md tarihsel inceleme katmanıdır; aşağıdaki sonuçlar o rapordan sonraki değişikliklerdir.

16 MOD ve PH-00–PH-06 tam hedef olarak korunur. Bu paket yalnız ilk güvenlik/bağlantı hazırlığı dilimidir. G0 OPEN, runtime NOT_RUN ve first13 0/13; insan/ürün kabulü üretilmedi. GUNCEL kaynakları veya A manifesti değiştirilmedi.

## Uygulanan davranışlar

1. `run_title_oracle` gerçek runtime girişi, enrolled ayrı güven sınırı henüz bağlanmadığı için aday kodu çalıştırmadan `ENROLLED_ISOLATED_VERIFIER_REQUIRED` ile reddeder. Kaynak testleri ayrı `run_source_title_oracle` fonksiyonuna alındı. Bu yol yalnız güvenilir repo test örnekleri içindir; keyfi model çıktısı için sandbox değildir.
2. Kaynak raporu `execution_class=SOURCE_TEST`, `acceptance_eligible=false`, `isolation=NOT_ESTABLISHED` taşır. Candidate, oracle, harness ve runner SHA256 kaydedilir; candidate ölçülen exact byte kopyasından çalıştırılır. Oracle-pin bypass parametresi kaldırıldı.
3. `BoundedCandidate` sınırlı kuyruklarla stdout/stderr tüketir. Supervisor threadi bloklayan pipe okumasına girmez. READY, vaka cevabı ve toplam deadline; satır/toplam/stderr bayt sınırları; bounded yazma ve exit kontrolü eklendi. Hatalı protokol tüm koşumu FAIL yapar. Windows'ta child kill/wait vardır; tam process-tree/cgroup/identity izolasyonu kanıtı yoktur. POSIX process-group cleanup kaynağı var, Linux kabulü bu tur yapılmadı.
4. Protokolde rastgele request ID, exact cevap şeması, duplicate-key ve nonfinite ret, exact tip karşılaştırması ve exit0 şartı var. Bunlar dosya gizliliği yerine geçmez. Saldırganın CASES dosyasını okuyabildiğini gösteren regresyon bilerek korunur: SOURCE_TEST içinde 13/13 üretebilir, gerçek kabul yetkisi edinemez. K01 için OS gizlilik açığı kapanmış sayılmadı.
5. `IndependentVerificationPipeline` SOURCE_TEST raporunu DB bağlantısından/imzadan önce reddeder. Runtime iddiası tek başına yeterli değildir; exact 13 check seti, digest ve trusted supervisor tarafından verilen `receipt_validator` gerekir. Bu validatorun gerçek enrolled implementasyonu bu pakette yoktur; varsayılan yol kapalıdır. Önceki native ingest→seal→provenance→accept zinciri korunur; fake-driver testi yalnız bağlantıyı sınar.
6. `read_secret_bytes` için path bypass ve varsayılan uid kaldırıldı. Yalnız explicit owner ile enrolled directory fd yolu kabul edilir; uid0 değeri 999'a çevrilmez. Linux izin kontrolleri mevcut owning `read_enrolled_key` üzerinden uygulanır.
7. Consent yardımcı fonksiyonu bounded belge okur; güvenilir dış pin, beklenen workspace ve root record ister, mevcut `OwnerConsentBinding.check` üzerinden doğrular. Yanlış insan/workspace/pin ve duplicate JSON reddedilir. `authority_granted=false`, independent identity NOT_VERIFIED kalır. Betiğin kendi belgesinden hash türetmesi güvenilir pin haline gelmedi; E2E call-site bağı hâlâ açık ve önkontrolde görünür.
8. `tools/workflow_preflight.py` workflow betiğini çalıştırmadan owning `company_os` import ve doğrudan çağrı imzalarını kontrol eder; exact source pinleri verir. 43 çağrı kontrol edildi, 1 dinamik çağrı atlandı, 17 uyumsuzluk bulundu. Method/return şeması ve bütün dinamik çağrılar için tam semantik analiz değildir.
9. E2E wrapper, mount/DB/systemd komutlarından önce bu önkontrolü çalıştırır ve exit2 döner. Trial `main()` girişinde de aynı önkontrol yer alır. Wrapperın hiçbir OS komutu çağırmadığı regresyon testinde doğrulandı. Trialın doğrudan gerçek Linux import/çalıştırılması yapılmadı.

## Doğrulama

| Komut | Sonuç | Kanıt sınıfı |
|---|---|---|
| `C:\Python314\python.exe -B -m pytest AiProjeOfisi/tests -q -rs` | exit0; **104 PASS, 4 SKIP, 105 subtest PASS**, 4.05 s | Windows UNIT / FAKE_DRIVER / yerel SOURCE_TEST |
| `C:\Python314\python.exe -B AiProjeOfisi/tools/workflow_preflight.py` | exit2, BLOCKED; 17 çağrı uyuşmazlığı | AST/signature; runtime kabulü değil |
| `C:\Python314\python.exe -B AiProjeOfisi/tools/run_disposable_e2e_workflow.py` | exit2, BLOCKED_BEFORE_ENVIRONMENT_SETUP | Önkontrol ret yolu; DB/mount başlatılmadı |
| `C:\Python314\python.exe -B GUNCEL/DOGRULA.py` | exit1; CALISMA_DURUMU.md hash uyuşmazlığı sürüyor | A tabanı bütünlük engeli; PASS verilmedi |

Dört SKIP engine socketpair, Linux FIFO/selectors ve iki Linux secret fd/owner/mode testidir. Bunlar dört rootless/cgroup testi değildir. Test artışı bütün modüllerin AC kabulü sayılmaz. Ham loglar `evidence/CODEX_UYGULAMA_20261111_*.log`; komut/exit/log hashleri CHECKS.json içinde, A doğrulama logu ayrıca kayıtlıdır.

Gözlenen ortam Python3.14.3 / Windows / Pydantic2.12.5. requirements.txt hedefi2.14.0; bu fark korunarak raporlandı. Global kurulum veya bağımlılık değiştirilmedi. Bugünkü test başarısı hedef Linux/Pydantic2.14.0 ortamının qualification kanıtı değildir.

Negatifler: READY/vaka cevabı newline vermeme; stdout/stderr taşması; bozuk JSON/yanlış request ID; candidate boyut sınırı; runtime girişinin spawn öncesi reddi; kaynak PASS'in kabul reddi; sahte runtime etiketi; validator yokluğu/ret; check-set/digest bozulması; path ve owner bypass; yanlış consent insan/workspace/pin/duplicate-key; ortam kurmadan E2E reddi. Doğru aday SOURCE_TEST PASS ve baseline 8/13 FAIL korunur.

## TaskSpec ve izlenebilirlik

| Alan | TASK-CODEX-20261111-01 |
|---|---|
| Amaç / MOD / faz | Verifier raporunun otorite sınırı ve bounded transport; MOD-008/009/016, PH-03 |
| REQ / BR / AC / TEST | REQ-010/011, BR-010/011, AC-010/011, TEST-010/011; tüm AC'nin kapanışı değil |
| Girdi | Mevcut MOD-008 kodu, doğru/baseline/mutant fixtureları, 11 Kasım negatif incelemesi |
| Çıktı | Source/runtime ayrımı, transport, kabulden önce validator portu, regresyonlar |
| Allowlist | company_os/verifier_runner.py, candidate_runner.py, yeni bounded_candidate.py; tests/unit/test_verifier_runner.py, yeni test_verifier_boundary.py |
| Başlangıç pinleri | evidence/CODEX_UYGULAMA_20261111_BASE.json; yeni dosyalar başlangıçta ABSENT |
| Bağımlılık | Gerçek kabul için ayrı enrolled process/fixture/profile/receipt validator; bu pakette sağlanmadı |
| Çıkış | Kaynak negatifleri PASS; source raporu imzalanmadan/DB açılmadan ret; gerçek güven sınırı OPEN |
| Durum | KISMEN/KAYNAK_HAZIR; runtime gerçek izolasyon ve validator bağlantısı BEKLIYOR |

| Alan | TASK-CODEX-20261111-02 |
|---|---|
| Amaç / MOD / faz | Anahtar/consent bypassını kaldırma; MOD-001/015/016, PH-01 |
| REQ / BR / AC / TEST | REQ-004, BR-004, AC-004/012, TEST-004/012; seçili alt sınırlar |
| Allowlist | company_os/secret_adapter.py, consent_binding.py; tests/unit/test_secret_adapter.py, test_consent_binding.py |
| Girdi / çıktı | Mevcut enrolled-key/consent binding → yardımcı APIler aynı kontrolleri taşır |
| Bağımlılık | Explicit trusted fd/owner/pin/workspace/root record; gerçek identity/custody ayrı |
| Negatif / çıkış | Yanlış insan/workspace/pin/duplicate JSON ve path bypass ret; uid0 korunur |
| Durum | KISMEN/KAYNAK_HAZIR; Linux izin ve E2E caller entegrasyonu ACIK |

| Alan | TASK-CODEX-20261111-03 |
|---|---|
| Amaç / MOD / faz | Owning API uyuşmazlığını ortam etkisinden önce yakalama; MOD-001/003–009/015/016, PH-01–03 hazırlık |
| Allowlist | Yeni tools/workflow_preflight.py, tools/__init__.py; tools/run_disposable_e2e_workflow.py, disposable_e2e_workflow_trial.py; yeni tests/unit/test_workflow_preflight.py |
| Girdi / çıktı | Trial AST + owning Python imzaları → pinli bulgu listesi ve erken ret |
| Negatif / çıkış | Hatalı çağrıda BLOCKED; wrapper hiçbir OS komutu çağırmaz; doğru fixture SOURCE_CALLS_COMPATIBLE olsa da runtime_ready false |
| Bağımlılık | PilotSession'ın mevcut portları ve gerçek scope/profile/lease/stop bağları |
| Durum | ONKONTROL_KAYNAK_HAZIR; 17 E2E call-site düzeltmesi ve actual runtime ACIK |

Ortak doküman allowlisti: PLAN.md, UYGULAMA_DURUM_MATRISI.md, bu rapor ve yalnız CODEX_UYGULAMA_20261111 önekli yeni kanıtlar. Kaynak/test başlangıç hashleri BASE.json, son pinler MANIFEST.json içinde. Önceki Antigravity/Codex kayıtları silinmedi. Bu paket kendi testlerini raporlar; ayrı bağımsız inceleme tamamlandı iddiası yoktur.

Rollback: yalnız bu paketin değişikliklerini geri alıp başlangıç pinleriyle karşılaştır; yeni dosyaları kaldırmadan önce başka bağımlılık/yazıcı olmadığını doğrula. G0/grant/epoch veya harici etkileri geri sarma. Git metaverisi yok; BASE hashleri içerik yedeği değildir ve otomatik rollback paketi sunulmadı. Eski ağaca runtime import veya genel manifest yenileme ile geri dönüş yapılmamalı.

## Mevcut görevlerin güncel durumu ve devam

- TASK-20261110-P0-1: Tamamlandı sayılmaz. Deadline/protokol/source-accept ayrımı uygulandı; gerçek bağımsız aday gizliliği/OS izolasyonu ve enrolled receipt validator açık.
- TASK-20261110-P0-2: Tamamlandı sayılmaz. Önkontrol artık gerçek kaynaklardan 17 çağrı uyuşmazlığı çıkarıyor; owning API wiring henüz düzeltilmedi. İsim/compatibility shim eklemek çözüm olarak kullanılmayacak.
- K04: Kaynak helper bypassları düzeltildi, kaynak negatifleri PASS; gerçek Linux fd/custody/enrollment kabulü yok.
- K07/K08: Tarihli ekler yazıldı; bütün modül kartlarının tam TaskSpec/kanıt uzlaştırması ve A manifest kök nedeni açık.
- V1: Panel kaynağı bu pakette değiştirilmedi; görsel denetim yapılmadı. V2: gerçek runtime NOT_RUN.

Sıradaki kaynak bağlantısı mevcut `composition.PilotSession` etrafında trusted worker/controller auth, `EngineBinding`, üç signer, directory fd, immutable source snapshot, `lease_state` ve stop portunu tamamlamaktır. E2E betiğindeki ikinci/uyumsuz Broker ve pump wiringini buna uyarlamak gerekir; ardından enrolled verifier receipt validator ve ayrı OS sınırı bağlanır. Gerçek ortam önkoşulları karşılanmadan test/mock değerleri gerçek profile çevrilmez. PH-05 operasyon/restore ve PH-06 katalog/hafıza/WorkType işleri tam hedefte kalır.
