# Bakım Kaydı — GUNCEL/DOGRULA.py Hash Uyuşmazlığı (2026-11-26)

- **Canonical workspace:** `E:\Projeler\Ai_Proje_Ofisi`
- **Tarih:** 2026-11-26
- **Durum:** `OPEN_MAINTENANCE_TRACKED` (aktif ürünü etkilemez)
- **Kapsam:** Eski A referans doğrulayıcısı (`GUNCEL/DOGRULA.py`)

## Gözlenen Kanıt

`C:\Python314\python.exe -B GUNCEL/DOGRULA.py` koşumu şu uyuşmazlıkla sonlanır:

- **Dosya:** `GUNCEL/dokumanlar/hedef-mimari-v1/CALISMA_DURUMU.md`
- **Manifestte beklenen SHA-256 (`GUNCEL/SOURCE_MANIFEST.json`):** `061f96f5cff767e1158041f8a64f19bd35b8f59e747ba5dd21119b3daeb9f4e6`
- **Diskteki güncel SHA-256:** `fb9f4e0ab4af1294cf4f30b31d4831157ffc8c6769e599567e570526d935b2bf`

## Politika ve Sınır

1. Kök `AGENTS.md` kuralı gereği bu bilinen hash uyuşmazlığı `SOURCE_MANIFEST.json` otomatik veya körlemesine yenilenerek kapatılmaz.
2. Aktif ürün (`product/`, `contracts/`, `verifier/`, `database/`) bu dosyaya runtime bağımlılığı taşımaz; aktif kaynak bütünlüğü `scripts/verification/verify_layout.py` ve `scripts/development/run.py verify` üzerinden doğrulanır.
3. Eski A referans paketinde tarihsel/dokümantasyon uzlaştırması yapıldığında bu kayıt kaynak gerekçesiyle birlikte güncellenir veya kapatılır.
