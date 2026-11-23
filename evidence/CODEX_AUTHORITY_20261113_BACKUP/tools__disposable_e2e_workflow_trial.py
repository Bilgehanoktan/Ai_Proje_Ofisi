"""Supervisor-only canonical MGT01 trial entry; no synthetic bootstrap or fallback.

The former synthetic/custom-port trial is preserved byte-exact in
 evidence/CODEX_WORKFLOW_20261112_BACKUP/tools__disposable_e2e_workflow_trial.py.
This entry never provisions a DB, launches a service, enrolls keys or invents
runtime/identity evidence. The CLI remains blocked without enrolled ports.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from company_os.workflow import PilotWorkflow
from company_os.workflow_trust import check_workflow_trust
from company_os.execution_protocol import Denied

CANONICAL_WORKSPACE = r"E:\Projeler\Ai_Proje_Ofisi"


def main(*, trust_inputs=None, workflow_ports=None, request=None, read_bootstrap=None):
    from tools.workflow_preflight import check_workflow
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
            or bootstrap.get('accepted_human_id') != root['actual_human_id']):
        raise Denied('BOOTSTRAP_TRUST_IDENTITY_MISMATCH')
    workflow = PilotWorkflow(**workflow_ports)
    result = workflow.run(**request)
    print(json.dumps({'status': 'CANONICAL_WORKFLOW_RETURNED', 'result': result,
                      'consent_authority_granted': consent.authority_granted,
                      'g0': 'OPEN', 'human_acceptance_claimed': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
