# Issue #207 — active fixed-N7 bankroll allocation

Status on Wednesday, August 12, 2026: retrospective Stage-4 research. `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=false`, `DEPLOYABLE_POLICY=false`. No betting, release, frontend selectability, or #208 activation authority.

## Boundary and lanes

Lane A reconstructs the full frozen #206 request panel from the exact source-bound candidate ledger. It preserves exact N=7 ticket identity, ordered source cells, probability/SP trace, rank, split, policy, and source-package binding. Stage 4 may change only issue-level risk fraction and non-negative integer ¥2 repeat counts. It may not change ticket identity, `k`, policy, chronology, or read LOCKED_TEST labels.

Lane B remains a separate lower-exposure reference lane derived from #206 `NO_BET` fallback and pure cash. It is carried only for attribution and boundary evidence and is explicitly excluded from active matched-lift conclusions.

## Chronology and strict learned-choice freeze

- CV_2021 fits the simple logistic controller first and the bounded neural ablation second.
- CV_2022 freezes risk fractions and freezes the single learned-controller choice.
- CV_2023 is the only terminal historical evidentiary split.
- 2025/2026 LOCKED_TEST outcomes and official-final-SP labels remain unused.

Under the round-2 contract, the only frozen learned-controller choice is `BOUNDED_NEURAL`. `SIMPLE_LOGISTIC` is retained as a non-evidentiary replay row for sensitivity and leakage detection, but it cannot establish terminal evidence.

The emitted `frozen_learned_controller_choice.csv` shows the CV_2022 freeze surface. The top selected rows are all `BOUNDED_NEURAL`; the strongest freeze row is `LEARNED_MLP/K8/BOUNDED_NEURAL` with CV_2022 ending capital ¥118,931.92 and matched equal-funding lift ¥61,351.92.

## Regenerated results

The regenerated immutable package is `results/issue-207/` with manifest SHA256:

`661a3a8f57cf7a78d374fa6a8a399c397a27780adc5620a38a9dcebaeaef1ccd`

Key counts:

- Active request rows: 68,880
- Capital ledger rows: 13,560
- Matched comparator issue rows: 2,475
- Matched ticket/tax-lot rows: 92,400

Terminal decision summary:

- `ENGINE_VALID=true`
- `ACTIVE_OVERLAY_EVIDENCE=false`
- `DEPLOYABLE_POLICY=false`
- `frozen_learned_controller_choice=BOUNDED_NEURAL`
- `negative_freeze=NATIVE_2_YUAN`

The strongest absolute CV_2023 K=8 path remains `MARKET_WOR/NATIVE_2_YUAN` at ending capital ¥99,312.89, growth -0.6871%, turnover ¥880.00, active-support ROI -78.0807%, maximum drawdown 0.6871%, and ticket-identity stake HHI 0.002273.

The decisive matched evidence is negative under the strict freeze:

- `MARKET_WOR/SIMPLE_LOGISTIC` still shows a positive matched equal-funding lift of ¥6,172.46 and 6.0309 percentage points drawdown lift, but it is not terminal-evidentiary because `SIMPLE_LOGISTIC` was not the CV_2022 frozen learned choice.
- The terminal-evidentiary `MARKET_WOR/BOUNDED_NEURAL` row is identified on the same executable schedule and shows matched ending-capital lift of -¥4,436.46 and matched drawdown lift of -4.4365 percentage points versus `EQUAL_1PCT`.
- All other terminal-evidentiary K=8 equal-funding comparisons are zero or negative.

That is why `ACTIVE_OVERLAY_EVIDENCE=false` and the negative freeze remains the native ¥2 active control.

## Round-2 artifacts

- Executed notebook: `notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb`
- Reusable implementation: `src/bankroll_policy/fixed_n7.py`
- Replay/verify CLI: `scripts/run_bj207_bankroll.py`
- Immutable package: `results/issue-207/`
- Active requests: `active_research_ticket_requests.parquet`
- Capital replay: `issue_capital_ledger.parquet`
- Path summary: `capital_summary.csv`
- Anchored rolling windows: `rolling_window_metrics.csv`
- CV_2022 risk freeze: `controller_calibration.csv`
- Strict learned-choice freeze: `frozen_learned_controller_choice.csv`
- Decisive matched summary: `matched_comparisons.csv`
- Decisive matched issue replay: `matched_comparator_issue_ledger.parquet`
- Decisive matched ticket/tax-lot replay: `matched_ticket_tax_lot_ledger.parquet`
- Attribution: `attribution.csv`
- Decision contract: `decision.json`
- Full schema catalog: `schema.json`
- Provenance and replay contract: `provenance.json`
- #208 boundary: `stage4_handoff_schema.json`

## Schema and verifier changes

Round 2 adds:

- strict CV_2022 learned-choice freeze and CV_2023-only terminal evidence
- full per-table schema with columns, dtypes, nullability, units, domains, PKs, FKs, and relationships
- semantic verifier coverage for schema, provenance, handoff, decision, report, matched issue replay, matched ticket/tax-lot replay, and model-choice leakage
- ticket-identity HHI aggregation
- rolling 5/10/20 windows with a time-zero 100k anchor
- completed recovery episodes separate from terminal-open underwater duration
- explicit rejection of non-finite or negative bankrolls, budgets, and schedules, and empty/overfunded matched schedules
- `BaseException` / `KeyboardInterrupt` atomic cleanup plus stale-stage recovery
- mandatory remanifest tamper coverage for payout, self-consistent ledger, source trace, label/future leakage, attribution/schema/provenance/decision, and learned-choice leakage

## Replay status

Focused replay work completed in this worktree:

- Regenerated `results/issue-207/`
- Verified regenerated package under the new semantic verifier
- Notebook is executed cleanly: 6 of 6 code cells have execution counts and no error outputs

EV round-3 receipts: focused #207 `27 passed in 788.62s`; #206+#207 regression `65 passed in 930.53s`; notebook 6/6 clean-run followed by package verifier PASS without restoring notebook bytes; independent new-directory replay produced 22/22 byte-identical payload hashes. The final canonical package verifier passed with 22 payloads and manifest `661a3a8f57cf7a78d374fa6a8a399c397a27780adc5620a38a9dcebaeaef1ccd`.

Round 3 also closes the split-local chronology, local rolling-window drawdown, matched tax-lot primary-key, notebook self-reference and post-rename fsync recovery defects found at audited SHA `a8b0443b1cef0d56993706faa7360184e2beddc4`.

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj207_bankroll.py
```

#208 remains blocked. This package is a research-only handoff and does not grant activation authority.
