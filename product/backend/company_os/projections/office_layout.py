"""Read-only MOD-011 / MOD-012 Office FloorGeometryVersion (DEC-28C draft) and 087 Skill Library projection.

Strictly read-only presentation metadata: layout geometry, room portals, and catalog
skill pins never grant execution authority or mutate Kernel (MOD-001) state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from company_os.catalog.memory_promotion import (
    DEFAULT_ROLE_CARDS,
    DEFAULT_SKILL_CARDS,
)
from company_os.catalog.skill_metadata_pilot import PILOT_087_ROLE_CARDS
from company_os.engine.ollama_adapter import LOCAL_OLLAMA_MODEL_PROFILES

ROLE_SKILL_BINDINGS: dict[str, tuple[str, ...]] = {
    "MGR-01": ("SKILL-CEO-SYNTHESIS-01",),
    "EXP-01": ("SKILL-PATCH-ATOMIC-01",),
    "EXP-02": ("SKILL-RESEARCH-READBACK-01", "SKILL-OBLIGATION-EXTRACT-01"),
    "EXP-03": ("SKILL-SECURITY-AUDIT-01",),
    "EXP-04": ("SKILL-XLSX-AUDIT-01",),
    "QA-01": ("SKILL-RESEARCH-READBACK-01", "SKILL-SECURITY-AUDIT-01"),
}

ROLE_STATION_MAP: dict[str, str] = {
    "EXP-02": "ST-F1-RSCH-01",
    "EXP-04": "ST-F1-RSCH-02",
    "MGR-01": "ST-F1-ORCH-01",
    "EXP-01": "ST-F1-ENG-01",
    "QA-01": "ST-F1-QA-01",
    "EXP-03": "ST-F1-QA-02",
}


def build_dec28c_floor_geometry() -> dict[str, Any]:
    """Return the non-authoritative DEC-28C Floor 1 block layout specification with SHA-256 digest."""
    spec_core: dict[str, Any] = {
        "floor_id": "F1-DEC28C",
        "layout_revision": 1,
        "status": "DRAFT_SOURCE_ALIGNED_NOT_FROZEN",
        "authority_mode": "READ_ONLY_PRESENTATION_NO_GRANT",
        "grid": {
            "width": 48,
            "height": 30,
            "tile_unit": 32,
            "coordinate_system": "grid_dec28c_v1",
        },
        "zones": [
            {"zone_id": "F1-RSCH", "label": "Research", "category": "WORK_POD", "x": [2, 14], "y": [2, 11], "open": True},
            {"zone_id": "F1-ORCH", "label": "Orchestrator", "category": "HUB_POD", "x": [19, 28], "y": [2, 11], "open": True},
            {"zone_id": "F1-ENG", "label": "Engineer", "category": "WORK_POD", "x": [33, 45], "y": [2, 11], "open": True},
            {"zone_id": "F1-COR", "label": "Ana Koridor", "category": "CORRIDOR", "x": [2, 45], "y": [12, 18], "open": True},
            {"zone_id": "F1-EXP", "label": "Pasif Rezerv", "category": "RESERVE", "x": [2, 14], "y": [19, 27], "open": False},
            {"zone_id": "F1-BRIEF", "label": "Briefing / Giriş", "category": "SHARED_MEETING", "x": [19, 28], "y": [19, 27], "open": True},
            {"zone_id": "F1-QA", "label": "QA / Kontrol", "category": "ISOLATED_QA", "x": [33, 45], "y": [19, 27], "open": True},
        ],
        "door_portals": [
            {"door_id": "D-RSCH", "from_zone_id": "F1-RSCH", "to_zone_id": "F1-COR", "walk_anchor": [8, 12], "enabled": True},
            {"door_id": "D-ORCH", "from_zone_id": "F1-ORCH", "to_zone_id": "F1-COR", "walk_anchor": [24, 12], "enabled": True},
            {"door_id": "D-ENG", "from_zone_id": "F1-ENG", "to_zone_id": "F1-COR", "walk_anchor": [39, 12], "enabled": True},
            {"door_id": "D-EXP", "from_zone_id": "F1-EXP", "to_zone_id": "F1-COR", "walk_anchor": [8, 18], "enabled": False},
            {"door_id": "D-BRIEF", "from_zone_id": "F1-BRIEF", "to_zone_id": "F1-COR", "walk_anchor": [24, 18], "enabled": True},
            {"door_id": "D-QA", "from_zone_id": "F1-QA", "to_zone_id": "F1-COR", "walk_anchor": [39, 18], "enabled": True},
        ],
        "floor_portals": [
            {"portal_id": "P-ENTRY", "label": "Ana Giriş", "anchor": [24, 28], "enabled": True},
            {"portal_id": "P-UPPER-FLOOR", "label": "Kat Portali (Kat 02+)", "anchor": [30, 28], "enabled": False},
        ],
    }
    canonical = json.dumps(spec_core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return {
        **spec_core,
        "geometry_hash": f"sha256:{digest}",
    }


def build_office_architecture_payload(*, tenant_id: str = "default") -> dict[str, Any]:
    """Build combined FloorGeometryVersion + 087 Role/Skill/Model catalog summary for MOD-011 UI."""
    roles = []
    for role_id, spec in DEFAULT_ROLE_CARDS.items():
        entry = spec.to_entry(tenant_id)
        roles.append(
            {
                "name": entry.name,
                "kind": entry.kind.value,
                "version": entry.version,
                "digest": entry.digest,
                "station_id": ROLE_STATION_MAP.get(role_id, "ST-F1-ENG-01"),
                "bound_skills": list(ROLE_SKILL_BINDINGS.get(role_id, ())),
                "summary": spec.content,
            }
        )

    skills = []
    for _skill_id, spec in DEFAULT_SKILL_CARDS.items():
        entry = spec.to_entry(tenant_id)
        skills.append(
            {
                "name": entry.name,
                "kind": entry.kind.value,
                "version": entry.version,
                "digest": entry.digest,
                "summary": spec.content,
                "grant_authority": False,
            }
        )

    models = [
        {
            "name": prof.name,
            "kind": "MODEL",
            "version": prof.version,
            "digest": prof.digest,
            "cost_tier": "FREE_LOCAL_DEFAULT",
        }
        for prof in LOCAL_OLLAMA_MODEL_PROFILES.values()
    ]

    pilot_specialists = [
        {
            "name": card.name,
            "version": card.version,
            "license_spdx": card.license_spdx,
            "pinned_commit": card.pinned_commit,
            "digest": f"sha256:{hashlib.sha256(card.body.encode('utf-8')).hexdigest()}",
            "description": card.description,
        }
        for card in PILOT_087_ROLE_CARDS
    ]

    return {
        "floor_geometry": build_dec28c_floor_geometry(),
        "catalog_summary": {
            "authority_note": "SKILL_AND_ROLE_DEFINITIONS_ARE_NOT_GRANTS_MOD_001_REQUIRED",
            "roles": roles,
            "skills": skills,
            "models": models,
            "pilot_specialists": pilot_specialists,
            "role_skill_bindings": {k: list(v) for k, v in ROLE_SKILL_BINDINGS.items()},
        },
    }
