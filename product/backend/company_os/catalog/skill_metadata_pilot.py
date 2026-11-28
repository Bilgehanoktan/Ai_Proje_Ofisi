"""087 Catalog 3-role pilot & SKILL.md metadata-first parser (MOD-012).

Security boundary:
- `allowed_tools` declared inside a SKILL.md or role card is strictly advisory content.
- Effective tool authority ALWAYS comes from MOD-001 (Company Kernel) grants.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from company_os.catalog.memory_promotion import CatalogEntry, CatalogKind


@dataclass(frozen=True)
class SkillMetadataCard:
    name: str
    description: str
    version: str
    source_repo: str
    pinned_commit: str
    license_spdx: str
    allowed_tools: tuple[str, ...]
    body: str


def parse_skill_markdown(raw_md: str) -> SkillMetadataCard:
    """Parse a metadata-first SKILL.md document with strict frontmatter validation."""
    text = raw_md.lstrip("\ufeff")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise ValueError("SKILL_MD_MISSING_FRONTMATTER")
    lines = text.splitlines()
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError("SKILL_MD_UNCLOSED_FRONTMATTER")

    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError("SKILL_MD_INVALID_METADATA_LINE")
        key, val = stripped.split(":", 1)
        meta[key.strip()] = val.strip().strip('"').strip("'")

    required = ("name", "description", "version", "source_repo", "pinned_commit", "license_spdx")
    for req_key in required:
        if not meta.get(req_key):
            raise ValueError(f"SKILL_MD_MISSING_{req_key.upper()}")

    raw_tools = meta.get("allowed-tools", "")
    tools = tuple(t.strip() for t in raw_tools.split(",") if t.strip())
    body = "\n".join(lines[end_idx + 1 :]).strip()
    return SkillMetadataCard(
        name=meta["name"],
        description=meta["description"],
        version=meta["version"],
        source_repo=meta["source_repo"],
        pinned_commit=meta["pinned_commit"],
        license_spdx=meta["license_spdx"],
        allowed_tools=tools,
        body=body,
    )


def resolve_effective_tools(
    card: SkillMetadataCard,
    kernel_grants: frozenset[str],
) -> tuple[str, ...]:
    """Intersect advisory card tools with MOD-001 Kernel grants.

    A card can never escalate privileges beyond `kernel_grants`.
    """
    return tuple(tool for tool in card.allowed_tools if tool in kernel_grants)


PILOT_087_ROLE_CARDS: tuple[SkillMetadataCard, ...] = (
    SkillMetadataCard(
        name="CODE-REVIEWER-01",
        description="Correctness, security, and maintainability code reviewer.",
        version="2026.11.28-pilot1",
        source_repo="agency-agents",
        pinned_commit="pinned-pilot-20261128",
        license_spdx="MIT",
        allowed_tools=("workspace.read", "diff.inspect"),
        body="Review patches against KOD_KALITESI_KURALLARI.md without mutating authority.",
    ),
    SkillMetadataCard(
        name="SEC-QA-AUDITOR-01",
        description="Security and QA verification auditor for MOD-008 evidence.",
        version="2026.11.28-pilot1",
        source_repo="agency-agents",
        pinned_commit="pinned-pilot-20261128",
        license_spdx="MIT",
        allowed_tools=("workspace.read", "test.run"),
        body="Audit RLS, Broker scope boundaries, and negative test coverage.",
    ),
    SkillMetadataCard(
        name="TECH-WRITER-01",
        description="Technical documentation and handover summary writer.",
        version="2026.11.28-pilot1",
        source_repo="agency-agents",
        pinned_commit="pinned-pilot-20261128",
        license_spdx="MIT",
        allowed_tools=("workspace.read", "docs.draft"),
        body="Produce concise, evidence-linked Turkish technical documentation.",
    ),
)


def build_pilot_087_catalog_entries(tenant_id: str) -> list[CatalogEntry]:
    """Build deterministic, pinned 087 CatalogEntry items for the 3-role pilot."""
    entries: list[CatalogEntry] = []
    for card in PILOT_087_ROLE_CARDS:
        payload = (
            f"{card.name}|{card.version}|{card.source_repo}|"
            f"{card.pinned_commit}|{card.license_spdx}|{','.join(card.allowed_tools)}|{card.body}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        entries.append(
            CatalogEntry(
                tenant_id=tenant_id,
                kind=CatalogKind.ROLE,
                name=card.name,
                version=card.version,
                digest=digest,
                active=True,
            )
        )
    return entries
