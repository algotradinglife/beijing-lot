#!/usr/bin/env python3
"""Build + execute the #208 notebook against the committed results package."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/drwho1985/workspace/soccer/beijing-lot-bj208-r1")
PKG = "results/issue-208"

# Read real outputs for embedding into markdown cells
import pandas as pd

sel = json.loads((ROOT / PKG / "selection.json").read_text())
handoff = json.loads((ROOT / PKG / "handoff_209.json").read_text())
calib = pd.read_csv(ROOT / PKG / "calibration_curve.csv")
loss = pd.read_csv(ROOT / PKG / "chronological_train_val_loss.csv")
af = pd.read_csv(ROOT / PKG / "action_frequency.csv")
fallback = pd.read_csv(ROOT / PKG / "ood_fallback_census.csv")
ld = pd.read_parquet(ROOT / PKG / "issue_capital_ledger.parquet")
c23 = ld[ld["split"] == "CV_2023"]
ends = c23.groupby("policy").apply(lambda g: g.sort_values("issue").iloc[-1]["post_issue_bankroll_yuan"]).sort_values(ascending=False)

cells = []
def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text})
def code(src):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src})

md("# Issue #208 — dynamic N×K and risk-conditioned parlay policy frontier\n\nContract BJ-UNIFIED-DYNAMIC-N-001 / v3 (REWORK v3, PI payout-economics correction 2026-08-15). Primary candidate: per-issue learned action-value policy Q_theta(x,a) (MLPRegressor) on the bounded N×K×lane×capital catalog; controls = Ridge + best fixed action; 16 preregistered hash seeds aggregated. SIMPLE_ACTIVE capital = frozen #207 EQUAL_1PCT semantics. Payout economics: pre-tax gross multiple = hit × 0.65 × product(official SP), coefficient applied exactly once per winning ticket; the superseded division-out/omission/0.65^N interpretations are rejected. 2024/2025/2026 outcomes embargoed. This notebook reads the committed immutable package under `results/issue-208/` — no worker-local files.")

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

md("## 4. Chronological learned policy (safety-gated)\n\nFold 1 (train CV_2021 → test CV_2022) and Fold 2 (train CV_2021+CV_2022 → test CV_2023). Chronological validation block = last 15% of train issues by issue id; sklearn row-level early stopping disabled (REWORK v2 / D3). All payouts use the corrected pre-tax economics (0.65 applied exactly once per winning ticket).")

code("""for fold in ("fold1", "fold2"):
    learned = pd.read_parquet(PACKAGE / f"path_learned_{fold}.parquet")
    print(fold, "ending:", round(float(learned.iloc[-1]["post_issue_bankroll_yuan"]), 2), "issues:", len(learned))
loss = pd.read_csv(PACKAGE / "chronological_train_val_loss.csv")
loss""")

md("## 5. Controls / attribution matrix (CV_2023 test split)\n\nAll arms start ¥100,000. Payout economics corrected (REWORK v3): pre-tax gross multiple = hit × 0.65 × product(official SP), coefficient applied exactly once per winning ticket. capital_change_identical binds frozen #207 EQUAL_1PCT identities with the corrected multiples.")

code("""import glob
rows = []
for f in sorted(glob.glob(str(PACKAGE / "path_control_*_fold2.parquet"))):
    p = pd.read_parquet(f)
    name = Path(f).name.removeprefix("path_control_").removesuffix("_fold2.parquet")
    rows.append({"control": name, "ending_yuan": round(float(p.iloc[-1]["post_issue_bankroll_yuan"]), 2)})
pd.DataFrame(rows).sort_values("ending_yuan", ascending=False).reset_index(drop=True)""")

md("## 6. Learning diagnostics\n\nCalibration of predicted vs realized best lift is monotone (Q has signal); action frequency shows the ungated model prefers N4/K32/LEARNED_MLP; OOD/fallback census shows the conservative gate vetoes all 113 test executions → learned path ≡ incumbent.")

code("""calib = pd.read_csv(PACKAGE / "calibration_curve.csv")
calib.round(1)""")

code("""freq = pd.read_csv(PACKAGE / "action_frequency.csv")
freq.head(6)""")

code("""fallback = pd.read_csv(PACKAGE / "ood_fallback_census.csv")
fallback""")

md("## 7. Selection receipt and #209 handoff\n\nLexicographic rule over 2 constructible folds: learned matched lift = 0.0 on both folds (safety-gated to incumbent), so no row qualifies → freeze N7/K8/MARKET_WOR/native-¥2 incumbent. Handoff carries fitted MLP weights + scaler (label-blind replay).")

code("""selection = json.loads((PACKAGE / "selection.json").read_text())
print("eligible:", selection["eligible"])
print("median matched lift:", selection["median_matched_lift_yuan"])
print("positive folds:", selection["positive_fold_count"], "/", selection["constructible_fold_count"])
print("frozen candidate:", selection["frozen_candidate"]["policy"])
handoff = json.loads((PACKAGE / "handoff_209.json").read_text())
print("handoff model_serialized:", handoff["model"].get("model_serialized"))
print("handoff scaler_mean present:", handoff["model"].get("scaler_mean") is not None)
print("handoff model_file:", handoff["model_file"])""")

md("## 8. Package verification + tamper self-tests (REQ-E06)\n\nProduction verifier: manifest full coverage, receipt binding, provenance identity, capital accounting (start ¥100,000, ¥2 units, continuity), embargo/2024 checks, and payout-economics recomputation (REWORK v3: 0.65 applied exactly once per winning ticket). All seven tamper attacks (mutate settlement / self-consistent ledger / forged manifest / forged provenance / omit payout coefficient / division-out payout / 0.65^N compounding) must be DETECTED by the production verifier.")

code("""from parlay_policy.verify import verify_manifest, verify_capital_accounting, verify_no_embargoed_split, verify_no_2024_issue, verify_receipt, verify_provenance
import json

expected = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
failures = verify_manifest(PACKAGE, expected)
print("manifest failures:", failures[:3] if failures else "NONE")
failures += verify_receipt(PACKAGE)
print("receipt failures:", failures[:3] if failures else "NONE")
ledger = pd.read_parquet(PACKAGE / "issue_capital_ledger.parquet")
failures += verify_capital_accounting(ledger)
failures += verify_no_embargoed_split(ledger)
failures += verify_no_2024_issue(ledger)
print("capital/embargo failures:", failures[:3] if failures else "NONE")
print("TOTAL verification failures:", len(failures))""")

code("""tamper = json.loads((PACKAGE / "tamper_results.json").read_text())
for res in tamper:
    print(res["attack"], "->", "DETECTED" if res["detected"] else "MISSED", res["failures"][:1])""")

md("## 9. Boundary statement\n\n- 2024 calendar year: embargoed (no 2024 issue appears in any #208 artifact; real 2024-mutation invariance test passes).\n- 2025/2026 LOCKED_TEST: embargoed.\n- No production betting or release authority follows from this research.")

# write notebook
nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
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
    ["/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/jupyter", "execute",
     "--ExecutePreprocessor.timeout=600", "--inplace", str(nb_path)],
    capture_output=True, text=True, timeout=1200,
)
print("exit:", res.returncode)
if res.returncode != 0:
    print(res.stderr[-3000:])
sys.exit(res.returncode)
