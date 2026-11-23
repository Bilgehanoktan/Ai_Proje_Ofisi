# Linux supervisor descriptor sahipliği ve ortam envanteri

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-12
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_LINUX_PARENT_FD_TEST; tam runtime NOT_RUN; bağımsız review PENDING
Kanıt: evidence/CODEX_FD_20261112_windows_tests.log; evidence/CODEX_FD_20261112_linux_tests.log; evidence/CODEX_FD_20261112_linux_inventory.json; evidence/CODEX_FD_20261112_preflight.json; evidence/CODEX_FD_20261112_manifest.json.

## Görev ve mimari sınır

TASK-CODEX-20261112-03; MOD-004/005/015/016 seçili supervisor/cleanup alt davranışı; PH-02/03. Dayanak mevcut hedef tasarım §16/27, kanonik portlar ve CODEX_KANONIK_AKIS_20261112.md. Tam16MOD/PH00–06 hedefi korunur; yeni modül/departman, izin/grant/SQL veya mimari onay üretilmedi.

## Doğrulanan hata ve düzeltme

PipeTransport.from_observation önceki kaynakta constructor başarısız olsa bile finally içinde özgün pipe fdlerini kapatıyordu. composition.from_launch_observation ise handoff_state alanını yalnız başarılı dönüşten sonra işaretliyordu. Böylece workflow cleanup, pipe sahibi hâlâ supervisor sanıp kapanmış veya yeniden kullanılmış fd numaralarını tekrar kapatabiliyordu. Bu kaynak karşıörneği, constructor hatası sonrası aynı fd numarasını gerçek Linux os.dup2 ile yeniden kullanarak test edildi.

from_observation artık orijinal fdlerin tüketilme sahipliğini ilk dup/close öncesinde yayınlar; constructor hatasında da işaret kalır. Buradaki pipes_transferred=true, özgün pipe sahipliğinin tüketildiğini ifade eder; canlı transport veya başarılı worker kanıtı değildir. Özgün fdlerden birini kapatma başarısız olursa kalanlarını da dener ve UNKNOWN döner; yeniden kapatmayı önermez.

company_os/supervisor_handles.py içinde somut LaunchObservationCloser eklendi. Supervisor observationı aktarım öncesinde kaydeder; pidfd türü, non-inheritable fdler, üç ayrı FIFO ve okuma/yazma yönleri kontrol edilir. Kayıtlı fd kimliği değiştiyse o fd kapatılmaz, hata UNKNOWN kalır; diğer sahip olunan fdlerin cleanupı denenir. Başarılı veya hatalı kapanıştan sonra fd numaraları yeniden kapatılmaz. Handoff sonrasında supervisor yalnız pidfd kapatır; transport kendi çoğalttığı pipe fdlerini yönetir. Bunlar cleanup korumalarıdır; worker kimliği veya izolasyonu doğrulamaz.

PilotWorkflow kayıt işlemini activation/handoff öncesinde çağırır. close_observation verilmezse Linux somut closer kullanılır; SOURCE_TESTlerde açık fake port sağlanabilir. Linux dışı varsayılan closer reddedilir. Gerçek observer/verifier yerine fake başarı eklenmedi.

## Ölçülen testler

Windows:158test,149PASS9LinuxSKIP,exit0. Önceki4LinuxSKIPe yeni5gerçek parent-fd testi eklenmiştir.

Linux Ubuntu-E, mevcut aipof-dbtest uid/euid999, Python3.14.4/Pydantic2.14.0:158PASS0SKIP,exit0. Beş yeni test gerçek os.pipe/os.pidfd_open/os.fstat/os.dup2 işlemleriyle bu test sürecinin parent handlelarını sınadı. Üç platform/port-hatası ve iki workflow bağlantı testi de eklendi. Testlerdeki process pidfdi test sürecine aittir; gerçek ajan veya bağımsız verifier çalıştırıldığı iddia edilmez. SOURCE_TEST candidate subprocessleri ve DB/OS doubles önceki test kapsamını korur; PostgreSQL/Kernel fiziksel zinciri koşulmadı.

Aktif preflight6doğrudan imza/2dinamik atlama/29introspect edilemeyen çağrı;0finding/exit0. Instance-method ve değer doğrulaması AST kapsamı dışındadır; runtime_ready=false.

## Salt okunur Linux envanteri

Yeni tools/inspect_linux_supervisor.py environment inventory üretir; profil yaratmaz, servis/worker kurmaz, runtime qualification veya onay vermez. uid999 koşumunda stdout JSON, child exit2; dış WSL Python/test capture komutu exit0. Önceki doğrudan WSL çağrısının dış exit1 sonucu child exit2 ile aynı şey değildir.

Ölçülenler:config/profiles altında JSON yok; uid/euid999; user namespace inode4026531837; uid_map 0→0/4294967295; cgroup0::/init.scope; cgroup kökü os.access yazılabilirlik ipucu false. Bu ipucu delegation veya enforcement testi değildir. İncelenen observer/test sürecinde NoNewPrivs0/Seccomp0/CapEff0 görülür; bunlar launch edilmiş workerın özellikleri diye sunulmaz. Varsayılan WSL oturumunun uid0 olduğu ayrı salt okunur ölçümde görüldü; testler uid999 ile yapıldı. WSL user-session başlangıcında 'Failed to start the systemd user session for aipof-dbtest' uyarısı verdi; kullanıcı servisi onarılmadı veya kabul edilmiş sayılmadı.

Runtime profile, enrolled observer/receipt validator/runtime verifier, trusted clock/signer/profile bağları ve rootless namespace/cgroup fiziksel kabulü açık. Dolayısıyla G0OPEN,first13 0/13; tam modül veya insan kabulü yok. DB/model/uygulama workerı başlatılmadı; WSL kendi kullanıcı oturumu açmayı denedi ve uyarı üretti. GUNCEL/DOGRULA.py eski CALISMA_DURUMU.md hash hatası bu dilimde yeniden test edilmedi:REPORTED_NOT_RETESTED.

## Devam ve geri dönüş

Sıradaki iş, kaynakta eksik observer/validator/runtime-verifier implementasyonlarını ve izinli rootless ortam profilinin qualification bağlarını tamamlamak; gerçek profil değerlerini veya insan enrollmentını varsaymamak. Profil dosyası oluşturmak tek başına qualification değildir. Eksik namespace/delegation/bağımsız kimlik kanıtı kapatılmadan actual ilk13 koşumu başlatılmaz.

Değişen önceki kaynaklar evidence/CODEX_FD_20261112_BACKUP altında byte-exact saklandı. Güncel kaynak/rapor/test/kanıt SHA256 pinleri manifesttedir. Otomatik rollback yapılmadı; concurrent değişiklik overwrite edilmez; DB/epoch/grant geri sarılmadı.
