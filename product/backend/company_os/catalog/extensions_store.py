"""PostgreSQL 087 extension tables store (MOD-012, MOD-013, MOD-014).

Uses strictly parameterized SQL against company.catalog_entries,
company.memory_promotions, company.work_template_validations, and
company.external_effect_ledger. Never relaxes FORCE RLS or separation-of-duties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from company_os.budget.ledger import ExternalEffectEntry
from company_os.catalog.memory_promotion import CatalogEntry, MemoryRecord


def _require_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}_REQUIRED")
    return value.strip()


@dataclass
class Extensions087Store:
    """Parameterized DB adapter for 087 MOD-012..MOD-014 tables."""

    connect: Callable[[], Any]

    def upsert_catalog_entry(self, entry: CatalogEntry) -> dict[str, Any]:
        tenant_id = _require_non_empty(entry.tenant_id, "TENANT_ID")
        sql = """
            INSERT INTO company.catalog_entries
                (tenant_id, kind, name, version, digest, active)
            VALUES (%s::uuid, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, kind, name, version) DO NOTHING
            RETURNING tenant_id::text, kind, name, version, digest, active
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        tenant_id,
                        entry.kind.value,
                        _require_non_empty(entry.name, "NAME"),
                        _require_non_empty(entry.version, "VERSION"),
                        _require_non_empty(entry.digest, "DIGEST"),
                        bool(entry.active),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            existing = self.list_catalog_entries(tenant_id)
            for item in existing:
                if (
                    item["kind"] == entry.kind.value
                    and item["name"] == entry.name
                    and item["version"] == entry.version
                ):
                    if item["digest"] != entry.digest:
                        raise ValueError("CATALOG_DIGEST_CONFLICT")
                    return item
            raise RuntimeError("CATALOG_UPSERT_READBACK_MISSING")
        return {
            "tenant_id": row[0],
            "kind": row[1],
            "name": row[2],
            "version": row[3],
            "digest": row[4],
            "active": row[5],
        }

    def list_catalog_entries(self, tenant_id: str) -> list[dict[str, Any]]:
        tid = _require_non_empty(tenant_id, "TENANT_ID")
        sql = """
            SELECT tenant_id::text, kind, name, version, digest, active
            FROM company.catalog_entries
            WHERE tenant_id = %s::uuid
            ORDER BY kind, name, version
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tid,))
                rows = cur.fetchall()
        return [
            {
                "tenant_id": r[0],
                "kind": r[1],
                "name": r[2],
                "version": r[3],
                "digest": r[4],
                "active": r[5],
            }
            for r in rows
        ]

    def save_memory_promotion(self, record: MemoryRecord) -> dict[str, Any]:
        tid = _require_non_empty(record.tenant_id, "TENANT_ID")
        if record.promoted_by is not None and record.promoted_by == record.verified_by:
            raise PermissionError("SEPARATION_OF_DUTIES_REQUIRED")
        sql = """
            INSERT INTO company.memory_promotions
                (tenant_id, record_id, summary, evidence_digest, state, verified_by, promoted_by)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, record_id) DO UPDATE
                SET state = EXCLUDED.state,
                    verified_by = EXCLUDED.verified_by,
                    promoted_by = EXCLUDED.promoted_by
            RETURNING tenant_id::text, record_id, summary, evidence_digest, state, verified_by, promoted_by
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        tid,
                        _require_non_empty(record.record_id, "RECORD_ID"),
                        _require_non_empty(record.summary, "SUMMARY"),
                        _require_non_empty(record.evidence_digest, "EVIDENCE_DIGEST"),
                        record.state.value,
                        record.verified_by,
                        record.promoted_by,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return {
            "tenant_id": row[0],
            "record_id": row[1],
            "summary": row[2],
            "evidence_digest": row[3],
            "state": row[4],
            "verified_by": row[5],
            "promoted_by": row[6],
        }

    def list_memory_promotions(self, tenant_id: str) -> list[dict[str, Any]]:
        tid = _require_non_empty(tenant_id, "TENANT_ID")
        sql = """
            SELECT tenant_id::text, record_id, summary, evidence_digest, state, verified_by, promoted_by
            FROM company.memory_promotions
            WHERE tenant_id = %s::uuid
            ORDER BY record_id
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tid,))
                rows = cur.fetchall()
        return [
            {
                "tenant_id": r[0],
                "record_id": r[1],
                "summary": r[2],
                "evidence_digest": r[3],
                "state": r[4],
                "verified_by": r[5],
                "promoted_by": r[6],
            }
            for r in rows
        ]

    def record_work_validation(
        self,
        *,
        tenant_id: str,
        work_type: str,
        template_id: str,
        template_version: str,
        validated: bool,
        evidence_digest: str,
    ) -> dict[str, Any]:
        tid = _require_non_empty(tenant_id, "TENANT_ID")
        sql = """
            INSERT INTO company.work_template_validations
                (tenant_id, work_type, template_id, template_version, validated, evidence_digest)
            VALUES (%s::uuid, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id::text, work_type, template_id, template_version, validated, evidence_digest
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        tid,
                        _require_non_empty(work_type, "WORK_TYPE"),
                        _require_non_empty(template_id, "TEMPLATE_ID"),
                        _require_non_empty(template_version, "TEMPLATE_VERSION"),
                        bool(validated),
                        _require_non_empty(evidence_digest, "EVIDENCE_DIGEST"),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return {
            "id": row[0],
            "tenant_id": row[1],
            "work_type": row[2],
            "template_id": row[3],
            "template_version": row[4],
            "validated": row[5],
            "evidence_digest": row[6],
        }

    def record_external_effect(self, entry: ExternalEffectEntry) -> dict[str, Any]:
        tid = _require_non_empty(entry.tenant_id, "TENANT_ID")
        sql = """
            INSERT INTO company.external_effect_ledger
                (tenant_id, idempotency_key, effect_id, provider, status)
            VALUES (%s::uuid, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING tenant_id::text, idempotency_key, effect_id, provider, status
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        tid,
                        _require_non_empty(entry.idempotency_key, "IDEMPOTENCY_KEY"),
                        _require_non_empty(entry.effect_id, "EFFECT_ID"),
                        _require_non_empty(entry.provider, "PROVIDER"),
                        _require_non_empty(entry.status, "STATUS"),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            for item in self.list_external_effects(tid):
                if item["idempotency_key"] == entry.idempotency_key:
                    if item["effect_id"] != entry.effect_id or item["provider"] != entry.provider:
                        raise ValueError("EXTERNAL_EFFECT_IDEMPOTENCY_CONFLICT")
                    return item
            raise RuntimeError("EXTERNAL_EFFECT_READBACK_MISSING")
        return {
            "tenant_id": row[0],
            "idempotency_key": row[1],
            "effect_id": row[2],
            "provider": row[3],
            "status": row[4],
        }

    def list_external_effects(self, tenant_id: str) -> list[dict[str, Any]]:
        tid = _require_non_empty(tenant_id, "TENANT_ID")
        sql = """
            SELECT tenant_id::text, idempotency_key, effect_id, provider, status
            FROM company.external_effect_ledger
            WHERE tenant_id = %s::uuid
            ORDER BY idempotency_key
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tid,))
                rows = cur.fetchall()
        return [
            {
                "tenant_id": r[0],
                "idempotency_key": r[1],
                "effect_id": r[2],
                "provider": r[3],
                "status": r[4],
            }
            for r in rows
        ]
