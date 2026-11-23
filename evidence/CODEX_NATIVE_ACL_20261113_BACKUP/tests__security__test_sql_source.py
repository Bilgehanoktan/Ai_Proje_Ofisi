"""Kaynak regresyonları; PostgreSQL ACL davranış testi değildir."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SqlSourceTests(unittest.TestCase):
    def test_bootstrap_definitions_are_inactive_and_conflicts_abort(self):
        choices = json.loads((ROOT / 'config/registry-decisions.json').read_text('utf-8'))
        sql = (ROOT / 'sql/035_R58_OPERATION_REGISTRY.sql').read_text('utf-8')
        self.assertIs(choices['grant_issuance'], False)
        self.assertEqual(len(choices['rows']), 9)
        for row in choices['rows']:
            expected = "VALUES('{operation_id}','{permission}','PROJECT','COMMAND',0,NULL)".format(**row)
            self.assertIn(expected, sql)
        self.assertIn("RAISE EXCEPTION 'APPLICATION_BOOTSTRAP_REGISTRY_CONFLICT'", sql)
        block = sql.split('-- New application bootstrap definitions.', 1)[1]
        self.assertNotIn('INSERT INTO company.project_grants', block)
        self.assertNotIn('UPDATE company_private.operation_permissions', block)

    def test_internal_bootstrap_operations_have_inactive_definitions(self):
        choices = json.loads((ROOT / 'config/registry-decisions.json').read_text('utf-8'))
        sql = (ROOT / 'sql/035_R58_OPERATION_REGISTRY.sql').read_text('utf-8')
        self.assertEqual({r['operation_id'] for r in choices['bootstrap_internal_rows']},
                         {'projects.read', 'projects.create', 'e0.evaluation_attempt_create'})
        for row in choices['bootstrap_internal_rows']:
            self.assertIn("VALUES('{operation_id}','{permission}','PROJECT','{execution_class}',0,NULL)".format(**row), sql)
        self.assertIn("RAISE EXCEPTION 'BOOTSTRAP_DEFINITION_CONFLICT'", sql)

    def test_assembly_is_complete_pinned_and_inert(self):
        manifest = json.loads((ROOT / 'sql/assembly.json').read_text('utf-8'))
        self.assertIs(manifest['automatic_execution'], False)
        rows = manifest['order']
        self.assertEqual(len(rows), 83)
        self.assertEqual(len({r['path'] for r in rows}), 83)
        for index, row in enumerate(rows, 1):
            with self.subTest(path=row['path']):
                path = (ROOT / row['path']).resolve()
                self.assertTrue(path.is_relative_to((ROOT / 'sql').resolve()))
                self.assertTrue(path.name.startswith(f'{index:03}_'))
                data = path.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
                self.assertTrue(data.rstrip().endswith(b'ROLLBACK;'))
                if index != 45:
                    self.assertIn(b'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED', data)

    def test_trigger_public_privilege_is_revoked_before_trigger_creation(self):
        sql = (ROOT / 'sql/017_R55_TRUSTED_CLOCK_GUARDED_CANDIDATE.sql').read_text('utf-8')
        create = sql.index('CREATE FUNCTION company_private.r55_cp_clock_epoch_immutable()')
        revoke = sql.index('REVOKE ALL ON FUNCTION company_private.r55_cp_clock_epoch_immutable() FROM PUBLIC;')
        trigger = sql.index('CREATE TRIGGER r55_clock_epoch_immutable')
        self.assertLess(create, revoke)
        self.assertLess(revoke, trigger)


if __name__ == '__main__':
    unittest.main()
