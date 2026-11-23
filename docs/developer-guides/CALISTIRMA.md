# Çalıştırma ve doğrulama

Komutlar E:\Projeler\Ai_Proje_Ofisi kökünden çalıştırılır. Başlatıcı yalnız güncel kaynak köklerini ekler; AiProjeOfisi/GUNCEL/ARSIV üzerinden runtime yüklemez.

```powershell
C:\Python314\python.exe -B scripts/development/run.py tasks --port 8766
C:\Python314\python.exe -B scripts/development/run.py progress
C:\Python314\python.exe -B scripts/development/run.py preview
C:\Python314\python.exe -B scripts/development/run.py verify
C:\Python314\python.exe -B scripts/development/run.py preflight
C:\Python314\python.exe -B scripts/verification/verify_layout.py
```

Görev ekranı: http://127.0.0.1:8766; ilerleme: /progress; ofis: /office. Varsayılan sunucu gerçek backend, oturum, model veya ajan oluşturmaz; gönderim kapalıdır.

Yetkili mevcut Kernel bağlantısı için:

```powershell
C:\Python314\python.exe -B scripts/development/run.py kernel --profile ONAYLI_PROFIL_YOLU --sha256 ONAYLI_SHA256 --check-only
```

Profil ve hash dışarıdan onaylanmalıdır. Bu örnekte gerçek profil veya sır bulunmaz. --check-only metadata/bağlantı kontrolüdür; oturum/iş kabulü değildir.

Kaynak geliştirme bağımlılığı pyproject.toml içindedir; mevcut Windows kontrolleri pydantic 2.12.5 kullanır. Gerçek DB bağlantısı için isteğe bağlı database bağımlılığı psycopg 3.3.4'tür. Bu geçişte paket kurulmadı veya mevcut ortam değiştirilmedi. Kaynak paketinin kurulabilmesi bağımsız üretim kurulumu/asset dağıtımı kabulü değildir.

Linux kaynak kontrolü mevcut özel test ortamında:

```powershell
wsl.exe -d Ubuntu-E --user aipof-dbtest --exec /mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/kernel-linux314/bin/python -B /mnt/e/Projeler/Ai_Proje_Ofisi/scripts/verification/verify_source.py
```

Yerel DB'yi değiştirmeyen durum kontrolü:

```powershell
.\scripts\database\manage_local_postgres.ps1 inspect
```

prepare/initialize, migration veya fixture betiklerini sıradan başlatma komutu olarak çalıştırma. Süreç/DB başlatma ve fixture koşumları ayrı etkiler taşır. Gizli anahtarlar, DB data, gerçek profiller ve bağımsız verifier oracle'ları depo dışında kalır.


## Kurulum ve oturum tanısı

`C:\Python314\python.exe -B scripts/development/run.py doctor --summary` salt okunur gerçek WSL/DB tanısıdır; session sayımı ile root/bootstrap engellerini ayırır. [Owner oturumu rehberi](../operations/OWNER_OTURUMU.md). Legacy serve_configured_ui.py artık --profile/--sha256 ile gerçek Kernel başlatıcısıdır; demo başarı üretmez.
