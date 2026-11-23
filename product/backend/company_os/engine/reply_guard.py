"""Fresh DB authorization held across each engine reply write."""

from contextlib import contextmanager

from company_os.kernel.execution_protocol import Denied


class EngineReplyGuard:
    def __init__(self, *, scope, binding):
        self.scope = scope
        self.binding = binding.model_copy(deep=True)

    @contextmanager
    def __call__(self, reply):
        if reply.status != "OK" or reply.receipt_id is None:
            raise Denied("SEALED_REPLY_REQUIRED")
        with self.scope.open("candidate.r58.artifacts.read") as cur:
            cur.execute(
                "SELECT company_private.r65_engine_reply_guard(%s::uuid)", (str(reply.receipt_id),)
            )
            row = cur.fetchone()[0]
            if (
                type(row) is not dict
                or row.get("receipt_id") != str(reply.receipt_id)
                or row.get("request_id") != str(reply.request_id)
                or row.get("engine_session_id") != str(self.binding.engine_session_id)
            ):
                raise Denied("EXACT_ENGINE_REPLY_BINDING_REQUIRED")
            yield row
