# Issue #207 — active fixed-N7 bankroll allocation

Status: retrospective Stage-4 research. `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=true`, `DEPLOYABLE_POLICY=false`. No betting, release, frontend, or #208 activation authority.

## Boundary and lanes

Lane A reconstructs 68,880 research-only ticket requests from the exact frozen #206 candidate ledger and selector implementation. The controlling panel is K=8 for `MARKET_WR`, `MARKET_WOR`, `LOGISTIC_BASELINE`, `LEARNED_MLP`, and the aggressive diagnostic `TOP_K_EXPECTED`; K=16/32 are sensitivity-only. Every row preserves the exact N=7 identity, ordered source cells, probability/SP/uncertainty trace, rank and source-package binding. No outcome chooses an identity.

Lane B separately reproduces #206 fallback-mixed NO_BET and pure cash for all 75 LOCKED_TEST issues. Both are labelled `LOWER_EXPOSURE_ONLY` and are excluded from active matched lift.

## Chronology and controllers

- CV-2021 fits a scikit-learn `LogisticRegression` controller first, then a bounded one-hidden-layer `MLPClassifier` ablation.
- CV-2022 freezes the risk fraction from `{1%, 5%, 25%, 100%}`. Both package controllers selected 1% under the preregistered mean-ending-capital / worst-drawdown ordering.
- CV-2023 is the terminal historical evaluation.
- All 2025/2026 LOCKED_TEST outcomes and official-final-SP labels remain embargoed.

The active panel includes native ¥2-per-ticket, equal-weight 1/5/25/100%, score-weighted 5%, simple logistic and bounded neural paths. Projection is deterministic largest remainder in integer ¥2 tax lots; the residual is always in `[0, ¥2)`. Same-issue tickets are funded concurrently from pre-issue capital with no top-up.

## Absolute and matched results

The strongest absolute controlling row was `MARKET_WOR/K8/NATIVE_2_YUAN`: ending capital ¥99,245.38, growth -0.7546%, turnover ¥880, active-support ROI -85.75%, and maximum drawdown 0.7546%. This absolute result is not the Stage-4 conclusion.

On the exact executable yuan schedule of the `MARKET_WOR/K8/SIMPLE_LOGISTIC` candidate, equal ticket weights ended ¥4,012.10 lower and had maximum drawdown 4.0121 percentage points worse. The same simple controller also exceeded the score-weighted active component by ¥4,137.48 on that matched schedule. Other simple/neural K8 rows were zero-lift or negative; the bounded neural `MARKET_WOR` row underperformed equal weights by ¥2,883.70. Thus the preregistered active rule has one qualifying row and emits `ACTIVE_OVERLAY_EVIDENCE=true`.

This is hypothesis-generating retrospective evidence, not a deployable policy. The #206 accepted-baseline comparability gap remains unresolved, sparse N7 hits make the estimate fragile, and no separate strict confirmation has run. The native ¥2 active control remains the operationally simplest reference; no result authorizes replacing a policy.

## Evidence

- Executed notebook: `notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb`
- Reusable implementation: `src/bankroll_policy/fixed_n7.py`
- Replay/verify CLI: `scripts/run_bj207_bankroll.py`
- Focused tests: `tests/test_bj207_bankroll.py`
- Immutable package: `results/issue-207/`
- Active tickets: `results/issue-207/active_research_ticket_requests.parquet`
- Issue capital trace: `results/issue-207/issue_capital_ledger.parquet`
- Absolute metrics: `results/issue-207/capital_summary.csv`
- Matched lift: `results/issue-207/matched_comparisons.csv`
- Attribution: `results/issue-207/attribution.csv`
- Rolling holding evidence: `results/issue-207/rolling_window_metrics.csv`
- Terminal decisions: `results/issue-207/decision.json`
- #208 handoff boundary: `results/issue-207/stage4_handoff_schema.json`

## Replay

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py verify --output results/issue-207
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj207_bankroll.py
PYTHONPATH=src .venv/bin/python scripts/execute_bj207_notebook.py --kernel python3
```

#208 remains blocked until PI terminal review and an explicit activation receipt. The handoff schema conveys evidence and identity fields only.
