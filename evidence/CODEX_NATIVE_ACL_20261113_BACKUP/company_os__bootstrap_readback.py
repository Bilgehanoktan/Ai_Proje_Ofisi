"""Dedicated read-only bootstrap witness adapter, never a provisioning writer.

Uses the owning r57 replay witness conditions without invoking bootstrap consume.
Requires an already-authorized reader login with explicit SELECT visibility. No
role/grant/clock/root authority is created; MATCH is not current authorization.
"""
import copy
import re
from uuid import UUID

from .provisioning import ProvisioningBlocked

FIELDS=('installation_id','generation','tenant_id','project_id','accepted_human_id',
        'command_id','payload_digest','setup_manifest_digest','initial_grants_digest','r56_result_digest')

QUERY='''SELECT b.installation_id::text,b.generation,b.tenant_id::text,b.project_id::text,b.accepted_human_id::text,
b.command_id::text,b.payload_digest,b.setup_manifest_digest,b.initial_grants_digest,b.r56_result_digest
FROM company_private.bootstrap_receipts b
JOIN company_private.installation_bootstrap_control ctl ON ctl.installation_id=b.installation_id
JOIN company.principals p ON p.tenant_id=b.tenant_id AND p.id=b.accepted_human_id
JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id
JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id
JOIN company.audit_events a ON a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id
JOIN company.outbox e ON e.tenant_id=c.tenant_id AND e.project_id=b.project_id AND e.event_instance_id=c.id
WHERE b.installation_id=%s::uuid AND b.generation=%s::bigint
AND ctl.state='CONSUMED' AND ctl.payload_digest=b.payload_digest
AND ctl.generation=b.generation AND ctl.expected_tenant_id=b.tenant_id AND ctl.expected_project_id=b.project_id
AND ctl.expected_human_id=b.accepted_human_id
AND p.kind='HUMAN' AND m.role='OWNER'
AND c.operation='trusted_setup.consume' AND c.principal_id=b.accepted_human_id
AND c.state='SUCCEEDED' AND c.result_ref=b.installation_id AND c.payload_digest=b.payload_digest
AND c.r55_source_revision='r56' AND c.r55_result_digest=b.r56_result_digest
AND b.r56_final_proof IS NOT NULL AND b.r56_final_proof->>'phase'='COMMIT_CUT'
AND c.r55_result_payload->'final_proof'=b.r56_final_proof
AND b.r56_final_proof->>'installation_id'=b.installation_id::text
AND b.r56_final_proof->>'generation'=b.generation::text
AND b.r56_final_proof->>'manifest_digest'=b.payload_digest
AND c.r55_result_digest=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,b.installation_id,c.r55_result_payload)::text,'UTF8')),'hex')
AND a.kind='InstallationBootstrapped' AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id
AND e.kind='InstallationBootstrapped' AND e.project_sequence=1 AND e.event_writer_generation=54
AND e.payload->>'result_digest'=c.r55_result_digest AND e.aggregate_id=b.project_id AND e.aggregate_revision=0
AND e.payload->>'request_digest'=c.payload_digest
AND e.event_digest=encode(sha256(convert_to(jsonb_build_array(e.aggregate_id,e.aggregate_revision,e.kind,e.payload)::text,'UTF8')),'hex')
LIMIT 2'''


def read_bootstrap_receipt(connect, *, expected, expected_login, timeout_ms=2000):
    if (type(expected) is not dict or set(expected)!=set(FIELDS)
            or type(expected_login) is not str or not 1<=len(expected_login)<=63
            or type(timeout_ms) is not int or not 1<=timeout_ms<=5000):
        raise ProvisioningBlocked('EXACT_BOOTSTRAP_READBACK_INPUT_REQUIRED')
    pinned=copy.deepcopy(expected)
    for name in FIELDS:
        value=pinned[name]
        if name=='generation':
            if type(value) is not int or not 1<=value<=9007199254740991:
                raise ProvisioningBlocked('EXACT_BOOTSTRAP_GENERATION_REQUIRED')
        elif name.endswith('digest'):
            if type(value) is not str or re.fullmatch('[a-f0-9]{64}',value) is None:
                raise ProvisioningBlocked('EXACT_BOOTSTRAP_DIGEST_REQUIRED')
        else:
            try:
                if type(value) is not str or str(UUID(value))!=value:raise ValueError()
            except (ValueError,TypeError,AttributeError):
                raise ProvisioningBlocked('CANONICAL_BOOTSTRAP_ID_REQUIRED') from None
    try:connection=connect()
    except Exception:raise ProvisioningBlocked('BOOTSTRAP_READER_CONNECTION_FAILED') from None
    try:
        if connection.autocommit or int(connection.info.transaction_status)!=0:
            raise ProvisioningBlocked('IDLE_DEDICATED_BOOTSTRAP_READER_REQUIRED')
        with connection.cursor() as cursor:
            cursor.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for name in ('statement_timeout','lock_timeout','idle_in_transaction_session_timeout'):
                cursor.execute('SELECT set_config(%s,%s,true)',(name,str(timeout_ms)+'ms'))
            cursor.execute('SELECT session_user')
            if cursor.fetchone()!=(expected_login,):
                raise ProvisioningBlocked('BOOTSTRAP_READER_LOGIN_MISMATCH')
            cursor.execute(QUERY,(pinned['installation_id'],pinned['generation']))
            rows=cursor.fetchall()
            if (type(rows) is not list or len(rows)!=1 or type(rows[0]) not in (tuple,list)
                    or len(rows[0])!=len(FIELDS) or tuple(rows[0])!=tuple(pinned[name] for name in FIELDS)):
                raise ProvisioningBlocked('BOOTSTRAP_RECEIPT_OR_WITNESS_MISMATCH')
        return dict(pinned,readback='EXACT_COMMITTED_WITNESS_MATCH',authorization='NOT_VERIFIED',new_grants=0)
    except ProvisioningBlocked:
        raise
    except Exception:
        raise ProvisioningBlocked('BOOTSTRAP_READBACK_FAILED') from None
    finally:
        try:connection.rollback()
        except Exception:raise ProvisioningBlocked('BOOTSTRAP_READER_ROLLBACK_FAILED') from None
        finally:
            try:connection.close()
            except Exception:raise ProvisioningBlocked('BOOTSTRAP_READER_CLOSE_FAILED') from None


class BootstrapReadback:
    def __init__(self, *, connect, expected, expected_login, timeout_ms=2000):
        self.connect=connect
        self.expected=copy.deepcopy(expected)
        self.login=expected_login
        self.timeout=timeout_ms

    def __call__(self):
        return read_bootstrap_receipt(self.connect,expected=self.expected,
            expected_login=self.login,timeout_ms=self.timeout)
