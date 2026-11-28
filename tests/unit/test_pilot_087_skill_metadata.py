"""Unit and security tests for Faz B1: 087 3-role pilot & SKILL.md metadata."""

from __future__ import annotations

import unittest

from company_os.catalog.memory_promotion import CatalogEntry, CatalogKind, TenantCatalogRegistry
from company_os.catalog.skill_metadata_pilot import (
    PILOT_087_ROLE_CARDS,
    build_pilot_087_catalog_entries,
    parse_skill_markdown,
    resolve_effective_tools,
)


class Pilot087SkillMetadataTests(unittest.TestCase):
    def test_parse_skill_markdown_and_kernel_authority_boundary(self) -> None:
        raw = """---
name: CODE-REVIEWER-01
description: Review code for correctness and security
version: 2026.11.28-pilot1
source_repo: agency-agents
pinned_commit: abc123def456
license_spdx: MIT
allowed-tools: workspace.read, shell_exec, db_admin
---
# Reviewer Instructions
Check boundaries carefully.
"""
        card = parse_skill_markdown(raw)
        self.assertEqual(card.name, "CODE-REVIEWER-01")
        self.assertEqual(card.license_spdx, "MIT")
        self.assertEqual(card.allowed_tools, ("workspace.read", "shell_exec", "db_admin"))

        # Negative security check: card cannot escalate beyond MOD-001 Kernel grants
        kernel_grants = frozenset({"workspace.read"})
        effective = resolve_effective_tools(card, kernel_grants)
        self.assertEqual(effective, ("workspace.read",))
        self.assertNotIn("shell_exec", effective)
        self.assertNotIn("db_admin", effective)

    def test_missing_frontmatter_or_required_field_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "SKILL_MD_MISSING_FRONTMATTER"):
            parse_skill_markdown("# No frontmatter")

        with self.assertRaisesRegex(ValueError, "SKILL_MD_MISSING_LICENSE_SPDX"):
            parse_skill_markdown(
                "---\nname: X\ndescription: D\nversion: 1\nsource_repo: r\npinned_commit: c\n---\nbody"
            )

    def test_three_pilot_roles_pin_and_reject_digest_conflict(self) -> None:
        self.assertEqual(len(PILOT_087_ROLE_CARDS), 3)
        entries = build_pilot_087_catalog_entries("tenant-pilot-1")
        self.assertEqual(len(entries), 3)

        registry = TenantCatalogRegistry()
        for entry in entries:
            registry.register(entry)

        # Negative check: tampering digest for same (tenant, kind, name, version) must fail
        tampered = CatalogEntry(
            tenant_id="tenant-pilot-1",
            kind=CatalogKind.ROLE,
            name=entries[0].name,
            version=entries[0].version,
            digest="0" * 64,
            active=True,
        )
        with self.assertRaisesRegex(ValueError, "CATALOG_DIGEST_CONFLICT"):
            registry.register(tampered)


if __name__ == "__main__":
    unittest.main()
