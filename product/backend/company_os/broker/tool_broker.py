"""Bound company-tool/1 broker candidate. No default DB/OS implementation.

Kernel must durably consume once and hold revocation locks across effect_scope.
Journal must durably reserve O_EXCL before effect. Neither is an engine object.
Missing adapters cannot yield OK. Independent verification is a separate service.
"""

import hashlib
from uuid import UUID

from packages.contracts.execution import ToolReply, parse_tool_request


class RecoveryRequired(RuntimeError):
    pass


class Broker:
    def __init__(
        self,
        *,
        binding,
        kernel,
        journal,
        executor,
        allowed_read_paths: frozenset[str] = frozenset({"task_title.py"}),
    ):
        self.binding = binding.model_copy(deep=True)
        self.kernel = kernel
        self.journal = journal
        self.executor = executor
        self.allowed_read_paths = frozenset(allowed_read_paths)
        self.sequence = 1
        self.halted = False

    def handle(self, frame, *, channel):
        if self.halted:
            raise RecoveryRequired("STREAM_HALTED_RECONCILE_REQUIRED")
        try:
            request = parse_tool_request(
                frame, binding=self.binding, expected_sequence=self.sequence, channel=channel
            )
        except Exception:
            self.halted = True
            raise RecoveryRequired("INVALID_ENGINE_FRAME_STREAM_HALTED") from None

        def reply(status, receipt=None, artifacts=None, error=None):
            return ToolReply(
                protocol="company-tool/1",
                request_id=request.request_id,
                status=status,
                receipt_id=receipt,
                artifact_ids=artifacts or [],
                error_code=error,
            )

        # Only the first pilot's named source file is readable; no shell or verifier proxy.
        if request.call.tool_id == "verification.request":
            self.halted = True
            return reply("DENIED", error="INDEPENDENT_VERIFIER_ROUTE_REQUIRED")
        if (
            request.call.tool_id == "workspace.read"
            and request.call.arguments.relative_path not in self.allowed_read_paths
        ):
            self.halted = True
            return reply("DENIED", error="PILOT_PATH_OUT_OF_SCOPE")
        digest = hashlib.sha256(frame).hexdigest()
        # Even a lost consume acknowledgement may have committed. Halt, never retry.
        try:
            permit = self.kernel.consume(request, frame_digest=digest, frame=frame)
            if (
                type(permit) is not dict
                or permit.get("effect_permitted") is not True
                or permit.get("frame_digest") != digest
            ):
                self.halted = True
                return reply("UNKNOWN_RECOVERY", error="NO_FRESH_ONE_USE_PERMISSION")
            consume_id = UUID(str(permit["consume_id"]))
            # The local durable ledger is additional protection; it cannot replace DB CAS.
            self.journal.reserve(
                str(consume_id), {"frame_digest": digest, "request_id": str(request.request_id)}
            )
            with self.kernel.effect_scope(consume_id, request, frame_digest=digest) as transaction:
                result = self.executor.execute(request.call, transaction=transaction)
                # complete() records signed effect proof + receipt in the same transaction.
                receipt = transaction.complete(consume_id, result)
                if (
                    type(receipt) is not dict
                    or receipt.get("status") != "SUCCEEDED"
                    or receipt.get("consume_id") != str(consume_id)
                    or receipt.get("frame_digest") != digest
                ):
                    raise RecoveryRequired("CANONICAL_EFFECT_RECEIPT_REQUIRED")
                receipt_id = UUID(str(receipt["receipt_id"]))
                artifacts = [UUID(str(x)) for x in receipt.get("artifact_ids", [])]
                answer = reply("OK", receipt_id, artifacts)
            # Context exit must confirm COMMIT before any engine-visible OK.
            if request.call.tool_id == "patch.apply":
                self.kernel.finalize_patch(transaction)
            self.sequence += 1
            return answer
        except Exception:
            self.halted = True
            return reply("UNKNOWN_RECOVERY", error="EFFECT_OUTCOME_RECONCILIATION_REQUIRED")


class Unknown(RuntimeError):
    pass
