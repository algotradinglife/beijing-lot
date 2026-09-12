"""Runner ordering regression; numerical functions tested with real inputs elsewhere."""
import concurrent.futures
import gzip,hashlib,json,runpy,sys
from pathlib import Path
import pytest
import src.n7_sleeve_candidates
import src.n7_sleeve_portfolio
import src.temporal_learning
import src.temporal_learning.provenance
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('failure',['none','initial_hash','later_mutation'])
def test_every_plan_freezes_before_settlement_access(tmp_path,monkeypatch,failure):
    cfg=json.loads(Path('config/n7_sleeve_424.json').read_text());origin=tmp_path/'origin';pools=tmp_path/'pools'
    origin.mkdir();pools.mkdir();sources={}
    for issue in ('001','002'):
        path=pools/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(dict(issue=issue,cutoffs={'0':'2010-01-01T00:00:00+00:00'})).encode()))
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    if failure=='initial_hash':sources[str(pools/'001.json.gz')]='wrong'
    r=dict(issues=['001','002'],source_hashes=sources,implementation={})
    (origin/'plans-frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    cfg.update(origin=str(origin),pool_root=str(pools));config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    output=tmp_path/'out';events=[]
    class SettlementOpened(Exception):pass
    original_read=Path.read_bytes
    def guarded_read(path):
        if path==origin/'evaluation-receipt.json':
            events.append('settlement')
            frozen=json.loads((output/'plans-frozen.json').read_text())
            assert len(frozen['receipt']['plan_hashes'])==2*len(cfg['seeds'])*len(cfg['arms'])
            assert all(Path(p).exists() for p in frozen['receipt']['plan_hashes'])
            raise SettlementOpened
        return original_read(path)
    def builder(pool,**kwargs):
        if failure=='later_mutation' and pool['issue']=='001':(pools/'001.json.gz').write_bytes(b'changed')
        return pool
    def constructor(bundle,**kwargs):return dict(plans=[dict(arm=a) for a in cfg['arms']],sleeve_simulation=[])
    class ImmediateExecutor:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def submit(self,fn,*args,**kwargs):
            f=concurrent.futures.Future();f.set_result(fn(*args,**kwargs));return f
    monkeypatch.setattr(Path,'read_bytes',guarded_read)
    monkeypatch.setattr(concurrent.futures,'ProcessPoolExecutor',ImmediateExecutor)
    monkeypatch.setattr(src.n7_sleeve_candidates,'build_sleeve_candidates',builder)
    monkeypatch.setattr(src.n7_sleeve_portfolio,'sleeve_portfolios',constructor)
    monkeypatch.setattr(src.temporal_learning,'verify_implementation_closure',lambda *args:None)
    monkeypatch.setattr(src.temporal_learning.provenance,'implementation_closure',lambda *args,**kwargs:{})
    monkeypatch.setattr(sys,'argv',['runner','--output',str(output),'--config',str(config)])
    with pytest.raises(SettlementOpened if failure=='none' else ValueError):
        runpy.run_module('scripts.replay_n7_sleeves',run_name='__main__')
    assert events==(['settlement'] if failure=='none' else [])
