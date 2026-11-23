"""Dijital şirket sözleşmeleri ve saf karar korumaları; çalışan Kernel değildir."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from packages.contracts.models import (
    Contract,
    Digest,
    Positive,
    Revision,
    SourceFingerprint,
    Text,
    Title,
)

SkillCode = Annotated[str, Field(pattern=r"^SKILL_[A-Z0-9_]{3,64}$")]


class Mission(Contract):
    mission_id: UUID
    tenant_id: UUID
    objective_id: UUID
    revision: Revision
    state: Literal["PROPOSED", "ACTIVE", "PAUSED", "CLOSED"]
    activation_approval_id: UUID | None
    outcome_metric: Title
    target_value: Annotated[int, Field(ge=0, strict=True)]
    observed_value: Annotated[int, Field(strict=True)] | None
    currency: Literal["TRY"] | None
    metric_unit: Literal["COUNT", "TRY_MINOR_UNITS"]
    deadline: datetime
    max_active_projects: Annotated[int, Field(ge=1, le=10, strict=True)]

    @model_validator(mode="after")
    def active_requires_approval(self):
        if self.state == "ACTIVE" and self.activation_approval_id is None:
            raise ValueError("MISSION_ACTIVATION_APPROVAL_REQUIRED")
        if self.deadline.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        if (self.metric_unit == "TRY_MINOR_UNITS") != (self.currency == "TRY"):
            raise ValueError("METRIC_UNIT_CURRENCY_MISMATCH")
        if (
            self.metric_unit == "COUNT"
            and self.observed_value is not None
            and self.observed_value < 0
        ):
            raise ValueError("NEGATIVE_COUNT")
        return self


class Stage(Contract):
    stage_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
    depends_on: list[str]
    required_capabilities: Annotated[list[SkillCode], Field(min_length=1)]
    verification_profile: Text


class WorkflowTemplateVersion(Contract):
    template_id: Text
    version: Digest
    job_class: Text
    input_schema: Text
    required_capabilities: Annotated[list[SkillCode], Field(min_length=1)]
    stage_dag: Annotated[list[Stage], Field(min_length=1, max_length=32)]
    policy_version: Digest
    budget_profile: Text
    budget_profile_digest: Digest
    schema_bundle_digest: Digest
    verification_profile: Text
    verification_profile_digest: Digest
    output_schema: Text
    failure_policy: Literal["STOP_AND_RECORD", "BOUNDED_REVISION"]
    compensation_policy: Literal["RESTORE_ISOLATED_COPY", "QUARANTINE_OUTPUT", "NO_SIDE_EFFECT"]
    runtime_status: Literal["NOT_IMPLEMENTED"]

    @model_validator(mode="after")
    def dag_is_closed(self):
        ids = [s.stage_id for s in self.stage_dag]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_STAGE")
        available = set(self.required_capabilities)
        deps = {s.stage_id: set(s.depends_on) for s in self.stage_dag}
        for stage in self.stage_dag:
            if not set(stage.required_capabilities) <= available:
                raise ValueError("UNDECLARED_CAPABILITY")
            if len(stage.depends_on) != len(set(stage.depends_on)):
                raise ValueError("DUPLICATE_DEPENDENCY")
            if not deps[stage.stage_id] <= set(ids):
                raise ValueError("UNKNOWN_STAGE")
        resolved: set[str] = set()
        while len(resolved) < len(ids):
            ready = {
                ident
                for ident, parents in deps.items()
                if ident not in resolved and parents <= resolved
            }
            if not ready:
                raise ValueError("WORKFLOW_CYCLE")
            resolved |= ready
        return self


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_template_binding(
    template: WorkflowTemplateVersion, *, policy: dict, budget: dict, profile: dict, schemas: dict
) -> bool:
    payload = template.model_dump(mode="json")
    version = payload.pop("version")
    if canonical_digest(payload) != version:
        raise ValueError("TEMPLATE_CONTENT_CHANGED")
    for expected, actual in [
        (template.policy_version, policy),
        (template.budget_profile_digest, budget),
        (template.verification_profile_digest, profile),
        (template.schema_bundle_digest, schemas),
    ]:
        if canonical_digest(actual) != expected:
            raise ValueError("TEMPLATE_DEPENDENCY_CHANGED")
    if (
        budget.get("id") != template.budget_profile
        or profile.get("profile_id") != template.verification_profile
    ):
        raise ValueError("TEMPLATE_REFERENCE_MISMATCH")
    return True


class Qualification(Contract):
    tenant_id: UUID
    role_id: Text
    skill_code: SkillCode
    model_digest: Digest
    engine_version: Text
    role_digest: Digest
    tool_manifest_digest: Digest
    suite_digest: Digest
    result: Literal["PASS", "FAIL", "REVOKED", "NOT_RUN"]
    valid_until: datetime
    false_accepts: Annotated[int, Field(ge=0, strict=True)]

    @model_validator(mode="after")
    def truthful(self):
        if self.valid_until.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        if self.result == "PASS" and self.false_accepts != 0:
            raise ValueError("FALSE_ACCEPT_DISQUALIFIES")
        return self


def eligible(
    q: Qualification,
    *,
    tenant_id: UUID,
    role_id: str,
    skill_code: str,
    model_digest: str,
    engine_version: str,
    role_digest: str,
    tool_manifest_digest: str,
    suite_digest: str,
    now: datetime,
) -> bool:
    if now.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return (
        q.result == "PASS"
        and q.false_accepts == 0
        and q.valid_until > now
        and (
            q.tenant_id,
            q.role_id,
            q.skill_code,
            q.model_digest,
            q.engine_version,
            q.role_digest,
            q.tool_manifest_digest,
            q.suite_digest,
        )
        == (
            tenant_id,
            role_id,
            skill_code,
            model_digest,
            engine_version,
            role_digest,
            tool_manifest_digest,
            suite_digest,
        )
    )


class ActionScope(Contract):
    tenant_id: UUID
    project_id: UUID
    task_id: UUID
    action_digest: Digest
    target_digest: Digest
    policy_digest: Digest
    effect: Literal[
        "ANALYZE",
        "READ_AUTHORIZED",
        "WRITE_ISOLATED_TEST",
        "SEND_MESSAGE",
        "SPEND_MONEY",
        "PUBLISH_PRODUCTION",
        "SHARE_CUSTOMER_DATA",
    ]


class HumanAuthorization(ActionScope):
    approval_id: UUID
    approved_by: UUID
    expires_at: datetime
    revoked: bool
    consumed: bool

    @model_validator(mode="after")
    def aware(self):
        if self.expires_at.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return self


def authorize(
    *,
    scope: ActionScope,
    effect: str,
    level: int,
    grants: dict[str, bool],
    trusted_origin: str,
    approval: HumanAuthorization | None,
    now: datetime,
) -> str:
    """Girdiler gelecekte doğrulanmış Kernel kaydından gelir; modelden alınmaz."""
    if now.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    if type(level) is not int or level not in range(5):
        return "DENY_INVALID_LEVEL"
    if trusted_origin not in {"HUMAN_REQUEST", "KERNEL_POLICY"}:
        return "DENY_UNTRUSTED_AUTHORITY"
    required = {"role", "tool", "task", "policy"}
    if set(grants) != required or any(value is not True for value in grants.values()):
        return "DENY_SCOPE"
    minimum = {
        "ANALYZE": 0,
        "READ_AUTHORIZED": 1,
        "WRITE_ISOLATED_TEST": 2,
        "SEND_MESSAGE": 3,
        "SPEND_MONEY": 3,
        "PUBLISH_PRODUCTION": 3,
        "SHARE_CUSTOMER_DATA": 3,
    }
    if effect not in minimum:
        return "DENY_UNKNOWN_EFFECT"
    if scope.effect != effect:
        return "DENY_ACTION_BINDING"
    if level < minimum[effect]:
        return "DENY_AUTONOMY_LEVEL"
    if minimum[effect] < 3:
        return "ALLOW_WITHIN_SCOPE"
    if approval is None:
        return "REQUIRES_HUMAN_AUTHORIZATION"
    bound = all(getattr(approval, k) == getattr(scope, k) for k in ActionScope.model_fields)
    if not bound or approval.revoked or approval.consumed or approval.expires_at <= now:
        return "DENY_STALE_APPROVAL"
    return "ALLOW_SINGLE_AUTHORIZED_ACTION"


class ToolDefinitionVersion(Contract):
    tool_id: Text
    manifest_digest: Digest
    input_schema: Text
    output_schema: Text
    effect: Literal[
        "READ_AUTHORIZED",
        "WRITE_ISOLATED_TEST",
        "SEND_MESSAGE",
        "SPEND_MONEY",
        "PUBLISH_PRODUCTION",
        "SHARE_CUSTOMER_DATA",
    ]
    executor: Literal["ROOTLESS_CONTAINER", "LOCAL_READ_BROKER", "APPROVED_CONNECTOR"]
    data_trust: Literal["UNTRUSTED_SOURCE", "DERIVED_EVIDENCE", "VERIFIED_RECORD"]
    network: Literal["NONE", "EXPLICIT_ALLOWLIST"]
    network_allowlist: Annotated[
        list[Annotated[str, Field(pattern=r"^https://[a-z0-9.-]+(?::443)?$")]], Field(max_length=20)
    ] = Field(default_factory=list)
    timeout_seconds: Annotated[int, Field(ge=1, le=600, strict=True)]
    output_limit_bytes: Annotated[int, Field(ge=1, le=52428800, strict=True)]
    compensation: Text
    activation: Literal["DISABLED"]

    @model_validator(mode="after")
    def explicit_network_scope(self):
        if self.network == "EXPLICIT_ALLOWLIST" and not self.network_allowlist:
            raise ValueError("NETWORK_ALLOWLIST_REQUIRED")
        if self.network == "NONE" and self.network_allowlist:
            raise ValueError("NETWORK_NONE_WITH_DESTINATIONS")
        return self


class VerificationProfileVersion(Contract):
    profile_id: Text
    job_class: Text
    required_checks: Annotated[list[Text], Field(min_length=2)]
    independent_actor_required: Literal[True]
    source_fingerprint_required: Literal[True]
    missing_evidence: Literal["BLOCKED"]
    failing_check: Literal["FAIL"]
    runtime_status: Literal["NOT_IMPLEMENTED"]


class IntegrationCandidate(Contract):
    candidate_digest: Digest
    base_digest: Digest
    changeset_digests: Annotated[list[Digest], Field(min_length=1)]
    integrated_verification_digest: Digest | None
    verified_candidate_digest: Digest | None
    conflict_count: Annotated[int, Field(ge=0, strict=True)]
    check_result: Literal["PASS", "FAIL", "NOT_RUN"]


def releasable(candidate: IntegrationCandidate, current_base_digest: str) -> bool:
    return (
        candidate.base_digest == current_base_digest
        and candidate.conflict_count == 0
        and candidate.check_result == "PASS"
        and candidate.integrated_verification_digest is not None
        and candidate.verified_candidate_digest == candidate.candidate_digest
    )


class EvaluationScorecard(Contract):
    suite_digest: Digest
    candidate_digest: Digest
    sample_count: Positive
    first_pass_count: Annotated[int, Field(ge=0, strict=True)]
    false_accepts: Annotated[int, Field(ge=0, strict=True)]
    critical_regressions: Annotated[int, Field(ge=0, strict=True)]
    # Bu ölçüler gerçek zaman sayacı/receiptlerden gelir; boş veri 0'a çevrilmez.
    total_duration_ms: Annotated[int, Field(ge=0, strict=True)] | None
    resource_units: Annotated[int, Field(ge=0, strict=True)] | None

    @model_validator(mode="after")
    def count_is_realistic(self):
        if self.first_pass_count > self.sample_count:
            raise ValueError("INVALID_DENOMINATOR")
        return self


def promotion_eligible(
    baseline: EvaluationScorecard,
    candidate: EvaluationScorecard,
    *,
    human_authorized: bool,
    policy_changed: bool,
    quality_threshold_lowered: bool,
) -> bool:
    if (
        human_authorized is not True
        or policy_changed is not False
        or quality_threshold_lowered is not False
    ):
        return False
    if candidate.candidate_digest == baseline.candidate_digest:
        return False
    if (
        candidate.suite_digest != baseline.suite_digest
        or candidate.sample_count != baseline.sample_count
    ):
        return False
    if candidate.false_accepts or candidate.critical_regressions:
        return False
    if (
        baseline.total_duration_ms is None
        or baseline.resource_units is None
        or candidate.total_duration_ms is None
        or candidate.resource_units is None
    ):
        return False
    b_duration = baseline.total_duration_ms
    b_resources = baseline.resource_units
    c_duration = candidate.total_duration_ms
    c_resources = candidate.resource_units
    no_worse = (
        candidate.first_pass_count >= baseline.first_pass_count
        and c_duration <= b_duration
        and c_resources <= b_resources
    )
    improved = (
        candidate.first_pass_count > baseline.first_pass_count
        or c_duration < b_duration
        or c_resources < b_resources
    )
    return no_worse and improved


def business_completion(
    *, technical_accepted: bool, customer_accepted: bool, collection_verified: bool
) -> dict:
    return {
        "delivery_completed": technical_accepted is True and customer_accepted is True,
        "collection_verified": collection_verified is True,
        "net_income": "UNKNOWN_REQUIRES_COST_PERIOD_TAX_RECONCILIATION",
    }


class SoftwareJobInput(Contract):
    project_id: UUID
    task_id: UUID
    workspace_id: UUID
    source: SourceFingerprint
    expected_behavior: Annotated[str, Field(min_length=10, max_length=4000)]
    acceptance_criteria: Annotated[list[Text], Field(min_length=1, max_length=20)]


class SoftwareJobOutput(Contract):
    task_id: UUID
    attempt_id: UUID
    changeset_digest: Digest
    patch_artifact_id: UUID
    source: SourceFingerprint
    status: Literal["PROPOSED_NOT_ACCEPTED"]


class SpreadsheetJobInput(Contract):
    project_id: UUID
    task_id: UUID
    input_artifact_id: UUID
    input_sha256: Digest
    expected_sheets: Annotated[list[Title], Field(min_length=1, max_length=30)]
    required_checks: Annotated[list[Text], Field(min_length=2, max_length=30)]


class SpreadsheetJobOutput(Contract):
    task_id: UUID
    attempt_id: UUID
    output_artifact_id: UUID
    output_sha256: Digest
    formula_report_artifact_id: UUID
    status: Literal["PROPOSED_NOT_ACCEPTED"]


class ResearchJobInput(Contract):
    project_id: UUID
    task_id: UUID
    question: Annotated[str, Field(min_length=10, max_length=4000)]
    source_artifact_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]
    freshness_cutoff: datetime

    @model_validator(mode="after")
    def timezone_required(self):
        if self.freshness_cutoff.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return self


class ResearchClaim(Contract):
    claim: Text
    source_artifact_ids: Annotated[list[UUID], Field(max_length=30)]
    status: Literal["SUPPORTED", "CONTRADICTED", "UNRESOLVED"]

    @model_validator(mode="after")
    def sourced_claim(self):
        if self.status != "UNRESOLVED" and not self.source_artifact_ids:
            raise ValueError("CLAIM_SOURCE_REQUIRED")
        return self


class ResearchJobOutput(Contract):
    task_id: UUID
    attempt_id: UUID
    report_artifact_id: UUID
    report_sha256: Digest
    claims: Annotated[list[ResearchClaim], Field(min_length=1, max_length=100)]
    status: Literal["PROPOSED_NOT_ACCEPTED"]


COMPANY_MODELS = [
    Mission,
    WorkflowTemplateVersion,
    Qualification,
    ActionScope,
    HumanAuthorization,
    ToolDefinitionVersion,
    VerificationProfileVersion,
    IntegrationCandidate,
    EvaluationScorecard,
    SoftwareJobInput,
    SoftwareJobOutput,
    SpreadsheetJobInput,
    SpreadsheetJobOutput,
    ResearchJobInput,
    ResearchJobOutput,
]
