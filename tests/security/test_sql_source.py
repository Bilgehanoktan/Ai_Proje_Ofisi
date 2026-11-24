"""Kaynak regresyonlarÄ±; PostgreSQL ACL davranÄ±ÅŸ testi deÄŸildir."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SqlSourceTests(unittest.TestCase):
    def test_bootstrap_definitions_are_inactive_and_conflicts_abort(self):
        choices = json.loads((ROOT / 'config/registry-decisions.json').read_text('utf-8'))
        sql = (ROOT / 'database/sources/035_R58_OPERATION_REGISTRY.sql').read_text('utf-8')
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
        sql = (ROOT / 'database/sources/035_R58_OPERATION_REGISTRY.sql').read_text('utf-8')
        self.assertEqual({r['operation_id'] for r in choices['bootstrap_internal_rows']},
                         {'projects.read', 'projects.create', 'e0.evaluation_attempt_create'})
        for row in choices['bootstrap_internal_rows']:
            self.assertIn("VALUES('{operation_id}','{permission}','PROJECT','{execution_class}',0,NULL)".format(**row), sql)
        self.assertIn("RAISE EXCEPTION 'BOOTSTRAP_DEFINITION_CONFLICT'", sql)

    def test_assembly_is_complete_pinned_and_inert(self):
        manifest = json.loads((ROOT / 'database/assembly/assembly.json').read_text('utf-8'))
        self.assertIs(manifest['automatic_execution'], False)
        rows = manifest['order']
        self.assertEqual(len(rows), 88)
        self.assertEqual(len({r['path'] for r in rows}), 88)
        for index, row in enumerate(rows, 1):
            with self.subTest(path=row['path']):
                path = (ROOT / row['path']).resolve()
                self.assertTrue(path.is_relative_to((ROOT / 'database/sources').resolve()))
                self.assertTrue(path.name.startswith(f'{index:03}_'))
                data = path.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
                self.assertTrue(data.rstrip().endswith(b'ROLLBACK;'))
                if index != 45:
                    self.assertIn(b'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED', data)

    def test_launch_delivery_receipts_remain_scoped_to_committed_actor_command(self):
        sql = (ROOT / 'database/sources/083_R65_REPLY_GUARD.sql').read_text('utf-8')
        for receipt in ('audit', 'outbox'):
            with self.subTest(receipt=receipt):
                policy = sql.split(f'CREATE POLICY r60_delivery_{receipt}_read ', 1)[1].split(';', 1)[0]
                self.assertIn('FOR SELECT TO company_execution_functions_r58', policy)
                self.assertIn("x.operation_id='process.launch_delivery'", policy)
                self.assertIn('x.db_login=session_user', policy)
                self.assertIn('c.r55_project_id=x.project_id', policy)
                self.assertIn('c.principal_id=x.principal_id', policy)
                self.assertIn("c.operation='process.launch_consume' AND c.state='SUCCEEDED'", policy)
                self.assertIn("kind='LaunchConsumed'", policy)
                link = 'audit_events.id=c.r55_audit_id' if receipt == 'audit' else 'outbox.event_instance_id=c.id'
                self.assertIn(link, policy)

    def test_reconcile_uses_intermediate_stop_with_fresh_revision(self):
        sql = (ROOT / 'database/sources/059_R60_LEASE_RECOVERY_NATIVE.sql').read_text('utf-8')
        body = sql.split('CREATE FUNCTION company_private.r60_process_reconcile', 1)[1]
        proof = body.index('R60_ACTUAL_QUIESCENCE_REQUIRED')
        intermediate = body.index("SET state='STOP_REQUESTED',revision=revision+1")
        refreshed = body.index('RETURNING * INTO STRICT r;', intermediate)
        terminal = body.index("ELSE 'STOPPED' END", refreshed)
        self.assertLess(proof, intermediate)
        self.assertIn("r.state IN ('STARTING','RUNNING')", body[proof:intermediate])
        self.assertIn('revision=r.revision', body[terminal:])

    def test_trigger_public_privilege_is_revoked_before_trigger_creation(self):
        sql = (ROOT / 'database/sources/017_R55_TRUSTED_CLOCK_GUARDED_CANDIDATE.sql').read_text('utf-8')
        create = sql.index('CREATE FUNCTION company_private.r55_cp_clock_epoch_immutable()')
        revoke = sql.index('REVOKE ALL ON FUNCTION company_private.r55_cp_clock_epoch_immutable() FROM PUBLIC;')
        trigger = sql.index('CREATE TRIGGER r55_clock_epoch_immutable')
        self.assertLess(create, revoke)
        self.assertLess(revoke, trigger)

    def test_native_readback_has_narrow_owner_caller_and_no_authority_writes(self):
        sql=(ROOT/'database/sources/084_APPLICATION_BOOTSTRAP_READBACK_V1.sql').read_text('utf-8')
        self.assertIn("session_user<>'company_provisioning_runtime_r55'",sql)
        self.assertIn("USING(session_user='company_provisioning_runtime_r55')",sql)
        self.assertIn('NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT',sql)
        self.assertIn('SECURITY DEFINER SET search_path=pg_catalog',sql)
        self.assertIn('PROVISIONING_ROLE_DEPENDENCY_NOT_INSTALLED',sql)
        self.assertIn('FROM PUBLIC;',sql)
        self.assertNotIn('GRANT company_bootstrap_readback_v1 TO',sql)
        for line in sql.splitlines():
            if line.startswith('GRANT SELECT'):
                self.assertTrue(line.endswith('TO company_bootstrap_readback_v1;'))
        body=sql.split('DECLARE matches integer;',1)[1].split('END $$;',1)[0]
        for keyword in ('INSERT INTO','UPDATE ','DELETE FROM','FOR SHARE','FOR UPDATE'):
            self.assertNotIn(keyword,body)
        self.assertIn("'authorization','NOT_VERIFIED','new_grants',0",body)

    def test_current_window_delegates_to_native_clock_without_authority_writes(self):
        sql=(ROOT/'database/sources/085_APPLICATION_BOOTSTRAP_WINDOW_V1.sql').read_text('utf-8')
        self.assertIn("session_user<>'company_provisioning_runtime_r55'",sql)
        self.assertIn('company_private.r56_root_bounds(p_installation)',sql)
        self.assertIn("b.state IN ('ARMED','CONSUMED')",sql)
        self.assertIn('e.enrollment_digest=p_enrollment AND e.host_boot_id=p_boot',sql)
        self.assertIn('SECURITY DEFINER SET search_path=pg_catalog',sql)
        self.assertIn('FROM PUBLIC;',sql)
        for keyword in ('INSERT INTO','UPDATE ','DELETE FROM','CREATE ROLE','GRANT SELECT','GRANT company_'):
            self.assertNotIn(keyword,sql)
        self.assertIn("'authorization','BOOTSTRAP_WINDOW_ONLY_NOT_RUNTIME','new_grants',0",sql)

    def test_owner_auth_recovery_is_least_privilege_inert_and_preserves_existing_tenant(self):
        sql = (ROOT / 'database/sources/086_APPLICATION_OWNER_AUTH_RECOVERY_V1.sql').read_text(
            'utf-8'
        )
        self.assertIn('DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED', sql)
        self.assertTrue(sql.rstrip().endswith('ROLLBACK;'))
        for role_name in (
            'company_owner_auth_owner_v1',
            'company_owner_auth_readback_v1',
            'company_owner_auth_transport_v1',
        ):
            self.assertIn(
                f'CREATE ROLE {role_name} NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT',
                sql,
            )
        for required in (
            'FORCE ROW LEVEL SECURITY',
            'SECURITY DEFINER SET search_path=pg_catalog',
            'FROM PUBLIC;',
            'r55_cp_clock_current_bounds',
            'r55_cp_hmac_sha256',
            'r55_cp_tag_equal',
            'NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolcreaterole',
        ):
            self.assertIn(required, sql)
        for forbidden in (
            'r56_root_bounds',
            'e0_valid_until',
            'clock_timestamp()',
            'INSERT INTO company.project_grants',
            'INSERT INTO company.memberships',
            'GRANT company_owner_auth_owner_v1 TO',
            'GRANT company_owner_auth_readback_v1 TO',
        ):
            self.assertNotIn(forbidden, sql)
        readback_body = sql.split('CREATE FUNCTION company_private.owner_auth_receipt_readback_v1(', 1)[
            1
        ].split('END $$;', 1)[0]
        for write_op in ('INSERT INTO', 'UPDATE ', 'DELETE FROM', 'FOR SHARE', 'FOR UPDATE'):
            self.assertNotIn(write_op, readback_body)

    def test_mod012_mod014_extensions_have_force_rls_and_sod_check(self):
        sql = (ROOT / 'database/sources/087_MOD012_MOD014_EXTENSIONS_CANDIDATE.sql').read_text(
            'utf-8'
        )
        self.assertIn('DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED', sql)
        self.assertTrue(sql.rstrip().endswith('ROLLBACK;'))
        for table in (
            'company.catalog_entries',
            'company.memory_promotions',
            'company.work_template_validations',
            'company.external_effect_ledger',
        ):
            self.assertIn(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;', sql)
            self.assertIn(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY;', sql)
            self.assertIn(f'REVOKE ALL ON {table} FROM PUBLIC;', sql)
        self.assertIn('promoted_by <> verified_by', sql)


if __name__ == '__main__':
    unittest.main()
