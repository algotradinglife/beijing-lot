"""Orchestration boundary: all plans frozen before any target audit is read."""
import concurrent.futures
import gzip,hashlib,json,runpy,sys
from pathlib import Path
import pytest
import src.n7_sleeve_expansion
import src.temporal_learning
import src.temporal_learning.provenance
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('failure',['none','initial_hash','later_mutation'])
def test_expansion_freeze_before_audit(tmp_path,monkeypatch,failure):
    cfg=json.loads(Path('config/n7_sleeve_expansion.json').read_text())
    origin=tmp_path/'origin';old=tmp_path/'old';pools=tmp_path/'pools';output=tmp_path/'out'
    origin.mkdir();(old/'bundles').mkdir(parents=True);pools.mkdir();sources={};bundles={}
    for issue in ('001','002'):
        p=dict(issue=issue,seal='pool',cutoffs={'0':'2010-01-01T00:00:00+00:00'})
        path=pools/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(p).encode()))
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        b=dict(prior_pool_seal='pool',cutoffs=p['cutoffs'],sleeves=[dict(fixture_indices=list(range(7)))]*24)
        path=old/'bundles'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(b).encode()))
        bundles[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    if failure=='initial_hash':sources[str(pools/'001.json.gz')]='wrong'
    for base,r in ((origin,dict(issues=['001','002'],source_hashes=sources,implementation={})),
                   (old,dict(issues=['001','002'],bundle_hashes=bundles,implementation={}))):
        (base/'plans-frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    cfg.update(origin=str(origin),prior_study=str(old),pool_root=str(pools),pool_sizes=[24,30],seeds=[1])
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg));events=[]
    class SettlementOpened(Exception):pass
    original_read=Path.read_bytes
    def guarded_read(path):
        if path==origin/'evaluation-receipt.json':
            events.append('settlement');frozen=json.loads((output/'plans-frozen.json').read_text())
            assert len(frozen['receipt']['plan_hashes'])==8
            assert all(Path(p).exists() for p in frozen['receipt']['plan_hashes'])
            raise SettlementOpened
        return original_read(path)
    def builder(pool,**kwargs):
        if failure=='later_mutation':(pools/'001.json.gz').write_bytes(b'changed')
        return dict(pool,sleeves=[dict(coverage=.2)]*30)
    def sampler(bundle,**kwargs):return dict(issue=bundle['issue'])
    class ImmediateExecutor:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def submit(self,fn,*args,**kwargs):
            f=concurrent.futures.Future();f.set_result(fn(*args,**kwargs));return f
    monkeypatch.setattr(Path,'read_bytes',guarded_read)
    monkeypatch.setattr(concurrent.futures,'ProcessPoolExecutor',ImmediateExecutor)
    monkeypatch.setattr(src.n7_sleeve_expansion,'expand_top64',builder)
    monkeypatch.setattr(src.n7_sleeve_expansion,'sample_top64',sampler)
    monkeypatch.setattr(src.temporal_learning,'verify_implementation_closure',lambda *args:None)
    monkeypatch.setattr(src.temporal_learning.provenance,'implementation_closure',lambda *args,**kwargs:{})
    monkeypatch.setattr(sys,'argv',['runner','--output',str(output),'--config',str(config)])
    with pytest.raises(SettlementOpened if failure=='none' else ValueError):
        runpy.run_module('scripts.replay_n7_sleeve_expansion',run_name='__main__')
    assert events==(['settlement'] if failure=='none' else [])
