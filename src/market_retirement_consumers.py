"""Read-only verification of the installed collector before raw retirement."""
import hashlib
import json
from pathlib import Path
import subprocess

SERVICE_CONFIGURATION_FIELDS = (
    'Environment', 'EnvironmentFiles', 'PassEnvironment', 'UnsetEnvironment',
    'ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost',
    'DropInPaths', 'FragmentPath', 'RootDirectory', 'RootImage', 'User', 'Group',
)

def verify_retirement_collector(data_root, *, deployment, index_evidence, program_manifest_sha256,
                                effective_configuration):
    """Recheck stopped service, exact installed unit/program and active inputs.

    Inputs are decoded hash-verified deployment and full-index evidence. Caller
    holds worker and cleaning locks and binds these inputs and the expected
    program manifest SHA256 in final review.
    This checks deployed configuration; it does not start collection or grant
    deletion permission. Changed paths, hashes or active service raise ValueError.
    """
    root = Path(data_root).resolve(strict=True)
    if (deployment.get('state') != 'COLLECTOR_CONFIG_DEPLOYED_SERVICE_STOPPED' or
            index_evidence.get('state') != 'ACTIVE_CAPTURE_INDEX_SQLITE_READBACK_VERIFIED'):
        raise ValueError('verified collector cutover required')
    registry_bytes = (root / 'registry/markets-current.json').read_bytes()
    registry_hash = hashlib.sha256(registry_bytes).hexdigest()
    if registry_hash != deployment['registry_sha256'] or registry_hash != index_evidence['registry_sha256']:
        raise ValueError('collector registry changed')
    registry = json.loads(registry_bytes)
    index_path = (root / registry['index']).resolve(strict=True)
    index_path.relative_to(root)
    if index_path != Path(index_evidence['index_path']).resolve(strict=True):
        raise ValueError('active index path mismatch')
    if hashlib.sha256(index_path.read_bytes()).hexdigest() != index_evidence['index_sha256']:
        raise ValueError('active index changed')
    plan = deployment['plan']
    if plan['service'] != registry['service']:
        raise ValueError('collector service mismatch')
    if hashlib.sha256(Path(plan['unit_path']).read_bytes()).hexdigest() != plan['unit_proposed_sha256']:
        raise ValueError('installed collector unit changed')
    program = Path(plan['program']).resolve(strict=True)
    manifest_bytes = (program / 'sqlite-deployment-staging.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != program_manifest_sha256:
        raise ValueError('collector implementation manifest changed')
    frozen = json.loads(manifest_bytes)
    if not frozen.get('implementation_hashes'):
        raise ValueError('collector implementation inventory missing')
    for name, digest in frozen['implementation_hashes'].items():
        file = (program / name).resolve(strict=True)
        file.relative_to(program)
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError('collector implementation changed')
    if set(effective_configuration) != set(SERVICE_CONFIGURATION_FIELDS) | {'manager_environment_sha256'}:
        raise ValueError('complete effective service configuration required')
    environment = subprocess.run(['systemctl', '--user', 'show-environment'],
                                 check=True, text=True, capture_output=True).stdout
    environment_hash = hashlib.sha256('\n'.join(sorted(environment.splitlines())).encode()).hexdigest()
    if environment_hash != effective_configuration['manager_environment_sha256']:
        raise ValueError('collector inherited environment changed')
    actual = subprocess.run(['systemctl', '--user', 'show', '--all', plan['service'],
                             '--property=' + ','.join(('ActiveState', 'MainPID', 'WorkingDirectory', 'ExecStart',
                                                       *SERVICE_CONFIGURATION_FIELDS))],
                            check=True, text=True, capture_output=True).stdout
    properties = dict(line.split('=', 1) for line in actual.splitlines() if '=' in line)
    for key in SERVICE_CONFIGURATION_FIELDS:
        properties.setdefault(key, '')
    if {key: properties.get(key) for key in SERVICE_CONFIGURATION_FIELDS} != {
            key: effective_configuration[key] for key in SERVICE_CONFIGURATION_FIELDS}:
        raise ValueError('effective collector configuration changed')
    if properties['DropInPaths'] or properties['EnvironmentFiles']:
        raise ValueError('collector drop-ins or environment files require explicit support before retirement')
    if Path(properties['FragmentPath']).resolve() != Path(plan['unit_path']).resolve():
        raise ValueError('collector fragment path mismatch')
    saved = dict(line.split('=', 1) for line in deployment['installed_service'].splitlines() if '=' in line)
    if properties.get('ActiveState') != 'inactive' or properties.get('MainPID') != '0':
        raise ValueError('collector must remain stopped')
    if (properties.get('WorkingDirectory') != str(program) or
            not properties.get('ExecStart') or properties['ExecStart'] != saved.get('ExecStart')):
        raise ValueError('loaded collector configuration changed')
    return dict(state='INSTALLED_COLLECTOR_REVERIFIED', registry_sha256=registry_hash,
                index_sha256=index_evidence['index_sha256'], service=plan['service'],
                program_files=len(frozen['implementation_hashes']), raw_deletion_authorized=False)
