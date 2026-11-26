"""MOD-001/MOD-015: Deterministic production readiness snapshot builder."""

from __future__ import annotations

from typing import Any, Iterable

from company_os.broker.https_allowlist import HttpsAllowlistPolicy
from company_os.kernel.key_rotation import KeyRotationPolicy


def build_production_readiness_snapshot(
    *,
    schema_version: int,
    owner_auth_enrolled: bool,
    clock_epoch_active: bool,
    allowed_https_domains: Iterable[str],
    signer_key_age_days: int,
    remote_ssh_host: str | None = None,
) -> dict[str, Any]:
    """Evaluate local & external production readiness invariants without mutating state."""
    domains = frozenset(d.strip().lower() for d in allowed_https_domains if d.strip())
    key_policy = KeyRotationPolicy()
    key_status = key_policy.evaluate_key_age(signer_key_age_days)

    https_policy_valid = True
    if domains:
        try:
            HttpsAllowlistPolicy(allowed_domains=domains)
        except ValueError:
            https_policy_valid = False

    checks = {
        "schema_088_ready": schema_version >= 88,
        "owner_auth_enrolled": bool(owner_auth_enrolled),
        "clock_epoch_active": bool(clock_epoch_active),
        "signer_key_valid": key_status in ("ACTIVE", "ROTATION_DUE"),
        "https_allowlist_configured": len(domains) > 0 and https_policy_valid,
        "remote_ssh_host_configured": bool((remote_ssh_host or "").strip()),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "ready_for_remote_deploy": len(blockers) == 0,
        "key_status": key_status,
        "checks": checks,
        "blockers": blockers,
    }
