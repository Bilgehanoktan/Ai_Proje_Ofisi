"""Unit tests for Faz C1: MOD-012 Codebase Memory adapter & 10-point gate."""

from __future__ import annotations

import unittest

from company_os.catalog.code_intel_adapter import (
    CODEBASE_MEMORY_GATE,
    RepoGateChecklist,
    detect_code_intel_adapter,
)


class CodeIntelAdapterTests(unittest.TestCase):
    def test_codebase_memory_passes_10_point_gate(self) -> None:
        self.assertTrue(CODEBASE_MEMORY_GATE.is_passed())
        status = detect_code_intel_adapter()
        self.assertEqual(status["adapter"], "codebase-memory-mcp")
        self.assertEqual(status["license"], "MIT")
        self.assertEqual(status["authority_mode"], "READ_ONLY_INDEX_MOD_012")

    def test_noncommercial_or_second_authority_fails_gate(self) -> None:
        noncommercial = RepoGateChecklist(
            canonical_repo="https://example.com/gitnexus",
            pinned_version="v1.0.0",
            license_spdx="PolyForm-Noncommercial-1.0.0",
            no_paid_lockin=True,
            module_mapping="MOD-012",
            no_second_authority=True,
            security_boundaries=True,
            tests_present=True,
            hardware_measured=True,
            independent_acceptance=True,
        )
        self.assertFalse(noncommercial.is_passed())


if __name__ == "__main__":
    unittest.main()
