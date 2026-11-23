"""Fake DB-API testleri; fiziksel PostgreSQL kabulü değildir."""
import unittest
from types import SimpleNamespace
from company_os.kernel.registry_preflight import REQUIRED, RegistryBlocked
from company_os.kernel.registry_reader import inspect_registry, QUERY


class Connection:
    def __init__(self):
        self.info = SimpleNamespace(transaction_status=0)
        self.autocommit = False
        self.calls = []
        self.closed = False
        self.fail = False
        self.rows = [(op, 'synthetic', 'PROJECT', 'COMMAND', 0, None)
                     for op in sorted(REQUIRED)]

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        if self.fail:
            raise RuntimeError('sensitive-driver-detail')

    def fetchall(self):
        return self.rows

    def rollback(self):
        self.calls.append(('ROLLBACK', ()))

    def close(self):
        self.closed = True


class ReaderTests(unittest.TestCase):
    def test_readonly_snapshot_parameter_binding_and_cleanup(self):
        c = Connection()
        result = inspect_registry(lambda: c)
        self.assertEqual(result['authorization'], 'NOT_VERIFIED')
        self.assertEqual(c.calls[0][0], 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertIn((QUERY, (sorted(REQUIRED),)), c.calls)
        self.assertEqual(c.calls[-1][0], 'ROLLBACK')
        self.assertTrue(c.closed)

    def test_missing_or_malformed_readback_never_succeeds(self):
        for rows in [[], [('bad',)]]:
            c = Connection()
            c.rows = rows
            with self.assertRaises(RegistryBlocked):
                inspect_registry(lambda: c)
            self.assertTrue(c.closed)

    def test_database_error_is_redacted_and_connection_closed(self):
        c = Connection()
        c.fail = True
        with self.assertRaisesRegex(RegistryBlocked, '^REGISTRY_READBACK_FAILED$'):
            inspect_registry(lambda: c)
        self.assertTrue(c.closed)

    def test_active_or_autocommit_connection_is_rejected_before_query(self):
        for attribute in ('autocommit', 'transaction_status'):
            c = Connection()
            if attribute == 'autocommit':
                c.autocommit = True
            else:
                c.info.transaction_status = 2
            with self.assertRaises(RegistryBlocked):
                inspect_registry(lambda: c)
            self.assertFalse(any(sql == QUERY for sql, _ in c.calls))
            self.assertTrue(c.closed)

    def test_invalid_timeout_does_not_connect(self):
        for value in (True, 0, -1, 5001):
            with self.assertRaises(RegistryBlocked):
                inspect_registry(lambda: self.fail('must not connect'), timeout_ms=value)
