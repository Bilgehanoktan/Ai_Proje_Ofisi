"""Bound patch staging/reading/recording. No DB or OS work on import."""

import base64
import copy
import hashlib
from contextlib import contextmanager
from uuid import UUID, uuid4

from company_os.broker.tool_executor import replacement
from company_os.kernel import command_host as host
from company_os.kernel.execution_protocol import Denied, Unknown, canonical, exact
from company_os.kernel.kernel_adapters import (
    EffectTransaction as BaseTransaction,
)
from company_os.kernel.kernel_adapters import (
    ToolKernel as BaseKernel,
)


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def b64(raw):
    return base64.b64encode(raw).decode("ascii")


def bounded_source(raw):
    if type(raw) is not bytes or len(raw) > 16384 or b"\0" in raw:
        raise Denied("BOUNDED_UTF8_SOURCE_REQUIRED")
    raw.decode("utf-8")
    return raw


class PatchProposalProducer:
    """Trusted supervisor adapter signs provenance, never claims code correctness.

    source_snapshot supplies supervisor-measured bytes/head, not model assertions.
    One staged proposal is bound to exactly one request and stream sequence.
    """

    def __init__(self, *, connect, controller_auth, signer, binding, process_id, source_snapshot):
        self.connect = connect
        self.auth = dict(controller_auth)
        self.signer = signer
        self.binding = binding.model_copy(deep=True)
        self.process = str(UUID(process_id))
        self.snapshot = source_snapshot
        self.halted = False
        if (
            str(self.auth.get("attempt_id")) != str(binding.attempt_id)
            or self.auth.get("fence") != binding.fencing_epoch
        ):
            raise Denied("STAGING_ATTEMPT_BINDING")

    def frame(self, replacement_bytes, *, sequence):
        if self.halted:
            raise Unknown("STAGING_HALTED_NO_RETRY")
        bounded_source(replacement_bytes)
        if type(sequence) is not int or sequence < 1:
            raise Denied("SEQUENCE_REQUIRED")
        snapshot = self.snapshot()
        exact(snapshot, {"head_digest", "source_bytes"})
        head = snapshot["head_digest"]
        base = bounded_source(snapshot["source_bytes"])
        if (
            type(head) is not str
            or len(head) != 64
            or any(c not in "0123456789abcdef" for c in head)
        ):
            raise Denied("MEASURED_HEAD_REQUIRED")
        raw = canonical(
            dict(
                format="company.replace-file/1",
                path="task_title.py",
                base_content_digest=digest_bytes(base),
                replacement_base64=b64(replacement_bytes),
            )
        )
        if len(raw) > 32768:
            raise Denied("PATCH_ARTIFACT_LIMIT")
        request = str(uuid4())
        payload = dict(
            task_id=self.auth["task_id"],
            attempt_id=str(self.binding.attempt_id),
            fencing_epoch=self.binding.fencing_epoch,
            process_id=self.process,
            engine_session_id=str(self.binding.engine_session_id),
            tool_manifest_digest=self.binding.tool_manifest_digest,
            sequence=sequence,
            request_id=request,
            expected_source_digest=head,
            artifact_digest=digest_bytes(raw),
            artifact_base64=b64(raw),
        )
        proof, statement, tag = self.signer.sign("r60.patch-proposal.v1", payload)
        try:
            envelope = host.execute(
                self.connect(),
                self.auth,
                "evidence.attestation_ingest",
                [
                    proof,
                    str(self.signer.issuer),
                    str(self.signer.key_id),
                    self.signer.revision,
                    "r60.patch-proposal.v1",
                    statement,
                    tag,
                    "r65-proposal:" + proof,
                    str(uuid4()),
                ],
            )
            if (
                type(envelope.get("command_receipt")) is not dict
                or envelope["command_receipt"].get("state") != "SUCCEEDED"
                or envelope["result"].get("receipt_id") != proof
            ):
                raise Denied("COMMITTED_PROPOSAL_REQUIRED")
        except Exception:
            self.halted = True
            raise Unknown("STAGING_OUTCOME_RECONCILE_NO_RETRY") from None
        return (
            canonical(
                dict(
                    protocol="company-tool/1",
                    request_id=request,
                    engine_session_id=str(self.binding.engine_session_id),
                    attempt_id=str(self.binding.attempt_id),
                    fencing_epoch=self.binding.fencing_epoch,
                    expected_revision=self.binding.revision,
                    sequence=sequence,
                    tool_manifest_digest=self.binding.tool_manifest_digest,
                    call=dict(
                        tool_id="patch.apply", patch_artifact_id=proof, expected_source_digest=head
                    ),
                )
            )
            + b"\n"
        )


class PatchEffectTransaction(BaseTransaction):
    def __init__(self, cursor, guard, signer, owner):
        super().__init__(cursor, guard, signer)
        self.owner = owner
        self.active = True
        self.committed = False
        self.patch = None

    def read_patch(self, artifact_id):
        if not self.active or self.used or self.patch is not None:
            raise Denied("ONE_ACTIVE_PATCH_READ_REQUIRED")
        identity = str(UUID(str(artifact_id)))
        self.cur.execute(
            "SELECT company_private.r65_patch_artifact_read(%s::uuid,%s::uuid)",
            (self.guard["consume_id"], identity),
        )
        row = self.cur.fetchone()[0]
        if (
            type(row) is not dict
            or row.get("artifact_id") != identity
            or row.get("consume_id") != self.guard["consume_id"]
            or row.get("frame_digest") != self.guard["frame_digest"]
            or row.get("kind") != "BOUND_PATCH_PROPOSAL_NOT_VERIFICATION"
        ):
            raise Denied("BOUND_PATCH_READBACK_REQUIRED")
        raw = base64.b64decode(row["content_base64"], validate=True)
        base, data = replacement(raw, row["sha256"])
        if row.get("base_content_digest") != base or row.get(
            "replacement_content_digest"
        ) != digest_bytes(data):
            raise Denied("PATCH_CONTENT_READBACK_REQUIRED")
        self.patch = dict(sha256=row["sha256"], base=base, result=digest_bytes(data))
        return dict(raw=raw, sha256=row["sha256"])

    def require_current(self):
        if not self.active or self.used:
            raise Denied("ACTIVE_UNUSED_EFFECT_REQUIRED")
        self.cur.execute(
            "SELECT company_private.r65_effect_guard(%s::uuid)", (self.guard["consume_id"],)
        )
        if self.cur.fetchone()[0] != self.guard:
            raise Denied("EFFECT_GUARD_CHANGED")

    def complete(self, consume_id, result):
        if not self.active:
            raise Denied("ACTIVE_EFFECT_TRANSACTION_REQUIRED")
        if result.get("kind") == "PATCH" and (
            self.patch is None
            or result.get("patch_digest") != self.patch["sha256"]
            or result.get("base_content_digest") != self.patch["base"]
            or result.get("result_content_digest") != self.patch["result"]
        ):
            raise Denied("EXACT_READ_PATCH_EFFECT_REQUIRED")
        self.require_current()
        return super().complete(consume_id, result)


class PatchReceiptRecorder:
    """After confirmed effect COMMIT, record signed patch and transition VERIFYING.

    This uses a separate r58.patch.v1 signer enrollment, not the effect key by
    default. Lost acknowledgements halt and require reconciliation, never replay OS.
    """

    def __init__(self, *, connect, controller_auth, worker_auth, patch_signer):
        self.connect = connect
        self.controller = dict(controller_auth)
        self.worker = dict(worker_auth)
        self.signer = patch_signer
        self.used = False
        self.confirmed = None

    def record(self, transaction):
        if self.used:
            raise Unknown("PATCH_RECORDER_CANNOT_RETRY")
        self.used = True
        g = transaction.guard
        result = transaction.effect_result
        proof = str(uuid4())
        binding = dict(
            task_id=g["task_id"],
            attempt_id=g["attempt_id"],
            fencing_epoch=g["fencing_epoch"],
            base_head=result["base_head"],
            result_head=result["result_head"],
            patch_digest=result["patch_digest"],
            tool_request_id=g["kernel_request_id"],
            process_id=g["process_id"],
            request_digest=g["frame_digest"],
            receipt_artifact_id=proof,
        )
        identity, raw, tag = self.signer.sign("r58.patch.v1", binding, receipt_id=proof)
        envelope = host.execute(
            self.connect(),
            self.controller,
            "evidence.attestation_ingest",
            [
                identity,
                str(self.signer.issuer),
                str(self.signer.key_id),
                self.signer.revision,
                "r58.patch.v1",
                raw,
                tag,
                "r65-patch-proof:" + identity,
                str(uuid4()),
            ],
        )
        if (
            type(envelope.get("command_receipt")) is not dict
            or envelope["command_receipt"].get("state") != "SUCCEEDED"
            or envelope["result"].get("receipt_id") != identity
        ):
            raise Denied("COMMITTED_PATCH_PROOF_REQUIRED")
        envelope = host.execute(
            self.connect(),
            self.worker,
            "patch.receipt",
            [
                g["task_id"],
                g["attempt_id"],
                g["fencing_epoch"],
                identity,
                "r65-patch:" + g["consume_id"],
                str(uuid4()),
            ],
        )
        result = envelope["result"]
        if (
            type(envelope.get("command_receipt")) is not dict
            or envelope["command_receipt"].get("state") != "SUCCEEDED"
            or type(result) is not dict
            or result.get("patch_id") != identity
            or result.get("attestation") != identity
            or result.get("result_head") != transaction.effect_result["result_head"]
            or result.get("patch_digest") != transaction.effect_result["patch_digest"]
        ):
            raise Denied("COMMITTED_PATCH_RECEIPT_REQUIRED")
        self.confirmed = copy.deepcopy(result)
        return copy.deepcopy(result)


class ToolKernel(BaseKernel):
    def __init__(self, *, patch_recorder, **kwargs):
        super().__init__(**kwargs)
        self.patch_recorder = patch_recorder

    @contextmanager
    def effect_scope(self, *args, **kwargs):
        transaction = None
        try:
            with super().effect_scope(*args, **kwargs) as original:
                transaction = PatchEffectTransaction(
                    original.cur, original.guard, original.signer, self
                )
                yield transaction
                transaction.active = False
            transaction.committed = True
        finally:
            if transaction is not None:
                transaction.active = False

    def finalize_patch(self, transaction):
        if (
            transaction.owner is not self
            or not transaction.committed
            or transaction.active
            or not transaction.used
            or getattr(transaction, "recorded", False)
        ):
            raise Denied("ONE_CONFIRMED_EFFECT_COMMIT_REQUIRED")
        transaction.recorded = True
        try:
            return self.patch_recorder.record(transaction)
        except Exception:
            raise Unknown("PATCH_RECORDING_OUTCOME_RECONCILE_NO_OS_RETRY") from None


