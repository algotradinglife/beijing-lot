import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement

def test_top2_sets_not_top1_and_handicap_boundary():
    rows=[]
    for slot,h,p,q in [
        (1,0,(.5,.3,.2),(.3,.5,.2)),
        (2,0,(.5,.3,.2),(.5,.2,.3)),
        (3,1,(.5,.3,.2),(.5,.2,.3)),
        (4,-1,(.5,.3,.2),(.5,.2,.3)),
        (5,0,(.4,.3,.3),(.4,.3,.3)),
    ]:
        rows.append(dict(issue="001",slot=slot,provider_id=str(slot),handicap=h,
            **dict(zip(["p_W","p_D","p_L"],p)),**dict(zip(["q_W","q_D","q_L"],q))))
    f=pd.DataFrame(rows);before=f.copy(deep=True)
    cuts={str(s):Cutoff.decision_epoch("001","2010-01-01T00:00:00Z") for s in f.slot}
    z,r=exclude_zero_top2_disagreement(f,cutoffs=cuts)
    assert list(z.slot)==[1,3,4,5] and r["receipt"]["dropped_slots"]==[2]
    assert r["receipt"]["input_count"]==5 and r["receipt"]["retained_count"]==4
    pd.testing.assert_frame_equal(f,before)
    with pytest.raises(ValueError):exclude_zero_top2_disagreement(f,cutoffs={})
    with pytest.raises(ValueError):exclude_zero_top2_disagreement(f.assign(actual_direction="W"),cutoffs=cuts)
    with pytest.raises(ValueError,match="No retained"):
        exclude_zero_top2_disagreement(f[f.slot==2],cutoffs={"2":cuts["2"]})

@pytest.mark.parametrize("design,expected",[("paired",192),("independent",384)])
def test_report_archive_and_global_exclusion(tmp_path,design,expected):
    import gzip,json,hashlib,subprocess,sys
    from pathlib import Path
    fixture=Path("tests/fixtures/candidate_exclusion_"+design+".json.gz")
    saved=json.loads(gzip.decompress(fixture.read_bytes()))
    assert all(hashlib.sha256(body.encode()).hexdigest()==saved["hashes"][name] for name,body in saved["files"].items())
    target=tmp_path/design
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",str(fixture),"--output",str(target)],check=True)
    result=json.loads((target/"results.json").read_text())
    assert len(result["rows"])==expected
    ledgers=result["filter_ledgers"]
    assert sum(v["receipt"]["input_count"]-v["receipt"]["retained_count"] for v in ledgers.values())==511
    for leg in result["legs"]:
        assert leg["slot"] not in ledgers[leg["issue"]]["receipt"]["dropped_slots"]
    assert all(row["stake"]+row["cash_cny"]==1024 for row in result["rows"])
