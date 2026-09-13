"""Offline orchestration contract tests; numerical R tests live in testthat."""
from pathlib import Path
import copy
import gzip
import hashlib
import json
import gc
import weakref
from types import SimpleNamespace

import pytest

import src.n7_joint_study as study
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash

ROOT = Path(__file__).resolve().parents[1]


def test_completed_issue_futures_are_released_before_study_finishes(tmp_path, monkeypatch, fixture_bundle):
    source = tmp_path / 'source'; (source / 'bundles').mkdir(parents=True)
    bundles = {}; hashes = {}
    for issue in ('100101', '100102', '100103'):
        bundle = copy.deepcopy(fixture_bundle); bundle['issue'] = issue
        bundle['seal'] = stable_json_hash({k:v for k,v in bundle.items() if k != 'seal'})
        path = source / 'bundles' / f'{issue}.json.gz'
        path.write_bytes(gzip.compress(json.dumps(bundle).encode()))
        bundles[issue] = bundle; hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = dict(issues=list(bundles), historical_admission=False, bundle_hashes=hashes)
    (source / 'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt, seal=stable_json_hash(receipt))))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(dict(seeds=[42], arms=['QUALITY_PROB'], workers=1,
        provenance_roots=['src.n7_joint_study', 'src.temporal_learning'])))

    def run(path, *args, **kwargs):
        result = empty_result(bundles[path.name.removesuffix('.json.gz')], [42], ['QUALITY_PROB'])
        for plan in result['plans']: plan['seal'] = stable_json_hash(plan)
        return result

    original = study.as_completed
    observed = []
    def watch(futures):
        iterator = original(futures)
        first = next(iterator); ref = weakref.ref(first)
        yield first
        del first
        second = next(iterator)
        yield second
        del second
        gc.collect()
        observed.append(ref() is None)
        yield from iterator

    monkeypatch.setattr(study, 'run_prefix_issue', run)
    monkeypatch.setattr(study, 'as_completed', watch)
    frozen = study.freeze_prefix_study(source, tmp_path / 'output', config, repository_root=ROOT,
        python='unused', rscript='unused', entry_point='scripts/run_n7_joint_issue.R', r_sources=study.JOINT_R_SOURCES)
    assert observed == [True]
    assert len(frozen['receipt']['plan_hashes']) == 3


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
    got = study.run_prefix_issue(path, tmp_path / "config.json", out, cutoffs=cuts,
        repository_root=ROOT, python="explicit-python", rscript="Rscript", entry_point="scripts/run_n7_joint_issue.R")
    plan = got["plans"][0]
    assert plan["seal"] == stable_json_hash({k: v for k, v in plan.items() if k != "seal"})
    for entry in ("../escape.R", "src/n7_joint_study.py", "scripts/missing.R"):
        with pytest.raises(ValueError, match="entry point"):
            study.run_prefix_issue(path, tmp_path / "config.json", tmp_path / "invalid.json",
                cutoffs=cuts, repository_root=ROOT, python="explicit-python", rscript="Rscript",
                entry_point=entry)
    with pytest.raises(ValueError, match="overwrite"):
        study.run_prefix_issue(path, tmp_path / "config.json", out, cutoffs=cuts,
            repository_root=ROOT, python="explicit-python", rscript="Rscript", entry_point="scripts/run_n7_joint_issue.R")
    with pytest.raises(ValueError, match="cutoff"):
        study.run_prefix_issue(path, tmp_path / "config.json", tmp_path / "bad.json", cutoffs={},
            repository_root=ROOT, python="explicit-python", rscript="Rscript", entry_point="scripts/run_n7_joint_issue.R")
    bad_cuts = {s: Cutoff.decision_epoch("wrong", t) for s, t in bundle["cutoffs"].items()}
    with pytest.raises(ValueError, match="Native target"):
        study.run_prefix_issue(path, tmp_path / "config.json", tmp_path / "bad.json", cutoffs=bad_cuts,
            repository_root=ROOT, python="explicit-python", rscript="Rscript", entry_point="scripts/run_n7_joint_issue.R")
    bundle["expanded_pool"]["fixtures"][0]["p_W"] += .1
    path.write_bytes(gzip.compress(json.dumps(bundle).encode()))
    with pytest.raises(ValueError, match="bundle changed"):
        study.run_prefix_issue(path, tmp_path / "config.json", tmp_path / "bad.json", cutoffs=cuts,
            repository_root=ROOT, python="explicit-python", rscript="Rscript", entry_point="scripts/run_n7_joint_issue.R")


@pytest.mark.parametrize("core_layers", [False, True])
def test_freeze_precedes_labels_and_evaluation_cannot_rewrite_plans(tmp_path, monkeypatch, fixture_bundle, core_layers):
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
    if core_layers:
        cfg["provenance_roots"].append("src.n7_core_settlement")
    config = tmp_path / "config.json"; config.write_text(json.dumps(cfg))

    def run(*args, **kwargs):
        assert not (source / "evaluation-receipt.json").exists()
        result = empty_result(bundle, cfg["seeds"], cfg["arms"])
        for p in result["plans"]:
            if core_layers:
                p.update(schema="CORE_COPY_LAYERS_V1", layers=[], unique_tickets=0)
            p["seal"] = stable_json_hash(p)
        return result

    monkeypatch.setattr(study, "run_prefix_issue", run)
    output = tmp_path / "study"
    frozen = study.freeze_prefix_study(source, output, config, repository_root=ROOT,
        python="unused", rscript="unused",
        entry_point="scripts/run_n7_joint_issue.R", r_sources=study.JOINT_R_SOURCES)
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
    with pytest.raises(ValueError, match="callback is not bound"):
        study.evaluate_prefix_study(source, output, repository_root=ROOT,
            describe_plan=study.describe_joint_plan, reference_arms=[], reference_seeds=[],
            settle_plan=lambda plan, rows: {})
    from src.n7_core_settlement import settle_core_layers
    result = study.evaluate_prefix_study(source, output, repository_root=ROOT,
        settle_plan=settle_core_layers if core_layers else study.settle_single_tickets,
        describe_plan=study.describe_joint_plan, reference_arms=("MONOLITHIC_PROB512", "MONOLITHIC_COVERAGE512"), reference_seeds=[42])
    assert len(result["rows"]) == 3
    assert result["rows"][0]["status"] == "NO_BET"
    assert result["rows"][0]["net"] == 0
    if core_layers:
        assert result["rows"][0]["paid_hits"] == 0
        assert result["rows"][0]["opportunity_gross"] == 0
    assert all(Path(p).read_bytes() == raw for p, raw in original_plans.items())
    with pytest.raises(ValueError, match="already frozen"):
        study.evaluate_prefix_study(source, output, repository_root=ROOT,
        describe_plan=study.describe_joint_plan, reference_arms=("MONOLITHIC_PROB512", "MONOLITHIC_COVERAGE512"), reference_seeds=[42])
    # Replaying with changed raw input must stop, not update old receipts.
    (output / "evaluation-receipt.json").unlink()
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="source changed"):
        study.evaluate_prefix_study(source, output, repository_root=ROOT,
        describe_plan=study.describe_joint_plan, reference_arms=("MONOLITHIC_PROB512", "MONOLITHIC_COVERAGE512"), reference_seeds=[42])


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
    monkeypatch.setattr(study, "run_prefix_issue", run)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="Worker failed" if worker_error else "Incomplete"):
        study.freeze_prefix_study(source, out, config, repository_root=ROOT, python="unused", rscript="unused",
        entry_point="scripts/run_n7_joint_issue.R", r_sources=study.JOINT_R_SOURCES)
    assert not (out / "plans-frozen.json").exists()
    if worker_error:
        assert "cancelling queued issues" in capsys.readouterr().out
