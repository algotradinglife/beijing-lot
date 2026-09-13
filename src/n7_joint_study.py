"""Offline orchestration and settlement for R-native #424 joint selection.

The R module owns domain enumeration/optimization. Shared temporal_learning owns
Cutoff and provenance. This module does not fit history or implement chronology.
No import-time I/O. Existing historical artifacts are hash-verified evidence,
never relabeled as newly admitted data or re-sealed with current implementation.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import gzip
import hashlib
import json
import os
import subprocess

import pandas as pd

from src.n7_study_scope import n7_study_scope
from src.fundamentals_n7_baseline import rank_double_candidates
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff, implementation_closure, verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_callable_binding

JOINT_R_SOURCES = ("r/n7_joint_sleeves.R", "r/n7_sleeve_tables.R",
                   "scripts/run_n7_joint_issue.R", "config/n7_joint_runtime.json",
                   "config/compression_breadth_runtime.json")


def run_prefix_issue(bundle_path, config_path, output_path, *, cutoffs,
                     repository_root, python, rscript, entry_point):
    """Validate one immutable prediction bundle and invoke the thin R entry point.

    Explicit native Cutoffs must match the entire fixture scope. Writes one new
    JSON result and a sibling log; refuses overwrite. No settlement access. The
    subprocess has a one-hour operational timeout, which aborts the study rather
    than converting partial output into a successful/no-bet research result.
    """
    root = Path(repository_root).resolve()
    entry = (root / entry_point).resolve()
    if not entry.is_relative_to(root) or not entry.is_file() or entry.suffix != '.R':
        raise ValueError("R entry point must be a repository R file")
    bundle_path, output_path = Path(bundle_path), Path(output_path)
    if output_path.exists():
        raise ValueError("Refusing to overwrite issue output")
    bundle = json.loads(gzip.decompress(bundle_path.read_bytes()))
    if bundle.get("seal") != stable_json_hash({k: v for k, v in bundle.items() if k != "seal"}):
        raise ValueError("Frozen candidate bundle changed")
    _, bound = rank_double_candidates(pd.DataFrame(bundle["expanded_pool"]["fixtures"]), cutoffs=cutoffs)
    if bound != bundle["cutoffs"]:
        raise ValueError("Cutoff mismatch")
    env = dict(os.environ, PYTHONPATH=str(repository_root), RETICULATE_PYTHON=str(python),
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    with output_path.with_suffix(".log").open("w") as log:
        subprocess.run([str(rscript), "--vanilla", str(entry.relative_to(root)),
                        str(bundle_path.resolve()), str(Path(config_path).resolve()),
                        str(output_path.resolve()), str(python)], cwd=repository_root,
                       env=env, stdout=log, stderr=subprocess.STDOUT, timeout=3600, check=True)
    result = json.loads(output_path.read_text())
    if result.get("cutoffs") != bound or result.get("historical_admission") is not False:
        raise ValueError("R result cutoff/admission mismatch")
    for plan in result["plans"]:
        if plan["cutoffs"] != bound or plan["issue"] != bundle["issue"]:
            raise ValueError("R plan identity mismatch")
        plan["seal"] = stable_json_hash(plan)
    return result


def freeze_prefix_study(source, output, config_path, *, repository_root, python, rscript,
                        entry_point, r_sources, source_manifest, settle_plan=settle_single_tickets):
    """Run the entire fixed issue/arm/seed grid and seal it before any evaluation.

    Reads an explicit sealed candidate manifest and its bundles. All raw responses/pools remain
    untouched. Output must not exist. Partial failures leave diagnostic logs but
    no plans-frozen receipt, hence cannot be evaluated as a complete study.
    Returns the shared-hash receipt; source and current transitive code are
    rechecked after workers finish. No cross-cutoff or cross-implementation cache.
    """
    source, output, root = Path(source).resolve(), Path(output).resolve(), Path(repository_root).resolve()
    cfg_raw = Path(config_path).read_bytes(); cfg = json.loads(cfg_raw)
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir(); (output / "plans").mkdir()
    (output / "config.json").write_bytes(cfg_raw)
    manifest = Path(source_manifest).resolve(strict=True)
    prior_raw = manifest.read_bytes(); prior = json.loads(prior_raw)
    if prior["seal"] != stable_json_hash(prior["receipt"]) or prior["receipt"]["historical_admission"] is not False:
        raise ValueError("Invalid candidate source manifest")
    scope = n7_study_scope(prior["receipt"]["requested_issues"],
        prior["receipt"]["issues"], prior["receipt"]["unavailable"])
    (output / "prior-freeze.json").write_bytes(prior_raw)
    # Package roots are explicitly inventoried, because a submodule import also
    # executes its parents' __init__.py. The shared closure does the hashing.
    impl = implementation_closure(root, cfg["provenance_roots"], distributions=["numpy", "pandas", "scipy"])
    if entry_point not in r_sources or len(r_sources) != len(set(r_sources)):
        raise ValueError("R source inventory must uniquely bind the entry point")
    r_sources = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in r_sources}
    callback_identity = f"{settle_plan.__module__}:{settle_plan.__qualname__}"
    callback_binding = verify_callable_binding(root, impl, settle_plan, expected_identity=callback_identity)
    sources = {str(manifest): hashlib.sha256(prior_raw).hexdigest(),
               str(Path(config_path).resolve()): hashlib.sha256(cfg_raw).hexdigest()}
    expected = {(issue, seed, arm) for issue in prior["receipt"]["issues"]
                for seed in cfg["seeds"] for arm in cfg["arms"]}
    hashes, raw_hashes, statuses, cutoff_receipts = {}, {}, [], {}
    with ThreadPoolExecutor(max_workers=cfg["workers"]) as executor:
        jobs = {}
        for issue in prior["receipt"]["issues"]:
            path = source / "bundles" / f"{issue}.json.gz"
            raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
            old_keys = [k for k in prior["receipt"]["bundle_hashes"] if Path(k).name == path.name]
            if len(old_keys) != 1 or prior["receipt"]["bundle_hashes"][old_keys[0]] != digest:
                raise ValueError("Historical bundle bytes changed")
            sources[str(path)] = digest
            bundle = json.loads(gzip.decompress(raw))
            cuts = {slot: Cutoff.decision_epoch(issue, ts) for slot, ts in bundle["cutoffs"].items()}
            cutoff_receipts[issue] = bundle["cutoffs"]
            job = executor.submit(run_prefix_issue, path, output / "config.json", output / "raw" / f"{issue}.json",
                                  cutoffs=cuts, repository_root=root, python=python, rscript=rscript,
                                  entry_point=entry_point)
            jobs[job] = issue
        total_jobs = len(jobs)
        for count, job in enumerate(as_completed(jobs), 1):
            # A Future retains its result. Drop completed futures from our map
            # so full issue curves/worlds do not accumulate for the entire study.
            issue = jobs.pop(job)
            try:
                result = job.result()
            except Exception:
                print(f"FAILED issue {issue}; cancelling queued issues. No freeze/evaluation will be created.", flush=True)
                for queued in jobs:
                    queued.cancel()
                raise
            raw_path = output / "raw" / f"{issue}.json.gz"
            raw_path.write_bytes(gzip.compress(json.dumps(result, sort_keys=True).encode(), mtime=0))
            raw_hashes[str(raw_path)] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            uncompressed = output / "raw" / f"{issue}.json"
            if uncompressed.exists():
                uncompressed.unlink()  # Only the just-compressed generated intermediate.
            for row in result["frontier_status"]:
                statuses.append(dict(issue=issue, **row))
            for plan in result["plans"]:
                key = (plan["issue"], plan["seed"], plan["arm"])
                if key not in expected:
                    raise ValueError("Duplicate or unexpected plan grid member")
                expected.remove(key)
                path = output / "plans" / f"{issue}_{plan['seed']}_{plan['arm']}.json.gz"
                raw = gzip.compress(json.dumps(plan, sort_keys=True).encode(), mtime=0)
                path.write_bytes(raw); hashes[str(path)] = hashlib.sha256(raw).hexdigest()
            print(f"Frozen R issue {count}/{total_jobs}: {issue}", flush=True)
    if expected:
        raise ValueError("Incomplete frozen plan grid")
    verify_implementation_closure(root, impl)
    if verify_callable_binding(root, impl, settle_plan, expected_identity=callback_identity) != callback_binding:
        raise ValueError("Executing settlement callback changed during freeze")
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in sources.items()):
        raise ValueError("Inputs changed during selection")
    if any(hashlib.sha256((root / p).read_bytes()).hexdigest() != h for p, h in r_sources.items()):
        raise ValueError("R implementation changed during selection")
    receipt = dict(issues=scope["requested_issues"], modeled_issues=scope["modeled_issues"],
        unavailable_issues=scope["unavailable_issues"], parameters=cfg, source_hashes=sources,
        plan_hashes=hashes, raw_hashes=raw_hashes, implementation=impl, r_implementation=r_sources, cutoffs=cutoff_receipts,
        prior_freeze_seal=prior["seal"], source_manifest=str(manifest), historical_admission=False, evidence_class="EXPOSED_HISTORICAL_DIAGNOSTIC",
        maximum_source_availability=None, maximum_label_availability=None,
        historical_partitions="NO_NEW_FIT_TUNE_CALIBRATION", frontier_statuses=statuses,
        entry_point=entry_point, settlement_callback=callback_binding)
    frozen = dict(receipt=receipt, seal=stable_json_hash(receipt))
    (output / "plans-frozen.json").write_text(json.dumps(frozen, sort_keys=True))
    return frozen


def describe_joint_plan(plan):
    """Project the #424 plan diagnostics into its issue-level reporting schema."""
    return {k: plan[k] for k in ("train_coverage", "eval_coverage", "train_path_drawdown", "eval_path_drawdown",
        "expected_roi", "max_reuse", "max_overlap", "solver_status", "mean_sleeve_coverage")}


def evaluate_prefix_study(source, output, *, repository_root, describe_plan,
                          reference_arms, reference_seeds, audit_path, audit_sha256,
                          settle_plan=settle_single_tickets):
    """Settle a complete frozen R study through the existing authoritative API.

    Only this phase opens target labels/SP. Returns one row per issue/arm/seed
    plus explicitly requested archived references. The settlement snapshot path
    and SHA256 are mandatory. With no reference arms, no prior evaluation or
    result files are opened. Rejects missing
    settlement, mismatched freeze/source/plan hashes and duplicate evaluation.
    Does not alter any tickets, limits or coefficients after seeing outcomes.
    A custom settlement callback must be included in the frozen code closure.
    """
    source, output, root = Path(source).resolve(), Path(output).resolve(), Path(repository_root).resolve()
    if (output / "evaluation-receipt.json").exists():
        raise ValueError("Evaluation already frozen")
    raw = (output / "plans-frozen.json").read_bytes(); frozen = json.loads(raw)
    receipt = frozen["receipt"]
    if frozen["seal"] != stable_json_hash(receipt):
        raise ValueError("Freeze changed")
    verify_implementation_closure(root, receipt["implementation"])
    binding = receipt["settlement_callback"]
    if verify_callable_binding(root, receipt["implementation"], settle_plan,
                               expected_identity=binding["identity"]) != binding:
        raise ValueError("Executing settlement callback binding changed")
    for name, digest in receipt["r_implementation"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("R implementation changed")
    for name, digest in receipt["source_hashes"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen source changed")
    audit_path = Path(audit_path).resolve(strict=True)
    audit_raw = audit_path.read_bytes()
    if hashlib.sha256(audit_raw).hexdigest() != audit_sha256:
        raise ValueError("Settlement snapshot hash mismatch")
    (output / "audit-snapshot.json").write_bytes(audit_raw)
    audit = pd.DataFrame(json.loads(audit_raw)["rows"]); audit.issue = audit.issue.astype(str)
    rows = []
    for name, digest in sorted(receipt["plan_hashes"].items()):
        raw = Path(name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Frozen plan changed")
        plan = json.loads(gzip.decompress(raw)); settled = settle_plan(plan, audit[audit.issue == plan["issue"]])
        if settled["status"] not in ("COMPLETE", "NO_BET"):
            raise ValueError(f"Unresolved settlement: {plan['issue']} {settled['status']}")
        rows.append(dict(issue=plan["issue"], seed=plan["seed"], arm=plan["arm"],
            decision_year=min(plan["cutoffs"].values())[:4], **{k: value for k, value in settled.items() if k != "issue"},
            **describe_plan(plan),
            reference=False))
    controls = []
    reference_hashes = {}
    if reference_arms:
        er_raw = (source / "evaluation-receipt.json").read_bytes()
        old_er = json.loads(er_raw)
        if (old_er["freeze_sha256"] != receipt["source_hashes"][receipt["source_manifest"]]
                or old_er["audit_sha256"] != audit_sha256):
            raise ValueError("Reference evaluation source/audit mismatch")
        old_results = (source / "results.json").read_bytes()
        if hashlib.sha256(old_results).hexdigest() != old_er["result_sha256"]:
            raise ValueError("Archived reference results changed")
        controls = [dict(row, reference=True) for row in json.loads(old_results)["rows"]
                    if row["arm"] in reference_arms and row["seed"] in reference_seeds]
        reference_hashes = dict(prior_evaluation_sha256=hashlib.sha256(er_raw).hexdigest(),
                                reference_results_sha256=hashlib.sha256(old_results).hexdigest())
    keys = {(r["issue"], r["seed"], r["arm"]) for r in controls}
    expected = {(i, s, a) for i in receipt["issues"] for s in reference_seeds for a in reference_arms}
    if keys != expected or len(controls) != len(expected):
        raise ValueError("Archived reference grid mismatch")
    for missing in receipt["unavailable_issues"]:
        for seed in receipt["parameters"]["seeds"]:
            for arm in receipt["parameters"]["arms"]:
                rows.append(dict(**missing, seed=seed, arm=arm, reference=False,
                    stake=None, gross=None, net=None, roi=None, hits=None))
    payload = dict(rows=rows + controls, issue_order=receipt["issues"], freeze_seal=frozen["seal"], historical_admission=False)
    result_raw = json.dumps(payload, sort_keys=True).encode(); (output / "results.json").write_bytes(result_raw)
    er = dict(freeze_sha256=hashlib.sha256((output / "plans-frozen.json").read_bytes()).hexdigest(),
              result_sha256=hashlib.sha256(result_raw).hexdigest(), audit_sha256=audit_sha256,
              audit_path=str(audit_path), **reference_hashes)
    (output / "evaluation-receipt.json").write_text(json.dumps(er, sort_keys=True))
    return payload
