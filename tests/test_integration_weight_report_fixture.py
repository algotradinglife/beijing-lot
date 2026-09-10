import hashlib,json,subprocess,sys
from pathlib import Path


def test_saved_report_fixture_binds_bytes_and_refuses_overwrite(tmp_path):
    output=tmp_path/'report'
    command=[sys.executable,'scripts/prepare_integration_weight_report_fixture.py','--output',str(output)]
    subprocess.run(command,check=True,capture_output=True)
    receipt=json.loads((output/'independent-check.json').read_text())
    assert receipt['fixture_mode']=='ARCHIVED_RENDER_ONLY_ORIGINAL_REPLAY_NOT_RERUN'
    for name,h in receipt['source_hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
    assert subprocess.run(command,capture_output=True).returncode!=0
