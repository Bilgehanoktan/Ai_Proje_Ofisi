"""MOD-012 Code Intelligence Adapter & 10-Point Repo Gate (Faz C1).

Selects `codebase-memory-mcp` (MIT) as the single local code-intelligence
adapter while keeping `MOD-001` (Company Kernel) as sole write authority.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class RepoGateChecklist:
    canonical_repo: str
    pinned_version: str
    license_spdx: str
    no_paid_lockin: bool
    module_mapping: str
    no_second_authority: bool
    security_boundaries: bool
    tests_present: bool
    hardware_measured: bool
    independent_acceptance: bool

    def is_passed(self) -> bool:
        return (
            bool(self.canonical_repo.strip())
            and bool(self.pinned_version.strip())
            and self.license_spdx in {"MIT", "Apache-2.0", "BSD-3-Clause"}
            and self.no_paid_lockin
            and bool(self.module_mapping.strip())
            and self.no_second_authority
            and self.security_boundaries
            and self.tests_present
            and self.hardware_measured
            and self.independent_acceptance
        )


CODEBASE_MEMORY_GATE = RepoGateChecklist(
    canonical_repo="https://github.com/DeusData/codebase-memory-mcp",
    pinned_version="local-installed-20261128",
    license_spdx="MIT",
    no_paid_lockin=True,
    module_mapping="MOD-012",
    no_second_authority=True,
    security_boundaries=True,
    tests_present=True,
    hardware_measured=True,
    independent_acceptance=True,
)


def detect_code_intel_adapter() -> dict[str, str | bool | None]:
    """Return the active MOD-012 code-intelligence adapter status."""
    binary = shutil.which("codebase-memory-mcp")
    return {
        "adapter": "codebase-memory-mcp",
        "license": CODEBASE_MEMORY_GATE.license_spdx,
        "gate_passed": CODEBASE_MEMORY_GATE.is_passed(),
        "installed": binary is not None,
        "binary": binary,
        "authority_mode": "READ_ONLY_INDEX_MOD_012",
    }
