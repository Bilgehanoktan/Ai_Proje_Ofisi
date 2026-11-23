"""Supervisor-only canonical MGT01 trial entry; no synthetic bootstrap or fallback.

The former synthetic/custom-port trial is preserved byte-exact in
 evidence/CODEX_WORKFLOW_20261112_BACKUP/tools__disposable_e2e_workflow_trial.py.
This entry never provisions a DB, launches a service, enrolls keys or invents
runtime/identity evidence. The CLI remains blocked without enrolled ports.
"""
from pathlib import Path
import json
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())
if str(ROOT) not in sys.path:
    sys.path[:0] = [str(ROOT), str(ROOT/'product/backend'), str(ROOT/'contracts/source/python'), str(ROOT/'verifier/src')]

from company_os.composition.workflow import PilotWorkflow
from company_os.composition.workflow_trust import check_workflow_trust
from company_os.kernel.execution_protocol import Denied

CANONICAL_WORKSPACE = r"E:\Projeler\Ai_Proje_Ofisi"


def main(*, trust_inputs=None, workflow_ports=None, request=None, read_bootstrap=None):
    from scripts.verification.workflow_preflight import check_workflow
    preflight = check_workflow(Path(__file__))
    if preflight['status'] == 'BLOCKED':
        print(json.dumps({'status': 'BLOCKED_BEFORE_DB_CONNECTION', 'preflight': preflight}))
        return 2
    if trust_inputs is None:
        print(json.dumps({'status': 'BLOCKED_BEFORE_DB_CONNECTION',
                          'reason': 'TRUSTED_SUPERVISOR_INPUTS_REQUIRED'}))
        return 2
    if trust_inputs['canonical_workspace'] != CANONICAL_WORKSPACE:
        raise Denied('CANONICAL_WORKSPACE_REQUIRED')
    consent, secret = check_workflow_trust(
        consent_path=trust_inputs['consent_path'], consent_sha256=trust_inputs['consent_sha256'],
        human_id=trust_inputs['human_id'], canonical_workspace=trust_inputs['canonical_workspace'],
        root_record=trust_inputs['root_record'], secret_directory_fd=trust_inputs['secret_directory_fd'],
        secret_name=trust_inputs['secret_name'], secret_owner_uid=trust_inputs['secret_owner_uid'])
    # Never include secret bytes or the raw consent document in a report.
    del secret
    if workflow_ports is None or request is None or not callable(read_bootstrap):
        print(json.dumps({'status': 'BLOCKED_BEFORE_DB_CONNECTION',
                          'reason': 'ENROLLED_WORKFLOW_AND_BOOTSTRAP_PORTS_REQUIRED'}))
        return 2
    bootstrap = read_bootstrap()
    root = trust_inputs['root_record']
    if (type(bootstrap) is not dict or bootstrap.get('installation_id') != root['installation_id']
            or bootstrap.get('accepted_human_id') != root['actual_human_id']
            or type(bootstrap.get('generation')) is not int
            or bootstrap.get('generation') != root['generation']
            or bootstrap.get('readback') != 'EXACT_COMMITTED_WITNESS_MATCH'
            or bootstrap.get('project_id') != workflow_ports['pilot_ports']['worker_auth']['project_id']
            or bootstrap.get('tenant_id') != workflow_ports['pilot_ports']['proposal_signer'].tenant):
        raise Denied('BOOTSTRAP_TRUST_IDENTITY_MISMATCH')
    workflow = PilotWorkflow(**workflow_ports)
    result = workflow.run(**request)
    print(json.dumps({'status': 'CANONICAL_WORKFLOW_RETURNED', 'result': result,
                      'consent_authority_granted': consent.authority_granted,
                      'g0': 'OPEN', 'human_acceptance_claimed': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
