"""MOD-001/MOD-004: Deterministic signer key rotation policy for production readiness."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyRotationPolicy:
    """Enforces bounded key age, grace periods, and distinct rotated key IDs."""

    max_key_age_days: int = 90
    grace_period_days: int = 7

    def __post_init__(self) -> None:
        if self.max_key_age_days < 1:
            raise ValueError("MAX_KEY_AGE_DAYS_MIN_1")
        if self.grace_period_days < 0 or self.grace_period_days >= self.max_key_age_days:
            raise ValueError("INVALID_GRACE_PERIOD_DAYS")

    def evaluate_key_age(self, age_days: int) -> str:
        """Return ACTIVE, ROTATION_DUE, or EXPIRED for a signer key age."""
        if age_days < 0:
            raise ValueError("NEGATIVE_KEY_AGE")
        if age_days >= self.max_key_age_days:
            return "EXPIRED"
        if age_days >= (self.max_key_age_days - self.grace_period_days):
            return "ROTATION_DUE"
        return "ACTIVE"

    def validate_rotation(self, current_key_id: str, next_key_id: str) -> None:
        """Ensure rotated key identifier is non-empty and distinct from the current key."""
        cur = (current_key_id or "").strip()
        nxt = (next_key_id or "").strip()
        if not cur or not nxt:
            raise ValueError("KEY_IDS_REQUIRED")
        if cur == nxt:
            raise ValueError("ROTATED_KEY_MUST_BE_DISTINCT")
