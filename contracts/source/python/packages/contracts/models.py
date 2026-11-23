from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Title = Annotated[str, Field(min_length=3, max_length=200)]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Revision = Annotated[int, Field(ge=0, strict=True)]
Positive = Annotated[int, Field(gt=0, strict=True)]


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class TaskState(str, Enum):
    DRAFT='DRAFT'
    READY='READY'
    RUNNING='RUNNING'
    WAITING_APPROVAL='WAITING_APPROVAL'
    VERIFYING='VERIFYING'
    CHANGES_REQUIRED='CHANGES_REQUIRED'
    BLOCKED='BLOCKED'
    ACCEPTED='ACCEPTED'
    FAILED='FAILED'
    CANCELLED='CANCELLED'


class SourceFingerprint(Contract):
    build_digest: Digest
    commit: Annotated[str, Field(pattern=r'^(?:[a-f0-9]{40}|UNCOMMITTED)$')]
    dirty_digest: Digest


class CommandMeta(Contract):
    idempotency_key: Annotated[str, Field(min_length=16, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')]
    correlation_id: UUID


class ProjectCreate(CommandMeta):
    name: Title
    workspace_id: UUID
    # tenant_id, actor_id ve mutlak root kullanıcı payloadından alınmaz.


class BootstrapRequest(Contract):
    bootstrap_token: Digest
    owner_name: Title


class SessionRead(Contract):
    principal_id: UUID
    tenant_id: UUID
    permissions: list[str]


class LeaseRead(Contract):
    attempt_id: UUID
    task_id: UUID
    fencing_epoch: Positive
    lease_expires_at: datetime


class ArtifactRead(Contract):
    id: UUID
    project_id: UUID
    task_id: UUID
    attempt_id: UUID
    sha256: Digest
    size_bytes: Annotated[int, Field(ge=0, strict=True)]
    state: Literal['STAGING','AVAILABLE','QUARANTINED']


class WorkspaceRead(Contract):
    id: UUID
    name: Title
    trust_class: Literal['DISPOSABLE_TEST','TRUSTED_LOCAL','UNTRUSTED']


class WorkspaceList(Contract):
    items: Annotated[list[WorkspaceRead],Field(max_length=200)]


class ProjectRead(Contract):
    id: UUID
    workspace_id: UUID
    name: Title
    revision: Revision


class ProjectList(Contract):
    items: Annotated[list[ProjectRead],Field(max_length=200)]


class ObjectiveRead(Contract):
    id: UUID
    project_id: UUID
    goal: Annotated[str,Field(min_length=10,max_length=4000)]
    constraints: list[Text]
    expected_outputs: list[Text]


class PlanRead(Contract):
    id: UUID
    project_id: UUID
    objective_id: UUID
    revision: Revision
    assumptions: list[Text]
    acceptance_criteria: Annotated[list[Text],Field(min_length=1)]


class ObjectiveCreate(CommandMeta):
    project_id: UUID
    goal: Annotated[str, Field(min_length=10, max_length=4000)]
    constraints: Annotated[list[Text], Field(min_length=1, max_length=20)]
    expected_outputs: Annotated[list[Text], Field(min_length=1, max_length=10)]


class PlanCreate(CommandMeta):
    project_id: UUID
    objective_id: UUID
    expected_revision: Revision
    assumptions: Annotated[list[Text], Field(max_length=20)]
    acceptance_criteria: Annotated[list[Text], Field(min_length=1, max_length=20)]


class TaskCreate(CommandMeta):
    project_id: UUID
    plan_id: UUID
    title: Title
    role_id: Annotated[str, Field(pattern=r'^(?:MGR|EXP)-\d{2,3}$')]
    acceptance_criteria: Annotated[list[Text], Field(min_length=1, max_length=20)]
    depends_on: Annotated[list[UUID], Field(max_length=32, json_schema_extra={'uniqueItems':True})] = Field(default_factory=list)

    @field_validator('depends_on')
    @classmethod
    def unique_dependencies(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('DUPLICATE_DEPENDENCY')
        return value


class TaskAction(CommandMeta):
    expected_revision: Revision
    action: Literal['ready', 'cancel', 'retry', 'approve', 'reject']
    reason: Text
    approval_ref: UUID | None = None

    @model_validator(mode='after')
    def approval_required(self):
        if self.action in {'approve','reject'} and self.approval_ref is None:
            raise ValueError('APPROVAL_REFERENCE_REQUIRED')
        return self


class ClaimRequest(CommandMeta):
    project_id: UUID
    capabilities: Annotated[list[Annotated[str, Field(min_length=1, max_length=80)]], Field(min_length=1, max_length=20)]


class AttemptReport(CommandMeta):
    model_config = ConfigDict(extra='forbid',json_schema_extra={'allOf':[{'if':{'properties':{'state':{'enum':['STOPPED','PRODUCED']}}},'then':{'required':['receipt_id'],'properties':{'receipt_id':{'type':'string','format':'uuid'}}}}]})
    attempt_id: UUID
    fencing_epoch: Positive
    expected_revision: Revision
    state: Literal['RUNNING','CANCEL_REQUESTED','STOPPED','FAILED','PRODUCED','UNKNOWN_RECOVERY']
    receipt_id: UUID | None = None

    @model_validator(mode='after')
    def receipt_required(self):
        if self.state in {'STOPPED','PRODUCED'} and self.receipt_id is None:
            raise ValueError('RECEIPT_REQUIRED')
        return self


class Heartbeat(Contract):
    attempt_id: UUID
    fencing_epoch: Positive


class ArtifactStage(CommandMeta):
    project_id: UUID
    task_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    filename: Annotated[str, Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$',json_schema_extra={'not':{'pattern':r'\.\.|\.$'}})]
    sha256: Digest
    size_bytes: Annotated[int, Field(ge=0, le=50*1024*1024, strict=True)]
    media_type: Literal['text/plain','application/json','application/zip','text/x-diff']

    @field_validator('filename')
    @classmethod
    def safe_filename(cls,value):
        if '..' in value or value.endswith('.'):
            raise ValueError('INVALID_ARTIFACT_NAME')
        return value


class VerificationRequest(CommandMeta):
    task_id: UUID
    attempt_id: UUID
    expected_revision: Revision
    profile_version: Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,63}$')]
    source: SourceFingerprint
    artifact_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]


class AcceptanceRequest(CommandMeta):
    task_id: UUID
    attempt_id: UUID
    expected_revision: Revision
    verification_run_id: UUID
    evidence_ids: Annotated[list[UUID], Field(min_length=1, max_length=30)]
    source: SourceFingerprint


class VerificationReport(CommandMeta):
    model_config = ConfigDict(extra='forbid',json_schema_extra={'allOf':[{'if':{'properties':{'result':{'const':'PASS'}}},'then':{'properties':{'exit_code':{'const':0},'evidence_ids':{'minItems':1}},'required':['exit_code']}}]})
    verification_run_id: UUID
    task_id: UUID
    attempt_id: UUID
    fencing_epoch: Positive
    profile_version: Annotated[str,Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,63}$')]
    source: SourceFingerprint
    result: Literal['PASS','FAIL','BLOCKED']
    exit_code: Annotated[int,Field(strict=True)] | None
    evidence_ids: Annotated[list[UUID],Field(max_length=30)]

    @model_validator(mode='after')
    def pass_requires_evidence(self):
        if self.result=='PASS' and (self.exit_code!=0 or not self.evidence_ids):
            raise ValueError('PASS_REQUIRES_EXIT_AND_EVIDENCE')
        return self


class VerificationRead(Contract):
    id: UUID
    task_id: UUID
    attempt_id: UUID
    profile_version: str
    source: SourceFingerprint
    result: Literal['NOT_RUN','RUNNING','PASS','FAIL','BLOCKED']
    exit_code: Annotated[int,Field(strict=True)] | None


class MessageCreate(CommandMeta):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True,json_schema_extra={'allOf':[{'if':{'properties':{'kind':{'const':'ANSWER'}}},'then':{'required':['reply_to'],'properties':{'reply_to':{'type':'string','format':'uuid'}}}}]})
    project_id: UUID
    task_id: UUID
    attempt_id: UUID
    recipient_id: UUID
    kind: Literal['QUESTION','ANSWER','HELP_REQUEST','FINDING','REVIEW_REQUEST','HANDOFF','BLOCKER','STATUS']
    body: Annotated[str, Field(min_length=1, max_length=16384)]
    reply_to: UUID | None = None

    @model_validator(mode='after')
    def validate_message(self):
        if len(self.body.encode('utf-8')) > 16384:
            raise ValueError('MESSAGE_BYTES_EXCEEDED')
        if self.kind == 'ANSWER' and self.reply_to is None:
            raise ValueError('ANSWER_REQUIRES_REPLY_TO')
        return self


class ErrorEnvelope(Contract):
    code: Annotated[str, Field(pattern=r'^[A-Z][A-Z0-9_]{2,63}$')]
    message: Text
    correlation_id: UUID
    retryable: Annotated[bool,Field(strict=True)]
    # Serbest exception/stack/dict taşınmaz.


class CommandReceipt(Contract):
    command_id: UUID
    correlation_id: UUID
    state: Literal['QUEUED','RUNNING','SUCCEEDED','FAILED']
    result_ref: UUID | None = None


class TaskRead(Contract):
    id: UUID
    project_id: UUID
    title: Title
    state: TaskState
    revision: Revision
    active_attempt_id: UUID | None = None


class SnapshotRead(Contract):
    project_id: UUID
    cursor: Revision
    tasks: Annotated[list[TaskRead], Field(max_length=200)]


class EventEnvelope(Contract):
    event_id: Positive
    tenant_id: UUID
    project_id: UUID
    aggregate_id: UUID
    aggregate_revision: Revision
    attempt_id: UUID | None
    kind: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.]{1,79}$')]
    occurred_at: datetime
    # İstemciye serbest DB satırı taşımayan, sınırlı projection.
    task_state: TaskState | None = None

    @field_validator('occurred_at')
    @classmethod
    def aware_time(cls,value):
        if value.tzinfo is None:
            raise ValueError('TIMEZONE_REQUIRED')
        return value


class RoleBudget(Contract):
    max_turns: Annotated[int, Field(ge=1, le=3, strict=True)]
    max_tool_calls: Annotated[int, Field(ge=0, le=12, strict=True)]
    timeout_seconds: Annotated[int, Field(ge=30, le=600, strict=True)]
    paid_provider_allowed: Literal[False]


class RoleCard(Contract):
    schema_version: Literal['0.15']
    role_id: Annotated[str, Field(pattern=r'^(?:MGR-00|EXP-\d{3})$')]
    name: Title
    activation_status: Literal['DISABLED']
    approval_status: Literal['PENDING_HUMAN_REVIEW']
    competency_status: Literal['NOT_RUN']
    source_file: Text
    source_sha256: Digest
    license_sha256: Digest
    source_is_authority: Literal[False]
    purpose: Text
    inputs: Annotated[list[Text], Field(min_length=1)]
    outputs: Annotated[list[Text], Field(min_length=1)]
    requested_capabilities: Annotated[list[Text], Field(min_length=1)]
    allowed_tools: Annotated[list[str], Field(max_length=0)]
    budget: RoleBudget
    workflow: Annotated[list[Text], Field(min_length=3)]
    handoff_to: Annotated[list[str], Field(min_length=1)]
    stop_conditions: Annotated[list[Text], Field(min_length=2)]
    acceptance_checks: Annotated[list[Text], Field(min_length=2)]
    adaptations: Annotated[list[Text], Field(min_length=2)]


TRANSITIONS = {
    'DRAFT': {'READY','CANCELLED'},
    'READY': {'RUNNING','BLOCKED','CANCELLED'},
    'RUNNING': {'WAITING_APPROVAL','VERIFYING','BLOCKED','FAILED','CANCELLED'},
    'WAITING_APPROVAL': {'READY','BLOCKED','CANCELLED'},
    'VERIFYING': {'ACCEPTED','CHANGES_REQUIRED','BLOCKED','FAILED','CANCELLED'},
    'CHANGES_REQUIRED': {'READY','CANCELLED'},
    'BLOCKED': {'READY','FAILED','CANCELLED'},
    'ACCEPTED': set(), 'FAILED': set(), 'CANCELLED': set(),
}


def validate_transition(before: str, after: str, *, evidence_pass=False, current_source=False,
                        independent_actor=False, children_stopped=False, effects_reconciled=False):
    if after not in TRANSITIONS.get(before,set()):
        raise ValueError('INVALID_TASK_TRANSITION')
    if after=='ACCEPTED' and not (evidence_pass and current_source and independent_actor):
        raise ValueError('ACCEPTANCE_EVIDENCE_REQUIRED')
    if after=='CANCELLED' and before in {'RUNNING','VERIFYING','WAITING_APPROVAL'}:
        if not (children_stopped and effects_reconciled):
            raise ValueError('CANCELLATION_NOT_RECONCILED')
    return after


MODELS=[SourceFingerprint,BootstrapRequest,SessionRead,LeaseRead,ArtifactRead,SnapshotRead,
        WorkspaceRead,WorkspaceList,ProjectRead,ProjectList,ObjectiveRead,PlanRead,VerificationReport,VerificationRead,
        ProjectCreate,ObjectiveCreate,PlanCreate,TaskCreate,TaskAction,
        ClaimRequest,AttemptReport,Heartbeat,ArtifactStage,VerificationRequest,AcceptanceRequest,
        MessageCreate,ErrorEnvelope,CommandReceipt,TaskRead,EventEnvelope,RoleCard]
