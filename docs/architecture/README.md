# Mimari giriş

Güncel uygulama product/backend ve product/frontend altındadır. Ortak sözleşmeler contracts/source/python içindedir. Bu yer değişikliği mimari sürüm veya teknoloji değişimi değildir.

- [Sürümlü ana mimari](../../GUNCEL/dokumanlar/AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v0.16.2-r68.md)
- [Tam hedef tasarım — 16 modül/PH-00–PH-06](../../GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md)
- [Kaynak pini](architecture-source.json)
- [Modül eşlemesi](../../catalog/sources/MODULE_MAP.json)
- [Geçiş planı](../migration/MIGRATION_PLAN.md)

Ana mimari halen GUNCEL içinde tek asıl kopyadır. Burada ikinci master oluşturulmadı. Kernel tek kanonik domain writer; Broker tek dosya/araç sınırı; verifier bağımsız verdict üretir; yetkili acceptance Kernel üzerinden kaydedilir. Ücretsiz yerel varsayılan korunur.
