"""MOD-012: Tenant-scoped catalog and controlled product memory promotion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


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

    def _get_scoped(self, tenant_id: str, record_id: str) -> MemoryRecord:
        key = (tenant_id, record_id)
        if key not in self._records:
            raise PermissionError("TENANT_SCOPE_VIOLATION_OR_MISSING")
        return self._records[key]
