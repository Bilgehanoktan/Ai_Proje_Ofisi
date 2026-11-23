"""Transactional session doubles; never identity/enrollment or live DB evidence."""

import copy
import hashlib
import unittest
from types import SimpleNamespace

from company_os.bootstrap.provisioning import ProvisioningBlocked, ProvisioningOutcomeUnknown
from company_os.kernel.session_provisioning import (
    SESSION_READBACK_SQL,
    issue_committed_owner_session,
)

from tests.unit.test_session_provisioning import Cursor


class SessionHarness:
    def __init__(self):
        self.base = Cursor()
        self.connections = []
        self.saved = None
        self.mode = "ok"
        self.token = "fixture-secret-session-" * 3

    def connect(self):
        connection = SessionConnection(self)
        self.connections.append(connection)
        return connection

    def issue(self):
        return issue_committed_owner_session(
            self.connect,
            installation_id=self.base.installation,
            token=self.token,
            expected_login="physical-fixture",
            ttl_seconds=30,
        )


class SessionCursor(Cursor):
    def __init__(self, connection):
        self.__dict__.update(copy.deepcopy(connection.harness.base.__dict__))
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=()):
        super().execute(sql, args)
        self.connection.calls.append((sql, args))
        if sql.startswith("INSERT INTO company.sessions"):
            self.connection.harness.saved = args

    def fetchone(self):
        sql = self.calls[-1][0]
        if sql.startswith("SELECT session_user,current_user"):
            elevated = self.connection.harness.mode == "superuser"
            return ("physical-fixture", "physical-fixture", elevated, False, False)
        if "r56_root_bounds" in sql and self.connection.harness.mode == "expired":
            error = RuntimeError("must-not-leak-driver-details")
            error.diag = SimpleNamespace(message_primary="ROOT_BOOTTIME_EXPIRED_OR_REBOOTED")
            raise error
        result = super().fetchone()
        if "r56_root_bounds" in sql and len(self.connection.harness.connections) == 2:
            if self.connection.harness.mode == "generation":
                result[0]["generation"] += 1
        return result

    def fetchall(self):
        h = self.connection.harness
        if self.calls[-1][0] != SESSION_READBACK_SQL:
            return super().fetchall()
        tenant, session, principal, token_hash, expires = h.saved
        identity = {"kind": "SESSION", "tenant_id": tenant, "session_id": session}
        row = [expires, token_hash, 0, 0, 2, identity]
        if h.mode == "wrong-token":
            row[1] = "0" * 64
        if h.mode == "wrong-lock":
            row[5]["tenant_id"] = self.boot
        if h.mode == "revoked":
            return []
        return [tuple(row)]


class SessionConnection:
    def __init__(self, harness):
        self.harness = harness
        self.info = SimpleNamespace(transaction_status=0)
        self.autocommit = False
        self.calls = []
        self.closed = False

    def cursor(self):
        return SessionCursor(self)

    def commit(self):
        self.calls.append(("COMMIT", ()))
        if self.harness.mode == "lost-ack":
            raise OSError("secret-driver-details")

    def rollback(self):
        self.calls.append(("ROLLBACK", ()))

    def close(self):
        self.closed = True


class CommittedSessionTests(unittest.TestCase):
    def test_commit_then_independent_readback_never_returns_token(self):
        h = SessionHarness()
        result = h.issue()
        self.assertEqual(result["independent_readback"], "MATCH")
        self.assertEqual(result["commit"], "ACKNOWLEDGED")
        self.assertEqual(result["new_grants"], 0)
        self.assertEqual(len(h.connections), 2)
        writer, reader = h.connections
        self.assertTrue(writer.closed and reader.closed)
        self.assertIn(("COMMIT", ()), writer.calls)
        self.assertNotIn(("COMMIT", ()), reader.calls)
        self.assertFalse(any(sql.startswith("INSERT") for sql, _ in reader.calls))
        self.assertNotIn(h.token, repr(writer.calls) + repr(reader.calls) + repr(result))
        self.assertEqual(h.saved[3], hashlib.sha256(h.token.encode()).hexdigest())

    def test_superuser_and_expired_root_never_commit_or_readback(self):
        for mode in ("superuser", "expired"):
            h = SessionHarness()
            h.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ProvisioningBlocked) as caught:
                h.issue()
            self.assertNotIn("driver-details", str(caught.exception))
            self.assertEqual(len(h.connections), 1)
            self.assertIsNone(h.saved)
            self.assertTrue(h.connections[0].closed)
            self.assertNotIn(("COMMIT", ()), h.connections[0].calls)

    def test_lost_ack_never_reissues_or_opens_readback_connection(self):
        h = SessionHarness()
        h.mode = "lost-ack"
        with self.assertRaises(ProvisioningOutcomeUnknown):
            h.issue()
        self.assertEqual(len(h.connections), 1)
        self.assertEqual(
            sum(
                sql.startswith("INSERT INTO company.sessions") for sql, _ in h.connections[0].calls
            ),
            1,
        )

    def test_post_commit_mismatch_requires_reconciliation_without_retry(self):
        for mode in ("wrong-token", "wrong-lock", "revoked", "generation"):
            h = SessionHarness()
            h.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ProvisioningOutcomeUnknown):
                h.issue()
            self.assertEqual(len(h.connections), 2)
            self.assertTrue(all(connection.closed for connection in h.connections))
            self.assertEqual(
                sum(
                    sql.startswith("INSERT INTO company.sessions")
                    for connection in h.connections
                    for sql, _ in connection.calls
                ),
                1,
            )

    def test_invalid_configuration_never_opens_connection(self):
        with self.assertRaises(ProvisioningBlocked):
            issue_committed_owner_session(
                lambda: self.fail("Must not connect"),
                installation_id=Cursor().installation,
                token="valid-fixture-token-" * 3,
                expected_login="",
            )
