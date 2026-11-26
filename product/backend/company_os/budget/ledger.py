"""MOD-014: Non-zero budget reservations, UNKNOWN cost reconciliation, and external effect ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReservationState(str, Enum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    UNKNOWN = "UNKNOWN"


@dataclass
class BudgetReservation:
    reservation_id: str
    tenant_id: str
    reserved_minor: int
    settled_minor: int = 0
    state: ReservationState = ReservationState.RESERVED


@dataclass
class ExternalEffectEntry:
    effect_id: str
    tenant_id: str
    idempotency_key: str
    provider: str
    status: str  # COMMITTED | UNKNOWN | REVERTED


@dataclass
class BudgetAndEffectLedger:
    """Enforces non-zero budget limits, UNKNOWN cost reconciliation, and external effect idempotency."""

    tenant_id: str
    budget_limit_minor: int
    max_single_effect_minor: int | None = None
    _reservations: dict[str, BudgetReservation] = field(default_factory=dict)
    _effects_by_key: dict[str, ExternalEffectEntry] = field(default_factory=dict)

    @property
    def spent_minor(self) -> int:
        return sum(r.settled_minor for r in self._reservations.values() if r.state == ReservationState.SETTLED)

    @property
    def held_minor(self) -> int:
        return sum(
            r.reserved_minor
            for r in self._reservations.values()
            if r.state in (ReservationState.RESERVED, ReservationState.UNKNOWN)
        )

    @property
    def available_minor(self) -> int:
        return self.budget_limit_minor - self.spent_minor - self.held_minor

    def has_unresolved_unknown(self) -> bool:
        return any(r.state == ReservationState.UNKNOWN for r in self._reservations.values())

    def reserve(self, reservation_id: str, amount_minor: int) -> BudgetReservation:
        if amount_minor <= 0:
            raise ValueError("NON_ZERO_RESERVATION_REQUIRED")
        if (
            self.max_single_effect_minor is not None
            and amount_minor > self.max_single_effect_minor
        ):
            raise ValueError("SINGLE_EFFECT_CAP_EXCEEDED")
        if self.has_unresolved_unknown():
            raise RuntimeError("BLOCKED_BY_UNKNOWN_COST")
        if reservation_id in self._reservations:
            raise ValueError("RESERVATION_ALREADY_EXISTS")
        if amount_minor > self.available_minor:
            raise ValueError("BUDGET_EXCEEDED")
        res = BudgetReservation(reservation_id=reservation_id, tenant_id=self.tenant_id, reserved_minor=amount_minor)
        self._reservations[reservation_id] = res
        return res

    def mark_unknown(self, reservation_id: str) -> BudgetReservation:
        res = self._reservations[reservation_id]
        if res.state != ReservationState.RESERVED:
            raise ValueError("INVALID_STATE_FOR_UNKNOWN")
        res.state = ReservationState.UNKNOWN
        return res

    def settle(self, reservation_id: str, actual_minor: int) -> BudgetReservation:
        res = self._reservations[reservation_id]
        if res.state not in (ReservationState.RESERVED, ReservationState.UNKNOWN):
            raise ValueError("INVALID_STATE_FOR_SETTLE")
        if actual_minor < 0 or actual_minor > res.reserved_minor:
            raise ValueError("SETTLE_OUT_OF_RESERVED_BOUNDS")
        res.settled_minor = actual_minor
        res.state = ReservationState.SETTLED
        return res

    def release(self, reservation_id: str) -> BudgetReservation:
        res = self._reservations[reservation_id]
        if res.state != ReservationState.RESERVED:
            raise ValueError("CANNOT_RELEASE_NON_RESERVED")
        res.state = ReservationState.RELEASED
        return res

    def record_external_effect(
        self, effect_id: str, idempotency_key: str, provider: str, status: str
    ) -> ExternalEffectEntry:
        if idempotency_key in self._effects_by_key:
            existing = self._effects_by_key[idempotency_key]
            if existing.effect_id != effect_id or existing.provider != provider:
                raise ValueError("EXTERNAL_EFFECT_IDEMPOTENCY_CONFLICT")
            return existing
        entry = ExternalEffectEntry(
            effect_id=effect_id,
            tenant_id=self.tenant_id,
            idempotency_key=idempotency_key,
            provider=provider,
            status=status,
        )
        self._effects_by_key[idempotency_key] = entry
        return entry

    def provider_summary(self) -> dict[str, dict[str, int]]:
        """Aggregate external effect outcomes per provider for reconciliation reporting."""
        summary: dict[str, dict[str, int]] = {}
        for entry in self._effects_by_key.values():
            bucket = summary.setdefault(
                entry.provider, {"COMMITTED": 0, "REVERTED": 0, "UNKNOWN": 0}
            )
            status = entry.status if entry.status in bucket else "UNKNOWN"
            bucket[status] += 1
        return summary
