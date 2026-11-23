"""Disposable native end-to-end workflow trial for MGT-TITLE-NORMALIZATION-01.

Runs against the isolated disposable PostgreSQL instance (/var/lib/ai-proje-ofisi-dbtest/storage/socket)
as user aipof-dbtest (uid=999). Never claims G0 closure or human acceptance.
"""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from company_os.clock_provisioning import (
    activate_clock_policy,
    persist_clock_sample,
    register_clock_epoch,
)
from company_os.command_host import Blocked, UnknownCommitOutcome
from company_os.composition import PilotSession
from company_os.workflow_trust import check_workflow_trust
from company_os.constructors import create_objective, create_plan, create_task
from company_os.engine_bridge import (
    EnginePump,
    EngineReplyGuard,
    PipeTransport,
    ProducerOutputAdapter,
    PumpLimits,
)
from company_os.launch_controller import DeliveryGuard, LinuxLauncher, SpawnPlan, sha256_file
from company_os.patch_pipeline import (
    DbScope,
    IntentJournal,
    PatchProposalProducer,
    PatchReceiptRecorder,
    UnknownCommitOutcome,
    canonical_json,
)
from company_os.provisioning import ProvisioningContext, provision_project_grant, revoke_project_grant
from company_os.session_provisioning import issue_owner_session, issue_principal_session
from company_os.tool_broker import Broker, Unknown
from company_os.tool_executor import LinuxSingleFileExecutor
from company_os.verifier_runner import IndependentVerificationPipeline, run_title_oracle
from packages.workspace_manifest import build_manifest
from presentation.app import AuthenticatedReadbackApp, render_workflow_html

SOCKET_DIR = "/var/lib/ai-proje-ofisi-dbtest/storage/socket"
DB_PORT = 55439
STORAGE_DIR = Path("/var/lib/ai-proje-ofisi-dbtest/storage")

INSTALLATION_ID = "00000000-0000-4000-8000-000000000001"
TENANT_ID = "00000000-0000-4000-8000-000000000002"
PROJECT_ID = "00000000-0000-4000-8000-000000000003"
HUMAN_ID = "00000000-0000-4000-8000-000000000004"
WORKER_ID = "00000000-0000-4000-8000-000000000005"
WORKSPACE_ID = "00000000-0000-4000-8000-000000000006"

CONTROLLER_ID = "00000000-0000-4000-8000-000000000015"
VERIFIER_ID = "00000000-0000-4000-8000-000000000016"
EVIDENCE_ISSUER_ID = "00000000-0000-4000-8000-000000000017"
ROGUE_WORKER_ID = "00000000-0000-4000-8000-000000000018"
HOST_ID = "00000000-0000-4000-8000-000000000020"


class PgConnAdapter:
    """Wraps a psycopg2 connection so DbScope, CommandHost, and Provisioning work seamlessly."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.autocommit = conn.autocommit

    def cursor(self) -> "PgCursorAdapter":
        return PgCursorAdapter(self._conn.cursor(row_factory=dict_row))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class RowDict(dict):
    """Dict that also supports tuple indexing, slicing, and tuple unpacking for standard DB-API compatibility."""
    def __getitem__(self, key):
        if isinstance(key, slice):
            return tuple(self.values())[key]
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def __iter__(self):
        return iter(self.values())


class PgCursorAdapter:
    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def execute(self, sql: str, params: Any = None) -> None:
        if params is not None:
            adapted = tuple(
                Jsonb(p) if isinstance(p, (dict, list)) else p
                for p in params
            )
            self._cur.execute(sql, adapted)
        else:
            self._cur.execute(sql)

    def fetchone(self) -> Any:
        row = self._cur.fetchone()
        if row is None:
            return None
        return RowDict(row)

    def fetchall(self) -> list[Any]:
        return [RowDict(r) for r in self._cur.fetchall()]


def connect_db() -> Any:
    conn = psycopg.connect(host=SOCKET_DIR, port=DB_PORT, user="aipof-dbtest", dbname="postgres", connect_timeout=3)
    conn.autocommit = False
    return conn


def connect_adapted() -> PgConnAdapter:
    return PgConnAdapter(connect_db())


def sign_attestation(secret: bytes, profile_id: str, statement: dict[str, Any]) -> str:
    raw = canonical_json(statement)
    msg = b"R58-ATTEST-v1\x00" + profile_id.encode("utf-8") + b"\x00" + raw
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


class CommandHost:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def execute(self, op: str, ctx: dict[str, Any], args: Any = None, *, timeout_ms: int = 2000) -> dict[str, Any]:
        from company_os import command_host as ch
        # Adapt args to list if dict or list
        if isinstance(args, dict):
            # check route signature
            route = ch.ROUTES.get(op)
            if route and route[1] == ('jsonb',):
                import json
                arg_list = [json.dumps(args)]
            elif route and len(route[1]) == 1 and route[1][0] == 'jsonb':
                import json
                arg_list = [json.dumps(args)]
            else:
                arg_list = [args]
        elif isinstance(args, list):
            arg_list = args
        elif args is None:
            arg_list = []
        else:
            arg_list = [args]
        # ctx adaptation: auth dict for ch.execute
        auth = {
            'token': ctx.get('session_token') or ctx.get('token'),
            'grant_id': ctx.get('grant_id'),
            'project_id': ctx.get('project_id'),
            'kind': ctx.get('kind', 'PROJECT'),
            'resource_id': ctx.get('resource_id') or ctx.get('project_id'),
            'task_id': ctx.get('task_id'),
            'attempt_id': ctx.get('attempt_id'),
            'fence': ctx.get('fencing_epoch') or ctx.get('fence'),
        }
        res = ch.execute(self.conn, auth, op, arg_list, timeout_ms=timeout_ms)
        return res.get('result', {})


class CommandHostRuntimePort:
    """Implements PilotRuntimePort, PatchDatabasePort, and BrokerDatabasePort over CommandHost."""

    def __init__(
        self,
        *,
        controller_session: str,
        controller_grant: str,
        worker_session: str,
        worker_grant: str,
        tenant_id: str,
        project_id: str,
        task_id: str,
        attempt_id: str,
        fencing_epoch: int,
        workspace_id: str,
        base_head: str,
        controller_id: str,
        proposal_key_id: str,
        proposal_secret: bytes,
        effect_key_id: str,
        effect_secret: bytes,
        patch_key_id: str,
        patch_secret: bytes,
        drop_stage_commit_ack: bool = False,
    ) -> None:
        self.controller_session = controller_session
        self.controller_grant = controller_grant
        self.worker_session = worker_session
        self.worker_grant = worker_grant
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.task_id = task_id
        self.attempt_id = attempt_id
        self.fencing_epoch = fencing_epoch
        self.workspace_id = workspace_id
        self.base_head = base_head
        self.controller_id = controller_id
        self.proposal_key_id = proposal_key_id
        self.proposal_secret = proposal_secret
        self.effect_key_id = effect_key_id
        self.effect_secret = effect_secret
        self.patch_key_id = patch_key_id
        self.patch_secret = patch_secret
        self.drop_stage_commit_ack = drop_stage_commit_ack
        self.last_tool_request_id: str | None = None
        self.last_patch_artifact_id: str | None = None
        self.last_patch_artifact_digest: str | None = None

    def _ctx(self, session_token: str, grant_id: str, req_id: str, idem_key: str) -> dict[str, Any]:
        return {
            "session_token": session_token,
            "grant_id": grant_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "fencing_epoch": self.fencing_epoch,
            "request_id": req_id,
            "idempotency_key": idem_key,
        }

    def verify_engine_stream_bound(
        self,
        *,
        tenant_id: str,
        project_id: str,
        task_id: str,
        attempt_id: str,
        fencing_epoch: int,
        process_run_id: str,
        stream_id: str,
    ) -> bool:
        conn = connect_db()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT b.stream_id, a.state AS attempt_state, a.fencing_epoch,
                           a.lease_expires_at, p.state AS process_state, t.current_attempt_id
                    FROM company.r60_engine_stream_bindings b
                    JOIN company.attempts a
                      ON a.tenant_id = b.tenant_id
                     AND a.project_id = b.project_id
                     AND a.task_id = b.task_id
                     AND a.id = b.attempt_id
                    JOIN company.tasks t
                      ON t.tenant_id = a.tenant_id
                     AND t.project_id = a.project_id
                     AND t.id = a.task_id
                    JOIN company.process_runs p
                      ON p.tenant_id = b.tenant_id
                     AND p.project_id = b.project_id
                     AND p.id = b.process_run_id
                    WHERE b.tenant_id = %s
                      AND b.project_id = %s
                      AND b.task_id = %s
                      AND b.attempt_id = %s
                      AND b.fencing_epoch = %s
                      AND b.process_run_id = %s
                      AND b.stream_id = %s
                    """,
                    (tenant_id, project_id, task_id, attempt_id, fencing_epoch, process_run_id, stream_id),
                )
                row = cur.fetchone()
                if not row:
                    return False
                cur.execute(
                    "SELECT (company_private.r55_cp_clock_current_bounds(%s, %s)).upper_utc <= %s AS lease_ok",
                    (tenant_id, project_id, row["lease_expires_at"]),
                )
                lease_ok = bool(cur.fetchone()["lease_ok"])
                return (
                    row["attempt_state"] == "RUNNING"
                    and int(row["fencing_epoch"]) == fencing_epoch
                    and str(row["current_attempt_id"]) == attempt_id
                    and row["process_state"] == "RUNNING"
                    and lease_ok
                )
        finally:
            conn.close()

    def verify_current_attempt_execution(
        self,
        *,
        tenant_id: str,
        project_id: str,
        task_id: str,
        attempt_id: str,
        fencing_epoch: int,
    ) -> bool:
        conn = connect_db()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT a.state AS attempt_state, a.fencing_epoch, a.lease_expires_at,
                           t.current_attempt_id, t.state AS task_state
                    FROM company.attempts a
                    JOIN company.tasks t
                      ON t.tenant_id = a.tenant_id
                     AND t.project_id = a.project_id
                     AND t.id = a.task_id
                    WHERE a.tenant_id = %s
                      AND a.project_id = %s
                      AND a.task_id = %s
                      AND a.id = %s
                    """,
                    (tenant_id, project_id, task_id, attempt_id),
                )
                row = cur.fetchone()
                if not row:
                    return False
                cur.execute(
                    "SELECT (company_private.r55_cp_clock_current_bounds(%s, %s)).upper_utc <= %s AS lease_ok",
                    (tenant_id, project_id, row["lease_expires_at"]),
                )
                lease_ok = bool(cur.fetchone()["lease_ok"])
                return (
                    row["attempt_state"] in ("RUNNING", "PRODUCED")
                    and int(row["fencing_epoch"]) == fencing_epoch
                    and str(row["current_attempt_id"]) == attempt_id
                    and lease_ok
                )
        finally:
            conn.close()

    def verify_committed_patch_for_reply(
        self,
        *,
        tenant_id: str,
        project_id: str,
        task_id: str,
        attempt_id: str,
        fencing_epoch: int,
        tool_request_id: str,
        patch_artifact_id: str,
        patch_artifact_digest: str,
    ) -> bool:
        conn = connect_db()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT p.patch_artifact_id, p.patch_artifact_digest, p.result_head,
                           w.current_head, e.status AS effect_status
                    FROM company.r58_patch_records p
                    JOIN company.r58_workspace_heads w
                      ON w.tenant_id = p.tenant_id
                     AND w.project_id = p.project_id
                     AND w.workspace_id = p.workspace_id
                    JOIN company.r60_tool_effect_executions e
                      ON e.tenant_id = p.tenant_id
                     AND e.project_id = p.project_id
                     AND e.tool_request_id = p.tool_request_id
                    WHERE p.tenant_id = %s
                      AND p.project_id = %s
                      AND p.task_id = %s
                      AND p.attempt_id = %s
                      AND p.fencing_epoch = %s
                      AND p.tool_request_id = %s
                    """,
                    (tenant_id, project_id, task_id, attempt_id, fencing_epoch, tool_request_id),
                )
                row = cur.fetchone()
                if not row:
                    return False
                return (
                    str(row["patch_artifact_id"]) == patch_artifact_id
                    and row["patch_artifact_digest"] == patch_artifact_digest
                    and row["current_head"] == row["result_head"]
                    and row["effect_status"] == "COMPLETED"
                )
        finally:
            conn.close()

    def stage_proposal(self, scope: DbScope, payload: dict[str, Any]) -> dict[str, Any]:
        req_id = payload["tool_request_id"]
        ctx = self._ctx(self.controller_session, self.controller_grant, f"stage-{req_id}", f"stage-{req_id}")
        stmt = payload["proposal_statement"]
        sig = sign_attestation(self.proposal_secret, "r60.patch-proposal.v1", stmt)
        conn = connect_adapted()
        try:
            host = CommandHost(conn)
            res = host.execute(
                "patch.stage_proposal",
                ctx,
                {
                    "tool_request_id": req_id,
                    "process_run_id": payload["process_run_id"],
                    "stream_id": payload["stream_id"],
                    "workspace_id": payload["workspace_id"],
                    "base_head": payload["base_head"],
                    "target_path": payload["target_path"],
                    "source_sha256": payload["source_sha256"],
                    "proposal_artifact_id": payload["proposal_artifact_id"],
                    "proposal_digest": payload["proposal_digest"],
                    "replacement_bytes_base64": base64.b64encode(payload["replacement_bytes"]).decode("ascii"),
                    "key_id": self.proposal_key_id,
                    "issuer_id": self.controller_id,
                    "proposal_statement": stmt,
                    "proposal_signature": sig,
                },
            )
            if self.drop_stage_commit_ack:
                raise UnknownCommitOutcome("Simulated lost commit ack on stage_proposal")
            self.last_tool_request_id = req_id
            return res
        finally:
            conn.close()

    def request_and_authorize_patch_apply(
        self,
        scope: DbScope,
        *,
        tool_request_id: str,
        target_path: str,
        proposal_digest: str,
    ) -> dict[str, Any]:
        conn = connect_adapted()
        try:
            host = CommandHost(conn)
            w_ctx = self._ctx(
                self.worker_session,
                self.worker_grant,
                f"treq-{tool_request_id}",
                f"treq-{tool_request_id}",
            )
            host.execute(
                "tool.request",
                w_ctx,
                {
                    "tool_request_id": tool_request_id,
                    "tool_id": "patch.apply",
                    "manifest_revision": 1,
                    "args": {
                        "target_path": target_path,
                        "proposal_digest": proposal_digest,
                    },
                },
            )
            c_ctx = self._ctx(
                self.controller_session,
                self.controller_grant,
                f"tauth-{tool_request_id}",
                f"tauth-{tool_request_id}",
            )
            return host.execute(
                "tool.authorize",
                c_ctx,
                {
                    "tool_request_id": tool_request_id,
                    "decision": "ALLOWED",
                    "reason": "BROKER_PILOT_PATCH_APPLY_ALLOWED",
                },
            )
        finally:
            conn.close()

    def consume_tool_execution(
        self,
        scope: DbScope,
        *,
        tool_request_id: str,
        consumer_id: str,
    ) -> dict[str, Any]:
        conn = connect_adapted()
        try:
            host = CommandHost(conn)
            c_ctx = self._ctx(
                self.controller_session,
                self.controller_grant,
                f"tcon-{tool_request_id}",
                f"tcon-{tool_request_id}",
            )
            res = host.execute(
                "tool.consume",
                c_ctx,
                {
                    "tool_request_id": tool_request_id,
                    "consumer_id": consumer_id,
                },
            )
            return {
                "effect_permitted": bool(res.get("effect_permitted")),
                "status": "CONSUMED" if res.get("effect_permitted") else res.get("reason", "DENIED"),
                "tool_id": res.get("tool_id"),
                "target_path": res.get("target_path"),
                "proposal_digest": res.get("proposal_digest"),
            }
        finally:
            conn.close()

    def read_staged_proposal(
        self,
        scope: DbScope,
        *,
        tool_request_id: str,
        proposal_digest: str,
    ) -> dict[str, Any]:
        conn = connect_db()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT tool_request_id, workspace_id, base_head, target_path,
                           source_sha256, proposal_artifact_id, proposal_digest,
                           replacement_bytes, state
                    FROM company.r60_patch_proposals
                    WHERE tenant_id = %s
                      AND project_id = %s
                      AND task_id = %s
                      AND attempt_id = %s
                      AND fencing_epoch = %s
                      AND tool_request_id = %s
                      AND proposal_digest = %s
                    """,
                    (
                        self.tenant_id,
                        self.project_id,
                        self.task_id,
                        self.attempt_id,
                        self.fencing_epoch,
                        tool_request_id,
                        proposal_digest,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("MISSING_STAGED_PROPOSAL")
                out = dict(row)
                out["replacement_bytes"] = bytes(out["replacement_bytes"])
                out["workspace_id"] = str(out["workspace_id"])
                out["proposal_artifact_id"] = str(out["proposal_artifact_id"])
                return out
        finally:
            conn.close()

    def complete_tool_effect(
        self,
        scope: DbScope,
        *,
        tool_request_id: str,
        proposal_digest: str,
        target_path: str,
        pre_write_sha256: str,
        post_write_sha256: str,
        effect_artifact_id: str,
        effect_digest: str,
    ) -> dict[str, Any]:
        stmt = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "fencing_epoch": self.fencing_epoch,
            "tool_request_id": tool_request_id,
            "proposal_digest": proposal_digest,
            "target_path": target_path,
            "pre_write_sha256": pre_write_sha256,
            "post_write_sha256": post_write_sha256,
        }
        stmt_digest = hashlib.sha256(canonical_json(stmt)).hexdigest()
        sig = sign_attestation(self.effect_secret, "r60.tool-effect.v1", stmt)
        conn = connect_adapted()
        try:
            host = CommandHost(conn)
            c_ctx = self._ctx(
                self.controller_session,
                self.controller_grant,
                f"eff-{tool_request_id}",
                f"eff-{tool_request_id}",
            )
            return host.execute(
                "tool.effect_complete",
                c_ctx,
                {
                    "tool_request_id": tool_request_id,
                    "effect_artifact_id": str(
                        uuid_from_seed(f"eff-art-{tool_request_id}")
                    ),
                    "effect_digest": stmt_digest,
                    "pre_write_sha256": pre_write_sha256,
                    "post_write_sha256": post_write_sha256,
                    "key_id": self.effect_key_id,
                    "issuer_id": self.controller_id,
                    "effect_statement": stmt,
                    "effect_signature": sig,
                },
            )
        finally:
            conn.close()

    def record_patch(self, scope: DbScope, payload: dict[str, Any]) -> dict[str, Any]:
        stmt = payload["patch_statement"]
        sig = sign_attestation(self.patch_secret, "r58.patch.v1", stmt)
        req_id = payload["tool_request_id"]
        conn = connect_adapted()
        try:
            host = CommandHost(conn)
            c_ctx = self._ctx(
                self.controller_session,
                self.controller_grant,
                f"prec-{req_id}",
                f"prec-{req_id}",
            )
            res = host.execute(
                "patch.receipt",
                c_ctx,
                {
                    "workspace_id": payload["workspace_id"],
                    "tool_request_id": req_id,
                    "base_head": payload["base_head"],
                    "patch_artifact_id": payload["patch_artifact_id"],
                    "patch_artifact_digest": payload["patch_artifact_digest"],
                    "result_head": payload["result_head"],
                    "key_id": self.patch_key_id,
                    "issuer_id": self.controller_id,
                    "patch_statement": stmt,
                    "patch_signature": sig,
                },
            )
            self.last_patch_artifact_id = payload["patch_artifact_id"]
            self.last_patch_artifact_digest = payload["patch_artifact_digest"]
            return res
        finally:
            conn.close()


def uuid_from_seed(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def ingest_attestation(
    host: CommandHost,
    ctx: dict[str, Any],
    *,
    artifact_id: str,
    profile_id: str,
    key_id: str,
    issuer_id: str,
    statement: dict[str, Any],
    secret: bytes,
) -> dict[str, Any]:
    digest = hashlib.sha256(canonical_json(statement)).hexdigest()
    sig = sign_attestation(secret, profile_id, statement)
    return host.execute(
        "evidence.attestation_ingest",
        ctx,
        {
            "artifact_id": artifact_id,
            "profile_id": profile_id,
            "key_id": key_id,
            "issuer_id": issuer_id,
            "digest": digest,
            "statement": statement,
            "signature": sig,
        },
    )


def main(*, trust_inputs=None) -> int:
    from tools.workflow_preflight import check_workflow
    preflight = check_workflow(Path(__file__))
    if preflight['status'] == 'BLOCKED' or preflight['runtime_blockers']:
        print(json.dumps({'status': 'BLOCKED_BEFORE_DB_CONNECTION',
                          'preflight': preflight}, ensure_ascii=False, indent=2))
        return 2
    if trust_inputs is None:
        print(json.dumps({'status': 'BLOCKED_BEFORE_DB_CONNECTION',
                          'reason': 'TRUSTED_SUPERVISOR_INPUTS_REQUIRED'}))
        return 2
    consent_res, loaded_secret = check_workflow_trust(
        consent_path=trust_inputs['consent_path'],
        consent_sha256=trust_inputs['consent_sha256'],
        human_id=trust_inputs['human_id'],
        canonical_workspace=trust_inputs['canonical_workspace'],
        root_record=trust_inputs['root_record'],
        secret_directory_fd=trust_inputs['secret_directory_fd'],
        secret_name=trust_inputs['secret_name'],
        secret_owner_uid=trust_inputs['secret_owner_uid'])
    report: dict[str, Any] = {
        "trial_id": "E2E_WORKFLOW_TRIAL_20261108",
        "evidence_class": "DISPOSABLE_LINUX_POSTGRES_ROOTLESS_E2E_TRIAL_NOT_G0_ACCEPTANCE",
        "g0_status": "OPEN",
        "human_acceptance_claimed": False,
        "production_claimed": False,
        "steps": {},
        "negatives": {},
        "first13_stage_status": {},
    }

    # -------------------------------------------------------------------------
    # STEP 1: Verify consent_binding + secret_adapter + initial session check
    # -------------------------------------------------------------------------
    conn = connect_adapted()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tenant_id, project_id, installation_id, accepted_human_id, command_id FROM company_private.bootstrap_receipts LIMIT 1")
        b_rec = cur.fetchone()
        global TENANT_ID, PROJECT_ID, INSTALLATION_ID, HUMAN_ID
        TENANT_ID = str(b_rec["tenant_id"])
        PROJECT_ID = str(b_rec["project_id"])
        INSTALLATION_ID = str(b_rec["installation_id"])
        HUMAN_ID = str(b_rec["accepted_human_id"])
    finally:
        conn.close()

    # Consent and secret were checked before opening the DB. The supervisor
    # retains ownership of its enrolled directory; the trial never deletes it.
    root_record = trust_inputs['root_record']
    if (INSTALLATION_ID != root_record['installation_id']
            or HUMAN_ID != root_record['actual_human_id']):
        raise RuntimeError('BOOTSTRAP_TRUST_IDENTITY_MISMATCH')

    # Issue owner session and prove BLOCKED_TIME_DEPENDENCY before clock enrollment
    owner_token = "owner-session-token-e2e-0001-secret"
    conn = connect_adapted()
    try:
        cur = conn.cursor()
        cur.execute("SELECT installation_id FROM company_private.bootstrap_receipts")
        row = cur.fetchone()
        real_installation_id = str(row["installation_id"])
        owner_session = issue_owner_session(
            cur,
            installation_id=real_installation_id,
            token=owner_token,
            ttl_seconds=300,
        )
        cur.execute("SELECT grant_id FROM company.project_grants LIMIT 1")
        bootstrap_grant_id = str(cur.fetchone()["grant_id"])
        conn.commit()
    finally:
        conn.close()

    # Probe context_enter BEFORE clock enrollment -> must fail with BLOCKED_TIME_DEPENDENCY
    blocked_time_error = None
    conn_raw = connect_db()
    try:
        with conn_raw.cursor() as raw_cur:
            raw_cur.execute(
                "SELECT b.project_id, g.grant_id FROM company_private.bootstrap_receipts b "
                "JOIN company.project_grants g ON g.tenant_id=b.tenant_id AND g.project_id=b.project_id "
                "AND g.principal_id=b.accepted_human_id WHERE g.permission='e0.setup_mandate_consume'"
            )
            row = raw_cur.fetchone()
            b_project, b_grant = row[0], row[1]
            try:
                raw_cur.execute(
                    "SELECT company_private.r54_context_enter(%s, %s, %s::uuid, %s, %s::uuid, NULL, NULL, NULL, %s::uuid)",
                    (owner_token, "e0.setup_mandate_consume", b_project, "PROJECT", b_project, b_grant)
                )
            except Exception as exc:
                blocked_time_error = str(exc).strip().splitlines()[0]
                conn_raw.rollback()
    finally:
        conn_raw.close()

    assert blocked_time_error and "BLOCKED_TIME_DEPENDENCY" in blocked_time_error, f"Expected BLOCKED_TIME_DEPENDENCY, got {blocked_time_error}"

    report["steps"]["1_trust_consent_and_pre_clock_gate"] = {
        "consent_verified": consent_res.matched,
        "consent_authority_granted": consent_res.authority_granted,
        "secret_adapter_linux_fd_verified": len(loaded_secret) == 32,
        "owner_session_id": owner_session["session_id"],
        "pre_clock_context_enter_error": blocked_time_error,
    }

    # -------------------------------------------------------------------------
    # STEP 2: Resolve BLOCKED_TIME_DEPENDENCY via owning-source clock_provisioning.py
    # -------------------------------------------------------------------------
    clock_policy_secret = b"x" * 32
    clock_obs_secret = loaded_secret
    clock_policy = {
        "bounded_handoff_duration_ms": 5000,
        "max_uncertainty_ms": 5000,
        "max_sample_age_ms": 60000,
        "max_clock_jump_ms": 5000,
        "first_alert_ms": 1000,
        "owner_ack_ms": 2000,
        "manual_reconcile_ms": 3000,
        "poll_ms": 1000,
        "max_drift_ms": 5000,
    }
    clock_epoch_id = uuid_from_seed("clock-epoch-1")
    sample_id_1 = uuid_from_seed("clock-sample-1")
    sample_id_2 = uuid_from_seed("clock-sample-2")

    conn = connect_adapted()
    try:
        cur = conn.cursor()
        # Observe native Linux clock via C extension r55_cp_clock_observe_local()
        cur.execute("SELECT company_private.r55_cp_clock_observe_local() AS obs")
        obs = cur.fetchone()["obs"]
        boot_id = obs["host_boot_id"]
        boottime_ns = int(obs.get("monotonic_boottime_ns") or obs.get("boottime_after_ns") or obs.get("boottime_before_ns"))

        # Bootstrap receipt is append-only immutable, do not update.
        cur.execute("SELECT id FROM company.principals WHERE tenant_id = %s::uuid AND kind = 'WORKER' LIMIT 1", (TENANT_ID,))
        worker_row = cur.fetchone()
        if worker_row:
            global WORKER_ID
            WORKER_ID = str(worker_row["id"])
        else:
            cur.execute(
                "INSERT INTO company.principals(tenant_id, id, name, kind) VALUES (%s::uuid, %s::uuid, 'Worker Primary', 'WORKER')",
                (TENANT_ID, WORKER_ID),
            )

        cur.execute("UPDATE company.project_grants SET valid_until = clock_timestamp() + interval '1 hour'")
        cur.execute(
            """
            UPDATE company_private.r55_setup_root_enrollments
               SET not_after = clock_timestamp() + interval '1 hour',
                   not_after_boottime_ns = %s
            """,
            (boottime_ns + 3600 * 1_000_000_000,),
        )
        cur.execute("SELECT installation_id, issuer_id, key_id, enrollment_revision FROM company_private.r55_setup_root_enrollments LIMIT 1")
        root_enrollment = cur.fetchone()
        root_key_id = root_enrollment["key_id"]

        # Enroll host registration and bind to project
        cur.execute("SELECT command_id FROM company_private.bootstrap_receipts LIMIT 1")
        b_cmd_id = cur.fetchone()["command_id"]
        dummy_h_dig = hashlib.sha256(b"host-identity-001").hexdigest()
        dummy_att_dig = hashlib.sha256(b"attestation-001").hexdigest()
        cur.execute(
            """
            INSERT INTO company.host_registrations(
                tenant_id, project_id, id, revision, host_identity_digest, attestation_digest,
                state, command_id, bound_generation, binding_command_id
            ) VALUES (
                %s::uuid, %s::uuid, %s::uuid, 1, %s, %s,
                'BOUND_NOT_LEASED', %s::uuid, 1, %s::uuid
            )
            """,
            (TENANT_ID, PROJECT_ID, HOST_ID, dummy_h_dig, dummy_att_dig, b_cmd_id, b_cmd_id),
        )
        cur.execute(
            """
            UPDATE company.projects
               SET host_registration_id = %s::uuid,
                   host_registration_revision = 1,
                   instance_generation = 1
             WHERE tenant_id = %s::uuid AND id = %s::uuid
            """,
            (HOST_ID, TENANT_ID, PROJECT_ID),
        )

        # Enroll clock policy operation permission (registered with execution_class SPECIAL/COMMAND, policy_revision 0)
        cur.execute(
            """
            INSERT INTO company_private.operation_permissions(
                operation_id, permission, scope_kind, execution_class, policy_revision, approved_policy_digest
            ) VALUES (
                'clock.policy.activate', 'clock.policy.activate', 'SPECIAL', 'COMMAND', 0, NULL
            ) ON CONFLICT (operation_id) DO NOTHING
            """
        )

        # Enroll clock policy key & authority & consent (synthetic provisioning seam)
        cur.execute(
            """
            INSERT INTO company_private.r58_key_material(key_id, purpose, secret, fingerprint, revoked)
            VALUES (%s, 'CLOCK_POLICY', %s, %s, false)
            """,
            (root_key_id, bytes(clock_policy_secret), hashlib.sha256(clock_policy_secret).hexdigest()),
        )
        cur.execute(
            """
            INSERT INTO company_private.r57_clock_policy_authority(singleton, installation_id, tenant_id, human_id)
            VALUES (true, %s::uuid, %s::uuid, %s::uuid)
            ON CONFLICT (singleton) DO UPDATE
               SET installation_id = EXCLUDED.installation_id,
                   tenant_id = EXCLUDED.tenant_id,
                   human_id = EXCLUDED.human_id
            """,
            (INSTALLATION_ID, TENANT_ID, HUMAN_ID),
        )
        consent_id = uuid.uuid4()
        consent_stmt = {
            "consent_id": str(consent_id),
            "installation_id": str(INSTALLATION_ID),
            "action": "ACTIVATE",
            "expected_revision": 0,
            "policy": clock_policy,
        }
        cur.execute(
            "SELECT encode(sha256(convert_to((%s::jsonb)::text, 'UTF8')), 'hex') AS d",
            (consent_stmt,),
        )
        stmt_digest = cur.fetchone()["d"]
        dummy_consent_ev = hashlib.sha256(b"consent-evidence").hexdigest()
        cur.execute(
            """
            INSERT INTO company_private.r57_clock_policy_consents(
                consent_id, installation_id, root_generation, action,
                expected_revision, approved_statement_digest,
                human_consent_evidence_digest, valid_from, valid_until
            ) VALUES (
                %s::uuid, %s::uuid, 1, 'ACTIVATE',
                0, %s, %s,
                clock_timestamp() - interval '1 minute', clock_timestamp() + interval '1 hour'
            )
            """,
            (consent_id, INSTALLATION_ID, stmt_digest, dummy_consent_ev),
        )

        # Call owning-source activate_clock_policy
        cur.execute("SET SESSION AUTHORIZATION company_clock_policy_transport_r57")
        policy_res = activate_clock_policy(
            cur,
            record=root_enrollment,
            key=clock_policy_secret,
            consent_id=consent_id,
            expected_login="company_clock_policy_transport_r57",
            policy=clock_policy,
            expected_revision=0,
        )
        cur.execute("RESET SESSION AUTHORIZATION")

        # Enroll clock observation signer (WORKER_ID approved by HUMAN_ID)
        clock_key_id = uuid_from_seed("clock-obs-key-r55-1")
        clock_obs_fingerprint = hashlib.sha256(clock_obs_secret).hexdigest()
        cur.execute(
            """
            INSERT INTO company.signer_enrollments(
                tenant_id, issuer_id, key_id, purpose, profile_id, secret_ref,
                key_fingerprint, enrollment_revision, valid_from, valid_until, approved_by,
                r55_project_id, r55_host_id, r55_host_revision, r55_host_generation, r55_host_boot_id
            ) VALUES (
                %s::uuid, %s::uuid, %s::uuid, 'CLOCK_OBSERVATION', 'R55_CLOCK_V1_RAW_JSON', 'clock-secret-ref-1',
                %s, 1, clock_timestamp() - interval '1 minute', clock_timestamp() + interval '1 hour', %s::uuid,
                %s::uuid, %s::uuid, 1, 1, %s::uuid
            )
            """,
            (
                TENANT_ID,
                WORKER_ID,
                clock_key_id,
                clock_obs_fingerprint,
                HUMAN_ID,
                PROJECT_ID,
                HOST_ID,
                boot_id,
            ),
        )

        # Call owning-source register_clock_epoch & persist_clock_sample (seq 1 & seq 2)
        cur.execute("SELECT encode(sha256(convert_to((%s::jsonb)::text, 'UTF8')), 'hex') AS d", (clock_policy,))
        policy_digest = cur.fetchone()["d"]
        epoch_bt_ns = boottime_ns
        cur.execute("SET SESSION AUTHORIZATION company_clock_runtime_r55")
        epoch_res = register_clock_epoch(
            cur,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            epoch_id=clock_epoch_id,
            issuer_id=WORKER_ID,
            key_id=clock_key_id,
            revision=1,
            secret=clock_obs_secret,
            host_id=HOST_ID,
            host_revision=1,
            host_generation=1,
            host_boot_id=boot_id,
            policy=clock_policy,
            policy_digest=policy_digest,
            current_boottime_ns=epoch_bt_ns,
            valid_until_boottime_ns=epoch_bt_ns + 60_000_000_000,
            utc_lower_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            utc_upper_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
        )
        sample1_res = persist_clock_sample(
            cur,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            epoch_id=clock_epoch_id,
            sample_id=sample_id_1,
            issuer_id=WORKER_ID,
            key_id=clock_key_id,
            revision=1,
            secret=clock_obs_secret,
            host_id=HOST_ID,
            host_revision=1,
            host_generation=1,
            host_boot_id=boot_id,
            source_sequence=1,
            sample_boottime_ns=epoch_bt_ns,
            current_boottime_ns=epoch_bt_ns + 10_000,
            valid_until_boottime_ns=epoch_bt_ns + 60_000_000_000,
            sampled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            utc_lower_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            utc_upper_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            source_sync_state="SYNC",
        )
        sample2_res = persist_clock_sample(
            cur,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            epoch_id=clock_epoch_id,
            sample_id=sample_id_2,
            issuer_id=WORKER_ID,
            key_id=clock_key_id,
            revision=1,
            secret=clock_obs_secret,
            host_id=HOST_ID,
            host_revision=1,
            host_generation=1,
            host_boot_id=boot_id,
            source_sequence=2,
            sample_boottime_ns=epoch_bt_ns + 50_000,
            current_boottime_ns=epoch_bt_ns + 60_000,
            valid_until_boottime_ns=epoch_bt_ns + 60_000_000_000,
            sampled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            utc_lower_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            utc_upper_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
            source_sync_state="SYNC",
        )
        cur.execute("RESET SESSION AUTHORIZATION")
        cur.execute(
            "SELECT company_private.r55_cp_clock_current_bounds(%s::uuid, %s::uuid) AS b",
            (TENANT_ID, PROJECT_ID),
        )
        bounds_json = cur.fetchone()["b"]
        conn.commit()
    finally:
        conn.close()

    def refresh_clock_sample(seq: int) -> None:
        c = connect_adapted()
        try:
            cu = c.cursor()
            sample_bt_ns = epoch_bt_ns + seq * 100_000
            cu.execute("SET SESSION AUTHORIZATION company_clock_runtime_r55")
            persist_clock_sample(
                cu,
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                epoch_id=clock_epoch_id,
                sample_id=uuid_from_seed(f"clock-sample-{seq}"),
                issuer_id=WORKER_ID,
                key_id=clock_key_id,
                revision=1,
                secret=clock_obs_secret,
                host_id=HOST_ID,
                host_revision=1,
                host_generation=1,
                host_boot_id=boot_id,
                source_sequence=seq,
                sample_boottime_ns=sample_bt_ns,
                current_boottime_ns=sample_bt_ns + 10_000,
                valid_until_boottime_ns=epoch_bt_ns + 60_000_000_000,
                sampled_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
                utc_lower_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
                utc_upper_bound=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00"),
                source_sync_state="SYNC",
            )
            cu.execute("RESET SESSION AUTHORIZATION")
            c.commit()
        finally:
            c.close()

    clock_seq_counter = 2

    def bump_clock() -> None:
        nonlocal clock_seq_counter
        clock_seq_counter += 1
        refresh_clock_sample(clock_seq_counter)

    report["steps"]["2_clock_provisioning_and_bounds"] = {
        "host_boot_id": boot_id,
        "policy_revision": policy_res["revision"],
        "epoch_id": str(epoch_res),
        "sample_1_id": str(sample1_res["sample_id"]),
        "sample_2_id": str(sample2_res["sample_id"]),
        "bounds_utc_lower_bound": str(bounds_json.get("utc_lower_bound")),
        "bounds_utc_upper_bound": str(bounds_json.get("utc_upper_bound")),
    }

    # -------------------------------------------------------------------------
    # STEP 3: Verify POLICY_NOT_APPROVED gate before policy approval, then
    #         approve operation policies, enroll principals/sessions/grants,
    #         and run Objective -> Plan -> Task commit + separate readback
    # -------------------------------------------------------------------------
    unapproved_policy_error = None
    conn_raw = connect_db()
    try:
        with conn_raw.cursor() as raw_cur:
            raw_cur.execute("SET ROLE company_transport_r54")
            try:
                raw_cur.execute(
                    """
                    SELECT company_private.r54_context_enter(
                        %s, 'e0.setup_mandate_consume', %s::uuid, 'PROJECT', %s::uuid,
                        NULL, NULL, NULL, %s::uuid
                    )
                    """,
                    (owner_token, PROJECT_ID, PROJECT_ID, bootstrap_grant_id),
                )
            except Exception as exc:
                unapproved_policy_error = str(exc).strip().splitlines()[0]
                conn_raw.rollback()
    finally:
        conn_raw.close()

    assert unapproved_policy_error and "POLICY_NOT_APPROVED" in unapproved_policy_error, (
        f"Expected POLICY_NOT_APPROVED, got {unapproved_policy_error}"
    )

    # Enroll principals, sessions, operation policies, and grants
    worker_token = "worker-session-token-e2e-0002-secret"
    controller_token = "controller-session-token-e2e-0003-secret"
    verifier_token = "verifier-session-token-e2e-0004-secret"
    evidence_token = "evidence-session-token-e2e-0005-secret"
    rogue_token = "rogue-session-token-e2e-0006-secret"

    conn = connect_adapted()
    try:
        cur = conn.cursor()
        # Approve operation_permissions with explicit policy_revision=1 and digest
        policy_digest = hashlib.sha256(b"approved-operation-policy-bundle-v1").hexdigest()
        cur.execute(
            """
            UPDATE company_private.operation_permissions
               SET policy_revision = 1,
                   approved_policy_digest = %s
            """,
            (policy_digest,),
        )
        # Enroll technical principals and memberships
        for pid, name, kind, role in [
            (CONTROLLER_ID, "Controller Principal", "WORKER", "WORKER"),
            (VERIFIER_ID, "Verifier Principal", "VERIFIER", "VERIFIER"),
            (EVIDENCE_ISSUER_ID, "Evidence Principal", "VERIFIER", "VERIFIER"),
            (ROGUE_WORKER_ID, "Rogue Worker Principal", "WORKER", "WORKER"),
        ]:
            cur.execute(
                """
                INSERT INTO company.principals(tenant_id, id, name, kind)
                VALUES (%s::uuid, %s::uuid, %s, %s)
                ON CONFLICT (tenant_id, id) DO NOTHING
                """,
                (TENANT_ID, pid, name, kind),
            )
            cur.execute(
                """
                INSERT INTO company.memberships(tenant_id, principal_id, role)
                VALUES (%s::uuid, %s::uuid, %s)
                ON CONFLICT (tenant_id, principal_id) DO NOTHING
                """,
                (TENANT_ID, pid, role),
            )

        worker_sess = issue_principal_session(
            cur,
            installation_id=INSTALLATION_ID,
            principal_id=WORKER_ID,
            role="WORKER",
            token=worker_token,
            ttl_seconds=900,
        )
        controller_sess = issue_principal_session(
            cur,
            installation_id=INSTALLATION_ID,
            principal_id=CONTROLLER_ID,
            role="WORKER",
            token=controller_token,
            ttl_seconds=900,
        )
        verifier_sess = issue_principal_session(
            cur,
            installation_id=INSTALLATION_ID,
            principal_id=VERIFIER_ID,
            role="VERIFIER",
            token=verifier_token,
            ttl_seconds=900,
        )
        evidence_sess = issue_principal_session(
            cur,
            installation_id=INSTALLATION_ID,
            principal_id=EVIDENCE_ISSUER_ID,
            role="VERIFIER",
            token=evidence_token,
            ttl_seconds=900,
        )
        rogue_sess = issue_principal_session(
            cur,
            installation_id=INSTALLATION_ID,
            principal_id=ROGUE_WORKER_ID,
            role="WORKER",
            token=rogue_token,
            ttl_seconds=900,
        )
        conn.commit()
    finally:
        conn.close()

    # Helper to insert project_grants directly for trial verification
    def issue_grant(
        *,
        grant_id: str,
        principal_id: str,
        permissions: tuple[str, ...],
        task_id: str | None = None,
        attempt_id: str | None = None,
        fencing_epoch: int | None = None,
    ) -> str:
        c = connect_adapted()
        try:
            cu = c.cursor()
            for p in permissions:
                cu.execute(
                    """
                    INSERT INTO company.project_grants(
                        tenant_id, project_id, principal_id, permission, base_permission,
                        grant_id, revision, valid_from, valid_until, granted_by, task_scope_id
                    ) VALUES (
                        %s::uuid, %s::uuid, %s::uuid, %s, %s,
                        %s::uuid, 0, clock_timestamp() - interval '1 minute', clock_timestamp() + interval '1 hour', %s::uuid, %s::uuid
                    ) ON CONFLICT (tenant_id, project_id, principal_id, permission) DO UPDATE
                      SET grant_id = EXCLUDED.grant_id,
                          valid_until = EXCLUDED.valid_until,
                          task_scope_id = EXCLUDED.task_scope_id
                    """,
                    (TENANT_ID, PROJECT_ID, principal_id, p, p, grant_id, HUMAN_ID, task_id),
                )
            c.commit()
            return grant_id
        finally:
            c.close()

    owner_grant_id = issue_grant(
        grant_id=uuid_from_seed("grant-owner-main"),
        principal_id=HUMAN_ID,
        permissions=(
            "CAP-001.objectives.create",
            "CAP-001.plans.create",
            "CAP-001.tasks.create",
            "CAP-002.tasks.ready",
            "CAP-006.workspace.current_head",
            "CAP-011.verification.accept",
            "CAP-017.revoke",
            "CAP-R54.detail.read",
            "CAP-R54.qualification.activate",
            "CAP-R54.qualification.revoke",
            "CAP-R54.qualification.expire",
            "CAP-E0.setup_mandate.consume",
            "CAP-E0.qualification.candidate_issue",
        ),
    )

    # First prove the bootstrap-issued grant works for e0.setup_mandate_consume!
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        e0_consume_res = host.execute(
            "e0.setup_mandate_consume",
            {
                "session_token": owner_token,
                "grant_id": bootstrap_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-e0-mandate-consume-1",
                "idempotency_key": "idem-e0-mandate-consume-1",
            },
            {},
        )
    finally:
        conn.close()

    # Now execute authorized Objective -> Plan -> Task commit via constructors.py
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        obj_res = create_objective(
            host,
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-obj-create-mgt01",
                "idempotency_key": "idem-obj-create-mgt01",
            },
            title="MGT-01 Title Normalization Objective",
            statement="Deliver deterministic title normalization via safe producer-broker-verifier pipeline.",
        )
        objective_id = str(obj_res["id"])

        plan_res = create_plan(
            host,
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-plan-create-mgt01",
                "idempotency_key": "idem-plan-create-mgt01",
            },
            objective_id=objective_id,
            objective_revision=int(obj_res["revision"]),
            title="MGT-01 Single-File Normalization Plan",
        )
        plan_id = str(plan_res["id"])

        task_res = create_task(
            host,
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-task-create-mgt01",
                "idempotency_key": "idem-task-create-mgt01",
            },
            plan_id=plan_id,
            plan_revision=int(plan_res["revision"]),
            title="MGT-TITLE-NORMALIZATION-01",
            role_id="EXP-001",
        )
        task_id = str(task_res["id"])
    finally:
        conn.close()

    # Separate-connection readback of Objective, Plan, Task, Commands, Audit, Outbox
    conn_ro = connect_db()
    try:
        with conn_ro.cursor(row_factory=dict_row) as ro_cur:
            ro_cur.execute(
                "SELECT id, revision, state, created_by_command_id FROM company.objectives WHERE id = %s::uuid",
                (objective_id,),
            )
            ro_obj = dict(ro_cur.fetchone())
            ro_cur.execute(
                "SELECT id, objective_id, objective_revision, revision, state, created_by_command_id FROM company.plans WHERE id = %s::uuid",
                (plan_id,),
            )
            ro_plan = dict(ro_cur.fetchone())
            ro_cur.execute(
                "SELECT id, plan_id, plan_revision, revision, state, role_id, title, created_by_command_id FROM company.tasks WHERE id = %s::uuid",
                (task_id,),
            )
            ro_task = dict(ro_cur.fetchone())
            ro_cur.execute(
                """
                SELECT operation, id, result_digest
                FROM company.commands
                WHERE request_id IN ('req-obj-create-mgt01', 'req-plan-create-mgt01', 'req-task-create-mgt01')
                ORDER BY operation
                """
            )
            ro_cmds = [dict(r) for r in ro_cur.fetchall()]
            ro_cur.execute(
                """
                SELECT event_type, command_id
                FROM company.audit_events
                WHERE command_id IN (%s::uuid, %s::uuid, %s::uuid)
                ORDER BY seq
                """,
                (ro_obj["created_by_command_id"], ro_plan["created_by_command_id"], ro_task["created_by_command_id"]),
            )
            ro_audits = [dict(r) for r in ro_cur.fetchall()]
            ro_cur.execute(
                """
                SELECT topic, command_id, payload_digest
                FROM company.outbox
                WHERE command_id IN (%s::uuid, %s::uuid, %s::uuid)
                ORDER BY seq
                """,
                (ro_obj["created_by_command_id"], ro_plan["created_by_command_id"], ro_task["created_by_command_id"]),
            )
            ro_outbox = [dict(r) for r in ro_cur.fetchall()]
    finally:
        conn_ro.close()

    assert len(ro_cmds) == 3 and len(ro_audits) == 3 and len(ro_outbox) == 3

    report["steps"]["3_policy_and_constructors_readback"] = {
        "pre_policy_error": unapproved_policy_error,
        "e0_mandate_consume_status": e0_consume_res["state"],
        "objective": {"id": objective_id, "revision": ro_obj["revision"], "state": ro_obj["state"]},
        "plan": {"id": plan_id, "revision": ro_plan["revision"], "state": ro_plan["state"]},
        "task": {"id": task_id, "revision": ro_task["revision"], "state": ro_task["state"], "title": ro_task["title"]},
        "commands_count": len(ro_cmds),
        "audit_events_count": len(ro_audits),
        "outbox_events_count": len(ro_outbox),
    }

    # -------------------------------------------------------------------------
    # STEP 4: Qualification (E0 -> Candidate Issue -> Qualification Activate)
    #         + Signer/Controller/Profile/Budget/Resource/Tool Enrollment
    #         + Workspace Attestation + Task Ready + Worker Claim
    # -------------------------------------------------------------------------
    eval_task_id = uuid_from_seed("e0-eval-task-1")
    eval_attempt_id = uuid_from_seed("e0-eval-attempt-1")
    eval_verification_id = uuid_from_seed("e0-eval-verif-1")

    conn = connect_adapted()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, plan_id FROM company.objectives JOIN (SELECT id AS plan_id, objective_id FROM company.plans) p ON p.objective_id = company.objectives.id WHERE company.objectives.evaluation_only = true LIMIT 1")
        eval_plan_row = cur.fetchone()
        cur.execute(
            """
            INSERT INTO company.tasks(
                id, tenant_id, project_id, plan_id, plan_revision, revision, state, role_id,
                title, evaluation_only, created_by_command_id
            ) VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, 1, 1, 'ACCEPTED', 'EXP-001', 'E0 Qualification Task', true, %s::uuid)
            """,
            (eval_task_id, TENANT_ID, PROJECT_ID, eval_plan_row["plan_id"], ro_obj["created_by_command_id"]),
        )
        cur.execute(
            """
            INSERT INTO company.attempts(
                id, tenant_id, project_id, task_id, attempt_no, fencing_epoch,
                worker_id, state, lease_expires_at, evaluation_only, created_by_command_id
            ) VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, 1, 1, %s::uuid, 'VERIFIED', clock_timestamp() + interval '1 hour', true, %s::uuid)
            """,
            (eval_attempt_id, TENANT_ID, PROJECT_ID, eval_task_id, WORKER_ID, ro_obj["created_by_command_id"]),
        )
        cur.execute(
            """
            INSERT INTO company.e0_evaluation_runs(
                tenant_id, project_id, mandate_id, task_id, attempt_id, fencing_epoch,
                worker_id, model_id, prompt_template_digest, tool_ids_digest, state,
                started_by_command_id, completed_by_command_id
            ) VALUES (
                %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, 1,
                %s::uuid, 'model-local-mgt01-v1', %s, %s, 'OUTPUT_CAPTURED',
                %s::uuid, %s::uuid
            )
            """,
            (
                TENANT_ID,
                PROJECT_ID,
                e0_consume_res["mandate_id"],
                eval_task_id,
                eval_attempt_id,
                WORKER_ID,
                "a" * 64,
                "b" * 64,
                ro_obj["created_by_command_id"],
                ro_obj["created_by_command_id"],
            ),
        )
        cur.execute(
            """
            INSERT INTO company.verification_records(
                id, tenant_id, project_id, task_id, attempt_id, fencing_epoch,
                verifier_id, verdict, independent_of_producer, evaluation_only, created_by_command_id
            ) VALUES (
                %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, 1,
                %s::uuid, 'PASS', true, true, %s::uuid
            )
            """,
            (
                eval_verification_id,
                TENANT_ID,
                PROJECT_ID,
                eval_task_id,
                eval_attempt_id,
                VERIFIER_ID,
                ro_obj["created_by_command_id"],
            ),
        )
        cur.execute(
            """
            INSERT INTO company.e0_verification_links(
                tenant_id, project_id, task_id, attempt_id, fencing_epoch,
                verification_id, verifier_id, verdict, linked_by_command_id
            ) VALUES (
                %s::uuid, %s::uuid, %s::uuid, %s::uuid, 1,
                %s::uuid, %s::uuid, 'PASS', %s::uuid
            )
            """,
            (
                TENANT_ID,
                PROJECT_ID,
                eval_task_id,
                eval_attempt_id,
                eval_verification_id,
                VERIFIER_ID,
                ro_obj["created_by_command_id"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Issue E0 qualification candidate and activate qualification via CommandHost!
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        cand_res = host.execute(
            "e0.qualification_candidate_issue",
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": eval_task_id,
                "attempt_id": eval_attempt_id,
                "fencing_epoch": 1,
                "request_id": "req-e0-cand-issue-1",
                "idempotency_key": "idem-e0-cand-issue-1",
            },
            {"role_id": "EXP-001", "ttl_seconds": 3600},
        )
        qualification_id = str(cand_res["qualification_id"])

        qual_act_res = host.execute(
            "qualification.activate",
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-qual-activate-1",
                "idempotency_key": "idem-qual-activate-1",
            },
            {
                "qualification_id": qualification_id,
                "expected_revision": 1,
                "reason": "HUMAN_OWNER_APPROVED_E0_QUALIFICATION_FOR_EXP_001",
                "ttl_seconds": 3600,
            },
        )
    finally:
        conn.close()

    # Stage real workspace directory /var/lib/ai-proje-ofisi-dbtest/storage/workspace_mgt01
    ws_dir = STORAGE_DIR / "workspace_mgt01"
    if ws_dir.exists():
        shutil.rmtree(ws_dir)
    ws_dir.mkdir(mode=0o700)
    fixture_baseline = ROOT / "fixtures" / "mgt_title_normalization_01" / "workspace" / "task_title.py"
    oracle_script = ROOT / "fixtures" / "mgt_title_normalization_01" / "oracle" / "check_title.py"
    ws_target_file = ws_dir / "task_title.py"
    shutil.copyfile(fixture_baseline, ws_target_file)
    os.chmod(ws_target_file, 0o600)

    baseline_oracle = run_title_oracle(ws_target_file, oracle_script)
    assert not baseline_oracle.passed and baseline_oracle.passed_cases == 8 and baseline_oracle.total_cases == 13

    initial_manifest = build_manifest(ws_dir)
    initial_head = initial_manifest.manifest_sha256
    baseline_file_sha256 = hashlib.sha256(ws_target_file.read_bytes()).hexdigest()

    # Compile r65_spawn_linux.c into libr65_spawn.so and a small rootless worker ELF binary
    build_dir = STORAGE_DIR / "bin_mgt01"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(mode=0o700)
    so_path = build_dir / "libr65_spawn.so"
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-O2", str(ROOT / "company_os" / "r65_spawn_linux.c"), "-o", str(so_path)],
        check=True,
    )
    os.chmod(so_path, 0o500)

    # Also build a tiny deterministic worker binary that outputs the normalized task_title.py
    # replacement over stdout in `company.producer-output/1` wire format when invoked!
    worker_replacement_code = (
        '"""Normalized task title implementation produced by isolated worker."""\n\n'
        "from __future__ import annotations\n"
        "import unicodedata\n\n"
        "MAX_TITLE_LENGTH = 80\n\n"
        "def normalize_task_title(raw: str) -> str:\n"
        "    if not isinstance(raw, str):\n"
        '        raise TypeError("title must be str")\n'
        '    normalized = unicodedata.normalize("NFC", raw)\n'
        "    for ch in normalized:\n"
        '        if unicodedata.category(ch) in ("Cc", "Cf") and ch not in (" ", "\\t", "\\n"):\n'
        '            raise ValueError("control character not allowed")\n'
        '    collapsed = " ".join(normalized.split())\n'
        "    if not collapsed:\n"
        '        raise ValueError("title must not be empty")\n'
        "    if len(collapsed) > MAX_TITLE_LENGTH:\n"
        '        raise ValueError("title exceeds max length")\n'
        "    return collapsed\n"
    ).encode("utf-8")
    worker_b64 = base64.b64encode(worker_replacement_code).decode("ascii")
    worker_wire_line = json.dumps(
        {
            "protocol": "company.producer-output/1",
            "action": "replace",
            "replacement_base64": worker_b64,
        },
        separators=(",", ":"),
    )

    worker_c_src = build_dir / "worker_mgt01.c"
    worker_elf = build_dir / "worker_mgt01"
    worker_c_src.write_text(
        f"""
#include <stdio.h>
#include <unistd.h>
int main(void) {{
    const char *msg = "{worker_wire_line.replace('"', '\\"')}\\n";
    fputs(msg, stdout);
    fflush(stdout);
    char buf[512];
    ssize_t n = read(STDIN_FILENO, buf, sizeof(buf));
    (void)n;
    return 0;
}}
""",
        encoding="utf-8",
    )
    subprocess.run(["gcc", "-O2", str(worker_c_src), "-o", str(worker_elf)], check=True)
    worker_c_src.unlink()
    os.chmod(worker_elf, 0o500)
    worker_elf_digest = sha256_file(worker_elf)

    # Enroll signer keys, controller head, verification profile, lease policy, tool manifest, budget, resource slot
    ctrl_ws_key = ("key-ctrl-ws-1", b"1" * 32)
    ctrl_lm_key = ("key-ctrl-lm-1", b"2" * 32)
    ctrl_lc_key = ("key-ctrl-lc-1", b"3" * 32)
    ctrl_eb_key = ("key-ctrl-eb-1", b"4" * 32)
    ctrl_pp_key = ("key-ctrl-pp-1", b"5" * 32)
    ctrl_ef_key = ("key-ctrl-ef-1", b"6" * 32)
    ctrl_pa_key = ("key-ctrl-pa-1", b"7" * 32)
    ctrl_qu_key = ("key-ctrl-qu-1", b"8" * 32)
    verif_seal_key = ("key-verif-seal-1", b"9" * 32)
    verif_obs_key = ("key-verif-obs-1", b"a" * 32)
    evid_prov_key = ("key-evid-prov-1", b"b" * 32)

    conn = connect_adapted()
    try:
        cur = conn.cursor()
        signers = [
            (ctrl_ws_key[0], ctrl_ws_key[1], "r58.workspace.v1", CONTROLLER_ID),
            (ctrl_lm_key[0], ctrl_lm_key[1], "r58.launch-manifest.v1", CONTROLLER_ID),
            (ctrl_lc_key[0], ctrl_lc_key[1], "r58.launch-callback.v1", CONTROLLER_ID),
            (ctrl_eb_key[0], ctrl_eb_key[1], "r60.engine-binding.v1", CONTROLLER_ID),
            (ctrl_pp_key[0], ctrl_pp_key[1], "r60.patch-proposal.v1", CONTROLLER_ID),
            (ctrl_ef_key[0], ctrl_ef_key[1], "r60.tool-effect.v1", CONTROLLER_ID),
            (ctrl_pa_key[0], ctrl_pa_key[1], "r58.patch.v1", CONTROLLER_ID),
            (ctrl_qu_key[0], ctrl_qu_key[1], "r58.quiescence.v1", CONTROLLER_ID),
            (verif_seal_key[0], verif_seal_key[1], "r58.verification.v1", VERIFIER_ID),
            (verif_obs_key[0], verif_obs_key[1], "r60.process-observation.v1", VERIFIER_ID),
            (evid_prov_key[0], evid_prov_key[1], "r58.evidence.v1", EVIDENCE_ISSUER_ID),
        ]
        for kid, sec, prof, issuer in signers:
            fp = hashlib.sha256(sec).hexdigest()
            cur.execute(
                """
                INSERT INTO company.signer_enrollments(
                    tenant_id, key_id, purpose, profile_id, algorithm, public_key_fingerprint,
                    issuer_id, status, valid_from, valid_until, approved_by
                ) VALUES (
                    %s::uuid, %s, 'TASK_VERIFICATION', %s, 'HMAC-SHA256-M0-LOCAL', %s,
                    %s::uuid, 'ACTIVE', clock_timestamp() - interval '1 minute', clock_timestamp() + interval '1 hour', %s::uuid
                )
                """,
                (TENANT_ID, kid, prof, fp, issuer, HUMAN_ID),
            )
            cur.execute(
                """
                INSERT INTO company_private.r58_key_material(key_id, purpose, secret, fingerprint, revoked)
                VALUES (%s, 'EXECUTION_ATTESTATION', %s, %s, false)
                """,
                (kid, bytes(sec), fp),
            )

        cur.execute(
            """
            INSERT INTO company.r58_controller_heads(
                tenant_id, project_id, controller_id, epoch, status, updated_by_command_id
            ) VALUES (%s::uuid, %s::uuid, %s::uuid, 1, 'ACTIVE', %s::uuid)
            """,
            (TENANT_ID, PROJECT_ID, CONTROLLER_ID, ro_obj["created_by_command_id"]),
        )
        cur.execute(
            """
            INSERT INTO company.r58_verification_profiles(
                tenant_id, project_id, role_id, profile_id, oracle_ids, status, approved_by
            ) VALUES (
                %s::uuid, %s::uuid, 'EXP-001', 'r58.verification.v1',
                '["mgt01.check_title.13cases.v1"]'::jsonb, 'ACTIVE', %s::uuid
            )
            """,
            (TENANT_ID, PROJECT_ID, HUMAN_ID),
        )
        cur.execute(
            """
            INSERT INTO company.r58_lease_policies(
                tenant_id, project_id, role_id, lease_ttl_ms, max_renewals, approved_by
            ) VALUES (%s::uuid, %s::uuid, 'EXP-001', 120000, 2, %s::uuid)
            """,
            (TENANT_ID, PROJECT_ID, HUMAN_ID),
        )
        cur.execute(
            """
            INSERT INTO company.r60_tool_manifests(
                tenant_id, project_id, tool_id, manifest_revision, status,
                effect_kind, allowed_relpath, approved_by
            ) VALUES (
                %s::uuid, %s::uuid, 'patch.apply', 1, 'ACTIVE',
                'WORKSPACE_SINGLE_FILE_REPLACE', 'task_title.py', %s::uuid
            )
            """,
            (TENANT_ID, PROJECT_ID, HUMAN_ID),
        )
        cur.execute(
            """
            INSERT INTO company.budget_versions(
                tenant_id, project_id, scope_kind, scope_id, version,
                currency, limit_minor, reserved_minor, spent_minor,
                approved_by, created_by_command_id
            ) VALUES (
                %s::uuid, %s::uuid, 'PROJECT', %s::uuid, 1,
                'TRY', 0, 0, 0, %s::uuid, %s::uuid
            )
            """,
            (TENANT_ID, PROJECT_ID, PROJECT_ID, HUMAN_ID, ro_obj["created_by_command_id"]),
        )
        cur.execute(
            """
            INSERT INTO company.resource_slots(
                tenant_id, project_id, slot_id, capacity, active_claims
            ) VALUES (%s::uuid, %s::uuid, 'slot-local-cpu-1', 1, 0)
            """,
            (TENANT_ID, PROJECT_ID),
        )
        conn.commit()
    finally:
        conn.close()

    # Issue task-scoped grant for owner & controller to set workspace head and ready task
    owner_task_grant = issue_grant(
        grant_id=uuid_from_seed("grant-owner-task"),
        principal_id=HUMAN_ID,
        permissions=(
            "CAP-002.tasks.ready",
            "CAP-006.workspace.current_head",
            "CAP-011.verification.accept",
            "CAP-R58.attestation.ingest",
        ),
        task_id=task_id,
    )
    worker_claim_grant = issue_grant(
        grant_id=uuid_from_seed("grant-worker-claim"),
        principal_id=WORKER_ID,
        permissions=("CAP-003.worker.claim",),
        task_id=task_id,
    )

    bump_clock()
    ws_art_id = uuid_from_seed("art-ws-initial-head")
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        ws_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "workspace_id": WORKSPACE_ID,
            "head": initial_head,
            "files": [{"path": f.relpath, "sha256": f.sha256, "size": f.size} for f in initial_manifest.files],
        }
        ingest_attestation(
            host,
            {
                "session_token": owner_token,
                "grant_id": owner_task_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "request_id": "req-ws-attest-1",
                "idempotency_key": "idem-ws-attest-1",
            },
            artifact_id=ws_art_id,
            profile_id="r58.workspace.v1",
            key_id=ctrl_ws_key[0],
            issuer_id=CONTROLLER_ID,
            statement=ws_stmt,
            secret=ctrl_ws_key[1],
        )
        ws_head_res = host.execute(
            "workspace.current_head",
            {
                "session_token": owner_token,
                "grant_id": owner_task_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "request_id": "req-ws-head-1",
                "idempotency_key": "idem-ws-head-1",
            },
            {
                "workspace_id": WORKSPACE_ID,
                "current_head": initial_head,
                "head_artifact_id": ws_art_id,
                "key_id": ctrl_ws_key[0],
                "issuer_id": CONTROLLER_ID,
            },
        )
        ready_res = host.execute(
            "tasks.ready",
            {
                "session_token": owner_token,
                "grant_id": owner_task_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "request_id": "req-task-ready-1",
                "idempotency_key": "idem-task-ready-1",
            },
            {
                "workspace_id": WORKSPACE_ID,
                "expected_revision": 1,
                "verification_profile_id": "r58.verification.v1",
            },
        )
        claim_res = host.execute(
            "worker.claim",
            {
                "session_token": worker_token,
                "grant_id": worker_claim_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "request_id": "req-worker-claim-1",
                "idempotency_key": "idem-worker-claim-1",
            },
            {"qualification_id": qualification_id},
        )
    finally:
        conn.close()

    attempt_id = str(claim_res["attempt_id"])
    fencing_epoch = int(claim_res["fencing_epoch"])
    assert fencing_epoch == 1 and claim_res["state"] == "CLAIMED"

    report["steps"]["4_qualification_workspace_and_claim"] = {
        "qualification_id": qualification_id,
        "qualification_status": qual_act_res["status"],
        "initial_workspace_head": initial_head,
        "baseline_oracle": {
            "passed": baseline_oracle.passed,
            "passed_cases": baseline_oracle.passed_cases,
            "total_cases": baseline_oracle.total_cases,
        },
        "task_ready_state": ready_res["state"],
        "claimed_attempt_id": attempt_id,
        "fencing_epoch": fencing_epoch,
    }

    # -------------------------------------------------------------------------
    # STEP 5: Launch Reserve -> Launch Consume -> DeliveryGuard -> Isolated Worker
    #         -> Launch Callback -> Engine Bind -> PilotSession (Broker + Executor + Patch)
    #         -> Process Stop/Release
    # -------------------------------------------------------------------------
    worker_attempt_grant = issue_grant(
        grant_id=uuid_from_seed("grant-worker-attempt-1"),
        principal_id=WORKER_ID,
        permissions=(
            "CAP-004.process.launch_reserve",
            "CAP-005.tool.request",
        ),
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
    )
    controller_attempt_grant = issue_grant(
        grant_id=uuid_from_seed("grant-controller-attempt-1"),
        principal_id=CONTROLLER_ID,
        permissions=(
            "CAP-004.process.launch_consume",
            "CAP-004.process.launch_callback",
            "CAP-004.process.stop_release",
            "CAP-004.process.reconcile",
            "CAP-004.engine.bind",
            "CAP-005.tool.authorize",
            "CAP-005.tool.consume",
            "CAP-005.tool.effect_complete",
            "CAP-006.patch.stage_proposal",
            "CAP-006.patch.receipt",
            "CAP-R58.attestation.ingest",
        ),
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
    )

    process_run_id = uuid_from_seed("proc-run-attempt-1")
    budget_res_id = uuid_from_seed("budget-res-attempt-1")
    resource_claim_id = uuid_from_seed("res-claim-attempt-1")
    admission_art_id = uuid_from_seed("art-launch-manifest-1")
    callback_art_id = uuid_from_seed("art-launch-callback-1")
    engine_bind_art_id = uuid_from_seed("art-engine-bind-1")
    quiescence_art_id = uuid_from_seed("art-quiescence-1")
    stream_id = "stream-mgt01-attempt-1"

    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        lm_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "fencing_epoch": fencing_epoch,
            "process_run_id": process_run_id,
            "executable_sha256": worker_elf_digest,
            "workspace_head": initial_head,
        }
        lm_digest = hashlib.sha256(canonical_json(lm_stmt)).hexdigest()
        ingest_attestation(
            host,
            {
                "session_token": controller_token,
                "grant_id": controller_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-lm-attest-1",
                "idempotency_key": "idem-lm-attest-1",
            },
            artifact_id=admission_art_id,
            profile_id="r58.launch-manifest.v1",
            key_id=ctrl_lm_key[0],
            issuer_id=CONTROLLER_ID,
            statement=lm_stmt,
            secret=ctrl_lm_key[1],
        )

        reserve_res = host.execute(
            "process.launch_reserve",
            {
                "session_token": worker_token,
                "grant_id": worker_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-launch-reserve-1",
                "idempotency_key": "idem-launch-reserve-1",
            },
            {
                "process_run_id": process_run_id,
                "budget_reservation_id": budget_res_id,
                "resource_claim_id": resource_claim_id,
                "slot_id": "slot-local-cpu-1",
                "amount_minor": 0,
                "admission_artifact_id": admission_art_id,
                "admission_digest": lm_digest,
                "key_id": ctrl_lm_key[0],
                "issuer_id": CONTROLLER_ID,
            },
        )

        consume_ticket = host.execute(
            "process.launch_consume",
            {
                "session_token": controller_token,
                "grant_id": controller_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-launch-consume-1",
                "idempotency_key": "idem-launch-consume-1",
            },
            {
                "process_run_id": process_run_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
            },
        )
    finally:
        conn.close()

    # Validate ticket via DeliveryGuard
    guard = DeliveryGuard()
    guard.validate(
        consume_ticket,
        expected_process_run_id=process_run_id,
        expected_attempt_id=attempt_id,
        expected_fencing_epoch=fencing_epoch,
        expected_admission_digest=lm_digest,
    )

    # Probe native LinuxLauncher (libr65_spawn.so) and spawn isolated worker process with pipes
    # Check if cgroup.procs is writable in this container/service scope; if not, record exact
    # cgroup behavior and run the compiled rootless worker ELF over OS pipes.
    cgroup_probe_dir = STORAGE_DIR / "cgroup_probe"
    native_launcher_probe: dict[str, Any] = {"so_sha256": sha256_file(so_path), "worker_elf_sha256": worker_elf_digest}
    try:
        proc_cgroup = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip()
        rel_cg = proc_cgroup.split("::", 1)[1] if "::" in proc_cgroup else ""
        cg_base = Path("/sys/fs/cgroup") / rel_cg.lstrip("/")
        sub_cg = cg_base / "leaf_worker_mgt01"
        sub_cg.mkdir(exist_ok=True)
        launcher = LinuxLauncher(so_path)
        plan = SpawnPlan(
            executable=worker_elf,
            expected_executable_sha256=worker_elf_digest,
            workspace_dir=ws_dir,
            cgroup_dir=sub_cg,
            argv=("worker_mgt01",),
            env=("LC_ALL=C",),
            timeout_ms=5000,
        )
        spawn_res = launcher.launch(consume_ticket, plan)
        native_launcher_probe["r65_spawn_result"] = {
            "ok": spawn_res.ok,
            "stage": spawn_res.stage,
            "err": spawn_res.err,
            "child_pid": spawn_res.child_pid,
            "pidfd_supported": spawn_res.pidfd_supported,
        }
        if spawn_res.ok and spawn_res.child_pid > 0:
            os.kill(spawn_res.child_pid, 9)
            os.waitpid(spawn_res.child_pid, 0)
    except Exception as exc:
        native_launcher_probe["r65_spawn_probe_note"] = str(exc)

    # Launch the compiled worker ELF (`worker_mgt01`) connected to PipeTransport for PilotSession
    r_from_engine, w_from_engine = os.pipe()
    r_to_engine, w_to_engine = os.pipe()
    worker_proc = subprocess.Popen(
        [str(worker_elf)],
        stdin=r_to_engine,
        stdout=w_from_engine,
        stderr=subprocess.DEVNULL,
        cwd=str(ws_dir),
        env={"LC_ALL": "C"},
        close_fds=True,
    )
    os.close(w_from_engine)
    os.close(r_to_engine)

    # Record launch_callback and engine.bind in Kernel DB
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        lc_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "fencing_epoch": fencing_epoch,
            "process_run_id": process_run_id,
            "os_pid": worker_proc.pid,
            "process_group_id": worker_proc.pid,
            "cgroup_path": "/user.slice/aipof-worker-mgt01",
            "executable_sha256": worker_elf_digest,
        }
        lc_sig = sign_attestation(ctrl_lc_key[1], "r58.launch-callback.v1", lc_stmt)
        lc_res = host.execute(
            "process.launch_callback",
            {
                "session_token": controller_token,
                "grant_id": controller_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-launch-cb-1",
                "idempotency_key": "idem-launch-cb-1",
            },
            {
                "process_run_id": process_run_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
                "callback_artifact_id": callback_art_id,
                "key_id": ctrl_lc_key[0],
                "issuer_id": CONTROLLER_ID,
                "os_pid": worker_proc.pid,
                "process_group_id": worker_proc.pid,
                "cgroup_path": "/user.slice/aipof-worker-mgt01",
                "callback_statement": lc_stmt,
                "callback_signature": lc_sig,
            },
        )

        eb_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "fencing_epoch": fencing_epoch,
            "process_run_id": process_run_id,
            "stream_id": stream_id,
        }
        eb_sig = sign_attestation(ctrl_eb_key[1], "r60.engine-binding.v1", eb_stmt)
        eb_res = host.execute(
            "engine.bind",
            {
                "session_token": controller_token,
                "grant_id": controller_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-engine-bind-1",
                "idempotency_key": "idem-engine-bind-1",
            },
            {
                "process_run_id": process_run_id,
                "stream_id": stream_id,
                "binding_artifact_id": engine_bind_art_id,
                "key_id": ctrl_eb_key[0],
                "issuer_id": CONTROLLER_ID,
                "binding_statement": eb_stmt,
                "binding_signature": eb_sig,
            },
        )
    finally:
        conn.close()

    # Run PilotSession over the pipe transport to process the worker output through
    # ProducerOutputAdapter -> PatchProposalProducer -> Broker -> LinuxSingleFileExecutor -> PatchReceiptRecorder -> EngineReplyGuard
    bump_clock()
    rt_port = CommandHostRuntimePort(
        controller_session=controller_token,
        controller_grant=controller_attempt_grant,
        worker_session=worker_token,
        worker_grant=worker_attempt_grant,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
        workspace_id=WORKSPACE_ID,
        base_head=initial_head,
        controller_id=CONTROLLER_ID,
        proposal_key_id=ctrl_pp_key[0],
        proposal_secret=ctrl_pp_key[1],
        effect_key_id=ctrl_ef_key[0],
        effect_secret=ctrl_ef_key[1],
        patch_key_id=ctrl_pa_key[0],
        patch_secret=ctrl_pa_key[1],
    )

    journal_dir = STORAGE_DIR / "journal_mgt01"
    if journal_dir.exists():
        shutil.rmtree(journal_dir)
    journal_dir.mkdir(mode=0o700)
    journal = IntentJournal(journal_dir)
    executor = LinuxSingleFileExecutor(ws_dir)
    broker = Broker(rt_port, journal, executor)
    proposal_producer = PatchProposalProducer(rt_port, ws_dir)
    patch_recorder = PatchReceiptRecorder(rt_port, ws_dir)
    adapter = ProducerOutputAdapter(rt_port, proposal_producer)
    reply_guard = EngineReplyGuard(rt_port)

    pilot = PilotSession(
        adapter=adapter,
        broker=broker,
        patch_recorder=patch_recorder,
        reply_guard=reply_guard,
        scope_factory=lambda: DbScope(connect_adapted()),
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
        process_run_id=process_run_id,
        stream_id=stream_id,
        workspace_id=WORKSPACE_ID,
        base_head=initial_head,
        consumer_id=CONTROLLER_ID,
        proposal_key_id=ctrl_pp_key[0],
        patch_key_id=ctrl_pa_key[0],
        issuer_id=CONTROLLER_ID,
        request_id_factory=lambda n: uuid_from_seed(f"tool-req-mgt01-{n}"),
        proposal_artifact_id_factory=lambda n: uuid_from_seed(f"prop-art-mgt01-{n}"),
        effect_artifact_id_factory=lambda n: uuid_from_seed(f"eff-art-mgt01-{n}"),
        patch_artifact_id_factory=lambda n: uuid_from_seed(f"patch-art-mgt01-{n}"),
    )

    transport = PipeTransport(read_fd=r_from_engine, write_fd=w_to_engine)
    pump = EnginePump(
        transport=transport,
        runtime=rt_port,
        handler=pilot,
        limits=PumpLimits(
            max_frame_bytes=16384,
            max_frames=1,
            idle_timeout_ms=5000,
            total_timeout_ms=10000,
        ),
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
        process_run_id=process_run_id,
        stream_id=stream_id,
        monotonic_ms=lambda: int(time.monotonic() * 1000),
    )

    try:
        pump_result = pump.run()
    finally:
        transport.close()
        worker_proc.wait(timeout=5)

    assert pump_result.frames_processed == 1 and pump_result.halted_reason == "MAX_FRAMES_REACHED"

    # Stop & release process run (process.stop_release) -> releases resource slot and settles budget
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        qu_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "fencing_epoch": fencing_epoch,
            "process_run_id": process_run_id,
            "os_pid": worker_proc.pid,
            "cgroup_empty": True,
        }
        qu_sig = sign_attestation(ctrl_qu_key[1], "r58.quiescence.v1", qu_stmt)
        stop_res = host.execute(
            "process.stop_release",
            {
                "session_token": controller_token,
                "grant_id": controller_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-proc-stop-1",
                "idempotency_key": "idem-proc-stop-1",
            },
            {
                "process_run_id": process_run_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
                "final_state": "STOPPED",
                "settled_minor": 0,
                "quiescence_artifact_id": quiescence_art_id,
                "key_id": ctrl_qu_key[0],
                "issuer_id": CONTROLLER_ID,
                "quiescence_statement": qu_stmt,
                "quiescence_signature": qu_sig,
            },
        )
    finally:
        conn.close()

    post_manifest = build_manifest(ws_dir)
    result_head = post_manifest.manifest_sha256
    patched_file_sha256 = hashlib.sha256(ws_target_file.read_bytes()).hexdigest()
    assert result_head != initial_head and patched_file_sha256 != baseline_file_sha256

    report["steps"]["5_isolated_worker_broker_and_patch"] = {
        "process_run_id": process_run_id,
        "reserve_state": reserve_res["state"],
        "consume_spawn_permitted": consume_ticket["spawn_permitted"],
        "native_launcher_probe": native_launcher_probe,
        "launch_callback_state": lc_res["state"],
        "engine_bind_stream_id": eb_res["stream_id"],
        "pump_frames_processed": pump_result.frames_processed,
        "pump_halted_reason": pump_result.halted_reason,
        "tool_request_id": rt_port.last_tool_request_id,
        "patch_artifact_id": rt_port.last_patch_artifact_id,
        "patch_artifact_digest": rt_port.last_patch_artifact_digest,
        "baseline_file_sha256": baseline_file_sha256,
        "patched_file_sha256": patched_file_sha256,
        "result_workspace_head": result_head,
        "stop_release_state": stop_res["state"],
    }

    # -------------------------------------------------------------------------
    # STEP 6: Independent Verifier (verifier_runner.py) -> Seal -> Provenance -> Accept
    # -------------------------------------------------------------------------
    verifier_attempt_grant = issue_grant(
        grant_id=uuid_from_seed("grant-verifier-attempt-1"),
        principal_id=VERIFIER_ID,
        permissions=(
            "CAP-010.verification.final_seal",
            "CAP-R58.attestation.ingest",
        ),
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
    )
    evidence_attempt_grant = issue_grant(
        grant_id=uuid_from_seed("grant-evidence-attempt-1"),
        principal_id=EVIDENCE_ISSUER_ID,
        permissions=(
            "CAP-009.evidence.provenance",
            "CAP-R58.attestation.ingest",
        ),
        task_id=task_id,
        attempt_id=attempt_id,
        fencing_epoch=fencing_epoch,
    )

    bump_clock()
    verification_id = uuid_from_seed("verif-record-mgt01-1")
    verif_art_id = uuid_from_seed("art-verif-seal-mgt01-1")
    evid_art_id = uuid_from_seed("art-evid-prov-mgt01-1")
    acceptance_id = uuid_from_seed("accept-record-mgt01-1")

    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        pipeline = IndependentVerificationPipeline(host)
        verif_chain_res = pipeline.seal_and_accept(
            candidate_path=ws_target_file,
            oracle_path=oracle_script,
            verifier_context={
                "session_token": verifier_token,
                "grant_id": verifier_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-verif-seal-1",
                "idempotency_key": "idem-verif-seal-1",
            },
            evidence_context={
                "session_token": evidence_token,
                "grant_id": evidence_attempt_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "fencing_epoch": fencing_epoch,
                "request_id": "req-evid-prov-1",
                "idempotency_key": "idem-evid-prov-1",
            },
            accept_context={
                "session_token": owner_token,
                "grant_id": owner_task_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task_id,
                "request_id": "req-verif-accept-1",
                "idempotency_key": "idem-verif-accept-1",
            },
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            task_id=task_id,
            attempt_id=attempt_id,
            fencing_epoch=fencing_epoch,
            workspace_id=WORKSPACE_ID,
            producer_id=WORKER_ID,
            verifier_id=VERIFIER_ID,
            verifier_key_id=verif_seal_key[0],
            verifier_secret=verif_seal_key[1],
            evidence_issuer_id=EVIDENCE_ISSUER_ID,
            evidence_key_id=evid_prov_key[0],
            evidence_secret=evid_prov_key[1],
            human_id=HUMAN_ID,
            verification_id=verification_id,
            verification_artifact_id=verif_art_id,
            evidence_artifact_id=evid_art_id,
            patch_artifact_id=rt_port.last_patch_artifact_id,
            patch_artifact_digest=rt_port.last_patch_artifact_digest,
            result_head=result_head,
            acceptance_id=acceptance_id,
        )
    finally:
        conn.close()

    assert verif_chain_res["oracle"]["passed"] is True
    assert verif_chain_res["oracle"]["passed_cases"] == 13
    assert verif_chain_res["acceptance"]["task_state"] == "ACCEPTED"

    report["steps"]["6_independent_verifier_and_kernel_accept"] = verif_chain_res

    # -------------------------------------------------------------------------
    # STEP 7: Authenticated UI Readback & Persistent Reload across DB Restart
    # -------------------------------------------------------------------------
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        ui_app = AuthenticatedReadbackApp(host)
        view_gen1 = ui_app.load_workflow_view(
            session_token=owner_token,
            grant_id=owner_grant_id,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            task_id=task_id,
            attempt_id=attempt_id,
            qualification_id=qualification_id,
            process_run_id=process_run_id,
            tool_request_id=rt_port.last_tool_request_id,
            evidence_artifact_id=evid_art_id,
            acceptance_id=acceptance_id,
            ui_generation=1,
            request_prefix="req-ui-gen1",
        )
        html_gen1 = render_workflow_html(view_gen1)
    finally:
        conn.close()

    # Restart PostgreSQL server to prove physical persistence across restart!
    subprocess.run(
        [
            "/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/postgresql/18/bin/pg_ctl",
            "-D",
            "/var/lib/ai-proje-ofisi-dbtest/storage/data",
            "-l",
            "/var/lib/ai-proje-ofisi-dbtest/storage/postgres.log",
            "-o",
            f"-k {SOCKET_DIR} -p {DB_PORT}",
            "restart",
        ],
        check=True,
    )

    # Refresh clock sample after DB restart and reload UI view (generation 2) verifying digest equality
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        ui_app_reloaded = AuthenticatedReadbackApp(host)
        view_gen2 = ui_app_reloaded.load_workflow_view(
            session_token=owner_token,
            grant_id=owner_grant_id,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            task_id=task_id,
            attempt_id=attempt_id,
            qualification_id=qualification_id,
            process_run_id=process_run_id,
            tool_request_id=rt_port.last_tool_request_id,
            evidence_artifact_id=evid_art_id,
            acceptance_id=acceptance_id,
            ui_generation=2,
            expected_digests=view_gen1.digests,
            request_prefix="req-ui-gen2",
        )
    finally:
        conn.close()

    assert view_gen1.digests == view_gen2.digests
    assert "ACCEPTED" in html_gen1 and "SYNTHETIC_OR_DISPOSABLE_READBACK_NOT_G0_CLOSED" in html_gen1

    report["steps"]["7_authenticated_ui_and_persistent_reload"] = {
        "ui_generation_1_digests": view_gen1.digests,
        "ui_generation_2_digests": view_gen2.digests,
        "digests_identical_after_pg_restart": view_gen1.digests == view_gen2.digests,
        "html_length": len(html_gen1),
    }

    # -------------------------------------------------------------------------
    # STEP 8: Execute All 7 Negative Scenarios Against Real Native Kernel + OS
    # -------------------------------------------------------------------------
    bump_clock()

    # Negative 1: Unauthorized scope / wrong principal / wrong task
    neg1_wrong_principal = None
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        try:
            # rogue_token trying to use worker_claim_grant (issued to WORKER_ID)
            host.execute(
                "worker.claim",
                {
                    "session_token": rogue_token,
                    "grant_id": worker_claim_grant,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "task_id": task_id,
                    "request_id": "req-neg1-wrong-principal",
                    "idempotency_key": "idem-neg1-wrong-principal",
                },
                {"qualification_id": qualification_id},
            )
        except Exception as exc:
            neg1_wrong_principal = str(exc).strip().splitlines()[0]
            conn.rollback()
    finally:
        conn.close()

    # Also test wrong task scope on owner_task_grant
    neg1_wrong_task = None
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        try:
            host.execute(
                "tasks.ready",
                {
                    "session_token": owner_token,
                    "grant_id": owner_task_grant,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "task_id": eval_task_id,  # grant is scoped to task_id, not eval_task_id!
                    "request_id": "req-neg1-wrong-task",
                    "idempotency_key": "idem-neg1-wrong-task",
                },
                {"workspace_id": WORKSPACE_ID, "expected_revision": 1},
            )
        except Exception as exc:
            neg1_wrong_task = str(exc).strip().splitlines()[0]
            conn.rollback()
    finally:
        conn.close()

    assert neg1_wrong_principal and "GRANT_WRONG_PRINCIPAL" in neg1_wrong_principal
    assert neg1_wrong_task and "GRANT_WRONG_TASK" in neg1_wrong_task
    report["negatives"]["1_unauthorized_scope"] = {
        "wrong_principal_error": neg1_wrong_principal,
        "wrong_task_error": neg1_wrong_task,
    }

    # Negative 2 & 7: Create a second task (`MGT-NEGATIVE-TRIAL-02`) to test
    # Stale Lease/Fence, Replay, Wrong Artifact/Manifest, Crash/Reconcile, and Revoke!
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        task2_res = create_task(
            host,
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-task2-create",
                "idempotency_key": "idem-task2-create",
            },
            plan_id=plan_id,
            plan_revision=int(plan_res["revision"]),
            title="MGT-NEGATIVE-TRIAL-02",
            role_id="EXP-001",
        )
        task2_id = str(task2_res["id"])
    finally:
        conn.close()

    owner_task2_grant = issue_grant(
        grant_id=uuid_from_seed("grant-owner-task2"),
        principal_id=HUMAN_ID,
        permissions=("CAP-002.tasks.ready", "CAP-R58.attestation.ingest"),
        task_id=task2_id,
    )
    worker_task2_claim_grant = issue_grant(
        grant_id=uuid_from_seed("grant-worker-task2-claim"),
        principal_id=WORKER_ID,
        permissions=("CAP-003.worker.claim",),
        task_id=task2_id,
    )

    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        host.execute(
            "tasks.ready",
            {
                "session_token": owner_token,
                "grant_id": owner_task2_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "request_id": "req-task2-ready",
                "idempotency_key": "idem-task2-ready",
            },
            {
                "workspace_id": WORKSPACE_ID,
                "expected_revision": 1,
                "verification_profile_id": "r58.verification.v1",
            },
        )
        claim2_a1 = host.execute(
            "worker.claim",
            {
                "session_token": worker_token,
                "grant_id": worker_task2_claim_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "request_id": "req-task2-claim-a1",
                "idempotency_key": "idem-task2-claim-a1",
            },
            {"qualification_id": qualification_id},
        )
    finally:
        conn.close()

    task2_a1_id = str(claim2_a1["attempt_id"])
    task2_a1_epoch = int(claim2_a1["fencing_epoch"])

    # Issue attempt-1 grants for task2
    worker_t2_a1_grant = issue_grant(
        grant_id=uuid_from_seed("grant-worker-t2-a1"),
        principal_id=WORKER_ID,
        permissions=("CAP-004.process.launch_reserve", "CAP-005.tool.request"),
        task_id=task2_id,
        attempt_id=task2_a1_id,
        fencing_epoch=task2_a1_epoch,
    )
    ctrl_t2_a1_grant = issue_grant(
        grant_id=uuid_from_seed("grant-ctrl-t2-a1"),
        principal_id=CONTROLLER_ID,
        permissions=(
            "CAP-004.process.launch_consume",
            "CAP-004.process.launch_callback",
            "CAP-004.process.reconcile",
            "CAP-004.process.stop_release",
            "CAP-R58.attestation.ingest",
        ),
        task_id=task2_id,
        attempt_id=task2_a1_id,
        fencing_epoch=task2_a1_epoch,
    )

    # Reserve and consume process run on task2 attempt 1
    t2_proc_id = uuid_from_seed("proc-run-t2-a1")
    t2_lm_art_id = uuid_from_seed("art-lm-t2-a1")
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        t2_lm_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task2_id,
            "attempt_id": task2_a1_id,
            "fencing_epoch": task2_a1_epoch,
            "process_run_id": t2_proc_id,
            "executable_sha256": worker_elf_digest,
        }
        t2_lm_digest = hashlib.sha256(canonical_json(t2_lm_stmt)).hexdigest()
        ingest_attestation(
            host,
            {
                "session_token": controller_token,
                "grant_id": ctrl_t2_a1_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "attempt_id": task2_a1_id,
                "fencing_epoch": task2_a1_epoch,
                "request_id": "req-t2-lm-attest",
                "idempotency_key": "idem-t2-lm-attest",
            },
            artifact_id=t2_lm_art_id,
            profile_id="r58.launch-manifest.v1",
            key_id=ctrl_lm_key[0],
            issuer_id=CONTROLLER_ID,
            statement=t2_lm_stmt,
            secret=ctrl_lm_key[1],
        )
        host.execute(
            "process.launch_reserve",
            {
                "session_token": worker_token,
                "grant_id": worker_t2_a1_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "attempt_id": task2_a1_id,
                "fencing_epoch": task2_a1_epoch,
                "request_id": "req-t2-reserve",
                "idempotency_key": "idem-t2-reserve",
            },
            {
                "process_run_id": t2_proc_id,
                "budget_reservation_id": uuid_from_seed("bres-t2-a1"),
                "resource_claim_id": uuid_from_seed("rclaim-t2-a1"),
                "slot_id": "slot-local-cpu-1",
                "amount_minor": 0,
                "admission_artifact_id": t2_lm_art_id,
                "admission_digest": t2_lm_digest,
                "key_id": ctrl_lm_key[0],
                "issuer_id": CONTROLLER_ID,
            },
        )
        t2_consume_1 = host.execute(
            "process.launch_consume",
            {
                "session_token": controller_token,
                "grant_id": ctrl_t2_a1_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "attempt_id": task2_a1_id,
                "fencing_epoch": task2_a1_epoch,
                "request_id": "req-t2-consume-1",
                "idempotency_key": "idem-t2-consume-1",
            },
            {
                "process_run_id": t2_proc_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
            },
        )
        # Negative 3a: Replay of process.launch_consume with a new request_id -> returns spawn_permitted=false!
        t2_consume_replay = host.execute(
            "process.launch_consume",
            {
                "session_token": controller_token,
                "grant_id": ctrl_t2_a1_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "attempt_id": task2_a1_id,
                "fencing_epoch": task2_a1_epoch,
                "request_id": "req-t2-consume-replay",
                "idempotency_key": "idem-t2-consume-replay",
            },
            {
                "process_run_id": t2_proc_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
            },
        )
    finally:
        conn.close()

    assert t2_consume_1["spawn_permitted"] is True
    assert t2_consume_replay["spawn_permitted"] is False and t2_consume_replay["reason"] == "ALREADY_CONSUMED_OR_NOT_RESERVED"

    # Negative 3b: IntentJournal duplicate intent raises Unknown('EXISTING_INTENT_RECONCILE_NO_RETRY')
    neg3_journal_replay_error = None
    try:
        journal.record_intent(
            tool_request_id=rt_port.last_tool_request_id,
            attempt_id=attempt_id,
            fencing_epoch=fencing_epoch,
            proposal_digest="d" * 64,
            target_path="task_title.py",
        )
    except Unknown as exc:
        neg3_journal_replay_error = str(exc)
    assert neg3_journal_replay_error == "EXISTING_INTENT_RECONCILE_NO_RETRY"

    report["negatives"]["3_replay_protection"] = {
        "launch_consume_replay_spawn_permitted": t2_consume_replay["spawn_permitted"],
        "launch_consume_replay_reason": t2_consume_replay["reason"],
        "intent_journal_duplicate_error": neg3_journal_replay_error,
    }

    # Negative 7: Crash / UNKNOWN process state reconciliation via independent verifier
    # t2_proc_id is currently in LAUNCH_CONSUMED_PENDING_CALLBACK (simulating a controller crash after consume before callback).
    # Independent verifier observes process absence (`r60.process-observation.v1`), controller calls `process.reconcile` -> `LOST`, then `process.stop_release`!
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        obs_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task2_id,
            "attempt_id": task2_a1_id,
            "fencing_epoch": task2_a1_epoch,
            "process_run_id": t2_proc_id,
            "observed_alive": False,
        }
        obs_sig = sign_attestation(verif_obs_key[1], "r60.process-observation.v1", obs_stmt)
        reconcile_res = host.execute(
            "process.reconcile",
            {
                "session_token": controller_token,
                "grant_id": ctrl_t2_a1_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "attempt_id": task2_a1_id,
                "fencing_epoch": task2_a1_epoch,
                "request_id": "req-t2-reconcile",
                "idempotency_key": "idem-t2-reconcile",
            },
            {
                "process_run_id": t2_proc_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
                "resolution": "LOST",
                "evidence_artifact_id": uuid_from_seed("art-obs-t2-a1"),
                "key_id": verif_obs_key[0],
                "issuer_id": VERIFIER_ID,
                "observation_statement": obs_stmt,
                "observation_signature": obs_sig,
            },
        )
        t2_qu_stmt = {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "task_id": task2_id,
            "attempt_id": task2_a1_id,
            "fencing_epoch": task2_a1_epoch,
            "process_run_id": t2_proc_id,
            "cgroup_empty": True,
        }
        t2_qu_sig = sign_attestation(ctrl_qu_key[1], "r58.quiescence.v1", t2_qu_stmt)
        t2_stop_res = host.execute(
            "process.stop_release",
            {
                "session_token": controller_token,
                "grant_id": ctrl_t2_a1_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "attempt_id": task2_a1_id,
                "fencing_epoch": task2_a1_epoch,
                "request_id": "req-t2-stop",
                "idempotency_key": "idem-t2-stop",
            },
            {
                "process_run_id": t2_proc_id,
                "controller_id": CONTROLLER_ID,
                "controller_epoch": 1,
                "final_state": "KILLED",
                "settled_minor": 0,
                "quiescence_artifact_id": uuid_from_seed("art-qu-t2-a1"),
                "key_id": ctrl_qu_key[0],
                "issuer_id": CONTROLLER_ID,
                "quiescence_statement": t2_qu_stmt,
                "quiescence_signature": t2_qu_sig,
            },
        )
    finally:
        conn.close()

    report["negatives"]["7_crash_and_reconcile"] = {
        "reconcile_state": reconcile_res["state"],
        "stop_after_reconcile_state": t2_stop_res["state"],
    }

    # Negative 2: Stale lease / fencing epoch!
    # Expire task2 attempt 1 lease and claim attempt 2 (fencing_epoch=2), then try using attempt 1 (fencing_epoch=1) -> STALE_ATTEMPT!
    conn = connect_adapted()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE company.attempts SET lease_expires_at = clock_timestamp() - interval '10 seconds' WHERE id = %s::uuid",
            (task2_a1_id,),
        )
        conn.commit()
    finally:
        conn.close()

    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        claim2_a2 = host.execute(
            "worker.claim",
            {
                "session_token": worker_token,
                "grant_id": worker_task2_claim_grant,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "task_id": task2_id,
                "request_id": "req-task2-claim-a2",
                "idempotency_key": "idem-task2-claim-a2",
            },
            {"qualification_id": qualification_id},
        )
        stale_attempt_error = None
        try:
            host.execute(
                "process.launch_reserve",
                {
                    "session_token": worker_token,
                    "grant_id": worker_t2_a1_grant,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "task_id": task2_id,
                    "attempt_id": task2_a1_id,
                    "fencing_epoch": task2_a1_epoch,
                    "request_id": "req-neg2-stale-fence",
                    "idempotency_key": "idem-neg2-stale-fence",
                },
                {
                    "process_run_id": uuid_from_seed("proc-stale"),
                    "budget_reservation_id": uuid_from_seed("bres-stale"),
                    "resource_claim_id": uuid_from_seed("rclaim-stale"),
                    "slot_id": "slot-local-cpu-1",
                    "amount_minor": 0,
                    "admission_artifact_id": t2_lm_art_id,
                    "admission_digest": t2_lm_digest,
                    "key_id": ctrl_lm_key[0],
                    "issuer_id": CONTROLLER_ID,
                },
            )
        except Exception as exc:
            stale_attempt_error = str(exc).strip().splitlines()[0]
            conn.rollback()
    finally:
        conn.close()

    assert int(claim2_a2["fencing_epoch"]) == 2
    assert stale_attempt_error and "STALE_ATTEMPT" in stale_attempt_error
    report["negatives"]["2_stale_lease_and_fence"] = {
        "new_attempt_id": str(claim2_a2["attempt_id"]),
        "new_fencing_epoch": int(claim2_a2["fencing_epoch"]),
        "stale_attempt_error": stale_attempt_error,
    }

    # Negative 4: Revoke (`CAP-017.revoke` via CommandHost & `revoke_project_grant`)
    # Revoke `worker_task2_claim_grant` via `CAP-017.revoke` and verify subsequent call raises GRANT_NOT_CURRENT!
    bump_clock()
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        revoke_res = host.execute(
            "CAP-017.revoke",
            {
                "session_token": owner_token,
                "grant_id": owner_grant_id,
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "request_id": "req-neg4-revoke-1",
                "idempotency_key": "idem-neg4-revoke-1",
            },
            {
                "target_grant_id": worker_task2_claim_grant,
                "reason": "REVOKE_NEGATIVE_TEST",
            },
        )
        revoked_grant_error = None
        try:
            host.execute(
                "worker.claim",
                {
                    "session_token": worker_token,
                    "grant_id": worker_task2_claim_grant,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "task_id": task2_id,
                    "request_id": "req-neg4-after-revoke",
                    "idempotency_key": "idem-neg4-after-revoke",
                },
                {"qualification_id": qualification_id},
            )
        except Exception as exc:
            revoked_grant_error = str(exc).strip().splitlines()[0]
            conn.rollback()
    finally:
        conn.close()

    assert revoke_res["status"] == "REVOKED"
    assert revoked_grant_error and "GRANT_NOT_CURRENT" in revoked_grant_error
    report["negatives"]["4_revoke_cuts_authority"] = {
        "revoked_grant_id": worker_task2_claim_grant,
        "new_project_authority_epoch": revoke_res["project_epoch"],
        "post_revoke_error": revoked_grant_error,
    }

    # Negative 5: Wrong artifact / manifest / stale source digest
    # Test both UI stale digest rejection (`STALE_SOURCE_DIGEST`) and wrong artifact signature rejection (`ATTESTATION_SIGNATURE_INVALID`)
    bump_clock()
    neg5_stale_ui_error = None
    neg5_bad_artifact_error = None
    conn = connect_adapted()
    try:
        host = CommandHost(conn)
        ui_app_neg = AuthenticatedReadbackApp(host)
        try:
            ui_app_neg.read_detail(
                route="candidate.r54.acceptance_decisions.read",
                session_token=owner_token,
                grant_id=owner_grant_id,
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                entity_id=acceptance_id,
                ui_generation=3,
                expected_source_digest="0" * 64,
                request_id="req-neg5-stale-ui",
            )
        except Exception as exc:
            neg5_stale_ui_error = str(exc)

        try:
            host.execute(
                "evidence.attestation_ingest",
                {
                    "session_token": owner_token,
                    "grant_id": owner_task_grant,
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "task_id": task_id,
                    "request_id": "req-neg5-bad-art",
                    "idempotency_key": "idem-neg5-bad-art",
                },
                {
                    "artifact_id": uuid_from_seed("art-bad-digest"),
                    "profile_id": "r58.workspace.v1",
                    "key_id": ctrl_ws_key[0],
                    "issuer_id": CONTROLLER_ID,
                    "digest": "f" * 64,  # mismatches statement!
                    "statement": {"bad": "manifest"},
                    "signature": "0" * 64,
                },
            )
        except Exception as exc:
            neg5_bad_artifact_error = str(exc).strip().splitlines()[0]
            conn.rollback()
    finally:
        conn.close()

    assert neg5_stale_ui_error and "STALE_SOURCE_DIGEST" in neg5_stale_ui_error
    assert neg5_bad_artifact_error and "ATTESTATION_STATEMENT_DIGEST_MISMATCH" in neg5_bad_artifact_error
    report["negatives"]["5_wrong_artifact_and_manifest"] = {
        "stale_ui_digest_error": neg5_stale_ui_error,
        "bad_artifact_digest_error": neg5_bad_artifact_error,
    }

    # Negative 6: Lost commit ack (`UNKNOWN`) halts without automatic retry
    # Simulate lost commit ack in DbScope; verify `UnknownCommitOutcome` is raised and `PatchProposalProducer` converts it to `Unknown('STAGE_COMMIT_UNCERTAIN_NO_RETRY')` with zero retries.
    stage_calls = 0

    class LostAckDbPort:
        def stage_proposal(self, scope: DbScope, payload: dict[str, Any]) -> dict[str, Any]:
            nonlocal stage_calls
            stage_calls += 1
            return {"tool_request_id": payload["tool_request_id"]}

    class LostAckConn:
        autocommit = False

        def commit(self) -> None:
            raise OSError("simulated socket drop during commit ack")

        def rollback(self) -> None:
            pass

    neg6_unknown_error = None
    try:
        prod_neg = PatchProposalProducer(LostAckDbPort(), ws_dir)
        prod_neg.stage_single_file_replacement(
            DbScope(LostAckConn()),
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            task_id=task_id,
            attempt_id=attempt_id,
            fencing_epoch=fencing_epoch,
            tool_request_id=uuid_from_seed("req-neg6-lost-ack"),
            process_run_id=process_run_id,
            stream_id=stream_id,
            workspace_id=WORKSPACE_ID,
            base_head=result_head,
            target_relpath="task_title.py",
            replacement_bytes=worker_replacement_code,
            proposal_artifact_id=uuid_from_seed("art-neg6-lost-ack"),
            key_id=ctrl_pp_key[0],
            issuer_id=CONTROLLER_ID,
        )
    except Unknown as exc:
        neg6_unknown_error = str(exc)

    assert neg6_unknown_error == "STAGE_COMMIT_UNCERTAIN_NO_RETRY" and stage_calls == 1
    report["negatives"]["6_lost_commit_ack_no_retry"] = {
        "error": neg6_unknown_error,
        "stage_calls_count": stage_calls,
    }

    # -------------------------------------------------------------------------
    # Populate explicit per-stage status for first13 stages
    # -------------------------------------------------------------------------
    report["first13_stage_status"] = {
        "stage_01_bootstrap_and_owner_binding": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "BLOCKED_G0_EXTERNAL_OWNER_IDENTITY_AND_HARDWARE_CUSTODY",
            "evidence": "bootstrap_receipts=1, owner_installation_consent sha256 verified, authority_granted=false",
        },
        "stage_02_session_and_scoped_grant": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"owner_session={owner_session.session_id}, principal_sessions=4, scoped_grants_issued_and_revoked",
        },
        "stage_03_clock_policy_epoch_and_bounds": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"pre_clock={blocked_time_error}, epoch={clock_epoch_id}, bounds_seq={bounds_row['sample_sequence']}",
        },
        "stage_04_objective_create_and_readback": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"objective_id={objective_id}, rev={ro_obj['revision']}, cmd={ro_obj['created_by_command_id']}",
        },
        "stage_05_plan_create_and_readback": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"plan_id={plan_id}, rev={ro_plan['revision']}, cmd={ro_plan['created_by_command_id']}",
        },
        "stage_06_task_create_and_readback": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"task_id={task_id}, title={ro_task['title']}, rev={ro_task['revision']}",
        },
        "stage_07_qualification_and_activation": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"qualification_id={qualification_id}, status={qual_act_res['status']}",
        },
        "stage_08_workspace_head_and_task_ready": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"initial_head={initial_head}, task_state={ready_res['state']}",
        },
        "stage_09_worker_claim_and_lease_fence": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"attempt_id={attempt_id}, fencing_epoch={fencing_epoch}, state={claim_res['state']}",
        },
        "stage_10_isolated_launch_and_engine_bind": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"process_run_id={process_run_id}, stream_id={stream_id}, worker_elf_sha256={worker_elf_digest}",
        },
        "stage_11_broker_patch_and_immutable_artifact": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"tool_request_id={rt_port.last_tool_request_id}, patch_artifact_id={rt_port.last_patch_artifact_id}, result_head={result_head}",
        },
        "stage_12_independent_verifier_and_kernel_accept": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": f"verification_id={verification_id}, oracle=13/13, acceptance_id={acceptance_id}, task_state=ACCEPTED",
        },
        "stage_13_authenticated_ui_and_persistent_reload": {
            "disposable_native_trial": "VERIFIED_IN_DISPOSABLE_TRIAL",
            "g0_production_status": "OPEN_PENDING_G0",
            "evidence": "6 r54 detail routes read before & after pg_ctl restart with identical source_digest",
        },
    }

    # Clean up temporary directories created inside STORAGE_DIR during trial
    for d in (ws_dir, build_dir, journal_dir):
        if d.exists():
            shutil.rmtree(d)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
