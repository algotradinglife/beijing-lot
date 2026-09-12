"""Independent replay detects arithmetic, identity and risk mutations."""
from pathlib import Path
import copy
import gzip
import hashlib
import json

import numpy as np
import pytest

from src.n7_joint_check import check_joint_plan, check_joint_study
from src.temporal_learning import implementation_closure
from src.temporal_learning.core import stable_json_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def replay_case():
    cfg = json.loads((ROOT / "config/n7_joint_424.json").read_text())
    cfg.update(training_worlds=10, evaluation_worlds=10)
    canonical = np.indices((3,) * 7).reshape(7, -1).T
    p = np.array([.5, .3, .2]); mass = np.prod(p[canonical], axis=1)
    selected = np.lexsort((np.arange(2187), -mass))[:64]
    f = [dict(issue="010101", slot=i + 1, provider_id=f"{i+1:06}", handicap=0,
              **{f"{prefix}_{d}": float(p[j]) for prefix in "pq" for j, d in enumerate("WDL")}) for i in range(56)]
    cuts = {str(i + 1): "2010-01-01T00:00:00+00:00" for i in range(56)}
    ix = np.vstack([np.tile(np.arange(j * 7, j * 7 + 7), (64, 1)) for j in range(8)])
    code = np.tile(canonical[selected], (8, 1))
    keys = [dict(sleeve_id=j, rule="PROB", state_ids=selected.tolist(),
                 coverage=float(mass[selected].sum()), expected_gross=83.2) for j in range(8)]
    plan = dict(issue="010101", seed=42401, arm="JOINT_FULL", fixtures=f, cutoffs=cuts,
        fixture_indices=ix.tolist(), outcomes=code.tolist(), groups=512, stake=1024, cash_cny=0,
        budget_cny=1024, unit_cny=2, payout_factor=.65, historical_admission=False,
        solver_status="Optimal", solver=dict(mip_gap=0.), expected_net=665.6-1024,
        expected_roi=-.35, sleeve_keys=keys, max_reuse=1, max_overlap=0,
        mean_sleeve_coverage=float(mass[selected].sum()), train_coverage=1., eval_coverage=1.,
        train_path_drawdown=0., eval_path_drawdown=0.)
    plan["seal"] = stable_json_hash(plan)
    worlds = dict(seed=42401, training=np.zeros((10, 56), dtype=int).tolist(), evaluation=np.zeros((10, 56), dtype=int).tolist())
    return plan, worlds, cfg


def test_replay_and_mutations(replay_case):
    plan, worlds, cfg = replay_case
    assert check_joint_plan(plan, worlds, cfg)["eval_coverage"] == 1
    for field, value, message in [("expected_net", 0, "return arithmetic"),
                                  ("eval_coverage", .5, "union"),
                                  ("train_path_drawdown", 3, "drawdown"),
                                  ("max_reuse", 2, "U/P"),
                                  ("payout_factor", 1., "budget"),
                                  ("solver_status", "Iteration limit reached", "incumbent")]:
        bad = copy.deepcopy(plan); bad[field] = value
        bad["seal"] = stable_json_hash({k: v for k, v in bad.items() if k != "seal"})
        with pytest.raises(ValueError, match=message):
            check_joint_plan(bad, worlds, cfg)
    bad = copy.deepcopy(plan); bad["outcomes"][1] = bad["outcomes"][0]
    bad["seal"] = stable_json_hash({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(ValueError, match="identity"):
        check_joint_plan(bad, worlds, cfg)
    bad_worlds = copy.deepcopy(worlds); bad_worlds["evaluation"][0][0] = 4
    with pytest.raises(ValueError, match="Scenario"):
        check_joint_plan(plan, bad_worlds, cfg)
    bad = copy.deepcopy(plan); bad["sleeve_keys"][0]["expected_gross"] += 10
    bad["seal"] = stable_json_hash({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(ValueError, match="Sleeve expected return"):
        check_joint_plan(bad, worlds, cfg)
    bad = copy.deepcopy(plan); bad["fixture_indices"][0][0] = .5
    bad["seal"] = stable_json_hash({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(ValueError, match="Integer"):
        check_joint_plan(bad, worlds, cfg)


@pytest.mark.parametrize("source_change, accepted", [(None, True), ("roundoff", True),
    ("probability", False), ("identity", False)])
def test_all_plan_replay_binds_source_and_raw_files(tmp_path, replay_case, source_change, accepted):
    plan, worlds, cfg = replay_case
    (tmp_path / "plans").mkdir(); (tmp_path / "raw").mkdir(); (tmp_path / "bundles").mkdir()
    pp = tmp_path / "plans" / f"{plan['issue']}_{plan['seed']}_{plan['arm']}.json.gz"
    pp.write_bytes(gzip.compress(json.dumps(plan).encode()))
    rp = tmp_path / "raw" / "issue.json.gz"
    rp.write_bytes(gzip.compress(json.dumps(dict(plans=[plan], worlds=[worlds])).encode()))
    bp = tmp_path / "bundles" / "issue.json.gz"
    source_fixtures = copy.deepcopy(plan["fixtures"])
    if source_change == "roundoff":
        source_fixtures[0]["p_D"] += 3e-16
    elif source_change == "probability":
        source_fixtures[0]["p_D"] += 1e-8
    elif source_change == "identity":
        source_fixtures[0]["provider_id"] = "WRONG"
    bp.write_bytes(gzip.compress(json.dumps(dict(issue=plan["issue"], cutoffs=plan["cutoffs"],
        expanded_pool=dict(fixtures=source_fixtures), sleeves=[dict(id=j, fixture_indices=list(range(j * 7, j * 7 + 7))) for j in range(8)])).encode()))
    receipt = dict(parameters=cfg, source_hashes={str(bp): hashlib.sha256(bp.read_bytes()).hexdigest()},
        r_implementation={}, implementation=implementation_closure(ROOT, ["src.temporal_learning"]),
        plan_hashes={str(pp): hashlib.sha256(pp.read_bytes()).hexdigest()},
        raw_hashes={str(rp): hashlib.sha256(rp.read_bytes()).hexdigest()}, cutoffs={plan["issue"]: plan["cutoffs"]})
    (tmp_path / "plans-frozen.json").write_text(json.dumps(dict(receipt=receipt, seal=stable_json_hash(receipt))))
    if not accepted:
        with pytest.raises(ValueError, match="probabilities/identities"):
            check_joint_study(tmp_path, repository_root=ROOT)
        return
    assert check_joint_study(tmp_path, repository_root=ROOT)["plans_checked"] == 1
    rp.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Raw R output"):
        check_joint_study(tmp_path, repository_root=ROOT)
