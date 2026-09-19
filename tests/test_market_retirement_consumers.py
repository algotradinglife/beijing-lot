import hashlib
import json
from types import SimpleNamespace

import pytest
import src.market_retirement_consumers as module


def test_installed_collector_requires_current_inputs_and_stopped_service(tmp_path, monkeypatch):
    (tmp_path/'registry').mkdir()
    index=tmp_path/'index.json';index.write_text('{}')
    registry=dict(index='index.json',service='collector.service')
    raw=json.dumps(registry).encode();(tmp_path/'registry/markets-current.json').write_bytes(raw)
    registry_hash=hashlib.sha256(raw).hexdigest()
    program=tmp_path/'program';program.mkdir();(program/'worker.py').write_text('pass')
    (program/'sqlite-deployment-staging.json').write_text(json.dumps(dict(implementation_hashes={
        'worker.py':hashlib.sha256(b'pass').hexdigest()})))
    manifest_sha=hashlib.sha256((program/'sqlite-deployment-staging.json').read_bytes()).hexdigest()
    unit=tmp_path/'unit';unit.write_text('unit')
    service=f'ActiveState=inactive\nMainPID=0\nWorkingDirectory={program}\nExecStart=worker\n'
    effective={key:'' for key in module.SERVICE_CONFIGURATION_FIELDS}
    effective['FragmentPath']=str(unit)
    effective['manager_environment_sha256']=hashlib.sha256(b'MANAGER=value').hexdigest()
    service+=''.join(f'{key}={value}\n' for key,value in effective.items())
    deployment=dict(state='COLLECTOR_CONFIG_DEPLOYED_SERVICE_STOPPED',registry_sha256=registry_hash,
        installed_service=service,plan=dict(service='collector.service',unit_path=str(unit),
        unit_proposed_sha256=hashlib.sha256(b'unit').hexdigest(),program=str(program)))
    evidence=dict(state='ACTIVE_CAPTURE_INDEX_SQLITE_READBACK_VERIFIED',registry_sha256=registry_hash,
        index_path=str(index),index_sha256=hashlib.sha256(b'{}').hexdigest())
    manager='MANAGER=value'
    monkeypatch.setattr(module.subprocess,'run',lambda args,**kwargs:SimpleNamespace(stdout=manager if 'show-environment' in args else service))
    assert module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)['program_files']==1
    manager='PYTHONPATH=/unexpected'
    with pytest.raises(ValueError,match='inherited environment changed'):
        module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)
    manager='MANAGER=value'
    original_service=service
    service=service.replace('Environment=\n','Environment=PYTHONPATH=/unexpected\n')
    with pytest.raises(ValueError,match='effective collector configuration changed'):
        module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)
    service=original_service.replace('inactive','active')
    with pytest.raises(ValueError,match='remain stopped'):
        module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)
    service=service.replace('active','inactive').replace('ExecStart=worker','ExecStart=other')
    with pytest.raises(ValueError,match='loaded collector'):
        module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)
    index.write_text('changed')
    with pytest.raises(ValueError,match='index changed'):
        module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)

    index.write_text('{}')
    (program/'sqlite-deployment-staging.json').write_text('{}')
    with pytest.raises(ValueError,match='manifest changed'):
        module.verify_retirement_collector(tmp_path,deployment=deployment,index_evidence=evidence,program_manifest_sha256=manifest_sha,effective_configuration=effective)
