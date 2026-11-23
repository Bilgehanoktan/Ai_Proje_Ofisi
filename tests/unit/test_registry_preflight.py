"""Synthetic shape checks; gerçek registry/policy kabulü değildir."""
import unittest
from company_os.kernel.registry_preflight import REQUIRED, RegistryBlocked, check_required_registry


def fixture():
    return [dict(operation_id=op, permission='synthetic-not-authority',
                 scope_kind='PROJECT', execution_class='COMMAND',
                 policy_revision=0, approved_policy_digest=None)
            for op in sorted(REQUIRED)]


class RegistryTests(unittest.TestCase):
    def test_complete_shape_does_not_claim_authorization(self):
        self.assertEqual(check_required_registry(fixture())['authorization'], 'NOT_VERIFIED')

    def test_missing_and_duplicate_are_blocked(self):
        for rows in [[], fixture()[:-1], fixture() + fixture()[:1]]:
            with self.subTest(rows=len(rows)), self.assertRaises(RegistryBlocked):
                check_required_registry(rows)

    def test_invalid_bindings_are_blocked(self):
        for field, value in [('permission', ''), ('scope_kind', 'TENANT'),
                             ('execution_class', 'QUERY'), ('policy_revision', True),
                             ('policy_revision', -1), ('approved_policy_digest', 'fake')]:
            rows = fixture()
            rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(RegistryBlocked):
                check_required_registry(rows)

    def test_input_is_not_activated_or_modified(self):
        rows = fixture()
        before = [dict(row) for row in rows]
        check_required_registry(rows)
        self.assertEqual(rows, before)
