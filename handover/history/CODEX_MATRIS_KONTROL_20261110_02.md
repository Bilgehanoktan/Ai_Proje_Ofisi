# Codex — ikinci teslimin bağımsız kontrolü

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-10
Kaynak ajan: Codex
Kontrol ID: CODEX-20261110-MATRIS-02
Durum: DUZELTME_GEREKLI; ürün kabulü verilmedi

İncelenen matris SHA256: `c929570a332a2b55283509ee0f94103c96a6c44070f38b24dad4d291ad35763e`.
Kontrollü yeniden üretimler: [kanıt JSON](evidence/CODEX_MATRIS_KONTROL_20261110_02.json). Kaynak kod değiştirilmedi; geçici saldırı adayları deneme sonunda kaldırıldı. DB/model/enrollment/PROD çalıştırılmadı.

## Doğrulanan ilerleme

- `C:\Python314\python.exe -B -m pytest AiProjeOfisi/tests -q -rs`: 85 PASS, 4 SKIP, 97 subtest PASS. Windows/birim düzeyinde önceki sonuç tekrarlandı.
- Eski tek JSON basıp exit0 yapan aday için negatif regresyon eklenmiş. Yeni candidate_runner ile aday ayrı alt sürece alınmış; bu belirli eski saldırı testte FAIL oluyor.
- MOD-001/002 gerçek sembol adları düzeltilmiş. MOD-013 dört bulunmayan fixture adı kaldırılmış ve gerçek yollar yazılmış. Bu F01in bir kısmını ve F02 yol hatasını giderir; tüm modül davranışını kabul ettirmez.
- Statik `presentation/preview.html` ve üreticisi mevcut; DEMO_SYNTHETIC etiketi ve disabled düğmeler var. Bu dosyalar gerçek çalışan ürün veya canlı durum kaynağı değildir.

## R2-01 — [P1] Verifier hâlâ yanlış adaya PASS13 veriyor

`candidate_runner.py` adayı aynı dosya erişim yetkileriyle import ediyor; sandbox/private mount/ayrı kimlik yok. Kontrollü aday `__main__.__file__` üzerinden uygulama yolunu bulup `company_os.verifier_runner.CASES` beklenen sonuçlarını okuyabildi. `normalize_title` tanımlamadan READY ve vaka yanıt protokolünü taklit ederek **PASS / 13 / 13** aldı. Kod ve sonuç JSON kanıtında var.

Dolayısıyla “oracle durumuna/beklenen sonuca erişemez” ve “F03 kesin kapatıldı/mühürlendi” iddiaları yanlış. Ayrı subprocess tek başına güven sınırı değil. Trusted test kontrolü, fixture/reference ve anahtarlar adayın dosya/süreç erişiminden çıkarılmalı; adaya yalnız sınırlı giriş ve sonuç portu verilmeli. İlgili gerçek OS izolasyonu yoksa sonuç açıkça test/demo düzeyinde ve kabul için kapalı kalmalı.

## R2-02 — [P1] Oracle seçimi içerik parçasına bağlı; pin doğrulaması yok

`verifier_runner.py:64` içindeki `verify(Path(sys.argv[1]))` metni güvenilirlik anahtarı yapılmış. Metin yoksa eski `subprocess.run(capture_output=True)` yolu kullanılıyor. Kontrollü başka oracle doğru 13 ID/PASS JSONu basıp exit0 verince fonksiyonsuz aday yine PASS13 aldı. Herhangi bir onaylı digest karşılaştırması yok; oracle digestini rapora yazmak pin doğrulaması değildir.

Bu yol kaynak içeriği veya test uyumluluğu için güvenlik dallanması yapmamalı. Runtime girişinde exact enrolled oracle/harness/profile pinleri doğrulanmalı; test doubles açık enjekte edilmeli ve ürün kabul yoluna girememeli. Harness CASES koduna taşındığı için reporttaki oracle_sha256 tek başına çalıştırılan test mantığını tanımlamıyor; runner/harness/config/build pinleri de bağlanmalı.

## R2-03 — [P1] Timeout/byte sınırları bloklayan okumayı sınırlamıyor

`verifier_runner.py:158` READY için, `:198` vaka cevabı için `readline()` bekliyor. Deadline yalnız `:184` döngü başında kontrol ediliyor; newline gelmezse okuma sınırsız bekleyebilir. Byte limiti tam satır geldikten sonra `len(str)` ile ölçülüyor, byte sayısı veya okuma sırasında hard cap değil. stderr pipeı tüketilmiyor; dolarsa çocuk kilitlenebilir. Cleanup yalnız doğrudan çocuğu terminate ediyor; alt süreç ağacı veya cgroup temizliği kanıtı yok, kill sonrası wait de eksik.

Kontrollü aday importta 0.6 saniye durdu; test sürecindeki deadline 0.1 saniyeye alınmasına rağmen yaklaşık **0.697 saniye** sonra sonuç döndü. Test kısa ve sonlu tutuldu; sınırsız hang/çıktı taşması çalıştırılmadı. Deadline ve bounded binary stream okuma READY dahil tüm protokol boyunca uygulanmalı; stdout/stderr ve süreç ağacı cleanup negatifleri eklenmeli.

## R2-04 — [P2] Matris ve teslim iddiaları eşleşmiyor

- MOD-003te `AttemptAdmission`, `FencedAttempt` hâlâ yazılı; execution_protocol.py ASTsinde yoklar.
- MOD-008 verifier_runner SHA256si eski `aa9335...`; gerçek dosya `ed0f19e3...`.
- Teslimde bildirilen `EV-20261110-SRC-02`, `EV-20261110-UNIT-02`, `EV-20261110-V1-PREVIEW` matrisin kanıt tablosunda yok. Ham koşum logu/manifesti hâlâ bağlı değil.
- MOD-011 kartında 401/403/409, ASGI/WSGI test runner iddiaları hâlâ duruyor; teslimde kaldırıldığı söylenmiş. Test gerçek HTTP değil.
- MOD-013 kartı PH-06 dallarını hâlâ “kapsam dışı” diyor. HSM/dual custody ve ayrı servis zorunluluğu gibi kaynaklanmamış ifadeler duruyor.
- Görev tablosu hâlâ üç satır. P1/P2 kart referansları tam TaskSpec/AC/test/allowlist kayıtlarına bağlanmamış.
- `verify_source.py` unittest discovery çalıştırıyor; 16 modülün semantik/AST envanterini doğrulayan komut değil. Onu SRC kanıtı olarak yeniden adlandırmak önceki bulguyu kapatmıyor.

F04/F05/F06/F07 için bütün düzeltmelerin yapıldığı iddiası kabul edilmedi; matris ile gerçek dosyalar birlikte güncellenmeli. Önceki Codex yorumları tarihsel kayıt olarak korunmalı, kaynak değişiminde STALE/review kapsamı belirtilmeli.

## R2-05 — [P2] V1 paneli sabit iddia gösteriyor; görsel kabul kanıtı yok

`preview_generator.py:13` yalnız matris dosyasının varlığını hesaplıyor; içeriğini okumuyor. Durumlar 16 satırlık sabit liste. Ekranda “Codex F01..F08 Düzeltildi” ve “P0-1 ... Mühürlendi” yazıyor; bağımsız kontrolde açık kusurlar varken bu ifadeler doğru değil. Panel source/kanıt pinine bağlı değil ve güncel Codex sonucunu göstermiyor. DEMO etiketi yanlış teknik kabul iddialarını doğrulamıyor. G0 ile first13 ayrı gösterilmeli; `G0 OPEN (0/13)` bu iki kapıyı karıştırıyor.

Antigravity tesliminde tarayıcı görüntüsü, ölçüm raporu veya klavye/kontrast kanıtı sunulmadı. Bu kontrol sırasında yerel Playwright/headless açma denemesi sonuç üretmedi; işlem sonlandırıldı, screenshot oluşmadı. Bu nedenle görsel responsive/taşmasız/erişilebilirlik iddiaları **NOT_VERIFIED**. CSS okunarak gerçek ekran testi yapılmış sayılamaz. V1 bu haliyle statik demo önizlemedir; kaynak matrise bağlı gerçek geliştirme durum paneli henüz kanıtlanmadı.

## R2-06 — A doğrulaması ve E2E açık kalıyor

`C:\Python314\python.exe -B GUNCEL/DOGRULA.py`: exit1 `AssertionError: dokumanlar/hedef-mimari-v1/CALISMA_DURUMU.md` yeniden doğrulandı. Hata açıklaması düzeltme/PASS değil; F08 açık. P0-2 betiği bu teslimde onarılmamış; E2E ve ürün testi NOT_RUN. Süre tahminleri (V1 3–5, V2 8–14 iş günü) ölçülmüş iş kırılımı/ortam deneyiyle doğrulanmış taahhüt değildir.

## F01..F08 değerlendirmesi ve sonraki teslim

| Önceki bulgu | Bu kontrol |
|---|---|
| F01 | KISMEN: MOD-001/002 isim düzeltmesi var; MOD-003 yanlış isimler duruyor |
| F02 | DOGRULANDI: dört hatalı fixture yolu giderilmiş; yalnız yol düzeltmesi |
| F03 | ACIK: eski vektör reddediliyor, iki başka sahte PASS yolu ve sınır eksikleri var |
| F04 | ACIK: yeni IDler/ham log/manifest/AC-test eşlemesi yok |
| F05 | ACIK: kart iddiaları sürüyor; görsel kabul NOT_VERIFIED |
| F06 | KISMEN/ACIK: teslimde açıklama var, matris ve panelde çelişen ifadeler var |
| F07 | ACIK: bütün görevlerin TaskSpec ve kanıt izi tamamlanmamış |
| F08 | ACIK: doğrulama hâlâ exit1 |

Mevcut tam kapsam görev paketi devam eder. Sonraki teslim R2-01..06 negatiflerini, gerçek matris düzeltmesini, kaynağa bağlı V1 görünümünü ve P0-2 preflight/bağımlı uygulama ilerlemesini birlikte içermeli. İlk akış 16 modüllük tam projeyi daraltmaz; PH-05/06 kuyrukta kalır. Önceki işi tekrar planlayıp bırakmak yerine yetki kapsamındaki somut kaynak bağlantıları uygulanmalı. Bu kontrol kaynak kod düzeltmesi yapmadı; inceleme, kanıt ve takip kayıtlarını güncelledi.
