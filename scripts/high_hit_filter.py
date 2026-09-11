"""Freeze the fixed N6 filter comparison before reading this run's settlement."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_market_blend import blend_market_scores
from src.fundamentals_high_hit_filter import high_hit_n6_plan
from src.fundamentals_missed_portfolio import fixed_n67_wallets, settle_missed_portfolio
from src.fundamentals_n7_twocover import settle_n7_twocover


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["freeze", "settle"])
    parser.add_argument("--study", required=True)
    args = parser.parse_args()
    out = Path(args.study)
    root = Path("data/derived/fundamentals_417")
    pure = root / "new48-pure-baseline-v1/factors.json"
    old = root / "missed25-rescue-v1"
    source = root / "n7-hit-improvement-v1"
    pointer = root / "cap-depth-grid-v1/plans-frozen.json"
    if args.phase == "freeze":
        if out.exists():
            raise FileExistsError("New immutable study required")
        data = json.loads(pure.read_text())
        frame = pd.DataFrame(data["rows"])
        original = json.loads((old / "frozen.json").read_text())
        assert stable_json_hash(original["receipt"]) == original["seal"]
        hashes = {str(pure): hashlib.sha256(pure.read_bytes()).hexdigest(),
                  str(pointer): hashlib.sha256(pointer.read_bytes()).hexdigest(),
                  **data["source_hashes"]}
        # Old implementations are inventoried evidence, not claimed current replay APIs.
        for folder in [old, source, root/"candidate-exclusion-v1/paired",
                       root/"candidate-exclusion-v1/independent"]:
            path = folder / "frozen.json"
            previous = json.loads(path.read_text())
            assert stable_json_hash(previous["receipt"]) == previous["seal"]
            hashes.update(previous["receipt"]["plan_hashes"])
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        verify_clean_file_bindings(hashes, repository_root=Path.cwd())
        reports = ["quarto/105_high_hit_filter.qmd", "r/fundamentals_pure_report.R",
            "r/fundamentals_equity_curves.R", "r/fundamentals_missed_summary.R",
            "r/fundamentals_hit_improvement.R"]
        params = dict(budget_cny=1024, unit_cny=2, payout_factor=.65,
                      pool_seed=41900, pool_size=512, design_seed=41901, design_draws=1024)
        receipt = dict(issues=original["receipt"]["issues"], source_hashes=hashes,
            parameters=params, scope="EXPOSED_N6_FILTER_ONLY_REASSEMBLY",
            implementation=implementation_closure(Path.cwd(), ["scripts.high_hit_filter"],
                distributions=["numpy", "pandas", "scipy"]),
            report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports},
            historical_admission=False, exclusion_ledgers={}, control_replay={})
        (out / "plans").mkdir(parents=True)
        (out / "contract.json").write_text(json.dumps(dict(receipt=receipt, seal=stable_json_hash(receipt))))
        plan_hashes = {}
        for issue in receipt["issues"]:
            raw = frame[frame.issue == issue].copy()
            cuts = {str(s):Cutoff.decision_epoch(issue, data["cutoffs"][issue][str(s)]) for s in raw.slot}
            projected = Path(data["expert_source"]) / "projected" / f"{issue}.json"
            assert str(projected) in hashes
            x = json.loads(projected.read_text())
            blend = blend_market_scores(x["control"], x["market"], cutoffs=cuts,
                                         market_weight=1, minimum_handicap=2)
            b = pd.DataFrame(blend["rows"]).set_index("slot").loc[raw.slot]
            assert np.allclose(b[["q_W","q_D","q_L"]],raw[["q_W","q_D","q_L"]],atol=1e-12,rtol=0)
            current = raw.copy()
            current[["p_W","p_D","p_L"]] = b[["p_W","p_D","p_L"]].to_numpy()
            prior = json.loads(gzip.decompress((source/"plans"/f"{issue}.json.gz").read_bytes()))["bundles"]["W100_P0_C0"]["plan"]
            old_shape = json.loads(gzip.decompress((old/"plans"/f"{issue}.json.gz").read_bytes()))["H1_R050_N6_C1_RETENTION"]["shape_plan"]
            bundles = {}
            for excluded in (False, True):
                entry = high_hit_n6_plan(current, cutoffs=cuts, exclude_zero_top2=excluded, **params)
                if not excluded:
                    for field in ["tickets", "legs", "stake", "cash_cny", "groups"]:
                        assert entry["source_plan"][field] == prior[field], (issue, "source", field)
                        assert entry["shape_plan"][field] == old_shape[field], (issue, "shape", field)
                    receipt["control_replay"][issue] = "EXACT_LEGS_TICKETS_STAKE_CASH_GROUPS"
                else:
                    receipt["exclusion_ledgers"][issue] = entry["exclusion"]
                shaped = entry["shape_plan"]
                bound = {s:cuts[s] for s in shaped["cutoffs"]}
                portfolio = fixed_n67_wallets({"only":shaped}, cutoffs=bound,
                    wallets={"only":1024}, budget_cny=1024, unit_cny=2, payout_factor=.65)
                bundles["N6_FILTERED" if excluded else "N6_ORIGINAL"] = dict(
                    kind="N6", plan=portfolio, reconstruction=entry, blend_seal=blend["seal"])
            for uses, folder, name in [(3,"paired","PRIMARY_FILL"),(6,"independent","INDEPENDENT_C000")]:
                saved = json.loads(gzip.decompress((root/"candidate-exclusion-v1"/folder/"plans"/f"{issue}.json.gz").read_bytes()))
                assert saved["seal"] == stable_json_hash({k:v for k,v in saved.items() if k != "seal"})
                bundles[f"U{uses}_ORIGINAL"] = dict(kind="N7", plan=saved["plans"][name])
            target = out/"plans"/f"{issue}.json.gz"
            target.write_bytes(gzip.compress(json.dumps(bundles).encode(), mtime=0))
            plan_hashes[str(target)] = hashlib.sha256(target.read_bytes()).hexdigest()
            print("FROZEN", issue, {k:v["plan"]["stake"] for k,v in bundles.items()}, flush=True)
        receipt["plan_hashes"] = plan_hashes
        (out/"frozen.json").write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        print("SEALED 192 policy/issue plans before settlement")
    else:
        if (out/"results.json").exists():
            raise FileExistsError("Immutable results")
        frozen = json.loads((out/"frozen.json").read_text())
        receipt = frozen["receipt"]
        assert stable_json_hash(receipt) == frozen["seal"]
        verify_implementation_closure(Path.cwd(), receipt["implementation"])
        verify_clean_file_bindings({**receipt["source_hashes"],**receipt["plan_hashes"],
            **receipt["report_files"]}, repository_root=Path.cwd())
        witness = json.loads(pointer.read_text())
        assert hashlib.sha256(witness["canonical_json"].encode()).hexdigest() == witness["seal"]
        audits = {k:v for k,v in json.loads(witness["canonical_json"])["source_hashes"].items()
                  if k.endswith("settlement-audit.json")}
        assert len(audits) == 1
        verify_clean_file_bindings(audits, repository_root=Path.cwd())
        audit = pd.DataFrame(json.loads(Path(next(iter(audits))).read_text())["rows"])
        rows = []
        for issue in receipt["issues"]:
            bundles = json.loads(gzip.decompress((out/"plans"/f"{issue}.json.gz").read_bytes()))
            for policy, entry in bundles.items():
                plan = entry["plan"]
                if entry["kind"] == "N6":
                    settled = settle_missed_portfolio(plan, audit[audit.issue == issue])
                else:
                    settled = settle_n7_twocover(plan, audit[audit.issue == issue])
                    settled.update(n6_hits=0, n7_hits=settled["hits"])
                assert settled["status"] in ("COMPLETE", "NO_BET")
                rows.append(dict(settled, policy=policy, budget_cny=1024, cash_cny=plan["cash_cny"]))
        target = out/"results.json"
        target.write_text(json.dumps(dict(rows=rows, issue_order=receipt["issues"],
            exclusion_ledgers=receipt["exclusion_ledgers"], control_replay=receipt["control_replay"],
            upstream_freeze_seal=frozen["seal"], historical_admission=False)))
        verification = dict(scope="PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC",
            plan_freeze_seal=frozen["seal"], result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**receipt["source_hashes"],**receipt["plan_hashes"],**audits},
            implementation=receipt["implementation"], report_files=receipt["report_files"])
        canonical = json.dumps(verification,sort_keys=True,separators=(",",":"))
        (out/"plans-frozen.json").write_text(json.dumps(dict(canonical_json=canonical,
            seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print("SETTLED", len(rows), "policy/issue rows")
