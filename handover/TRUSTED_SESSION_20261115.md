# Güvenilir oturum bağlantısı ve demo ayrımı — 2026-11-15

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-15
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_TESTS_AND_NATIVE_DENIAL; LIVE_OWNER_LOGIN_NOT_ACCEPTED
Kanıt: evidence/runs/trusted-session-20261115/; evidence/runs/browser-8dbf5303/TASK_SCREEN_20261114_browser.json

## Uygulanan değişiklikler

1. scripts/serve_configured_ui.py içindeki doğrulanmamış InteractiveDemoBackend emekliye ayrıldı. Son kaynak sürümü SHA256 ile tarihsel, çalıştırılmayan .txt kanıtı olarak korundu. Başlatıcı importta servis açmaz; mevcut kernel_binding.main üzerinden --profile ve dışarıdan onaylı --sha256 gerektirir. Profil olmadan fake SUCCEEDED veya execution_verified=True üretmez.
2. company_os.kernel.session_provisioning.issue_committed_owner_session supervisor-only bağlantısı eklendi: idle/non-autocommit ve exact non-superuser/non-bypass/non-createrole login, SERIALIZABLE transaction, mevcut native root/clock/membership kontrolüyle issue_owner_session, commit, farklı bağlantıda generation/expiry/token-hash/principal/tenant/session-scope-lock readback. Token sonuçta veya logda yok. Lost ACK veya post-commit readback hatası yeniden issue edilmez; ProvisioningOutcomeUnknown ile reconciliation gerekir. Root süreleri ve grant/membership kayıtları değiştirilmez. Pozitif protokol testleri DB-API doubles kullanır; bu gerçek insan kimliği veya canlı session kabulü değildir.
3. scripts/development/run.py doctor --summary eklendi. Windows'ta mevcut Ubuntu-E/aipof-dbtest salt okunur audit'ini çalıştırır. Tanı root host/boot/wall window, bootstrap expiry ve session sayımlarını ayrı gösterir. OS/DB saat karşılaştırması sadece tanıdır; native authorization yerine geçmez. CONSUMED bootstrap yeniden kurulum/recovery sayılmaz.
4. Eski demo süreci 6072 kimliği doğrulanıp durduruldu; mevcut ürün tasks sunucusu 8766'da PID30684 ile açıldı. Bağımsız /api/connection readback configured=False/execution_verified=False verdi. Bu canlı UI konfigürasyon kontrolüdür; gerçek Kernel yazma kabulü değildir.

## Eşzamanlı kaynak çakışması

Çalışma sırasında Antigravity scripts/serve_configured_ui.py dosyasını yeniden demo ile yazdı. Üzerine hemen yazılmadı; kullanıcıya bildirildi. Kullanıcı diğer ajanın çalışmasının bittiğini söyledi. Son dosya yeniden okunup SHA256=c08428d0764042bb1da2297d8a45b85a9b8b4fc26a144abc8375fb4e10716bc7 ile korundu ve karşılaştırma sonrası gerçek başlatıcıya geçirildi. Diğer ajanın kaynakları sessizce sıfırlanmadı. Bu süreçte DB'deki session sayısı33/unexpired_unrevoked1 gözlendi; bu kayıt bu çalışmada üretilmedi, kökeni doğrulanmadı.

## Native ve kaynak kanıtı

- Yeni session readback SQL'i mevcut PostgreSQL18.6 şemasında READ ONLY EXPLAIN ile planlandı. Uygulama mutasyonu yapılmadı; canlı pozitif oturum kabulü değildir.
- Gerçek PostgreSQL'de yeni wrapper mevcut privileged login ile EXACT_LEAST_PRIVILEGE_SESSION_LOGIN_REQUIRED verdi. Önce/sonra session ve grant sayıları aynı: native-login-denial.json. Admin fallback ile ürün yürütülmedi.
- readiness.json snapshotı: root boottime/wall window kapalı; bootstrap unexpired0; consumed1. Süre açısından açık session satırı yetkili native login kabulü değildir.
- tests/unit/test_committed_session.py: commit/readback, lost ACK, wrong hash/lock/generation/revocation, unsafe login/root expiry ve invalid input testleri.
- tests/unit/test_installation_readiness.py: tanı, tarihsel root yanında yeni root değerlendirmesi, canonical ve legacy launcherın profile zorunluluğu.
- Son tam koşum: Windows270 test/249 başarılı/20skip/1FAIL; Linux270 test/269 başarılı/1FAIL. Tek failure, serve_standalone.py dosyasının sonrasında yeniden InteractiveDemoBackend ile değiştirilmesini yakalayan regresyondur. Son ham koşumlar ve layout kanıtları bu dilimin evidence dizinindedir. Çakışmayan altı Python dosyasında Ruff check/format PASS; sonradan değişen standalone dosyası kabul edilmedi. Tarayıcı9 senaryo PASS; pozitif command senaryoları mock olarak etiketli.

## Gerçek açık engel ve sıradaki iş

İncelenen mevcut kaynakta yalnız onay eksikliği yoktur: 016_R55_SETUP_MANDATE_NATIVE_CANDIDATE.sql arm yolu installation_bootstrap_control içine INSERT yapar. 027_R56_BOOTSTRAP_NATIVE_CANDIDATE.sql initial_write mevcut tenant için PREEXISTING_TENANT_NOT_FRESH_BOOTSTRAP üretir. Mevcut tüketilmiş bootstrap'ı yeniden çalıştırmak veri koruyan normal owner-session yenileme/recovery yolu değildir. Owner session yazıcısı halen geçerli root ve e0 mandate ister. Desteklenen owner-auth/recovery yaşam döngüsünün mevcut mimari kararlarla eşleştirilip eksik native/adapter yolunun uygulanması gerekir; yalnız 'insan onayı verildi, süreyi uzat' çözümü yoktur. Yeni kimlik/custody kanıtı ajan tarafından icat edilemez.

Sıra: gerçek owner-auth/recovery yolu ve gerekli bağımsız kimlik/custody girdileri → least-privilege provisioning/HTTP bağlantısı → panel kalıcı Objective/Plan/Task ve bağımsız readback → READY/scheduler → rootless worker/model/Broker → bağımsız verifier/acceptance. Tam16MOD/PH00–06 korunur; G0OPEN,first13 0/13 değişmez. Bu dilim tüm ürünün tamamlandığı iddiası değildir.

## Uzlaştırma ve son başlatma

Kullanıcının diğer ajanın çalışmasının bittiği teyidinden sonra ikinci demo scripts/serve_standalone.py de incelendi; aynı sahte authority/receipt yolu vardı. Tarihsel .txt kopyası korunup gerçek Kernel profil başlatıcısına geçirildi. Üç yalnız inspect.getsource/getsourcelines yapan geçici script, referansı bulunmadığı kontrol edilerek .runtime/trials/source-inspection-20261115 altına taşındı; silinmedi veya manifestte sessizce onaylanmadı. Son eski demo süreci18856 da kimliğiyle durduruldu. Ürün tasks sunucusu son olarak PID40248 ile 8766'da başlatıldı; son durum panel-state.json dosyasına tekrar okunur. Hem legacy girişin importta servis açmaması ve profilsiz DB'ye gitmemesi regresyon testiyle korunur.

## Tarihsel eşzamanlı kaynak engeli — aşağıdaki son bölümde çözüldü

Kullanıcının bitti teyidinden sonra serve_standalone.py 15:30:12'de tekrar InteractiveDemoBackend içeren2673byte dosyaya dönüştü. Yeni düzeltme üzerine yeniden yazılmadı; kullanıcıdan diğer çalışmayı açıkça durdurması istendi. İlgili regresyon iki ortamda da bu yüzden FAIL; beklenen güvenli pin korunur ve mevcut dosya ile uyuşmazlık gizlenmez. 'İki başlatıcı da artık güvenli' önceki ara durumdur, son durum değildir. serve_configured_ui.py güvenli; standalone çakışması açık. Oturum transaction, doctor ve canonical kernel yolu tamamlanıp ayrı test edildi. Tam ürün veya tam kaynak kapısı PASS ilan edilmez. Kaynak engeli çözülmeden scriptlerin tekrar başlatılması güvenilir değildir.

## Nihai sonuç — kullanıcı durdurma teyidi sonrası

Kullanıcı "durdurdum" teyidi verdi. Son standalone kaynağı f150e4fb915f9a274f51e976f044f7a61fa220ab6724d25357f40e4df7e73044 SHA256 ile .runtime/trials/retired-demo-20261115 altına .py.retired olarak taşınıp korundu; gerçek profil başlatıcısı geri kondu. Her iki giriş inert ve profilsiz DB erişimsizdir. Uzlaştırılmış tam koşumlar: Windows270 test/250 başarılı/20skip; Linux270 başarılı. Layout PASS. Ardından davranışı değiştirmeyen tuple[object,...] tip açıklamasıyla Mypy hatası giderildi; Mypy1.10 ilgili oturum dosyasında PASS, hedefli20 regresyon PASS, yedi değişen Python dosyasında Ruff check/format PASS. Proje geneli Mypy kabulü iddia edilmez.

panel-state-final.json: 8766'da configured=False/execution_verified=False, 8770 kapalı. readiness-final.json güncel tanı snapshotıdır. windows-reconciled.log ve linux-reconciled.log başarılı ham koşumlardır; eski başarısız koşumlar tarihsel olarak korundu. Eşzamanlı dosya çakışması kapanmıştır. Owner-auth/recovery, gerçek least-privilege oturum/HTTP ve gerçek model/izolasyon kabulü açık kalır; G0 ve first13 yükseltilmedi.
