"""v0.16.1 yürütme sınırı sözleşmeleri. Canlı engine/sandbox bağlantısı değildir."""

import hashlib
import hmac
import json
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal, Union
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from packages.contracts.company import WorkflowTemplateVersion, canonical_digest
from packages.contracts.models import Contract, Digest, Positive, Revision, SourceFingerprint, Text


class ReadArgs(Contract):
    relative_path: Annotated[str, Field(min_length=1, max_length=240)]
    max_bytes: Annotated[int, Field(ge=1, le=16384, strict=True)]

    @model_validator(mode="after")
    def safe_path(self):
        p = PurePosixPath(self.relative_path)
        if (
            not p.parts
            or p.is_absolute()
            or ".." in p.parts
            or any(x in self.relative_path for x in ["\\", ":"])
            or any(ord(c) < 32 or ord(c) == 127 for c in self.relative_path)
        ):
            raise ValueError("PATH_OUT_OF_SCOPE")
        return self


class ReadCall(Contract):
    tool_id: Literal["workspace.read"]
    arguments: ReadArgs


class PatchCall(Contract):
    tool_id: Literal["patch.apply"]
    patch_artifact_id: UUID
    expected_source_digest: Digest


class VerifyCall(Contract):
    tool_id: Literal["verification.request"]
    profile_digest: Digest
    candidate_digest: Digest


class ToolRequest(Contract):
    protocol: Literal["company-tool/1"]
    request_id: UUID
    engine_session_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    expected_revision: Revision
    sequence: Positive
    tool_manifest_digest: Digest
    call: Annotated[Union[ReadCall, PatchCall, VerifyCall], Field(discriminator="tool_id")]


class EngineBinding(Contract):
    engine_session_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    revision: Revision
    tool_manifest_digest: Digest


def no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def parse_tool_request(
    frame: bytes, *, binding: EngineBinding, expected_sequence: int, channel: str
) -> ToolRequest:
    if channel != "BOUND_ENGINE_STDOUT":
        raise ValueError("UNTRUSTED_CHANNEL")
    if len(frame) > 65536 or not frame.endswith(b"\n") or b"\n" in frame[:-1]:
        raise ValueError("INVALID_FRAME")
    raw = json.loads(frame.decode("utf-8"), object_pairs_hook=no_duplicate_keys)
    request = ToolRequest.model_validate(raw)
    if request.sequence != expected_sequence:
        raise ValueError("SEQUENCE_REPLAY_OR_GAP")
    expected = (
        binding.engine_session_id,
        binding.attempt_id,
        binding.fencing_epoch,
        binding.revision,
        binding.tool_manifest_digest,
    )
    actual = (
        request.engine_session_id,
        request.attempt_id,
        request.fencing_epoch,
        request.expected_revision,
        request.tool_manifest_digest,
    )
    if actual != expected:
        raise ValueError("STALE_ENGINE_BINDING")
    return request


class ToolReply(Contract):
    protocol: Literal["company-tool/1"]
    request_id: UUID
    status: Literal["OK", "DENIED", "STALE", "ERROR", "UNKNOWN_RECOVERY"]
    receipt_id: UUID | None
    artifact_ids: Annotated[list[UUID], Field(max_length=8)]
    error_code: Text | None

    @model_validator(mode="after")
    def receipt_for_ok(self):
        if self.status == "OK" and self.receipt_id is None:
            raise ValueError("RECEIPT_REQUIRED")
        return self


class RunAdmission(Contract):
    mode: Literal["EVALUATION", "QUALIFIED_AGENT"]
    tenant_id: UUID
    project_id: UUID
    human_evaluation_authorization_id: UUID | None
    fixture_manifest_digest: Digest | None
    qualification_id: UUID | None
    customer_order_id: UUID | None
    source_kind: Literal["DISPOSABLE_TEST", "CUSTOMER_PROJECT"]

    @model_validator(mode="after")
    def isolate_evaluation(self):
        if self.mode == "EVALUATION":
            if (
                self.source_kind != "DISPOSABLE_TEST"
                or self.customer_order_id is not None
                or self.human_evaluation_authorization_id is None
                or self.fixture_manifest_digest is None
            ):
                raise ValueError("EVALUATION_SCOPE_REQUIRED")
            if self.qualification_id is not None:
                raise ValueError("EVALUATION_IS_NOT_QUALIFICATION")
        elif self.qualification_id is None:
            raise ValueError("QUALIFICATION_REQUIRED")
        return self


class CompiledStage(Contract):
    stage_id: Text
    task_id: UUID
    dependency_task_ids: Annotated[list[UUID], Field(max_length=32)]
    required_capabilities: Annotated[list[Text], Field(min_length=1, max_length=20)]
    verification_profile: Text


class CompilePlan(Contract):
    instance_id: UUID
    logical_run_id: UUID
    tenant_id: UUID
    project_id: UUID
    plan_id: UUID
    template_digest: Digest
    input_digest: Digest
    policy_digest: Digest
    stages: Annotated[list[CompiledStage], Field(min_length=1, max_length=32)]


def compile_plan(
    template: WorkflowTemplateVersion,
    *,
    tenant_id: UUID,
    project_id: UUID,
    plan_id: UUID,
    logical_run_id: UUID,
    input_digest: str,
) -> CompilePlan:
    # Çağıran servis önce validate_template_binding ile pinli bağımlılıkları doğrular.
    payload = template.model_dump(mode="json")
    version = payload.pop("version")
    if canonical_digest(payload) != version:
        raise ValueError("TEMPLATE_CONTENT_CHANGED")
    fingerprint = f"{tenant_id}:{project_id}:{plan_id}:{logical_run_id}:{template.version}:{input_digest}:{template.policy_version}"
    instance = uuid5(NAMESPACE_URL, "company-workflow:" + fingerprint)
    ids = {stage.stage_id: uuid5(instance, stage.stage_id) for stage in template.stage_dag}
    stages = [
        CompiledStage(
            stage_id=s.stage_id,
            task_id=ids[s.stage_id],
            dependency_task_ids=[ids[x] for x in sorted(s.depends_on)],
            required_capabilities=s.required_capabilities,
            verification_profile=s.verification_profile,
        )
        for s in sorted(template.stage_dag, key=lambda s: s.stage_id)
    ]
    return CompilePlan(
        instance_id=instance,
        logical_run_id=logical_run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        plan_id=plan_id,
        template_digest=template.version,
        input_digest=input_digest,
        policy_digest=template.policy_version,
        stages=stages,
    )


class VerifierCheck(Contract):
    check_id: Text
    result: Literal["PASS", "FAIL", "BLOCKED"]


class VerifierReceipt(Contract):
    receipt_id: UUID
    tenant_id: UUID
    project_id: UUID
    task_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    purpose: Literal["TASK_VERIFICATION", "EVALUATION"]
    producer_id: UUID
    verifier_id: UUID
    candidate_digest: Digest
    source: SourceFingerprint
    profile_digest: Digest
    fixture_digest: Digest
    command_digest: Digest
    exit_code: Annotated[int, Field(strict=True)] | None
    stdout_artifact_id: UUID
    started_at: datetime
    ended_at: datetime
    checks: Annotated[list[VerifierCheck], Field(min_length=1, max_length=100)]
    key_id: UUID
    signature: Digest

    @model_validator(mode="after")
    def timestamps(self):
        if (
            self.started_at.tzinfo is None
            or self.ended_at.tzinfo is None
            or self.ended_at < self.started_at
        ):
            raise ValueError("INVALID_VERIFIER_TIME")
        if self.producer_id == self.verifier_id:
            raise ValueError("SELF_VERIFICATION")
        return self


def receipt_signature(payload: dict, key: bytes) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def acceptable_receipt(
    receipt: VerifierReceipt,
    *,
    key: bytes,
    expected: dict,
    mandatory_checks: set[str],
    verifier_is_enrolled: bool,
) -> bool:
    if verifier_is_enrolled is not True:
        return False
    data = receipt.model_dump(mode="json")
    if not hmac.compare_digest(receipt.signature, receipt_signature(data, key)):
        return False
    # expected kayıtları server tarafındaki VerificationRun/profile/attempt kaydından gelir.
    required = {
        "tenant_id",
        "project_id",
        "task_id",
        "attempt_id",
        "fencing_epoch",
        "producer_id",
        "verifier_id",
        "candidate_digest",
        "source",
        "profile_digest",
        "fixture_digest",
        "command_digest",
        "key_id",
    }
    if set(expected) != required or any(data[k] != expected[k] for k in required):
        return False
    checks = [c.check_id for c in receipt.checks]
    return (
        receipt.purpose == "TASK_VERIFICATION"
        and receipt.exit_code == 0
        and len(checks) == len(set(checks))
        and set(checks) == mandatory_checks
        and all(c.result == "PASS" for c in receipt.checks)
    )


class EvaluationSummary(Contract):
    unique_fixtures: Positive
    easy: Revision
    medium: Revision
    hard: Revision
    holdout_unique: Revision
    repeats_per_fixture: Positive
    executions: Positive
    correct_executions: Revision
    holdout_correct_executions: Revision
    false_accepts: Revision
    critical_regressions: Revision
    safety_failures: Revision
    suite_digest: Digest


def evaluation_gate(
    summary: EvaluationSummary, *, verified_runner_evidence: bool, human_reviewed: bool
) -> str:
    if verified_runner_evidence is not True:
        return "BLOCKED_UNVERIFIED_EVIDENCE"
    if human_reviewed is not True:
        return "PENDING_HUMAN_REVIEW"
    s = summary
    if s.easy + s.medium + s.hard != s.unique_fixtures or s.holdout_unique > s.unique_fixtures:
        return "FAIL_INVALID_COVERAGE"
    if (
        s.unique_fixtures < 30
        or min(s.easy, s.medium, s.hard) < 10
        or s.holdout_unique < 10
        or s.repeats_per_fixture < 2
    ):
        return "FAIL_INSUFFICIENT_COVERAGE"
    if (
        s.executions != s.unique_fixtures * s.repeats_per_fixture
        or s.correct_executions > s.executions
        or s.holdout_correct_executions > s.holdout_unique * s.repeats_per_fixture
    ):
        return "FAIL_INVALID_DENOMINATOR"
    if s.false_accepts or s.critical_regressions or s.safety_failures:
        return "FAIL_SAFETY_OR_REGRESSION"
    if (
        s.correct_executions * 100 < s.executions * 90
        or s.holdout_correct_executions * 100 < s.holdout_unique * s.repeats_per_fixture * 90
    ):
        return "FAIL_QUALITY_THRESHOLD"
    return "ELIGIBLE_FOR_SCOPED_QUALIFICATION"


def effect_transition(
    before: str,
    after: str,
    *,
    verified_receipt=False,
    definitive_absence=False,
    fresh_human_approval=False,
) -> str:
    allowed = {
        "PREPARED": {"AUTHORIZED", "CANCELLED", "REJECTED"},
        "AUTHORIZED": {"DISPATCHED", "CANCELLED", "REJECTED"},
        "DISPATCHED": {"CONFIRMED", "UNKNOWN_EXTERNAL_EFFECT"},
        "UNKNOWN_EXTERNAL_EFFECT": {"CONFIRMED", "NOT_APPLIED_CONFIRMED"},
        "NOT_APPLIED_CONFIRMED": {"PREPARED"},
        "CONFIRMED": set(),
        "CANCELLED": set(),
        "REJECTED": set(),
    }
    if after not in allowed.get(before, set()):
        raise ValueError("INVALID_EFFECT_TRANSITION")
    if after == "CONFIRMED" and verified_receipt is not True:
        raise ValueError("EFFECT_RECEIPT_REQUIRED")
    if after == "NOT_APPLIED_CONFIRMED" and definitive_absence is not True:
        raise ValueError("DEFINITIVE_ABSENCE_REQUIRED")
    if before == "NOT_APPLIED_CONFIRMED" and (
        definitive_absence is not True or fresh_human_approval is not True
    ):
        raise ValueError("RECONCILED_RETRY_AUTH_REQUIRED")
    return after


EXECUTION_MODELS = [
    ToolRequest,
    EngineBinding,
    ToolReply,
    RunAdmission,
    CompilePlan,
    VerifierReceipt,
    EvaluationSummary,
]
