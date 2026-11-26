"""MOD-012: Tenant-scoped catalog and controlled product memory promotion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Mapping


class PromotionState(str, Enum):
    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class CatalogKind(str, Enum):
    SKILL = "SKILL"
    ROLE = "ROLE"
    TOOL = "TOOL"
    MODEL = "MODEL"


@dataclass(frozen=True)
class CatalogProfileSpec:
    """Immutable definition for a role, skill, or local model card in the 087 catalog."""

    kind: CatalogKind
    name: str
    version: str
    content: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def to_entry(self, tenant_id: str, *, active: bool = True) -> "CatalogEntry":
        return CatalogEntry(
            tenant_id=tenant_id,
            kind=self.kind,
            name=self.name,
            version=self.version,
            digest=self.digest,
            active=active,
        )


DEFAULT_ROLE_CARDS: dict[str, CatalogProfileSpec] = {
    "EXP-01": CatalogProfileSpec(
        kind=CatalogKind.ROLE,
        name="EXP-01",
        version="1.0.0",
        content=(
            "Sen AI Proje Ofisi EXP-01 yazılım mühendisisin. Verilen kabul ölçütlerini çıkar. "
            "Mevcut davranışı koruyan en küçük değişikliği ve ilgili regresyon kontrolünü belirt. "
            "Gözlenen kanıtı varsayımdan ayır. Çalıştırmadığın testleri ve kullanmadığın araçları açıkça bildir."
        ),
    ),
    "EXP-02": CatalogProfileSpec(
        kind=CatalogKind.ROLE,
        name="EXP-02",
        version="1.0.0",
        content=(
            "Sen AI Proje Ofisi EXP-02 araştırma ve yükümlülük uzmanısın. Bulguları doğrulanmış kaynak "
            "makbuzu, madde/bölüm referansı, risk/belirsizlik sınırı ve somut doğrulama adımlarıyla raporla. "
            "Okunmamış kaynağı okunmuş gibi sunma."
        ),
    ),
    "MGR-01": CatalogProfileSpec(
        kind=CatalogKind.ROLE,
        name="MGR-01",
        version="1.0.0",
        content=(
            "Sen AI Proje Ofisi MGR-01 orkestratör yöneticisisin. Hedefi bağımsız doğrulanabilir görevlere "
            "ayır, görev ayrılığı (producer != verifier != acceptor) sınırını koru ve kapsam dışı genişlemeyi reddet."
        ),
    ),
    "QA-01": CatalogProfileSpec(
        kind=CatalogKind.ROLE,
        name="QA-01",
        version="1.0.0",
        content=(
            "Sen AI Proje Ofisi QA-01 bağımsız kalite ve kabul denetçisisin. Çıktıyı kabul ölçütlerine, "
            "SHA-256 kanıt özetine ve negatif regresyon kontrollerine göre bağımsız değerlendir; kanıtsız kabul verme."
        ),
    ),
    "EXP-03": CatalogProfileSpec(
        kind=CatalogKind.ROLE,
        name="EXP-03",
        version="1.0.0",
        content=(
            "Sen AI Proje Ofisi EXP-03 güvenlik ve gizlilik denetçisisin. Kod, yapılandırma ve dış kaynak "
            "akışlarını OWASP, SSRF/allowlist, en az yetki ve gizli veri sızıntısı açısından denetle. "
            "Her bulguyu etki, kanıt satırı ve somut giderim adımıyla raporla; doğrulanmamış varsayımı bulgu sayma."
        ),
    ),
    "EXP-04": CatalogProfileSpec(
        kind=CatalogKind.ROLE,
        name="EXP-04",
        version="1.0.0",
        content=(
            "Sen AI Proje Ofisi EXP-04 veri ve tablo analiz uzmanısın. .xlsx ve .csv çalışma kitaplarındaki "
            "sayısal tutarlılık, eksik/anomali kayıtlar ve özet metrikleri hücre/sütun referansı ile çıkar. "
            "Hesaplanmamış veya okunmamış değeri tahmin ederek doldurma."
        ),
    ),
}

DEFAULT_SKILL_CARDS: dict[str, CatalogProfileSpec] = {
    "SKILL-PATCH-ATOMIC-01": CatalogProfileSpec(
        kind=CatalogKind.SKILL,
        name="SKILL-PATCH-ATOMIC-01",
        version="1.0.0",
        content="Broker patch.apply ve Kernel effect_scope üzerinden kapsam içi atomik yama ve SHA-256 taban kontrolü.",
    ),
    "SKILL-RESEARCH-READBACK-01": CatalogProfileSpec(
        kind=CatalogKind.SKILL,
        name="SKILL-RESEARCH-READBACK-01",
        version="1.0.0",
        content="Broker workspace.read makbuzunun bağımsız aipof_research_readback servisiyle Kernel DB üzerinden doğrulanması.",
    ),
    "SKILL-XLSX-AUDIT-01": CatalogProfileSpec(
        kind=CatalogKind.SKILL,
        name="SKILL-XLSX-AUDIT-01",
        version="1.0.0",
        content="OpenXML .xlsx ve .csv çalışma kitaplarında paylaşımlı dizge, hücre sayısı ve toplam/formül mutabakatı.",
    ),
    "SKILL-OBLIGATION-EXTRACT-01": CatalogProfileSpec(
        kind=CatalogKind.SKILL,
        name="SKILL-OBLIGATION-EXTRACT-01",
        version="1.0.0",
        content="Yükümlülük belgelerinden ve izinli HTTPS kaynaklarından madde, süre sınırı ve kanıt kontrol listesi çıkarımı.",
    ),
    "SKILL-SECURITY-AUDIT-01": CatalogProfileSpec(
        kind=CatalogKind.SKILL,
        name="SKILL-SECURITY-AUDIT-01",
        version="1.0.0",
        content="SSRF/allowlist sınırları, gizli veri sızıntısı, yetki ayrılığı ve en az yetki kontrol listesi denetimi.",
    ),
    "SKILL-CEO-SYNTHESIS-01": CatalogProfileSpec(
        kind=CatalogKind.SKILL,
        name="SKILL-CEO-SYNTHESIS-01",
        version="1.0.0",
        content="Çoklu uzman ve QA çıktılarından çelişki denetimli, makbuz/kanıt referanslı nihai yönetici özeti sentezi.",
    ),
}


def build_default_087_catalog_entries(
    tenant_id: str,
    *,
    model_profiles: Mapping[str, Any] | None = None,
) -> list["CatalogEntry"]:
    """Build the canonical set of 087 ROLE, SKILL, and local Ollama MODEL catalog entries for a tenant."""
    entries: list[CatalogEntry] = []
    for spec in DEFAULT_ROLE_CARDS.values():
        entries.append(spec.to_entry(tenant_id))
    for spec in DEFAULT_SKILL_CARDS.values():
        entries.append(spec.to_entry(tenant_id))
    if model_profiles:
        for prof in model_profiles.values():
            entries.append(
                CatalogEntry(
                    tenant_id=tenant_id,
                    kind=CatalogKind.MODEL,
                    name=str(prof.name),
                    version=str(prof.version),
                    digest=str(prof.digest),
                    active=True,
                )
            )
    return entries


@dataclass(frozen=True)
class CatalogEntry:
    tenant_id: str
    kind: CatalogKind
    name: str
    version: str
    digest: str
    active: bool = True


@dataclass
class MemoryRecord:
    tenant_id: str
    record_id: str
    summary: str
    evidence_digest: str
    state: PromotionState = PromotionState.CANDIDATE
    verified_by: str | None = None
    promoted_by: str | None = None


@dataclass
class TenantCatalogRegistry:
    """In-memory tenant-scoped catalog with strict version pinning and isolation."""

    _entries: dict[tuple[str, CatalogKind, str, str], CatalogEntry] = field(default_factory=dict)

    def register(self, entry: CatalogEntry) -> None:
        if not entry.tenant_id or not entry.version or not entry.digest:
            raise ValueError("tenant_id, version, and digest are required")
        key = (entry.tenant_id, entry.kind, entry.name, entry.version)
        if key in self._entries:
            existing = self._entries[key]
            if existing.digest != entry.digest:
                raise ValueError("CATALOG_DIGEST_CONFLICT")
            return
        self._entries[key] = entry

    def resolve(self, tenant_id: str, kind: CatalogKind, name: str, version: str) -> CatalogEntry:
        key = (tenant_id, kind, name, version)
        if key not in self._entries:
            raise KeyError("CATALOG_ENTRY_NOT_FOUND")
        entry = self._entries[key]
        if entry.tenant_id != tenant_id or not entry.active:
            raise PermissionError("TENANT_SCOPE_OR_INACTIVE")
        return entry

    def deprecate(self, tenant_id: str, kind: CatalogKind, name: str, version: str) -> CatalogEntry:
        """Mark an existing tenant-scoped catalog entry inactive while preserving its digest."""
        key = (tenant_id, kind, name, version)
        if key not in self._entries:
            raise KeyError("CATALOG_ENTRY_NOT_FOUND")
        existing = self._entries[key]
        if existing.tenant_id != tenant_id:
            raise PermissionError("TENANT_SCOPE_VIOLATION")
        deprecated = CatalogEntry(
            tenant_id=existing.tenant_id,
            kind=existing.kind,
            name=existing.name,
            version=existing.version,
            digest=existing.digest,
            active=False,
        )
        self._entries[key] = deprecated
        return deprecated

    def list_entries(
        self,
        tenant_id: str,
        *,
        kind: CatalogKind | None = None,
        active_only: bool = True,
    ) -> list[CatalogEntry]:
        """List catalog entries strictly scoped to a single tenant."""
        return [
            entry
            for entry in self._entries.values()
            if entry.tenant_id == tenant_id
            and (kind is None or entry.kind == kind)
            and (not active_only or entry.active)
        ]

    def verify_digest(
        self, tenant_id: str, kind: CatalogKind, name: str, version: str, content: str
    ) -> bool:
        """Verify that raw content matches the SHA-256 digest of an active catalog entry."""
        entry = self.resolve(tenant_id, kind, name, version)
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return actual == entry.digest


@dataclass
class ProductMemoryPromotionPipeline:
    """Controlled learning promotion: CANDIDATE -> VERIFIED -> PROMOTED (tenant-scoped)."""

    _records: dict[tuple[str, str], MemoryRecord] = field(default_factory=dict)

    def submit_candidate(
        self, tenant_id: str, record_id: str, summary: str, evidence_digest: str
    ) -> MemoryRecord:
        if not tenant_id or not record_id or not evidence_digest:
            raise ValueError("tenant_id, record_id, and evidence_digest are required")
        key = (tenant_id, record_id)
        if key in self._records:
            raise ValueError("MEMORY_RECORD_ALREADY_EXISTS")
        rec = MemoryRecord(
            tenant_id=tenant_id,
            record_id=record_id,
            summary=summary,
            evidence_digest=evidence_digest,
        )
        self._records[key] = rec
        return rec

    def verify(self, tenant_id: str, record_id: str, verifier_id: str) -> MemoryRecord:
        rec = self._get_scoped(tenant_id, record_id)
        if rec.state != PromotionState.CANDIDATE:
            raise ValueError("INVALID_PROMOTION_TRANSITION")
        if not verifier_id:
            raise ValueError("verifier_id is required")
        rec.state = PromotionState.VERIFIED
        rec.verified_by = verifier_id
        return rec

    def promote(self, tenant_id: str, record_id: str, approver_id: str) -> MemoryRecord:
        rec = self._get_scoped(tenant_id, record_id)
        if rec.state != PromotionState.VERIFIED:
            raise ValueError("VERIFICATION_REQUIRED_BEFORE_PROMOTION")
        if not approver_id or approver_id == rec.verified_by:
            raise PermissionError("SEPARATION_OF_DUTIES_REQUIRED")
        rec.state = PromotionState.PROMOTED
        rec.promoted_by = approver_id
        return rec

    def list_promoted(self, tenant_id: str) -> list[MemoryRecord]:
        return [
            r for (t, _), r in self._records.items()
            if t == tenant_id and r.state == PromotionState.PROMOTED
        ]

    def search_promoted(self, tenant_id: str, query: str) -> list[MemoryRecord]:
        """Search promoted product memory records by substring, strictly tenant-scoped."""
        needle = (query or "").strip().lower()
        if not needle:
            return self.list_promoted(tenant_id)
        return [
            r
            for r in self.list_promoted(tenant_id)
            if needle in r.summary.lower() or needle in r.record_id.lower()
        ]

    def repropose_rejected(
        self, tenant_id: str, record_id: str, summary: str, evidence_digest: str
    ) -> MemoryRecord:
        """Re-submit a REJECTED memory record with updated evidence as a fresh CANDIDATE."""
        rec = self._get_scoped(tenant_id, record_id)
        if rec.state != PromotionState.REJECTED:
            raise ValueError("ONLY_REJECTED_CAN_BE_REPROPOSED")
        if not summary.strip() or not evidence_digest.strip():
            raise ValueError("SUMMARY_AND_DIGEST_REQUIRED")
        rec.summary = summary.strip()
        rec.evidence_digest = evidence_digest.strip()
        rec.state = PromotionState.CANDIDATE
        rec.verified_by = None
        rec.promoted_by = None
        return rec

    def _get_scoped(self, tenant_id: str, record_id: str) -> MemoryRecord:
        key = (tenant_id, record_id)
        if key not in self._records:
            raise PermissionError("TENANT_SCOPE_VIOLATION_OR_MISSING")
        return self._records[key]
