# Kullanıcı onaylı hedef ağaç — 2026-11-14

Aşağıdaki metin onaylanan hedef öneridir. Gerçekleştirilen dosya eşlemesi SOURCE_TO_TARGET.json içindedir; henüz kodu bulunmayan alanlar boş uygulama gibi oluşturulmadı. Fiziksel ilerleme için MIGRATION_PLAN.md ve VALIDATION.md esas alınır.

Canonical workspace: `E:\Projeler\Ai_Proje_Ofisi`

Durum: Hedef klasör önerisi. Fiziksel taşıma henüz uygulanmadı.

```text
Ai_Proje_Ofisi/
│
├── product/                         # Ürün uygulamaları
│   ├── frontend/
│   │   ├── pages/
│   │   │   ├── dashboard/
│   │   │   ├── office/
│   │   │   ├── projects/
│   │   │   ├── objectives/
│   │   │   ├── plans/
│   │   │   ├── tasks/
│   │   │   ├── agents/
│   │   │   ├── approvals/
│   │   │   ├── artifacts/
│   │   │   ├── knowledge/
│   │   │   ├── budget/
│   │   │   ├── operations/
│   │   │   └── settings/
│   │   ├── components/
│   │   │   ├── navigation/
│   │   │   ├── forms/
│   │   │   ├── tables/
│   │   │   ├── charts/
│   │   │   └── status/
│   │   ├── office/
│   │   │   ├── engine/
│   │   │   ├── scenes/
│   │   │   ├── rooms/
│   │   │   ├── furniture/
│   │   │   ├── avatars/
│   │   │   ├── animations/
│   │   │   ├── interactions/
│   │   │   ├── camera/
│   │   │   └── projections/
│   │   ├── design-system/
│   │   │   ├── tokens/
│   │   │   ├── typography/
│   │   │   ├── themes/
│   │   │   └── icons/
│   │   ├── services/
│   │   │   ├── api/
│   │   │   └── events/
│   │   ├── state/
│   │   ├── assets/
│   │   ├── previews/                # Geçici ekranlar ve demo
│   │   ├── tests/
│   │   └── README.md
│   │
│   └── backend/
│       ├── company_os/             # Mevcut Python paket kimliği korunur
│       │   ├── api/
│       │   │   ├── http/
│       │   │   ├── authentication/
│       │   │   ├── commands/
│       │   │   ├── queries/
│       │   │   └── emission/
│       │   ├── kernel/             # MOD-001: tek kanonik domain writer
│       │   │   ├── command_host/
│       │   │   ├── authorization/
│       │   │   ├── sessions/
│       │   │   ├── grants/
│       │   │   ├── policies/
│       │   │   ├── idempotency/
│       │   │   └── transactions/
│       │   ├── planning/           # MOD-002
│       │   │   ├── objectives/
│       │   │   ├── plans/
│       │   │   ├── dependencies/
│       │   │   └── agent_ceo/
│       │   ├── scheduling/         # MOD-003
│       │   │   ├── qualification/
│       │   │   ├── admission/
│       │   │   ├── dispatch/
│       │   │   ├── attempts/
│       │   │   └── leases/
│       │   ├── runtime/            # MOD-004
│       │   │   ├── supervisor/
│       │   │   ├── launch/
│       │   │   ├── isolation/
│       │   │   ├── ipc/
│       │   │   ├── observers/
│       │   │   ├── heartbeat/
│       │   │   ├── cancellation/
│       │   │   ├── quiescence/
│       │   │   └── fencing/
│       │   ├── engine/             # MOD-005
│       │   │   ├── bridge/
│       │   │   ├── protocol/
│       │   │   ├── bindings/
│       │   │   ├── providers/
│       │   │   ├── selection/
│       │   │   └── usage/
│       │   ├── broker/             # MOD-006: tek araç/etki sınırı
│       │   │   ├── authorization/
│       │   │   ├── intents/
│       │   │   ├── execution/
│       │   │   ├── effects/
│       │   │   └── reconciliation/
│       │   ├── workspace/          # MOD-007
│       │   │   ├── snapshots/
│       │   │   ├── patches/
│       │   │   ├── artifacts/
│       │   │   ├── provenance/
│       │   │   └── receipts/
│       │   ├── verification/       # Bağımsız verifier istemcisi
│       │   ├── acceptance/         # MOD-009: yetkili kabul işlemleri
│       │   ├── projections/        # MOD-010
│       │   │   ├── queries/
│       │   │   ├── snapshots/
│       │   │   ├── events/
│       │   │   ├── cursors/
│       │   │   └── subscriptions/
│       │   ├── knowledge/          # MOD-012: ürün hafızası/kataloğu
│       │   │   ├── catalog/
│       │   │   ├── memory/
│       │   │   ├── retrieval/
│       │   │   ├── provenance/
│       │   │   ├── retention/
│       │   │   └── access/
│       │   ├── worktypes/          # MOD-013
│       │   │   ├── software/
│       │   │   ├── research/
│       │   │   ├── spreadsheet/
│       │   │   └── obligation/
│       │   ├── commercial/         # MOD-014
│       │   │   ├── budgets/
│       │   │   ├── reservations/
│       │   │   ├── usage/
│       │   │   ├── ledger/
│       │   │   └── external_effects/
│       │   ├── operations/         # MOD-015
│       │   │   ├── health/
│       │   │   ├── recovery/
│       │   │   ├── incidents/
│       │   │   └── reconciliation/
│       │   ├── bootstrap/
│       │   │   ├── provisioning/
│       │   │   ├── enrollment/
│       │   │   ├── consent/
│       │   │   ├── clock/
│       │   │   ├── custody/
│       │   │   └── readback/
│       │   ├── adapters/
│       │   │   ├── postgres/
│       │   │   ├── secrets/
│       │   │   └── platform/
│       │   ├── composition/        # Bileşenleri bağlayan girişler
│       │   └── observability/
│       ├── native/
│       │   ├── linux/
│       │   │   ├── process/
│       │   │   ├── clock/
│       │   │   └── isolation/
│       │   └── build/
│       ├── tests/
│       ├── pyproject.toml
│       └── README.md
│
├── contracts/                      # Tek asıl sözleşme kaynağı
│   ├── source/
│   │   └── python/
│   │       └── packages/
│   │           └── contracts/
│   ├── generated/
│   │   ├── jsonschema/
│   │   ├── openapi/
│   │   └── typescript/
│   ├── registry/
│   ├── compatibility/              # Sözleşme uyumluluk kontrolleri
│   ├── generation/
│   └── README.md
│
├── database/
│   ├── sources/                    # Mevcut korumalı SQL kaynakları
│   ├── assembly/
│   │   └── assembly.json
│   ├── migrations/                 # Ayrı doğrulanmış geçiş paketleri
│   ├── bootstrap/
│   ├── seeds/
│   │   ├── reference/
│   │   └── development/
│   ├── security/
│   │   ├── roles/
│   │   ├── grants/
│   │   └── rls/
│   ├── verification/
│   ├── tests/
│   └── README.md
│
├── workers/                        # Yürütme girişleri; ikinci iş motoru yok
│   ├── scheduler/
│   ├── task/
│   ├── outbox/
│   ├── reconciliation/
│   ├── maintenance/
│   └── README.md
│
├── verifier/                       # MOD-008: bağımsız doğrulayıcı
│   ├── src/
│   │   ├── runner/
│   │   ├── evaluation/
│   │   ├── candidate_binding/
│   │   ├── isolation/
│   │   ├── oracle_access/
│   │   ├── provenance/
│   │   ├── receipts/
│   │   ├── signatures/
│   │   └── readback/
│   ├── rules/
│   ├── public-fixtures/
│   ├── tests/
│   ├── pyproject.toml
│   ├── AGENTS.md
│   └── README.md
│
├── integrations/                   # İhtiyaç duyuldukça eklenir
│   ├── filesystem/
│   ├── browser/
│   ├── mcp/
│   ├── webhooks/
│   ├── providers/
│   └── README.md
│
├── tests/                          # Sistem genelindeki testler
│   ├── integration/
│   ├── contracts/
│   ├── e2e/
│   ├── security/
│   ├── isolation/
│   ├── concurrency/
│   ├── performance/
│   ├── resilience/
│   ├── recovery/
│   ├── regression/
│   ├── acceptance/
│   │   ├── first13/
│   │   └── modules/
│   ├── fixtures/
│   │   ├── producer/
│   │   └── synthetic/
│   └── harness/
│
├── evidence/                       # Tek kanıt dizini
│   ├── runs/
│   ├── manifests/
│   ├── source-integrity/
│   └── README.md
│
├── infrastructure/
│   ├── local/
│   │   ├── windows/
│   │   └── linux/
│   ├── services/
│   ├── isolation/
│   ├── networking/
│   ├── observability/
│   ├── backup/
│   ├── restore/
│   ├── packaging/
│   └── runbooks/
│
├── config/
│   ├── schemas/
│   ├── defaults/
│   ├── profiles/
│   │   └── examples/
│   ├── capabilities/
│   └── README.md
│
├── scripts/
│   ├── development/
│   ├── verification/
│   ├── contracts/
│   ├── catalog/
│   ├── database/
│   ├── maintenance/
│   ├── release/
│   └── migration/
│
├── docs/
│   ├── architecture/
│   │   ├── AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v{version}-r{revision}.md
│   │   ├── AI_PROJE_OFISI_ANA_MIMARI_DOKUMANI_v{version}-r{revision}.txt
│   │   ├── modules/                # MOD-001–MOD-016
│   │   ├── phases/                 # PH-00–PH-06
│   │   ├── diagrams/
│   │   └── sources/
│   ├── requirements/
│   ├── api/
│   ├── database/
│   ├── user-guides/
│   ├── developer-guides/
│   ├── maintenance/
│   ├── troubleshooting/
│   ├── operations/
│   ├── research/
│   └── migration/
│       ├── SOURCE_TO_TARGET.json
│       ├── MIGRATION_PLAN.md
│       ├── VALIDATION.md
│       └── ROLLBACK.md
│
├── catalog/                        # Geliştirme kataloğu; ürün hafızası değil
│   ├── sources/
│   │   ├── MODULE_MAP.json
│   │   └── TRACEABILITY_MATRIX.json
│   ├── generated/
│   │   ├── FILE_CATALOG.json
│   │   ├── SYMBOL_CATALOG.json
│   │   ├── API_CATALOG.json
│   │   ├── DATABASE_CATALOG.json
│   │   ├── EVENT_CATALOG.json
│   │   ├── DEPENDENCY_CATALOG.json
│   │   └── TEST_CATALOG.json
│   └── README.md
│
├── decisions/
│   ├── adr/
│   ├── user/
│   ├── security/
│   ├── design/
│   └── DECISION_REGISTER.json
│
├── handover/
│   ├── CURRENT.md                  # İlerleme/kanıta bağlantılı devir
│   ├── NEXT_STEP.md
│   └── history/
│
├── progress/
│   ├── ILERLEME_TABLOSU.json        # Tek güncel ilerleme kaynağı
│   ├── ILERLEME_TABLOSU.md          # JSON'dan üretilir
│   ├── UYGULAMA_DURUM_MATRISI.md
│   ├── milestones/
│   └── history/
│
├── security/
│   ├── threat-model/
│   ├── policies/
│   ├── trust-boundaries/
│   ├── enrollment/
│   ├── key-management/
│   ├── revocation/
│   ├── supply-chain/
│   └── incident-response/
│
├── releases/
│   ├── manifests/
│   ├── checksums/
│   ├── notes/
│   └── acceptance/
│
├── examples/
│   ├── software/
│   │   └── mgt-title-normalization-01/
│   ├── api/
│   └── profiles/
│
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   ├── pull_request_template.md
│   └── CODEOWNERS
│
├── .ai-brain-outbox/               # Ortak hafızaya aktarım notları
│
├── AiProjeOfisi/                   # Geçiş sırasında mevcut uygulama
├── GUNCEL/                         # Geçiş sırasında mevcut A referansı
├── ARSIV/                          # Tarihsel kaynaklar korunur
│
├── README.md
├── AGENTS.md
├── CHANGELOG.md
├── ROADMAP.md                      # Sıra/hedef; ikinci ilerleme tablosu değil
├── SECURITY.md
├── CONTRIBUTING.md
├── BAKIM_VE_DEGISIKLIK_REHBERI.md
├── SOURCE_MANIFEST.json
├── .gitignore
├── .gitattributes
└── .env.example                    # Yalnız sır içermeyen örnekler
```

Yapının bağlayıcı kuralları:

1. **Tek yazıcı:** Kalıcı domain değişiklikleri Kernel üzerinden yapılır. Worker, entegrasyon veya ekran doğrudan alternatif yazıcı oluşturmaz.
2. **Tek araç sınırı:** Dosya ve dış sistem etkileri Broker üzerinden geçer. Entegrasyonlar bu yetkiyi aşamaz.
3. **Bağımsız doğrulama:** Verifier’ın ayrı klasörü, bağımsızlık kanıtı değildir. Kimlik, süreç, anahtar, oracle erişimi ve çalışma ortamı ayrıca ayrılır.
4. **Tek sözleşme kaynağı:** Mevcut Python sözleşmeleri başlangıç otoritesidir. Şema ve istemci tipleri üretilir; elle düzenlenen paralel sözleşmeler oluşturulmaz.
5. **Salt okunur ofis:** Sanal ofis, doğrulanmış backend durumunu gösterir; görev veya ajan durumu üretmez.
6. **Gerçek veriler depo dışında:** PostgreSQL data, gerçek anahtarlar, özel profiller, yedekler ve gizli oracle verileri bu ağaca konmaz. Yerleri yapılandırma referanslarıyla belirtilir.
7. **Ücretsiz yerel varsayılan:** Ücretli sağlayıcı veya ücretli fallback klasör yapısıyla etkinleşmez.
8. **Kapsam korunur:** İlk SOFTWARE teslimi ara hedeftir. Araştırma, tablo, yükümlülük, hafıza, ticari kayıt ve kurtarma kapsamları kaybolmaz.
9. **Tek kanıt deposu:** Test, güvenlik ve sürüm kayıtları `evidence/` içindeki koşumlara referans verir; aynı kanıtı farklı klasörlerde çoğaltmaz.
10. **Kontrollü geçiş:** Her dosyanın eski ve yeni yolu kayıt altına alınır. Import, SQL sırası, profil yolu, başlatıcı, belge bağlantısı ve kaynak manifesti birlikte doğrulanır.

Mevcut kaynakların ana eşlemesi:

| Mevcut konum | Hedef |
|---|---|
| `AiProjeOfisi/presentation/` | Görsel kaynaklar `product/frontend/`; Python HTTP bağlantısı backend `api/` |
| `AiProjeOfisi/company_os/` | Sorumluluğuna göre backend `company_os/`, `workers/` ve `verifier/` |
| `AiProjeOfisi/packages/contracts/` | `contracts/source/python/packages/contracts/` |
| `AiProjeOfisi/sql/` | `database/sources/` ve `database/assembly/` |
| `AiProjeOfisi/native/` ve mevcut C yardımcıları | `product/backend/native/` |
| `AiProjeOfisi/tests/` | Bileşen testleri ilgili bileşende; sistem testleri kök `tests/` altında |
| `AiProjeOfisi/evidence/` | `evidence/`; tarihsel kanıt bütünlüğü korunarak |
| `AiProjeOfisi/tools/` | Görevine göre `scripts/` veya `infrastructure/` |
| İlerleme dosyaları | `progress/`; uygulamadaki okuyucular da güncellenerek |
| Mimari belgeler | Kaynak ve sürüm bağları korunarak `docs/architecture/` |

`AiProjeOfisi/` ve `GUNCEL/` geçiş tamamlanana kadar korunur. Geçişten sonra aynı kodun iki aktif kopyası bırakılmaz; tarihsel kaynaklar çalışma zamanı bağımlılığı yapılmaz.