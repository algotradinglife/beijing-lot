"""Offline orchestration contract tests; numerical R tests live in testthat."""
from pathlib import Path
import copy
import gzip
import hashlib
import json
from types import SimpleNamespace

import pytest

import src.n7_joint_study as study
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_bundle():
    e = json.loads(gzip.decompress((ROOT / "tests/fixtures/n7_sleeve_numerical.json.gz").read_bytes()))["enumeration"]
    bundle = dict(issue=e["issue"], cutoffs=e["cutoffs"], expanded_pool=dict(fixtures=e["fixtures"]),
                  historical_admission=False)
    return dict(bundle, seal=stable_json_hash(bundle))


def empty_result(bundle, seeds, arms):
    plans = []
    for seed in seeds:
        for arm in arms:
            p = dict(issue=bundle["issue"], seed=seed, arm=arm, fixtures=bundle["expanded_pool"]["fixtures"],
                cutoffs=bundle["cutoffs"], fixture_indices=[], outcomes=[], groups=0, stake=0,
                cash_cny=1024, budget_cny=1024, unit_cny=2, payout_factor=.65, historical_admission=False,
                train_coverage=0., eval_coverage=0., train_path_drawdown=0., eval_path_drawdown=0.,
                expected_roi=None, max_reuse=0, max_overlap=0, solver_status="Infeasible", mean_sleeve_coverage=None)
            plans.append(p)
    return dict(plans=plans, frontier_status=[], cutoffs=bundle["cutoffs"], historical_admission=False)


def test_r_boundary_rejects_cutoffs_and_source_mutation(tmp_path, monkeypatch, fixture_bundle):
    bundle = fixture_bundle; path = tmp_path / "bundle.json.gz"
    path.write_bytes(gzip.compress(json.dumps(bundle).encode()))
    cuts = {s: Cutoff.decision_epoch(bundle["issue"], t) for s, t in bundle["cutoffs"].items()}
    result = empty_result(bundle, [1], ["QUALITY_PROB"])

    def invoke(command, **kwargs):
        assert command[:3] == ["Rscript", "--vanilla", "scripts/run_n7_joint_issue.R"]
        Path(command[5]).write_text(json.dumps(result))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(study.subprocess, "run", invoke)
    out = tmp_path / "out.json"
    got = study.run_joint_issue(path, tmp_path / "config.json", out, cutoffs=cuts,
        repository_root=ROOT, python="explicit-python", rscript="Rscript")
    plan = got["plans"][0]
    assert plan["seal"] == stable_json_hash({k: v for k, v in plan.items() if k != "seal"})
    with pytest.raises(ValueError, match="overwrite"):
        study.run_joint_issue(path, tmp_path / "config.json", out, cutoffs=cuts,
            repository_root=ROOT, python="explicit-python", rscript="Rscript")
    with pytest.raises(ValueError, match="cutoff"):
        study.run_joint_issue(path, tmp_path / "config.json", tmp_path / "bad.json", cutoffs={},
            repository_root=ROOT, python="explicit-python", rscript="Rscript")
    bad_cuts = {s: Cutoff.decision_epoch("wrong", t) for s, t in bundle["cutoffs"].items()}
    with pytest.raises(ValueError, match="Native target"):
        study.run_joint_issue(path, tmp_path / "config.json", tmp_path / "bad.json", cutoffs=bad_cuts,
            repository_root=ROOT, python="explicit-python", rscript="Rscript")
    bundle["expanded_pool"]["fixtures"][0]["p_W"] += .1
    path.write_bytes(gzip.compress(json.dumps(bundle).encode()))
    with pytest.raises(ValueError, match="bundle changed"):
        study.run_joint_issue(path, tmp_path / "config.json", tmp_path / "bad.json", cutoffs=cuts,
            repository_root=ROOT, python="explicit-python", rscript="Rscript")


def test_freeze_precedes_labels_and_evaluation_cannot_rewrite_plans(tmp_path, monkeypatch, fixture_bundle):
    bundle = fixture_bundle; issue = bundle["issue"]
    source = tmp_path / "source"; (source / "bundles").mkdir(parents=True)
    path = source / "bundles" / f"{issue}.json.gz"
    path.write_bytes(gzip.compress(json.dumps(bundle).encode()))
    prior_receipt = dict(issues=[issue], historical_admission=False,
                         bundle_hashes={str(path): hashlib.sha256(path.read_bytes()).hexdigest()})
    prior = dict(receipt=prior_receipt, seal=stable_json_hash(prior_receipt))
    (source / "plans-frozen.json").write_text(json.dumps(prior))
    cfg = dict(seeds=[42], arms=["QUALITY_PROB"], workers=1,
               provenance_roots=["src.n7_joint_study", "src.temporal_learning"])
    config = tmp_path / "config.json"; config.write_text(json.dumps(cfg))

    def run(*args, **kwargs):
        assert not (source / "evaluation-receipt.json").exists()
        result = empty_result(bundle, cfg["seeds"], cfg["arms"])
        for p in result["plans"]:
            p["seal"] = stable_json_hash(p)
        return result

    monkeypatch.setattr(study, "run_joint_issue", run)
    output = tmp_path / "study"
    frozen = study.freeze_joint_study(source, output, config, repository_root=ROOT,
        python="unused", rscript="unused")
    assert len(frozen["receipt"]["plan_hashes"]) == 1
    original_plans = {p: Path(p).read_bytes() for p in frozen["receipt"]["plan_hashes"]}
    # Labels did not even exist until every plan was frozen.
    audit = source / "audit-snapshot.json"; audit.write_text(json.dumps(dict(rows=[dict(issue=issue)])))
    controls = [dict(issue=issue, seed=42, arm=a) for a in ("MONOLITHIC_PROB512", "MONOLITHIC_COVERAGE512")]
    (source / "results.json").write_text(json.dumps(dict(rows=controls)))
    er = dict(freeze_sha256=hashlib.sha256((source / "plans-frozen.json").read_bytes()).hexdigest(),
        audit_path=str(audit), audit_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256((source / "results.json").read_bytes()).hexdigest())
    (source / "evaluation-receipt.json").write_text(json.dumps(er))
    result = study.evaluate_joint_study(source, output, repository_root=ROOT)
    assert len(result["rows"]) == 3
    assert result["rows"][0]["status"] == "NO_BET"
    assert result["rows"][0]["net"] == 0
    assert all(Path(p).read_bytes() == raw for p, raw in original_plans.items())
    with pytest.raises(ValueError, match="already frozen"):
        study.evaluate_joint_study(source, output, repository_root=ROOT)
    # Replaying with changed raw input must stop, not update old receipts.
    (output / "evaluation-receipt.json").unlink()
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="source changed"):
        study.evaluate_joint_study(source, output, repository_root=ROOT)


@pytest.mark.parametrize("worker_error", [False, True])
def test_incomplete_grid_never_gets_a_freeze_receipt(tmp_path, monkeypatch, fixture_bundle, worker_error, capsys):
    source = tmp_path / "source"; (source / "bundles").mkdir(parents=True)
    issue = fixture_bundle["issue"]; path = source / "bundles" / f"{issue}.json.gz"
    path.write_bytes(gzip.compress(json.dumps(fixture_bundle).encode()))
    receipt = dict(issues=[issue], historical_admission=False,
                   bundle_hashes={str(path): hashlib.sha256(path.read_bytes()).hexdigest()})
    (source / "plans-frozen.json").write_text(json.dumps(dict(receipt=receipt, seal=stable_json_hash(receipt))))
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps(dict(seeds=[42], arms=["QUALITY_PROB"], workers=1,
        provenance_roots=["src.n7_joint_study", "src.temporal_learning"])))
    def run(*args, **kwargs):
        if worker_error:
            raise ValueError("Worker failed")
        return dict(plans=[], frontier_status=[])
    monkeypatch.setattr(study, "run_joint_issue", run)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Worker failed" if worker_error else "Incomplete"):
        study.freeze_joint_study(source, out, config, repository_root=ROOT, python="unused", rscript="unused")
    assert not (out / "plans-frozen.json").exists()
    if worker_error:
        assert "cancelling queued issues" in capsys.readouterr().out
