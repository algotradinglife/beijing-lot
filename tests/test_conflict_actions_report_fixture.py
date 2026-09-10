"""Offline report archive is explicit, immutable and identical to reviewed data."""
import gzip,hashlib,json,subprocess,sys
from pathlib import Path


def test_report_fixture_hashes_model_identity_and_immutable_output(tmp_path):
    root=Path(__file__).resolve().parents[1]
    saved=json.loads(gzip.decompress((root/'tests/fixtures/conflict_actions_report.json.gz').read_bytes()))
    assert saved['original_check']['plans_checked']==480
    assert saved['original_check']['attribution_plans_checked']==40
    assert saved['original_check']['prediction_metrics_checked']==6939
    out=tmp_path/'fixture'
    command=[sys.executable,'scripts/prepare_conflict_actions_report_fixture.py','--output',str(out)]
    subprocess.run(command,cwd=root,check=True,capture_output=True)
    check=json.loads((out/'independent-check.json').read_text())
    assert check['fixture_mode']=='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY'
    for name,body in saved['files'].items():
        assert hashlib.sha256(body.encode()).hexdigest()==saved['hashes'][name]
        assert (out/name).read_text()==body
        rows=json.loads(body)
        assert rows['contract']['draw_version']=='1.1.0'
        assert rows['contract']['draw_weight']==rows['contract']['high_weight']==.5
        assert not rows['historical_admission']
    assert subprocess.run(command,cwd=root,capture_output=True).returncode!=0
