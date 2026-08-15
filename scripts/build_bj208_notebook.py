#!/usr/bin/env python3
"""Build + execute the #208 notebook against the committed results package."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

cells = []
def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text})
def code(src):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src})

md("# Issue #208 — dynamic N×K and risk-conditioned parlay policy frontier\n\nContract BJ-UNIFIED-DYNAMIC-N-001 / v7 (PI takeover of concurrent R7 EV REJECTs), generated from producer-code commit `7ff62c6b01fc6d24716608e3b45527a578722b26`. Primary candidate: per-issue learned action-value policy Q_theta(x,a) (MLPRegressor) on the bounded N×K×lane×capital catalog; controls = Ridge + best fixed action + state-conditioned restricted N/K/N×K policies; 16 preregistered hash seeds aggregated. Payout economics: pre-tax gross multiple = hit × 0.65 × product(official SP), coefficient applied exactly once per winning ticket. Every policy lane scores from its own strictly-prior live history. Exact lag-5/lag-10 use time-zero ¥100,000 until the lag exists in both fit and inference. All terminal fitted objects, selection authority, root-manifest boundary and publication transaction are production-bound. 2024/LOCKED_TEST outcomes remain embargoed. This executed notebook reads only the committed immutable package under `results/issue-208/`.")

code("""from pathlib import Path
import json
import pandas as pd

def _find_root():
    p = Path.cwd()
    for _ in range(6):
        if (p / "results" / "issue-208").exists():
            return p
        p = p.parent
    return Path.cwd()

ROOT = _find_root()
PACKAGE = ROOT / "results" / "issue-208"
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
print("package:", PACKAGE.resolve(), "exists:", PACKAGE.exists())""")

md("## 1. Data census\n\n171 development issues (CV_2021 58 / CV_2022 58 / CV_2023 55) + 75 LOCKED_TEST (embargoed). Panels built from the frozen #205 value matrix (sha 8fdace9c…); upstream #207 manifest (48c11d97…) bound at load. The frozen incumbent path is reconstructed from #207 CONTROLLING ticket identities under the corrected payout economics: pre-tax gross multiple = hit × 0.65 × product(official SP) — the Beijing payout coefficient applied exactly once per winning N-fold ticket (PI 2026-08-15).")

code("""census = pd.read_csv(PACKAGE / "census.csv")
census.groupby("split").agg(issues=("issue", "nunique"), mean_M=("M", "mean")).round(1)""")

md("## 2. Action frontier (counterfactual label surface)\n\nCV_2021 fit fold surface: per-issue × 168 actions, seed-aggregated matched pre-tax capital lift vs frozen N7/K8 incumbent.")

code("""surface = pd.read_parquet(PACKAGE / "label_surface_fit.parquet")
print("surface rows:", len(surface))
surface.groupby(["lane", "capital"]).agg(actions=("action_key", "count"), mean_lift=("matched_lift_mean", "mean")).round(1)""")

md("## 3. N×K performance surface (CV_2021 fit fold)\n\nMedian matched lift over lanes/capital, aggregated by N and K.")

code("""pivot = surface.pivot_table(index="n", columns="k", values="matched_lift_mean", aggfunc="median").round(1)
pivot""")

md("## 4. Chronological learned policy (safety-gated)\n\nFold 1 (train CV_2021 → test CV_2022) and Fold 2 (train CV_2021+CV_2022 → test CV_2023). Chronological validation block = last 15% of train issues by issue id. Validation issues are excluded before every MLP, Ridge, ranker, fixed-action and OOD fit; sklearn row-level early stopping remains disabled. In v7, fit and live inference share the same exact lag warm-up: before 5/10 completed issues, the corresponding anchor remains ¥100,000.")

code("""for fold in ("fold1", "fold2"):
    learned = pd.read_parquet(PACKAGE / f"path_learned_{fold}.parquet")
    print(fold, "ending:", round(float(learned.iloc[-1]["post_issue_bankroll_yuan"]), 2), "issues:", len(learned))
loss = pd.read_csv(PACKAGE / "chronological_train_val_loss.csv")
loss""")

code("""chronology = pd.read_parquet(PACKAGE / "chronology_blocks.parquet")
summary = chronology.groupby(["fold", "role"])["issue"].nunique().unstack(fill_value=0)
summary["fit_validation_overlap"] = [
    len(set(chronology.query("fold == @fold and role == 'FIT'")["issue"]) &
        set(chronology.query("fold == @fold and role == 'VALIDATION'")["issue"]))
    for fold in summary.index
]
summary""")

md("## 5. Controls / attribution matrix (CV_2023 test split)\n\nAll arms start ¥100,000. Payout economics use pre-tax gross multiple = hit × 0.65 × product(official SP), coefficient applied exactly once per winning ticket. `capital_change_identical` binds frozen #207 EQUAL_1PCT identities with the corrected multiples.")

code("""import glob
rows = []
for f in sorted(glob.glob(str(PACKAGE / "path_control_*_fold2.parquet"))):
    p = pd.read_parquet(f)
    name = Path(f).name.removeprefix("path_control_").removesuffix("_fold2.parquet")
    rows.append({"control": name, "ending_yuan": round(float(p.iloc[-1]["post_issue_bankroll_yuan"]), 2)})
pd.DataFrame(rows).sort_values("ending_yuan", ascending=False).reset_index(drop=True)""")

md("## 6. Learning diagnostics\n\nThe coarse calibration trend improves toward the highest predicted bin, but adjacent bins are not monotone and predicted/realized scales are mismatched. The conservative gate vetoes all 113 primary-policy executions, so learned path ≡ incumbent. This is a safe null result, not evidence that the neural policy improved the baseline.")

code("""calib = pd.read_csv(PACKAGE / "calibration_curve.csv")
calib.round(1)""")

code("""freq = pd.read_csv(PACKAGE / "action_frequency.csv")
freq.head(6)""")

code("""fallback = pd.read_csv(PACKAGE / "ood_fallback_census.csv")
fallback""")

md("## 7. Genuine dynamic controls\n\nEach restricted control scores lawful actions separately for every issue from causal state. N-only selects N4 on all CV_2022 issues and 54/55 CV_2023 issues (one N10); K-only selects K8 throughout; joint N×K varies N but keeps K8. There is slight dynamic N variation, but no learned dynamic K behavior.")

code("""dynamic = pd.read_parquet(PACKAGE / "dynamic_control_decisions.parquet")
dynamic.groupby(["split", "policy", "n", "k"]).size().rename("issues").reset_index()""")

md("## 8. Issue-level equity paths and holding feasibility\n\nCapital paths, rather than turnover ROI alone, are the primary view. Static N8 is positive only on CV_2023 and fails to replicate on CV_2022; cash is flat; learned is exactly the incumbent because every decision falls back.")

code("""import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(13, 4), sharey=True)
for ax, (fold, split) in zip(axes, [("fold1", "CV_2022"), ("fold2", "CV_2023")]):
    paths = {
        "learned/fallback": PACKAGE / f"path_learned_{fold}.parquet",
        "incumbent N7K8": PACKAGE / f"path_control_incumbent_n7k8_{fold}.parquet",
        "dynamic N×K": PACKAGE / f"path_control_dynamic_nk_fixed_generator_{fold}.parquet",
        "static N8K8": PACKAGE / f"path_control_static_n8k8_{fold}.parquet",
        "cash": PACKAGE / f"path_control_cash_no_bet_{fold}.parquet",
    }
    for label, path in paths.items():
        frame = pd.read_parquet(path).sort_values(["year", "issue"])
        ax.plot(range(1, len(frame) + 1), frame["post_issue_bankroll_yuan"], label=label)
    ax.axhline(100_000, color="black", linewidth=0.8, linestyle="--")
    ax.set(title=split, xlabel="issue sequence", ylabel="capital (yuan)")
    ax.legend(fontsize=7)
fig.tight_layout()
plt.show()""")

code("""holding = pd.read_parquet(PACKAGE / "path_holding_metrics.parquet")
holding.loc[:, [
    "split", "policy", "ending_capital_yuan", "turnover_yuan",
    "active_support_roi", "max_drawdown_pct",
    "max_consecutive_losing_issues", "rolling5_loss_prob",
    "max_recovery_issues", "ex_largest_issue_ending_capital_yuan",
]].sort_values(["split", "ending_capital_yuan"], ascending=[True, False])""")

md("## 9. Selection receipt and #209 handoff\n\nLexicographic rule over 2 constructible folds: learned matched lift = 0.0 on both folds (safety-gated to incumbent), so no row qualifies → freeze N7/K8/MARKET_WOR/native-¥2 incumbent. Handoff v7 is relation-bound to independently recomputed path primitives and the fitted primary model.")

code("""selection = json.loads((PACKAGE / "selection.json").read_text())
print("eligible:", selection["eligible"])
print("median matched lift:", selection["median_matched_lift_yuan"])
print("positive folds:", selection["positive_fold_count"], "/", selection["constructible_fold_count"])
print("frozen candidate:", selection["frozen_candidate"]["policy"])
handoff = json.loads((PACKAGE / "handoff_209.json").read_text())
print("handoff model_serialized:", handoff["model"].get("model_serialized"))
print("handoff scaler_mean present:", handoff["model"].get("scaler_mean") is not None)
print("handoff model_file:", handoff["model_file"])""")

md("## 10. Package verification + tamper self-tests\n\nThe production verifier checks manifest/receipt/provenance/code binding, the complete 55-frame schema inventory, chronology, issue-level path metrics, dynamic argmax decisions, all fitted objects, selection/handoff authority, capital, N/K bundles and payout economics. All 25 attacks must be detected, including false promotion and nested manifest-name escape.")

code("""from scripts.run_bj208_policy import verify_package

failures = verify_package(PACKAGE)
print("production verification failures:", failures if failures else "NONE")""")

code("""tamper = json.loads((PACKAGE / "tamper_results.json").read_text())
for res in tamper:
    print(res["attack"], "->", "DETECTED" if res["detected"] else "MISSED", res["failures"][:1])""")

md("## 11. Holdout boundary and decision\n\nThe frozen value matrix contains zero calendar-2024 rows, so no claim of a 2024 mutation is made. The production probe mutates all 50,970 available 2025/2026 `LOCKED_TEST` rows and performs two actual terminal-fold refits. Ranker, primary MLP, Ridge, best-fixed, three restricted MLPs, OOD scaler/threshold, diagnostic MLP and decisions are invariant and artifact-bound. Decision: no learned candidate promotes; retain the frozen incumbent for #209.")

code("""json.loads((PACKAGE / "holdout_mutation_receipt.json").read_text())""")

code("""inventory = json.loads((PACKAGE / "fitted_object_inventory.json").read_text())
print("fitted objects:", sorted(inventory["fitted_objects"]))
print("restricted MLPs:", sorted(inventory["fitted_objects"]["restricted_mlps"]))""")

# write notebook
nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": f"{sys.version_info.major}.{sys.version_info.minor}"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
nb_path = ROOT / "notebooks" / "research" / "issue-208" / "bj208_dynamic_nk_policy.ipynb"
nb_path.parent.mkdir(parents=True, exist_ok=True)
nb_path.write_text(json.dumps(nb, indent=1))

# execute via jupyter (kernel python3 in main venv)
print("executing notebook...")
res = subprocess.run(
    [sys.executable, "-m", "jupyter", "execute",
     "--ExecutePreprocessor.timeout=600", "--inplace", str(nb_path)],
    capture_output=True, text=True, timeout=1200,
)
print("exit:", res.returncode)
if res.returncode != 0:
    print(res.stderr[-3000:])
sys.exit(res.returncode)
