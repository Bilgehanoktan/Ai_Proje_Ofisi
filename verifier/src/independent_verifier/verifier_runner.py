"""MGT01 source-test harness and fail-closed runtime boundary.

Local candidates run as the same OS identity: SOURCE_TEST is never independent
verification evidence. Runtime execution stays denied until the enrolled
isolated launcher, hidden fixture and exact build/profile binding are connected.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from company_os.kernel import command_host as host
from company_os.kernel.execution_protocol import Denied

from independent_verifier.bounded_candidate import BoundedCandidate, CandidateProtocolError

ORACLE_ID = "mgt01.check_title.13cases.v1"
ENROLLED_ORACLE_SHA256 = "f43559258b69a6e0a502def4475d0ebd8832de8c185d3bb8ab841bc91d3e6c75"
MAX_LINE_BYTES = 4096
TOTAL_MAX_OUTPUT_BYTES = 65536
MAX_STDERR_BYTES = 16384
MAX_CANDIDATE_BYTES = 1048576
TOTAL_TIMEOUT_SECONDS = 5.0
READY_TIMEOUT_SECONDS = 2.0

CASES = [
    ("plain", "Görev", "Görev", None),
    ("trim", "  Görev  ", "Görev", None),
    ("collapse", "Yeni   görev", "Yeni görev", None),
    ("mixed", " \tYeni\n\tgörev  ", "Yeni görev", None),
    ("unicode", "  İŞ   ıslahı  ", "İŞ ıslahı", None),
    ("nbsp", "a\u00a0\u00a0b", "a b", None),
    ("empty", "", None, "ValueError"),
    ("only_space", " \t\n", None, "ValueError"),
    ("wrong_type", None, None, "TypeError"),
    ("numeric", 7, None, "TypeError"),
    ("boundary", "a" * 120, "a" * 120, None),
    ("too_long", "a" * 121, None, "ValueError"),
    ("normalized_length", "a" + " " * 121 + "b", "a b", None),
]

EXPECTED_CASE_IDS = {c[0] for c in CASES}


def run_title_oracle(candidate_path: Path, oracle_path: Path) -> dict:
    """Runtime entry: a local same-identity process cannot establish isolation."""
    raise Denied("ENROLLED_ISOLATED_VERIFIER_REQUIRED")


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CandidateProtocolError("DUPLICATE_RESPONSE_KEY")
        result[key] = value
    return result


def run_source_title_oracle(candidate_path: Path, oracle_path: Path) -> dict:
    """Run trusted repository test samples locally, never arbitrary runtime input.

    Its PASS is ineligible for Kernel acceptance. This helper intentionally has
    no security isolation and must not replace the runtime entry point.
    """
    candidate_path = Path(candidate_path).resolve()
    oracle_path = Path(oracle_path).resolve()
    if not candidate_path.is_file() or not oracle_path.is_file():
        raise Denied("ORACLE_OR_CANDIDATE_MISSING")
    # Stage the exact bytes measured here; do not execute a changed candidate path.
    with candidate_path.open("rb") as source:
        candidate_bytes = source.read(MAX_CANDIDATE_BYTES + 1)
    with oracle_path.open("rb") as source:
        oracle_bytes = source.read(MAX_CANDIDATE_BYTES + 1)
    if len(candidate_bytes) > MAX_CANDIDATE_BYTES or len(oracle_bytes) > MAX_CANDIDATE_BYTES:
        raise Denied("VERIFIER_SOURCE_BYTE_LIMIT")
    oracle_sha256 = hashlib.sha256(oracle_bytes).hexdigest()
    if oracle_sha256 != ENROLLED_ORACLE_SHA256:
        raise Denied("UNPINNED_ORACLE_REJECTED")
    runner_path = Path(__file__).resolve().parent / "candidate_runner.py"
    harness_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    clean_env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    clean_env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    results = {cid: "FAIL" for cid in sorted(EXPECTED_CASE_IDS)}
    failure = None
    process = None
    import tempfile

    # This staging directory pins bytes; it is explicitly NOT a security sandbox.
    with tempfile.TemporaryDirectory(prefix="mgt01-source-") as folder:
        staged = Path(folder) / "candidate.py"
        staged.write_bytes(candidate_bytes)
        try:
            process = BoundedCandidate(
                [sys.executable, "-I", "-B", str(runner_path), str(staged)],
                cwd=folder,
                env=clean_env,
                timeout=TOTAL_TIMEOUT_SECONDS,
                max_line_bytes=MAX_LINE_BYTES,
                max_output_bytes=TOTAL_MAX_OUTPUT_BYTES,
                max_stderr_bytes=MAX_STDERR_BYTES,
            )
            if process.read_line(timeout=READY_TIMEOUT_SECONDS, max_bytes=256) not in (
                b"READY\n",
                b"READY\r\n",
            ):
                raise CandidateProtocolError("INVALID_READY")
            for cid, value, expected_value, expected_error in CASES:
                request_id = uuid4().hex
                request = (
                    json.dumps({"id": request_id, "value": value}, ensure_ascii=True).encode(
                        "utf-8"
                    )
                    + b"\n"
                )
                process.write_line(request)
                raw = process.read_line(timeout=1.0)
                response = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_unique_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        CandidateProtocolError("NONFINITE_JSON")
                    ),
                )
                if type(response) is not dict or response.get("id") != request_id:
                    raise CandidateProtocolError("EXACT_RESPONSE_ID_REQUIRED")
                if response.get("status") == "SUCCESS":
                    if set(response) != {"id", "status", "value"}:
                        raise CandidateProtocolError("EXACT_SUCCESS_SCHEMA_REQUIRED")
                    passed = (
                        expected_error is None
                        and type(response["value"]) is type(expected_value)
                        and response["value"] == expected_value
                    )
                elif response.get("status") == "ERROR":
                    if (
                        set(response) != {"id", "status", "error_type"}
                        or type(response["error_type"]) is not str
                    ):
                        raise CandidateProtocolError("EXACT_ERROR_SCHEMA_REQUIRED")
                    passed = expected_error is not None and response["error_type"] == expected_error
                else:
                    raise CandidateProtocolError("UNKNOWN_RESPONSE_STATUS")
                results[cid] = "PASS" if passed else "FAIL"
            process.finish()
        except TimeoutError, CandidateProtocolError, OSError, ValueError, TypeError:
            # Fail the whole protocol on transport failure, not just the last case.
            failure = "CANDIDATE_PROTOCOL_FAILED"
            results = {cid: "FAIL" for cid in sorted(EXPECTED_CASE_IDS)}
        finally:
            if process is not None:
                process.close()
    checks = [{"id": cid, "result": result} for cid, result in results.items()]
    passed = sum(c["result"] == "PASS" for c in checks)
    report = {
        "oracle_id": ORACLE_ID,
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "oracle_sha256": oracle_sha256,
        "harness_sha256": harness_sha256,
        "runner_sha256": runner_sha256,
        "execution_class": "SOURCE_TEST",
        "acceptance_eligible": False,
        "isolation": "NOT_ESTABLISHED",
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "outcome": "PASS" if passed == len(EXPECTED_CASE_IDS) else "FAIL",
        "failure": failure,
    }
    raw = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    report["report_digest"] = hashlib.sha256(raw).hexdigest()
    return report


class IndependentVerificationPipeline:
    """Producer ve controller'dan ayrı verifier_id, evidence_issuer_id ve human_id."""

    def __init__(
        self,
        *,
        connect,
        verifier_auth,
        verifier_signer,
        evidence_auth,
        evidence_signer,
        human_auth,
        receipt_validator=None,
    ):
        if (
            len(
                {
                    verifier_signer.issuer,
                    evidence_signer.issuer,
                }
            )
            != 2
        ):
            raise Denied("DISTINCT_VERIFIER_AND_EVIDENCE_ISSUERS_REQUIRED")
        self.connect = connect
        self.verifier_auth = dict(verifier_auth)
        self.verifier_signer = verifier_signer
        self.evidence_auth = dict(evidence_auth)
        self.evidence_signer = evidence_signer
        self.human_auth = dict(human_auth)
        # Trusted supervisor dependency, never provided by candidate/report data.
        # No enrolled runtime implementation is configured by this module.
        self.receipt_validator = receipt_validator

    def seal_and_accept(
        self,
        *,
        task_id: str,
        attempt_id: str,
        fence: int,
        expected_task_revision: int,
        patch_id: str,
        head_digest: str,
        profile_digest: str,
        build_digest: str,
        acceptance_criteria_digest: str,
        oracle_report: dict,
    ) -> dict:
        if (
            type(oracle_report) is not dict
            or oracle_report.get("execution_class") == "SOURCE_TEST"
            or oracle_report.get("acceptance_eligible") is not True
        ):
            raise Denied("RUNTIME_VERIFICATION_RECEIPT_REQUIRED")
        if self.receipt_validator is None:
            raise Denied("ENROLLED_VERIFIER_RECEIPT_VALIDATOR_REQUIRED")
        checks = oracle_report.get("checks")
        if (
            oracle_report.get("execution_class") != "ACTUAL_RUNTIME"
            or oracle_report.get("oracle_id") != ORACLE_ID
            or oracle_report.get("oracle_sha256") != ENROLLED_ORACLE_SHA256
            or type(oracle_report.get("passed")) is not int
            or oracle_report["passed"] != 13
            or type(oracle_report.get("total")) is not int
            or oracle_report["total"] != 13
            or type(checks) is not list
            or len(checks) != 13
            or any(
                type(c) is not dict
                or set(c) != {"id", "result"}
                or type(c["id"]) is not str
                or c["result"] != "PASS"
                for c in checks
            )
            or {c["id"] for c in checks} != EXPECTED_CASE_IDS
        ):
            raise Denied("EXACT_RUNTIME_CHECK_SET_REQUIRED")
        unsigned = {key: value for key, value in oracle_report.items() if key != "report_digest"}
        digest = hashlib.sha256(
            json.dumps(
                unsigned, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        if oracle_report.get("report_digest") != digest:
            raise Denied("VERIFIER_REPORT_DIGEST_MISMATCH")
        expected = dict(
            task_id=str(task_id),
            attempt_id=str(attempt_id),
            fence=int(fence),
            expected_task_revision=int(expected_task_revision),
            patch_id=str(patch_id),
            head_digest=str(head_digest),
            profile_digest=str(profile_digest),
            build_digest=str(build_digest),
            acceptance_criteria_digest=str(acceptance_criteria_digest),
        )
        # The enrolled boundary must authenticate the receipt and re-read all
        # bindings. Dictionary fields and a self-calculated digest cannot do so.
        if self.receipt_validator.validate(oracle_report, expected=expected) is not True:
            raise Denied("VERIFIER_RECEIPT_BINDING_REJECTED")
        if oracle_report.get("outcome") != "PASS" or oracle_report.get("passed") != 13:
            raise Denied("VERIFICATION_ORACLE_DID_NOT_PASS")
        report_id = str(uuid4())
        results = [
            {
                "oracle_id": str(oracle_report["oracle_id"]),
                "outcome": "PASS",
                "artifact_digest": str(oracle_report["report_digest"]),
            }
        ]
        v_binding = dict(
            patch_id=str(patch_id),
            head_digest=str(head_digest),
            profile_digest=str(profile_digest),
            build_digest=str(build_digest),
            results=results,
            report_artifact_id=report_id,
            kind="ORDINARY",
            acceptance_criteria_digest=str(acceptance_criteria_digest),
        )
        v_id, v_raw, v_tag = self.verifier_signer.sign(
            "r58.verification.v1", v_binding, receipt_id=report_id
        )
        host.execute(
            self.connect(),
            self.verifier_auth,
            "evidence.attestation_ingest",
            [
                v_id,
                str(self.verifier_signer.issuer),
                str(self.verifier_signer.key_id),
                self.verifier_signer.revision,
                "r58.verification.v1",
                v_raw,
                v_tag,
                "r58-verif-attest:" + v_id,
                str(uuid4()),
            ],
        )
        seal_res = host.execute(
            self.connect(),
            self.verifier_auth,
            "verification.final_seal",
            [
                str(task_id),
                str(attempt_id),
                int(fence),
                v_id,
                "r58-verif-seal:" + v_id,
                str(uuid4()),
            ],
        )["result"]
        verification_id, seal_digest = seal_res["verification_id"], seal_res["seal_digest"]
        ev_binding = dict(
            verification_id=str(verification_id),
            seal_digest=str(seal_digest),
            artifact_id=v_id,
            artifact_digest=hashlib.sha256(v_raw).hexdigest(),
            head_digest=str(head_digest),
        )
        ev_att_id, ev_raw, ev_tag = self.evidence_signer.sign("r58.evidence.v1", ev_binding)
        host.execute(
            self.connect(),
            self.evidence_auth,
            "evidence.attestation_ingest",
            [
                ev_att_id,
                str(self.evidence_signer.issuer),
                str(self.evidence_signer.key_id),
                self.evidence_signer.revision,
                "r58.evidence.v1",
                ev_raw,
                ev_tag,
                "r58-ev-attest:" + ev_att_id,
                str(uuid4()),
            ],
        )
        prov_res = host.execute(
            self.connect(),
            self.evidence_auth,
            "evidence.provenance",
            [
                str(task_id),
                str(attempt_id),
                int(fence),
                ev_att_id,
                "r58-ev-prov:" + ev_att_id,
                str(uuid4()),
            ],
        )["result"]
        evidence_id = prov_res["evidence_id"]
        accept_res = host.execute(
            self.connect(),
            self.human_auth,
            "verification.accept",
            [
                str(task_id),
                str(attempt_id),
                int(fence),
                int(expected_task_revision),
                str(evidence_id),
                "r58-accept:" + str(evidence_id),
                str(uuid4()),
            ],
        )["result"]
        return dict(
            verification_attestation_id=v_id,
            verification_id=verification_id,
            seal_digest=seal_digest,
            evidence_attestation_id=ev_att_id,
            evidence_id=evidence_id,
            acceptance=accept_res,
        )
