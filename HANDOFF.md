# HANDOFF — Issue #208 (analyst/bj208-issue)

[SESSION] 20260814_003538_ea61b5
Resume: `hermes --resume 20260814_003538_ea61b5`

## Current HEAD

Branch `analyst/bj208-issue` (from origin/main @ `2dbcd88`), worktree
`/home/drwho1985/workspace/soccer/beijing-lot-bj208`.

## What is done

- Contract BJ-UNIFIED-DYNAMIC-N-001 / v3 executed: per-issue learned
  action-value policy `Q_theta(x,a)` (sklearn MLPRegressor + Ridge +
  best-fixed-action controls) on the bounded N×K×lane×capital catalog.
- Frozen upstream bound: #207 (sha `90869a959dc1`), value matrix
  (sha `8fdace9c…`), incumbent = N7/K8/MARKET_WOR/native-¥2 from #207
  CONTROLLING K8 identities (CV_2022/23 ledger + CV_2021 reconstruction).
- Chronological folds: CV_2021→CV_2022, CV_2021+CV_2022→CV_2023
  (protocol delta #208-1: no 2020 surface in frozen upstream).
- Safety gate implemented and enforced in replay: conservative lift
  (pred − 1×RMSE) + coverage/OOD/fundability; failure → frozen incumbent.
- Results package `results/issue-208/` verified (manifest, accounting,
  continuity, embargo, tamper 4/4). `method_preflight` PASS.
- Notebook executed clean (11/11 cells). Tests 16/16 pass.
- Decision report + wiki updated.

## Key decisions and rationale

1. **Selection = FROZEN_N7_INCUMBENT** (legal freeze, rule step 5): gate passes
   on only 3/113 test issues, all with 0 realized payout; gated path ≡ frozen
   incumbent (matched lift 0.0). Consistent with #207 negative overlay.
2. **Incumbent binding exact**: control arm and learned fallback use
   `FROZEN_INCUMBENT_207` rows (not a replay proxy) — CV_2023 ¥99,312.89,
   CV_2022 ¥99,072.00.
3. **Fold structure adjusted** (delta #208-1): "train≤2020/test 2021" not
   constructible; CV_2021 is the initial fit block.
4. **SIMPLE_ACTIVE capital lane** = #207 EQUAL_1PCT (simplest accepted active
   controller; contract says do not reopen Stage-4 grid).

## Known issues

- MLP ConvergenceWarning (max_iter=500) on fold 2 — benign; early stopping
  active; diagnostics show monotone calibration.
- `cash_no_bet` control arm reports NO_BET rows (funded 0) — it is a safety
  reference, excluded from active-Edge attribution.
- K16 sensitivity underperforms K8 native on both folds (consistent with #207).

## Next steps (for rework, if EV rejects)

1. Read EV defect list; classify per REQ-E09 (leakage/verifier-blind-spot/
   atomicity/metric-semantics/schema/boundary); same-class sweep across all
   call sites.
2. Fresh (not resume) unless EV marks REWORK_TYPE=minor.
3. Re-run `scripts/run_bj208_policy.py run --output results/issue-208`,
   re-execute notebook, re-run preflight + pytest, then re-deliver.

## Replay commands

```
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bj208_metrics.py tests/test_bj208_tamper.py -q
python3 /home/drwho1985/workspace/bot-dispatcher/method_preflight.py --worktree /home/drwho1985/workspace/soccer/beijing-lot-bj208
```
