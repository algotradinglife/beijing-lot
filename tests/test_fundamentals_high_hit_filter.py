import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_high_hit_filter import high_hit_n6_plan


@pytest.fixture
def sample():
    frame = pd.DataFrame([dict(issue="001", slot=i, provider_id=str(i),
        handicap=0 if i <= 5 else -1, p_W=.60+i*.001, p_D=.25, p_L=.15-i*.001,
        q_W=.45, q_D=.20 if i <= 5 else .30, q_L=.35 if i <= 5 else .25)
        for i in range(1, 22)])
    cuts = {str(i): Cutoff.decision_epoch("001", "2010-01-01T00:00:00Z") for i in frame.slot}
    args = dict(cutoffs=cuts, budget_cny=1024, unit_cny=2, payout_factor=.65,
                pool_seed=41900, pool_size=128, design_seed=41901, design_draws=32)
    return frame, args


@pytest.mark.parametrize("exclude", [False, True])
def test_rebuild_complete_groups_and_filter(sample, exclude):
    frame, args = sample
    before = frame.copy(deep=True)
    result = high_hit_n6_plan(frame, exclude_zero_top2=exclude, **args)
    pd.testing.assert_frame_equal(frame, before)
    assert result == high_hit_n6_plan(frame, exclude_zero_top2=exclude, **args)
    assert result["seal"] == stable_json_hash({k:v for k,v in result.items() if k != "seal"})
    shape = result["shape_plan"]
    assert shape["groups"] > 0 and shape["stake"] == shape["groups"] * 64
    assert shape["stake"] + shape["cash_cny"] == 1024
    groups = []
    for g in range(1, shape["groups"]+1):
        legs = [l for l in shape["legs"] if l["group"] == g]
        assert len(legs) == 6 and sorted(len(l["support"]) for l in legs) == [1,2,2,2,2,2]
        assert {t["code"] for t in shape["tickets"] if t["group"] == g} == {
            "".join(c) for c in itertools.product(*(l["support"] for l in legs))}
        groups.append({l["slot"] for l in legs})
    assert max(Counter(s for g in groups for s in g).values()) <= 6
    assert all(len(a & b) <= 5 for a,b in itertools.combinations(groups,2))
    if exclude:
        assert result["exclusion"]["receipt"]["dropped_slots"] == [1,2,3,4,5]
        assert not ({1,2,3,4,5} & set().union(*groups))
    else:
        assert result["exclusion"] is None


def test_cutoffs_labels_and_small_pool_fail_closed(sample):
    frame, args = sample
    for bad in [dict(cutoffs={}), dict(budget_cny=512), dict(unit_cny=4),
                dict(payout_factor=1), dict(pool_seed=-1)]:
        with pytest.raises(ValueError):
            high_hit_n6_plan(frame, exclude_zero_top2=True, **{**args, **bad})
    with pytest.raises(ValueError):
        high_hit_n6_plan(frame, exclude_zero_top2=1, **args)
    with pytest.raises(ValueError):
        high_hit_n6_plan(frame.assign(actual_direction="W"), exclude_zero_top2=True, **args)
    small = frame.iloc[:10].copy()
    with pytest.raises(ValueError, match="Seven retained"):
        high_hit_n6_plan(small, exclude_zero_top2=True,
            **{**args, "cutoffs":{str(s):args["cutoffs"][str(s)] for s in small.slot}})
    all_bad = frame.iloc[:5].copy()
    with pytest.raises(ValueError, match="No retained"):
        high_hit_n6_plan(all_bad, exclude_zero_top2=True,
            **{**args, "cutoffs":{str(s):args["cutoffs"][str(s)] for s in all_bad.slot}})


def test_cutoff_identity_changes_receipts_not_outcomes(sample):
    frame, args = sample
    first = high_hit_n6_plan(frame, exclude_zero_top2=True, **args)
    earlier = {k:Cutoff.decision_epoch("001", "2009-01-01T00:00:00Z") for k in args["cutoffs"]}
    second = high_hit_n6_plan(frame, exclude_zero_top2=True, **{**args, "cutoffs":earlier})
    assert first["seal"] != second["seal"]
    assert first["shape_plan"]["tickets"] == second["shape_plan"]["tickets"]

def test_archived_report_restore_and_accounting(tmp_path):
    import gzip, hashlib, json, subprocess, sys
    from pathlib import Path
    fixture = Path("tests/fixtures/high_hit_filter.json.gz")
    package = json.loads(gzip.decompress(fixture.read_bytes()))
    assert all(hashlib.sha256(body.encode()).hexdigest() == package["hashes"][name]
               for name,body in package["files"].items())
    result = json.loads(package["files"]["results.json"])
    assert len(result["rows"]) == 192 and len(result["issue_order"]) == 48
    assert len({(r["issue"],r["policy"]) for r in result["rows"]}) == 192
    for row in result["rows"]:
        assert row["stake"] + row["cash_cny"] == 1024
        assert row["net"] == pytest.approx(row["gross"] - row["stake"])
        assert row["hits"] <= row["groups"] and row["stake"] == row["groups"] * 64
    original = [r for r in result["rows"] if r["policy"] == "N6_ORIGINAL"]
    assert sum(r["hits"] > 0 for r in original) == 41
    assert sum(r["net"] for r in original) == pytest.approx(11357.614784795136)
    assert sum(len(l["receipt"]["dropped_slots"]) for l in result["exclusion_ledgers"].values()) == 511
    out = tmp_path / "report"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py",
                    "--fixture",str(fixture),"--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text()) == result
