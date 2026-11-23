"""Saf yaşam döngüsü korumaları; disk transactionı veya güvenilir worker değildir."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from packages.contracts.execution import VerifierReceipt, acceptable_receipt
from packages.contracts.models import Contract, Digest, Positive, Revision, SourceFingerprint


class WorkspaceRevision(Contract):
    workspace_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    revision: Revision
    source: SourceFingerprint
    candidate_digest: Digest


class CandidateSnapshot(WorkspaceRevision):
    manifest_artifact_id: UUID
    immutable: Literal[True]


class PatchReceipt(Contract):
    receipt_id: UUID
    request_id: UUID
    workspace_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    before_revision: Revision
    after_revision: Revision
    before_digest: Digest
    after_digest: Digest
    patch_artifact_id: UUID
    status: Literal["APPLIED", "REJECTED", "RECOVERY_REQUIRED"]

    @model_validator(mode="after")
    def progression(self):
        if self.status == "APPLIED" and self.after_revision != self.before_revision + 1:
            raise ValueError("PATCH_REVISION_MUST_ADVANCE_ONCE")
        if self.status != "APPLIED" and (
            self.after_revision != self.before_revision or self.after_digest != self.before_digest
        ):
            raise ValueError("UNCOMMITTED_PATCH_MUST_NOT_ADVANCE_HEAD")
        return self


def advance_workspace(
    head: WorkspaceRevision, receipt: PatchReceipt, *, committed_snapshot: CandidateSnapshot
) -> WorkspaceRevision:
    """Yalnız trusted Broker'ın CAS sonrası kaydı içindir; dosya yazmaz."""
    identity = ("workspace_id", "attempt_id", "fencing_epoch")
    if any(
        getattr(head, k) != getattr(receipt, k)
        or getattr(head, k) != getattr(committed_snapshot, k)
        for k in identity
    ):
        raise ValueError("WORKSPACE_BINDING_MISMATCH")
    if receipt.before_revision != head.revision or receipt.before_digest != head.candidate_digest:
        raise ValueError("STALE_WORKSPACE_REVISION")
    if receipt.status != "APPLIED":
        raise ValueError("PATCH_NOT_COMMITTED")
    if (
        committed_snapshot.revision != receipt.after_revision
        or committed_snapshot.candidate_digest != receipt.after_digest
        or committed_snapshot.source != head.source
    ):
        raise ValueError("SNAPSHOT_RECEIPT_MISMATCH")
    return WorkspaceRevision.model_validate(
        committed_snapshot.model_dump(exclude={"manifest_artifact_id", "immutable"})
    )


class SignerEnrollment(Contract):
    key_id: UUID
    verifier_id: UUID
    tenant_id: UUID
    project_id: UUID
    worker_image_digest: Digest
    valid_from: datetime
    valid_until: datetime
    state: Literal["ACTIVE", "REVOKED", "SUSPENDED"]

    @model_validator(mode="after")
    def interval(self):
        if (
            self.valid_from.tzinfo is None
            or self.valid_until.tzinfo is None
            or self.valid_until <= self.valid_from
        ):
            raise ValueError("INVALID_ENROLLMENT_INTERVAL")
        return self


def trusted_receipt(
    receipt: VerifierReceipt,
    *,
    enrollment: SignerEnrollment,
    now: datetime,
    worker_image_digest: str,
    process_evidence_verified: bool,
    receipt_already_consumed: bool,
    key: bytes,
    expected: dict,
    mandatory_checks: set[str],
) -> bool:
    """Girdiler trusted kayıtlar olmalı; bu fonksiyon process kanıtı toplamaz."""
    if now.tzinfo is None or enrollment.state != "ACTIVE":
        return False
    if (
        not enrollment.valid_from
        <= receipt.started_at
        <= receipt.ended_at
        <= now
        < enrollment.valid_until
    ):
        return False
    if any(
        getattr(receipt, k) != getattr(enrollment, k)
        for k in ("key_id", "verifier_id", "tenant_id", "project_id")
    ):
        return False
    if (
        worker_image_digest != enrollment.worker_image_digest
        or process_evidence_verified is not True
        or receipt_already_consumed is not False
    ):
        return False
    return acceptable_receipt(
        receipt,
        key=key,
        expected=expected,
        mandatory_checks=mandatory_checks,
        verifier_is_enrolled=True,
    )


def renewal_route(
    *,
    has_qualification: bool,
    expired: bool,
    binding_changed: bool,
    critical_incident: bool,
    contamination_suspected: bool,
    periodic_check_due: bool,
) -> str:
    """Kısmi kontrol qualification süresini uzatmaz; güvenlik eşiği sabittir."""
    if critical_incident:
        return "SUSPEND_AND_FULL_REQUALIFICATION"
    if contamination_suspected:
        return "NEW_HOLDOUT_AND_FULL_REQUALIFICATION"
    if not has_qualification or binding_changed or expired:
        return "FULL_QUALIFICATION_REQUIRED"
    if periodic_check_due:
        return "RISK_BASED_HEALTH_CHECK_NO_EXTENSION"
    return "KEEP_UNTIL_ORIGINAL_EXPIRY"


LIFECYCLE_MODELS = [WorkspaceRevision, CandidateSnapshot, PatchReceipt, SignerEnrollment]
