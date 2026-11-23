"""S0-MIN commit ve qualification kararları; DB kilidi veya auth servisi değildir."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from packages.contracts.lifecycle import (
    CandidateSnapshot,
    PatchReceipt,
    WorkspaceRevision,
    advance_workspace,
)
from packages.contracts.models import Contract, Digest, Positive, Revision


class CommitAuthority(Contract):
    workspace_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    revision: Revision
    candidate_digest: Digest
    lease_expires_at: datetime
    attempt_state: Literal["RUNNING", "CANCELLED", "EXPIRED", "FAILED"]
    policy_digest: Digest

    @model_validator(mode="after")
    def aware(self):
        if self.lease_expires_at.tzinfo is None:
            raise ValueError("NAIVE_LEASE_TIME")
        return self


def finalize_patch(
    head: WorkspaceRevision,
    receipt: PatchReceipt,
    *,
    snapshot: CandidateSnapshot,
    authority: CommitAuthority,
    db_now: datetime,
    policy_digest: str,
) -> WorkspaceRevision:
    """authority ve db_now son transaction içinde kilitli DB kaydından okunmalıdır."""
    if (
        db_now.tzinfo is None
        or authority.attempt_state != "RUNNING"
        or db_now >= authority.lease_expires_at
    ):
        raise ValueError("COMMIT_LEASE_OR_ATTEMPT_INVALID")
    if authority.policy_digest != policy_digest:
        raise ValueError("COMMIT_POLICY_CHANGED")
    if any(
        getattr(head, k) != getattr(authority, k)
        for k in ["workspace_id", "attempt_id", "fencing_epoch", "revision", "candidate_digest"]
    ):
        raise ValueError("COMMIT_FENCING_OR_HEAD_CHANGED")
    return advance_workspace(head, receipt, committed_snapshot=snapshot)


class QualificationClaim(Contract):
    qualification_id: UUID
    attempt_id: UUID
    binding_digest: Digest
    policy_digest: Digest
    valid_from: datetime
    valid_until: datetime
    claimed_at: datetime
    completion_deadline: datetime

    @model_validator(mode="after")
    def bounds(self):
        dates = [self.valid_from, self.valid_until, self.claimed_at, self.completion_deadline]
        if (
            any(d.tzinfo is None for d in dates)
            or not self.valid_from <= self.claimed_at < self.valid_until
        ):
            raise ValueError("INVALID_QUALIFICATION_AT_CLAIM")
        if not 0 < (self.completion_deadline - self.claimed_at).total_seconds() <= 7200:
            raise ValueError("INVALID_COMPLETION_WINDOW")
        return self


def qualification_allows(
    claim: QualificationClaim,
    *,
    action: str,
    now: datetime,
    attempt_id: UUID,
    binding_digest: str,
    policy_digest: str,
    current_state: str,
    lease_active: bool,
) -> bool:
    """Claim kaydı server tarafından yaratılıp immutable saklanır; client snapshotı kabul edilmez."""
    if now.tzinfo is None or current_state not in {"ACTIVE", "EXPIRED"} or now < claim.claimed_at:
        return False
    if (attempt_id, binding_digest, policy_digest) != (
        claim.attempt_id,
        claim.binding_digest,
        claim.policy_digest,
    ):
        return False
    if action == "CLAIM":
        return current_state == "ACTIVE" and now == claim.claimed_at and now < claim.valid_until
    if action not in {"CONTINUE", "ACCEPT"} or lease_active is not True:
        return False
    return now < claim.completion_deadline


class VerificationIdentity(Contract):
    base_snapshot_digest: Digest
    candidate_revision: Revision
    candidate_digest: Digest
    runtime_image_digest: Digest
    dependencies_digest: Digest
    test_profile_digest: Digest


def same_verification_build(expected: VerificationIdentity, observed: VerificationIdentity) -> bool:
    """Trusted kimlikleri karşılaştırır; snapshot/image toplamaz veya test çalıştırmaz."""
    return expected.model_dump() == observed.model_dump()


PILOT_MODELS = [CommitAuthority, QualificationClaim, VerificationIdentity]
