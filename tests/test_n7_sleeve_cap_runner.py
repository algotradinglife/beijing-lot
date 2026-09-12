"""Audit access must follow a complete immutable cap/control grid."""
import gzip,hashlib,json,runpy,sys
from pathlib import Path
import pytest
import src.n7_sleeve_probability_cap
import src.temporal_learning
import src.temporal_learning.provenance
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('failure',['none','initial_hash','later_mutation'])
@pytest.mark.parametrize('policy_count',[1,4])
def test_cap_runner_freezes_before_settlement(tmp_path,monkeypatch,failure,policy_count):
    cfg=json.loads(Path('config/n7_sleeve_probability_cap.json').read_text())
    origin=tmp_path/'origin';(origin/'bundles').mkdir(parents=True);(origin/'plans').mkdir()
    cfg.update(origin=str(origin),pool_sizes=[24],seeds=[1])
    cfg['policies']=[dict(arm=f'POLICY_{i}',max_fixture_reuse=3 if i else None,max_pair_overlap=2 if i else None) for i in range(policy_count)]
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    bundles={};plans={}
    for issue in ('001','002'):
        path=origin/'bundles'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(dict(issue=issue,cutoffs={'0':'2010-01-01T00:00:00+00:00'})).encode()))
        bundles[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        path=origin/'plans'/f'{issue}_24_EXPECTED_GROSS_1.json.gz';path.write_bytes(gzip.compress(b'{}'))
        plans[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    if failure=='initial_hash':bundles[str(origin/'bundles'/'001.json.gz')]='wrong'
    fr=dict(issues=['001','002'],source_hashes={},bundle_hashes=bundles,plan_hashes=plans,parameters=cfg,implementation={})
    parent=dict(receipt=fr,seal=stable_json_hash(fr));(origin/'plans-frozen.json').write_text(json.dumps(parent))
    (origin/'independent-replay.json').write_text(json.dumps(dict(freeze=parent['seal'],checked=1800,candidates=96000,implementation={})))
    output=tmp_path/'out';events=[];original_read=Path.read_bytes
    class AuditOpened(Exception):pass
    def guarded_read(path):
        if path==origin/'evaluation-receipt.json':
            events.append('audit');frozen=json.loads((output/'plans-frozen.json').read_text())
            assert len(frozen['receipt']['entries'])==len(frozen['receipt']['plan_hashes'])==2*(policy_count+1)
            assert all(Path(p).exists() for p in frozen['receipt']['plan_hashes'])
            raise AuditOpened
        return original_read(path)
    def sampler(bundle,**kwargs):
        if failure=='later_mutation':(origin/'bundles'/'001.json.gz').write_bytes(b'changed')
        return dict(issue=bundle['issue'])
    monkeypatch.setattr(Path,'read_bytes',guarded_read)
    monkeypatch.setattr(src.n7_sleeve_probability_cap,'sample_capped_sleeves',sampler)
    monkeypatch.setattr(src.temporal_learning,'verify_implementation_closure',lambda *args:None)
    monkeypatch.setattr(src.temporal_learning.provenance,'implementation_closure',lambda *args,**kwargs:{})
    monkeypatch.setattr(sys,'argv',['runner','--output',str(output),'--config',str(config)])
    with pytest.raises(AuditOpened if failure=='none' else ValueError):runpy.run_module('scripts.replay_n7_sleeve_probability_cap',run_name='__main__')
    assert events==(['audit'] if failure=='none' else [])
