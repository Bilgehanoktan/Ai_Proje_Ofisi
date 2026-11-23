# Kanonik ilk SOFTWARE akışı bağlantısı

Canonical workspace: E:\Projeler\Ai_Proje_Ofisi
Tarih: 2026-11-12
Kaynak ajan: Codex
Durum: VERIFIED_SOURCE_AND_FAKE_DRIVER; bağımsız review PENDING; runtime NOT_RUN
Kanıt: evidence/CODEX_WORKFLOW_20261112_tests.log; evidence/CODEX_WORKFLOW_20261112_preflight.json; evidence/CODEX_WORKFLOW_20261112_cli.log; evidence/CODEX_WORKFLOW_20261112_manifest.json.

## Kapsam ve sonuç

TASK-CODEX-20261112-02; mevcut tasarım §16, BR-001; MOD-004/005/006/007/008/009/015/016, PH-02/03 seçili bağlantılar. Tam16MOD/PH00–06 hedefi korunur; tam modül kapanışı değildir. Önceki dilim CODEX_GUVEN_GIRDILERI_20261112.md.

company_os/workflow.py içinde PilotWorkflow eklendi. Mevcut CommittedController/Controller ve Kernel delivery guard portlarıyla imzalı ticket doğrulaması/one-shot intent → launch observation → LaunchActivation (mevcut process.launch_callback ve engine.bind rotaları) → kanonik PilotSession/Broker/patch receipt → stop → ProcessReconciler (bağımsız gözlem doğrulaması, mevcut process.reconcile rotası) → runtime verifier portu → mevcut IndependentVerificationPipeline seal/provenance/accept çağrıları bağlandı. Domain yazarı CommandHost/Kernel, dosya yazarı Broker kalır. Yeni SQL/izin/grant yaratılmadı.

LaunchActivation gerçek RUNNING/identity/isolation ölçümünü dış enrolled observer ve validator portlarından ister; CREATED_NOT_EXEC_ATTESTED tek başına RUNNING sayılmaz. ProcessReconciler kayıtlı bağımsız signer/gözlem doğrulaması ve EXITED/fenced/usage-zero ister; yalnız stop isteği yeterli değildir. Producer/controller verifier olamaz. Pipeline SOURCE_TEST veya ret edilmiş receipt ile kabul üretmez.

Bütün fazlar tek kullanımlıdır. Dispatch/callback commit belirsizliğinde respawn yok; effect commit kaybında yeniden dosya etkisi/cevap yok. Setup, stop ve descriptor cleanup hataları başarı diye sunulmaz. composition.from_launch_observation içindeki handoff_state, constructor hata verse bile pipe sahipliğinin supervisor tarafından bilinmesini sağlar; supervisor pidfd sahibi kalır. close_observation portu pidfd ve devredilmemiş pipe cleanup uygulamasını sağlamalıdır; gerçek FD/OS kabulü bu testlerde kanıtlanmadı.

## E2E girişinin taşınması

3200 satırlık sentetik/custom-port disposable_e2e_workflow_trial.py yerine ince supervisor girişi kondu. Önceki dosya ve wrapper evidence/CODEX_WORKFLOW_20261112_BACKUP altında byte-exact korunur. Eski15uyuşmazlık yedek üstünde regresyon testinde hâlâ görünür; bunlar tek tek eski gövdede düzeltilmiş veya aynı sayımın0olmuş hali diye raporlanmaz. Custom CommandHostRuntimePort, eski ctor çağrıları, doğrudan worker fallback ve sentetik provisioning aktif girişten çıkarıldı. Standalone wrapper artık SQL bootstrap/mount/DB startup/role cleanup çalıştırmaz. Ortam hazırlığı ve enrolled in-memory portlar trusted supervisor sorumluluğudur.

Giriş önce trusted consent/root/key kontrolünü, sonra sağlanan bootstrap readback installation/human eşleşmesini ister. Anahtar/onay belgesi rapora konmaz. Kullanıcı girdilerinden key/profile/identity/verifier kanıtı üretilmez.

## Doğrulama ve sınırlar

148 test:144PASS,4LinuxSKIP,exit0. 18yeni workflow testi ve1ek aktif preflight testi vardır. Pozitif testlerde gerçek Python Controller/CommittedController/TicketCodec/IntentJournal/LeaseRegistry/PilotSession/Broker/Kernel adapter/verification pipeline sınıfları, sahte DB/OS/observer/verifier portları kullanıldı. Sahte report üzerinde ACTUAL_RUNTIME etiketi yalnız pipeline negatif/pozitif kablolama testi içindir; gerçek bağımsız runtime raporu değildir. Test fixture auth/signers gerçek enrollment değildir.

Negatifler: bozuk ticket, yabancı process scope, producer=verifier, ölçüm ret, callback readback farkı, commit ack kaybı, çalışan süreç, unfenced workspace, SOURCE_TEST ve ret edilmiş receipt, eksik validator, setup sonrası pipe sahipliği, stop/cleanup hatası, tekrar çalıştırma. Test sayısı first13 kabul sayacı değildir.

Aktif preflight3kaynak dosyasını tarar;5imza çağrısı kontrol edildi,2dinamik kwargs çağrısı atlandı,29imzası introspect edilemeyen çağrı (ağırlıkla exception sınıfları) ayrıca sayıldı. Instance method/dinamik değerler AST ile doğrulanmaz; davranış testleri ayrıdır. SOURCE_CALLS_COMPATIBLE/0finding,exit0; runtime_ready=false. Önceki42çağrı/15uyuşmazlıkla payda aynı değildir.

Standalone CLI exit2:TRUSTED_SUPERVISOR_INPUTS_REQUIRED; ortam kurulmadı. Gerçek LinuxLauncher/rootless namespace/cgroup, bağımsız OS ölçüm adapteri/receipt validator, gizli-fixture runtime verifier, trusted clock/profile/signers, bootstrap readback ve gerçek DB/UI zinciri bu dilimde çalıştırılmadı. run_title_oracle runtime ret sınırı değiştirilmedi. G0OPEN,first13 0/13,insan kabulü yok.

GUNCEL/DOGRULA.py önceki aynı gün koşumunda CALISMA_DURUMU.md hash hatasında; bu dilimde tekrar koşulmadı, REPORTED_NOT_RETESTED. GUNCEL/SQL/STATE değiştirilmedi.

## Devam ve geri dönüş

Sıradaki teknik iş: kaynakta tanımlanan observer/validator/runtime-verifier/FD-close portlarının rootless enrolled Linux supervisor profiline bağlanması ve izinli gerçek pozitif/negatif/readback/cleanup kanıtı. Bunun öncesinde kaynak bağımsız incelemesi gerekir; kaynak PASS fiziksel ortam veya insan onayı yerine kullanılmaz. MOD-010/011 UI/reload ve sonraki fazlar kapsamda kalır.

Baseline yedekleri ve yeni kaynak pinleri manifestte. Dosya geri dönüşü yalnız mevcut pin aynıysa değerlendirilir; concurrent değişiklik overwrite edilmez. DB/epoch/grant rollback yapılmadı. Otomatik rollback çalıştırılmadı.
