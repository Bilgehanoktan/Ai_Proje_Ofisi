"""Verifier-side MGT01 evaluation over an explicitly qualified candidate port.

No same-identity subprocess fallback. The enrolled supervisor supplies candidate
resolution, isolated launcher and independent qualification/current readback.
The candidate never supplies totals, checks, expected values or receipts.
"""

import copy
import hashlib
import json
import time
from uuid import UUID, uuid4

from independent_verifier.verifier_runner import (
    CASES,
    ENROLLED_ORACLE_SHA256,
    MAX_CANDIDATE_BYTES,
    MAX_LINE_BYTES,
    ORACLE_ID,
    READY_TIMEOUT_SECONDS,
)

from company_os.kernel.execution_protocol import Denied, Unknown, canonical

EXPECTED_FIELDS = frozenset(
    (
        "task_id",
        "attempt_id",
        "fence",
        "expected_task_revision",
        "patch_id",
        "head_digest",
        "profile_digest",
        "build_digest",
        "acceptance_criteria_digest",
    )
)


def validate_expected(expected):
    if type(expected) is not dict or set(expected) != EXPECTED_FIELDS:
        raise Denied("EXACT_RUNTIME_VERIFICATION_BINDING_REQUIRED")
    for key in ("task_id", "attempt_id", "patch_id"):
        try:
            if type(expected[key]) is not str or str(UUID(expected[key])) != expected[key]:
                raise ValueError()
        except ValueError, TypeError, AttributeError:
            raise Denied("CANONICAL_RUNTIME_VERIFICATION_ID_REQUIRED") from None
    for key in ("fence", "expected_task_revision"):
        if type(expected[key]) is not int or expected[key] < 1:
            raise Denied("EXACT_RUNTIME_VERIFICATION_REVISION_REQUIRED")
    for key in ("head_digest", "profile_digest", "build_digest", "acceptance_criteria_digest"):
        value = expected[key]
        if (
            type(value) is not str
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise Denied("EXACT_RUNTIME_VERIFICATION_DIGEST_REQUIRED")


def _response(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Denied("DUPLICATE_CANDIDATE_RESPONSE_KEY")
            result[key] = value
        return result

    if (
        type(raw) is not bytes
        or len(raw) > MAX_LINE_BYTES
        or not raw.endswith(b"\n")
        or b"\n" in raw[:-1]
    ):
        raise Denied("EXACT_CANDIDATE_RESPONSE_FRAME_REQUIRED")
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(Denied("NONFINITE_CANDIDATE_RESPONSE")),
    )
    if type(value) is not dict:
        raise Denied("EXACT_CANDIDATE_RESPONSE_REQUIRED")
    return value


class RuntimeTitleVerifier:
    def __init__(self, *, resolver, launcher, qualification, timeout=5.0):
        import math

        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise Denied("FINITE_RUNTIME_VERIFIER_TIMEOUT_REQUIRED")
        self.resolver = resolver
        self.launcher = launcher
        self.qualification = qualification
        self.timeout = timeout

    def verify(self, *, expected, deadline=None):
        validate_expected(expected)
        if self.qualification is None:
            raise Denied("ENROLLED_RUNTIME_QUALIFICATION_REQUIRED")
        end = time.monotonic() + self.timeout
        if deadline is not None:
            end = min(end, deadline)

        def left():
            value = end - time.monotonic()
            if value <= 0:
                raise TimeoutError("RUNTIME_VERIFIER_DEADLINE")
            return value

        left()
        artifact = self.resolver.resolve(expected=copy.deepcopy(expected), timeout=left())
        if (
            type(artifact) is not dict
            or set(artifact) != {"expected", "candidate_bytes", "candidate_digest"}
            or artifact["expected"] != expected
            or type(artifact["candidate_bytes"]) is not bytes
            or not 0 < len(artifact["candidate_bytes"]) <= MAX_CANDIDATE_BYTES
            or hashlib.sha256(artifact["candidate_bytes"]).hexdigest()
            != artifact["candidate_digest"]
        ):
            raise Denied("IMMUTABLE_BOUND_CANDIDATE_REQUIRED")
        if (
            self.qualification.validate(
                expected=copy.deepcopy(expected),
                phase="BEFORE_LAUNCH",
                candidate_digest=artifact["candidate_digest"],
                oracle_digest=ENROLLED_ORACLE_SHA256,
            )
            is not True
        ):
            raise Denied("RUNTIME_PROFILE_OR_FIXTURE_NOT_QUALIFIED")
        left()
        session = self.launcher.open(
            candidate_bytes=artifact["candidate_bytes"],
            expected=copy.deepcopy(expected),
            candidate_digest=artifact["candidate_digest"],
            oracle_digest=ENROLLED_ORACLE_SHA256,
            timeout=left(),
        )
        checks = []
        try:
            # This check must authenticate actual OS isolation before candidate I/O.
            if (
                self.qualification.validate(
                    expected=copy.deepcopy(expected),
                    phase="RUNNING",
                    candidate_digest=artifact["candidate_digest"],
                    oracle_digest=ENROLLED_ORACLE_SHA256,
                    session=session,
                )
                is not True
            ):
                raise Denied("ACTUAL_CANDIDATE_ISOLATION_REQUIRED")
            if session.read_line(timeout=min(left(), READY_TIMEOUT_SECONDS), max_bytes=256) not in (
                b"READY\n",
                b"READY\r\n",
            ):
                raise Denied("RUNTIME_CANDIDATE_READY_REQUIRED")
            for case_id, value, wanted, error in CASES:
                request_id = uuid4().hex
                session.write_line(
                    canonical(dict(id=request_id, value=value)) + b"\n", timeout=left()
                )
                response = _response(
                    session.read_line(timeout=min(left(), 1.0), max_bytes=MAX_LINE_BYTES)
                )
                if response.get("id") != request_id:
                    raise Denied("EXACT_CANDIDATE_RESPONSE_ID_REQUIRED")
                if response.get("status") == "SUCCESS" and set(response) == {
                    "id",
                    "status",
                    "value",
                }:
                    passed = (
                        error is None
                        and type(response["value"]) is type(wanted)
                        and response["value"] == wanted
                    )
                elif response.get("status") == "ERROR" and set(response) == {
                    "id",
                    "status",
                    "error_type",
                }:
                    passed = error is not None and response["error_type"] == error
                else:
                    raise Denied("EXACT_CANDIDATE_RESPONSE_SCHEMA_REQUIRED")
                checks.append(dict(id=case_id, result="PASS" if passed else "FAIL"))
            finished = session.finish(timeout=left())
            if (
                type(finished) is not dict
                or set(finished)
                != {"exit_code", "stdout_eof", "stderr_bytes", "trailing_stdout_bytes"}
                or type(finished["exit_code"]) is not int
                or finished["exit_code"] != 0
                or finished["stdout_eof"] is not True
                or type(finished["stderr_bytes"]) is not int
                or not 0 <= finished["stderr_bytes"] <= 16384
                or type(finished["trailing_stdout_bytes"]) is not int
                or finished["trailing_stdout_bytes"] != 0
            ):
                raise Denied("EXACT_CANDIDATE_EXIT_AND_OUTPUT_RECEIPT_REQUIRED")
        finally:
            try:
                session.close()
            except Exception:
                raise Unknown("VERIFIER_CANDIDATE_CLEANUP_UNCONFIRMED") from None
        if (
            self.qualification.validate(
                expected=copy.deepcopy(expected),
                phase="STOPPED",
                candidate_digest=artifact["candidate_digest"],
                oracle_digest=ENROLLED_ORACLE_SHA256,
                session=session,
            )
            is not True
        ):
            raise Denied("INDEPENDENT_VERIFIER_QUIESCENCE_REQUIRED")
        left()
        passed = sum(row["result"] == "PASS" for row in checks)
        report = dict(
            oracle_id=ORACLE_ID,
            oracle_sha256=ENROLLED_ORACLE_SHA256,
            execution_class="ACTUAL_RUNTIME",
            acceptance_eligible=True,
            candidate_sha256=artifact["candidate_digest"],
            expected=copy.deepcopy(expected),
            checks=checks,
            passed=passed,
            total=len(CASES),
            outcome="PASS" if passed == len(CASES) else "FAIL",
        )
        report["report_digest"] = hashlib.sha256(canonical(report)).hexdigest()
        return report
