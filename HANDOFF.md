# HANDOFF — Issue #207

[SESSION] 20260812_111138_94d772

Current branch: `analyst/bj207-active-n7-bankroll-r3` (push target: `analyst/bj207-issue`)

Current HEAD: resolve locally with `git rev-parse HEAD`.

## Completed

- Reworked `src/bankroll_policy/fixed_n7.py` to the EV round-2 contract.
- Froze the learned SIMPLE/NEURAL choice strictly on `CV_2022`.
- Restricted learned terminal evidence strictly to the frozen `CV_2023` choice only.
- Added decisive matched comparator summary, issue ledger, and ticket/tax-lot replay artifacts.
- Added ticket-identity stake HHI, anchored rolling 5/10/20 windows, and completed-recovery versus terminal-open-underwater accounting.
- Added full schema/provenance/handoff/report semantic verification.
- Added `BaseException` / `KeyboardInterrupt` stage cleanup and stale-stage recovery.
- Added stricter rejection for non-finite or negative bankroll, budget, and matched schedules, plus empty/overfunded schedules.
- Expanded tamper coverage for payout, self-consistent ledger, source trace, future/label leakage, attribution/schema/provenance/decision, and learned-choice leakage.
- Regenerated `results/issue-207/` and re-executed the notebook.

## Actual terminal outcome

- `ENGINE_VALID=true`
- `ACTIVE_OVERLAY_EVIDENCE=false`
- `DEPLOYABLE_POLICY=false`
- `frozen_learned_controller_choice=BOUNDED_NEURAL`
- `negative_freeze=NATIVE_2_YUAN`

The prior positive `MARKET_WOR/SIMPLE_LOGISTIC` matched lift remains present as a non-evidentiary sensitivity row, but it no longer counts because the round-2 contract freezes the learned choice on `CV_2022` and only the frozen learned choice may establish terminal evidence on `CV_2023`.

The regenerated verified package manifest is:

`2610071c0c3ec3395ed521f8180c86b2b7fdbf78acff1f4e0ae412e0479f6835`

Key artifact counts:

- active request rows: 68,880
- capital ledger rows: 13,560
- matched comparator issue rows: 2,475
- matched ticket/tax-lot rows: 92,400

## Key evidence

- `results/issue-207/frozen_learned_controller_choice.csv`
- `results/issue-207/matched_comparisons.csv`
- `results/issue-207/matched_comparator_issue_ledger.parquet`
- `results/issue-207/matched_ticket_tax_lot_ledger.parquet`
- `results/issue-207/schema.json`
- `results/issue-207/provenance.json`
- `results/issue-207/decision.json`
- `results/issue-207/DECISION_REPORT.md`

Notebook state:

- `notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb`
- executed code cells: 6 / 6
- error outputs: none

## Verification

Verified successfully during this session against the final canonical package:

- `PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py verify --output results/issue-207`
- PASS: 22 payloads; 68,880 active requests; 13,560 capital rows; 2,475 matched issue rows; 92,400 matched ticket rows; manifest `2610071c0c3ec3395ed521f8180c86b2b7fdbf78acff1f4e0ae412e0479f6835`.

Focused local test receipt:

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj207_bankroll.py`
- `21 passed in 770.06s (0:12:50)`

- `PYTHONPATH=src .venv/bin/python scripts/execute_bj207_notebook.py --kernel python3`
- `PASS cells=6 executed=6 kernel=python3`

## Constraints preserved

- Issue #207 was claimed from Ready to In Progress; no owner/Project membership changed.
- #208 remains blocked.
- No project files outside this worktree were modified.

## Next state

Next state should be `EV Review`.

Review focus:

- confirm the strict `CV_2022` learned-choice freeze and `CV_2023` terminal-evidence rule
- verify that `SIMPLE_LOGISTIC` positive rows are now sensitivity-only and not evidentiary
- recompute the matched issue and ticket/tax-lot ledgers
- confirm the anchored rolling and recovery metrics
- verify schema/provenance/handoff/decision/report semantic replay
- confirm that #208 remains blocked and receives schema/evidence only
