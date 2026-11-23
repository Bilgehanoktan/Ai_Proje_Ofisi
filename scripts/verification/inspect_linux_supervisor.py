"""Read-only environment inventory. Never provisions or qualifies a runtime."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())


def inspect_environment():
    result = dict(scope='READ_ONLY_ENVIRONMENT_INVENTORY_NOT_QUALIFICATION',
                  platform=sys.platform, python=sys.version.split()[0],
                  runtime_ready=False, g0='OPEN', first13='0/13')
    profiles = sorted(p.name for p in (ROOT / 'config/profiles').glob('*.json') if p.is_file())
    result['profile_files'] = profiles
    blockers = ['ENROLLED_OBSERVER_AND_VERIFIER_NOT_VERIFIED',
                'TRUSTED_CLOCK_PROFILE_AND_SIGNER_BINDINGS_NOT_VERIFIED']
    if not profiles:
        blockers.append('NO_RUNTIME_PROFILE_JSON')
    if sys.platform != 'linux':
        blockers.append('LINUX_SUPERVISOR_REQUIRED')
    else:
        result['uid'] = os.getuid()
        result['euid'] = os.geteuid()
        if os.getuid() == 0 or os.geteuid() == 0:
            blockers.append('ROOTLESS_SUPERVISOR_REQUIRED')
        result['pidfd_api_present'] = hasattr(os, 'pidfd_open')
        result['namespace_inodes'] = {name: os.stat('/proc/self/ns/' + name).st_ino
                                       for name in ('user', 'mnt', 'net', 'pid')}
        result['uid_map'] = Path('/proc/self/uid_map').read_text().strip()
        result['cgroup_membership'] = Path('/proc/self/cgroup').read_text().strip()
        result['cgroup_controllers'] = Path('/sys/fs/cgroup/cgroup.controllers').read_text().strip()
        result['cgroup_root_writable_access_hint_only'] = os.access('/sys/fs/cgroup', os.W_OK)
        status = dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
        result['process_status'] = {key: status.get(key, 'UNKNOWN').strip()
                                    for key in ('NoNewPrivs', 'Seccomp', 'CapEff')}
        # These measurements describe this observer process, not a worker sandbox.
        try:
            result['pydantic'] = importlib.metadata.version('pydantic')
        except importlib.metadata.PackageNotFoundError:
            result['pydantic'] = 'MISSING'
    result['runtime_blockers'] = blockers
    return result


def main():
    print(json.dumps(inspect_environment(), ensure_ascii=False, indent=2))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
