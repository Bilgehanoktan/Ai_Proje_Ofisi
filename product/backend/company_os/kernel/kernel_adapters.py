"""Enrolled DB-API adapters. Construction/import opens no connection."""

import base64
import hashlib
import hmac
import json
from contextlib import contextmanager
from uuid import uuid4

from company_os.kernel import command_host as host
from company_os.kernel.execution_protocol import Denied, Unknown, canonical


def committed_launch_ticket(
    *, connect, auth, args, codec, audience, clock, ticket_window_ns=5000000000
):
    if type(ticket_window_ns) is not int or not 1 <= ticket_window_ns <= 5000000000:
        raise Denied("BOUNDED_TICKET_WINDOW_REQUIRED")
    envelope = host.execute(connect(), auth, "process.launch_consume", args)
    result = envelope["result"]
    if result.get("spawn_permitted") is not True:
        raise Denied("REPLAY_CANNOT_ISSUE_LAUNCH_TICKET")
    t = result["tuple"]
    for key in ["controller_id", "controller_generation", "host_boot_id"]:
        if audience.get(key) != t[key]:
            raise Denied("EXACT_TICKET_AUDIENCE_REQUIRED")
    now = clock()
    expires = min(t["not_after_boottime_ns"], now + ticket_window_ns)
    if now >= expires:
        raise Denied("COMMITTED_CAPABILITY_EXPIRED_BEFORE_DELIVERY")
    return codec.seal_after_commit(
        envelope=envelope, delivery_id=str(uuid4()), audience=audience, expires_boottime_ns=expires
    )


class ProofSigner:
    def __init__(self, *, issuer_id, key_id, revision, key, tenant_id, project_id):
        if type(key) is not bytes or len(key) != 32:
            raise Denied("ENROLLED_PROOF_SECRET_REQUIRED")
        self.issuer = issuer_id
        self.key_id = key_id
        self.revision = revision
        self.key = key
        self.tenant = tenant_id
        self.project = project_id

    def sign(self, profile, binding, *, receipt_id=None):
        from uuid import UUID

        receipt = str(uuid4()) if receipt_id is None else str(UUID(receipt_id))
        if receipt_id is not None and receipt != receipt_id:
            raise Denied("CANONICAL_RECEIPT_ID_REQUIRED")
        raw = canonical(
            dict(
                tenant_id=self.tenant,
                project_id=self.project,
                receipt_id=receipt,
                profile=profile,
                binding=binding,
            )
        )
        parts = [
            str(self.issuer).encode(),
            str(self.key_id).encode(),
            str(self.revision).encode(),
            profile.encode(),
            raw,
        ]
        msg = b"R58-EXECUTION-ATTESTATION-v1\0" + b"".join(
            str(len(x)).encode() + b":" + x for x in parts
        )
        return receipt, raw, hmac.new(self.key, msg, "sha256").digest()


class DbScope:
    def __init__(self, connect, auth, timeout_ms=2000):
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
            raise Denied("BOUNDED_DB_SCOPE_REQUIRED")
        self.connect = connect
        self.auth = dict(auth)
        self.timeout = timeout_ms

    @contextmanager
    def open(self, operation):
        c = self.connect()
        committing = False
        try:
            if int(c.info.transaction_status) != 0:
                raise Denied("IDLE_DEDICATED_CONNECTION_REQUIRED")
            with c.cursor() as cur:
                cur.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
                cur.execute(
                    "SELECT set_config('statement_timeout',%s,true)", (str(self.timeout) + "ms",)
                )
                cur.execute(
                    "SELECT set_config('idle_in_transaction_session_timeout',%s,true)",
                    (str(self.timeout) + "ms",),
                )
                nonce = host.enter(cur, self.auth, operation)
                yield cur
                cur.execute("SELECT company_private.r55_cp_context_exit(%s::uuid)", (nonce,))
            committing = True
            c.commit()
            committing = False
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
            if committing:
                raise Unknown("UNKNOWN_SCOPE_COMMIT_NO_RETRY") from None
            raise
        finally:
            c.close()


class DeliveryGuard:
    def __init__(self, scope):
        self.scope = scope

    @contextmanager
    def __call__(self, ticket):
        with self.scope.open("process.launch_delivery") as cur:
            cur.execute(
                "SELECT company_private.r60_delivery_guard(%s::uuid,%s::uuid,%s::jsonb)",
                (
                    ticket["result"]["capability_id"],
                    ticket["command_receipt"]["command_id"],
                    json.dumps(ticket["snapshot"], allow_nan=False),
                ),
            )
            value = cur.fetchone()[0]
            if type(value) is not dict:
                raise Denied("CANONICAL_DELIVERY_READBACK_REQUIRED")
            yield value


class ToolKernel:
    def __init__(self, *, connect, worker_auth, controller_scope, process_id, signer):
        self.connect = connect
        self.worker_auth = dict(worker_auth)
        self.scope = controller_scope
        self.process = process_id
        self.signer = signer

    def consume(self, request, *, frame_digest, frame):
        if hashlib.sha256(frame).hexdigest() != frame_digest:
            raise Denied("RAW_FRAME_DIGEST")
        key = str(request.request_id)
        corr = str(uuid4())
        auth = host.execute(
            self.connect(),
            self.worker_auth,
            "tool.authorize_final",
            [
                self.worker_auth["task_id"],
                str(request.attempt_id),
                request.fencing_epoch,
                self.process,
                request.call.tool_id,
                frame_digest,
                "r60-auth:" + key,
                corr,
            ],
        )["result"]
        return host.execute(
            self.connect(),
            self.worker_auth,
            "tool.consume",
            [auth["request_id"], frame, "r60-consume:" + key, corr],
        )["result"]

    @contextmanager
    def effect_scope(self, consume_id, request, *, frame_digest):
        with self.scope.open("tool.effect") as cur:
            cur.execute("SELECT company_private.r65_effect_guard(%s::uuid)", (str(consume_id),))
            guard = cur.fetchone()[0]
            if (
                type(guard) is not dict
                or guard.get("frame_digest") != frame_digest
                or guard.get("process_id") != self.process
                or type(guard.get("frame_base64")) is not str
            ):
                raise Denied("CANONICAL_EFFECT_GUARD")
            # PostgreSQL encode(..., 'base64') inserts '\n' every 76 chars; normalize without mutating guard.
            raw = base64.b64decode(guard["frame_base64"].replace("\n", ""), validate=True)
            if hashlib.sha256(raw).hexdigest() != frame_digest or json.loads(
                raw
            ) != request.model_dump(mode="json"):
                raise Denied("EXACT_STORED_FRAME_REQUIRED")
            yield EffectTransaction(cur, guard, self.signer)


class EffectTransaction:
    def __init__(self, cursor, guard, signer):
        self.cur = cursor
        self.guard = guard
        self.signer = signer
        self.used = False

    def complete(self, consume_id, result):
        if self.used or str(consume_id) != self.guard["consume_id"]:
            raise Denied("ONE_EFFECT_COMPLETION_ONLY")
        self.used = True
        self.effect_result = result.copy()
        if result["kind"] == "PATCH":
            head = result["result_head"]
            effect_digest = result["patch_digest"]
            base = result["base_head"]
        elif result["kind"] == "READ":
            head = result["head_digest"]
            effect_digest = result["content_digest"]
            base = head
        else:
            raise Denied("BOUNDED_EFFECT_KIND_REQUIRED")
        if base != self.guard["base_head"]:
            raise Denied("EFFECT_SOURCE_HEAD_CHANGED")
        binding = dict(
            consume_id=str(consume_id),
            frame_digest=self.guard["frame_digest"],
            process_id=self.guard["process_id"],
            base_head=base,
            result_head=head,
            effect_digest=effect_digest,
            outcome="SUCCEEDED",
            effect=result,
        )
        proof, raw, tag = self.signer.sign("r60.tool-effect.v1", binding)
        self.cur.execute(
            "SELECT company_private.r60_effect_finish(%s::uuid,%s::uuid,%s::uuid,%s::bigint,%s::bytea,%s::bytea,%s::text,%s::uuid)",
            (
                str(consume_id),
                proof,
                str(self.signer.key_id),
                self.signer.revision,
                raw,
                tag,
                "r60-effect:" + str(consume_id),
                str(uuid4()),
            ),
        )
        row = self.cur.fetchone()[0]
        if (
            type(row) is not dict
            or row.get("state") != "SUCCEEDED"
            or type(row.get("result_payload")) is not dict
        ):
            raise Denied("SEALED_EFFECT_RESULT_REQUIRED")
        self.effect_receipt = row["result_payload"]
        return self.effect_receipt


class LeaseCoordinator:
    """No retries: phase uncertainty requires independent reconciliation."""

    def __init__(self, *, connect, auth, bridge):
        self.connect = connect
        self.auth = dict(auth)
        self.bridge = bridge

    def execute(self, operation, args):
        return host.execute(self.connect(), self.auth, operation, args)["result"]

    def ingest(self, proof, signer, profile):
        id, raw, tag = proof
        self.execute(
            "evidence.attestation_ingest",
            [
                id,
                str(signer.issuer),
                str(signer.key_id),
                signer.revision,
                profile,
                raw,
                tag,
                "r60-attest:" + id,
                str(uuid4()),
            ],
        )
        return id

    def extend(self, process_id, expected_revision):
        try:
            proposal = self.execute(
                "process.lease_prepare",
                [process_id, expected_revision, "r60-prepare:" + str(uuid4()), str(uuid4())],
            )
            prepared = self.bridge.prepare(proposal)
            proof = self.ingest(prepared, self.bridge.prepared_signer, "r60.lease-prepared.v1")
            extension = proposal["extension_id"]
            self.execute(
                "process.lease_commit", [extension, proof, "r60-commit:" + extension, str(uuid4())]
            )
            # bridge independently calls process.lease_read before activating watchdog.
            active = self.bridge.activate()
            proof = self.ingest(active, self.bridge.active_signer, "r60.lease-active.v1")
            return self.execute(
                "process.lease_activate",
                [extension, proof, "r60-active:" + extension, str(uuid4())],
            )
        except Exception:
            raise Unknown("LEASE_HANDSHAKE_OUTCOME_RECONCILE_NO_RETRY") from None
