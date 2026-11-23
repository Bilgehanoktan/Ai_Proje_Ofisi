"""Supervisor owner-auth/recovery adapter doubles; not live DB or human custody proof."""

import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from company_os.bootstrap.provisioning import ProvisioningBlocked, ProvisioningOutcomeUnknown
from company_os.kernel.owner_auth import (
    EXECUTE_QUERY,
    READBACK_QUERY,
    issue_committed_owner_auth_v1,
    owner_auth_tag,
    read_owner_auth_receipt_v1,
)


class OwnerAuthHarness:
    def __init__(self) -> None:
        self.installation = str(uuid4())
        self.tenant = str(uuid4())
        self.project = str(uuid4())
        self.human = str(uuid4())
        self.key_id = str(uuid4())
        self.enrollment_revision = 1
        self.signing_key = b"k" * 32
        self.token = "owner-secret-session-token-" * 3
        self.target_session = str(uuid4())
        self.session_id = str(uuid4())
        self.expires_at = (
            datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=5)
        ).isoformat()
        self.receipt_digest = "a" * 64
        self.audit_id = 42
        self.expected_login = "owner_auth_transport_fixture"
        self.connections: list[OwnerAuthConnection] = []
        self.mode = "ok"
        self.saved_execute_args: tuple[object, ...] | None = None

    def connect(self) -> "OwnerAuthConnection":
        if self.mode == "same-connection" and self.connections:
            return self.connections[0]
        conn = OwnerAuthConnection(self)
        self.connections.append(conn)
        return conn

    def issue(self, action: str = "ISSUE_SESSION", **overrides: object) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "installation_id": self.installation,
            "tenant_id": self.tenant,
            "project_id": self.project,
            "human_id": self.human,
            "action": action,
            "key_id": self.key_id,
            "enrollment_revision": self.enrollment_revision,
            "signing_key": self.signing_key,
            "expected_login": self.expected_login,
            "ttl_seconds": 300,
        }
        if action in ("ISSUE_SESSION", "RECOVER_ROTATE_SESSIONS"):
            kwargs["token"] = self.token
        else:
            kwargs["target_session_id"] = self.target_session
        kwargs.update(overrides)
        return issue_committed_owner_auth_v1(self.connect, **kwargs)  # type: ignore[arg-type]


class OwnerAuthCursor:
    def __init__(self, connection: "OwnerAuthConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "OwnerAuthCursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, args: tuple[object, ...] = ()) -> None:
        self.connection.calls.append((sql, args))
        if sql == EXECUTE_QUERY:
            self.connection.harness.saved_execute_args = args

    def fetchone(self) -> object:
        h = self.connection.harness
        sql, args = self.connection.calls[-1]
        if sql.startswith("SELECT session_user,current_user"):
            if h.mode == "superuser":
                return (h.expected_login, h.expected_login, True, False, False)
            if h.mode == "bypassrls":
                return (h.expected_login, h.expected_login, False, True, False)
            if h.mode == "createrole":
                return (h.expected_login, h.expected_login, False, False, True)
            if h.mode == "wrong-login":
                return ("other_role", "other_role", False, False, False)
            return (h.expected_login, h.expected_login, False, False, False)
        if sql.startswith("SELECT pg_backend_pid"):
            return (777, "1001", h.expected_login)
        if sql == EXECUTE_QUERY:
            if h.mode == "native-error":
                err = RuntimeError("sensitive-driver-dsn-leak")
                err.diag = SimpleNamespace(
                    message_primary="OWNER_AUTH_ENROLLMENT_EXPIRED_OR_AMBIGUOUS"
                )  # type: ignore[attr-defined]
                raise err
            if h.mode == "unknown-driver-error":
                raise RuntimeError("secret-pg-password-leak")
            installation, auth_request, key_id, rev, raw_bytes, tag = args
            wire = json.loads(bytes(raw_bytes).decode("utf-8"))  # type: ignore[arg-type]
            stmt = wire["statement"]
            action = stmt["action"]
            expected_tag = owner_auth_tag(
                h.signing_key,
                auth_request_id=str(auth_request),
                tenant_id=stmt["tenant_id"],
                project_id=stmt["project_id"],
                human_id=stmt["human_id"],
                key_id=str(key_id),
                enrollment_revision=int(rev),  # type: ignore[arg-type]
                raw=bytes(raw_bytes),  # type: ignore[arg-type]
            )
            assert hmac.compare_digest(bytes(tag), expected_tag)  # type: ignore[arg-type]
            if action == "REVOKE_SESSION":
                token_hash = hashlib.sha256(h.token.encode("utf-8")).hexdigest()
                session_id = stmt["params"]["target_session_id"]
                revoked_count = 1
                outcome = "REVOKED"
            elif action == "RECOVER_ROTATE_SESSIONS":
                token_hash = stmt["params"]["token_hash"]
                session_id = h.session_id
                revoked_count = 2
                outcome = "RECOVERED_ROTATED"
            else:
                token_hash = stmt["params"]["token_hash"]
                session_id = h.session_id
                revoked_count = 0
                outcome = "ISSUED"
            if h.mode == "wrong-token-hash":
                token_hash = "0" * 64
            return (
                {
                    "auth_request_id": auth_request,
                    "installation_id": installation,
                    "tenant_id": stmt["tenant_id"],
                    "project_id": stmt["project_id"],
                    "principal_id": stmt["human_id"],
                    "action": action,
                    "session_id": session_id,
                    "token_hash": token_hash,
                    "expires_at": h.expires_at,
                    "revoked_session_count": revoked_count,
                    "receipt_digest": h.receipt_digest,
                    "audit_id": h.audit_id,
                    "outcome": outcome,
                    "new_grants": 0,
                    "new_memberships": 0,
                    "authorization": "SESSION_LIFECYCLE_ONLY_NOT_WORKFLOW_ACCEPTANCE",
                },
            )
        if sql == READBACK_QUERY:
            if h.mode == "readback-mismatch":
                return (None,)
            if h.mode == "readback-wrong-digest":
                return (
                    {
                        "tenant_id": args[0],
                        "auth_request_id": args[1],
                        "installation_id": args[2],
                        "project_id": args[3],
                        "human_id": args[4],
                        "action": args[5],
                        "session_id": args[6],
                        "token_hash": args[7],
                        "receipt_digest": "f" * 64,
                        "expires_at": h.expires_at,
                        "revoked_session_count": 0,
                        "audit_id": h.audit_id,
                        "readback": "EXACT_COMMITTED_WITNESS_MATCH",
                        "authorization": "SESSION_RECORD_READBACK_NOT_WORKFLOW_ACCEPTANCE",
                        "new_grants": 0,
                        "new_memberships": 0,
                    },
                )
            revoked = (
                1
                if args[5] == "REVOKE_SESSION"
                else (2 if args[5] == "RECOVER_ROTATE_SESSIONS" else 0)
            )
            return (
                {
                    "tenant_id": args[0],
                    "auth_request_id": args[1],
                    "installation_id": args[2],
                    "project_id": args[3],
                    "human_id": args[4],
                    "action": args[5],
                    "session_id": args[6],
                    "token_hash": args[7],
                    "receipt_digest": args[8],
                    "expires_at": h.expires_at,
                    "revoked_session_count": revoked,
                    "audit_id": h.audit_id,
                    "readback": "EXACT_COMMITTED_WITNESS_MATCH",
                    "authorization": "SESSION_RECORD_READBACK_NOT_WORKFLOW_ACCEPTANCE",
                    "new_grants": 0,
                    "new_memberships": 0,
                },
            )
        return (None,)


class OwnerAuthConnection:
    def __init__(self, harness: OwnerAuthHarness) -> None:
        self.harness = harness
        self.info = SimpleNamespace(transaction_status=0)
        self.autocommit = False
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def cursor(self) -> OwnerAuthCursor:
        return OwnerAuthCursor(self)

    def commit(self) -> None:
        self.calls.append(("COMMIT", ()))
        if self.harness.mode == "lost-ack":
            raise OSError("driver-commit-socket-lost")

    def rollback(self) -> None:
        self.calls.append(("ROLLBACK", ()))

    def close(self) -> None:
        self.closed = True


class OwnerAuthTests(unittest.TestCase):
    def test_issue_revoke_and_recover_commit_with_independent_readback_no_secret_leak(self) -> None:
        for action, expected_outcome, expected_revoked in (
            ("ISSUE_SESSION", "ISSUED", 0),
            ("REVOKE_SESSION", "REVOKED", 1),
            ("RECOVER_ROTATE_SESSIONS", "RECOVERED_ROTATED", 2),
        ):
            h = OwnerAuthHarness()
            with self.subTest(action=action):
                result = h.issue(action)
                self.assertEqual(result["outcome"], expected_outcome)
                self.assertEqual(result["revoked_session_count"], expected_revoked)
                self.assertEqual(result["commit"], "ACKNOWLEDGED")
                self.assertEqual(result["independent_readback"], "MATCH")
                self.assertEqual(result["new_grants"], 0)
                self.assertEqual(result["new_memberships"], 0)
                self.assertEqual(len(h.connections), 2)
                writer, reader = h.connections
                self.assertTrue(writer.closed and reader.closed)
                self.assertIn(("COMMIT", ()), writer.calls)
                self.assertNotIn(("COMMIT", ()), reader.calls)
                self.assertIn(("BEGIN ISOLATION LEVEL SERIALIZABLE", ()), writer.calls)
                self.assertIn(("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY", ()), reader.calls)
                serialized = repr(writer.calls) + repr(reader.calls) + repr(result)
                self.assertNotIn(h.token, serialized)
                self.assertNotIn(repr(h.signing_key), serialized)
                self.assertNotIn("token_hash", result)

    def test_privileged_or_wrong_login_rejected_before_execute_and_commit(self) -> None:
        for mode in ("superuser", "bypassrls", "createrole", "wrong-login"):
            h = OwnerAuthHarness()
            h.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ProvisioningBlocked) as caught:
                h.issue()
            self.assertEqual(
                str(caught.exception), "EXACT_LEAST_PRIVILEGE_OWNER_AUTH_LOGIN_REQUIRED"
            )
            self.assertEqual(len(h.connections), 1)
            self.assertTrue(h.connections[0].closed)
            self.assertIsNone(h.saved_execute_args)
            self.assertNotIn(("COMMIT", ()), h.connections[0].calls)

    def test_lost_ack_raises_unknown_without_retry_or_readback_connection(self) -> None:
        h = OwnerAuthHarness()
        h.mode = "lost-ack"
        with self.assertRaises(ProvisioningOutcomeUnknown):
            h.issue()
        self.assertEqual(len(h.connections), 1)
        self.assertTrue(h.connections[0].closed)
        self.assertEqual(sum(sql == EXECUTE_QUERY for sql, _ in h.connections[0].calls), 1)

    def test_post_commit_readback_failures_require_reconciliation_without_retry(self) -> None:
        for mode in ("same-connection", "readback-mismatch", "readback-wrong-digest"):
            h = OwnerAuthHarness()
            h.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ProvisioningOutcomeUnknown):
                h.issue()
            self.assertTrue(all(conn.closed for conn in h.connections))
            self.assertEqual(
                sum(sql == EXECUTE_QUERY for conn in h.connections for sql, _ in conn.calls),
                1,
            )

    def test_native_and_driver_errors_are_redacted_safely(self) -> None:
        h1 = OwnerAuthHarness()
        h1.mode = "native-error"
        with self.assertRaises(ProvisioningBlocked) as caught_native:
            h1.issue()
        self.assertEqual(str(caught_native.exception), "OWNER_AUTH_ENROLLMENT_EXPIRED_OR_AMBIGUOUS")
        self.assertNotIn("sensitive-driver", str(caught_native.exception))

        h2 = OwnerAuthHarness()
        h2.mode = "unknown-driver-error"
        with self.assertRaises(ProvisioningBlocked) as caught_driver:
            h2.issue()
        self.assertEqual(str(caught_driver.exception), "OWNER_AUTH_NOT_COMMITTED")
        self.assertNotIn("secret-pg-password", str(caught_driver.exception))

    def test_read_owner_auth_receipt_reconciliation_is_readonly_and_strict(self) -> None:
        h = OwnerAuthHarness()
        expected = {
            "tenant_id": h.tenant,
            "auth_request_id": str(uuid4()),
            "installation_id": h.installation,
            "project_id": h.project,
            "human_id": h.human,
            "action": "ISSUE_SESSION",
            "session_id": h.session_id,
            "token_hash": hashlib.sha256(h.token.encode("utf-8")).hexdigest(),
            "receipt_digest": h.receipt_digest,
        }
        receipt = read_owner_auth_receipt_v1(
            h.connect, expected=expected, expected_login=h.expected_login
        )
        self.assertEqual(receipt["readback"], "EXACT_COMMITTED_WITNESS_MATCH")
        self.assertEqual(len(h.connections), 1)
        self.assertIn(
            ("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY", ()), h.connections[0].calls
        )
        self.assertNotIn(("COMMIT", ()), h.connections[0].calls)

        h_bad = OwnerAuthHarness()
        h_bad.mode = "readback-mismatch"
        with self.assertRaises(ProvisioningBlocked):
            read_owner_auth_receipt_v1(
                h_bad.connect, expected=expected, expected_login=h_bad.expected_login
            )

    def test_invalid_inputs_never_open_connection(self) -> None:
        h = OwnerAuthHarness()

        def fail_connect() -> OwnerAuthConnection:
            self.fail("Must not connect on invalid input")

        base: dict[str, object] = {
            "installation_id": h.installation,
            "tenant_id": h.tenant,
            "project_id": h.project,
            "human_id": h.human,
            "action": "ISSUE_SESSION",
            "key_id": h.key_id,
            "enrollment_revision": 1,
            "signing_key": b"k" * 32,
            "expected_login": "owner_auth",
            "token": "valid-session-token-" * 3,
            "ttl_seconds": 300,
        }
        invalid_cases: list[dict[str, object]] = [
            {"token": "short"},
            {"token": ""},
            {"ttl_seconds": True},
            {"ttl_seconds": 0},
            {"ttl_seconds": 901},
            {"signing_key": b"k" * 31},
            {"installation_id": "not-a-uuid"},
            {"target_session_id": h.target_session},
            {
                "action": "REVOKE_SESSION",
                "token": "unexpected",
                "target_session_id": h.target_session,
            },
            {"action": "ADMIN_GRANT"},
        ]
        for patch_args in invalid_cases:
            args = dict(base)
            args.update(patch_args)
            with self.subTest(patch=patch_args), self.assertRaises(ProvisioningBlocked):
                issue_committed_owner_auth_v1(fail_connect, **args)  # type: ignore[arg-type]
