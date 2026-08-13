# Issue #207 — active fixed-N7 bankroll allocation

Terminal status on August 13, 2026: PR #226 merged at audited HEAD `90869a959dc1b972cd872ffe465d1009e29df75e`; #207 is closed / Done. This remains retrospective Stage-4 research. `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=false`, `DEPLOYABLE_POLICY=false`. No betting, release, or frontend authority follows from this result.

## Boundary and lanes

Lane A reconstructs the full frozen #206 request panel from the exact source-bound candidate ledger. It preserves exact N=7 ticket identity, ordered source cells, probability/SP trace, rank, split, policy, and source-package binding. Stage 4 may change only issue-level risk fraction and non-negative integer ¥2 repeat counts. It may not change ticket identity, `k`, policy, chronology, or read LOCKED_TEST labels.

Lane B remains a separate lower-exposure reference lane derived from #206 `NO_BET` fallback and pure cash. It is carried only for attribution and boundary evidence and is explicitly excluded from active matched-lift conclusions.

## Chronology and strict learned-choice freeze

- CV_2021 fits the simple logistic controller first and the bounded neural ablation second.
- CV_2022 freezes risk fractions and freezes the single learned-controller choice.
- CV_2023 is the only terminal historical evidentiary split.
- 2025/2026 LOCKED_TEST outcomes and official-final-SP labels remain unused.

Under the final contract, the only frozen learned-controller choice is `BOUNDED_NEURAL`. `SIMPLE_LOGISTIC` is retained as a non-evidentiary replay row for sensitivity and leakage detection, but it cannot establish terminal evidence.

The emitted `frozen_learned_controller_choice.csv` shows the CV_2022 freeze surface. The top selected rows are all `BOUNDED_NEURAL`; the strongest freeze row is `LEARNED_MLP/K8/BOUNDED_NEURAL` with CV_2022 ending capital ¥118,931.92 and matched equal-funding lift ¥61,351.92.

## Regenerated results

The regenerated immutable package is `results/issue-207/` with manifest SHA256:

`48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6`

Key counts:

- Active request rows: 68,880
- Capital ledger rows: 13,560
- Matched comparator issue rows: 4,785
- Matched ticket/tax-lot rows: 129,360

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

## Final artifacts

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

## Schema and verifier coverage

The final R7 package covers:

- strict CV_2022 learned-choice freeze and CV_2023-only terminal evidence
- full per-table schema with columns, dtypes, nullability, units, domains, PKs, FKs, and relationships
- semantic verifier coverage for schema, provenance, handoff, decision, report, matched issue replay, matched ticket/tax-lot replay, and model-choice leakage
- ticket-identity HHI aggregation
- rolling 5/10/20 windows with a time-zero 100k anchor
- completed recovery episodes separate from terminal-open underwater duration
- explicit rejection of non-finite or negative bankrolls, budgets, and schedules, and empty/overfunded matched schedules
- `BaseException` / `KeyboardInterrupt` atomic cleanup plus stale-stage recovery
- mandatory remanifest tamper coverage for payout, self-consistent ledger, source trace, label/future leakage, attribution/schema/provenance/decision, and learned-choice leakage
- nullable-boolean settlement availability, finite/non-negative settlement gross, and negative-payout fail-closed checks
- per-cell binding among `source_cells_json`, match/outcome vectors, and encoded ticket identities
- normalized `Stage4Error` handling for malformed source and decision-trace JSON
- an independent 242-column schema audit matrix, including the corrected `log_joint_probability` unit/domain
- risk-fraction-aware minimum fundable capital (`¥2 / risk_fraction`) rather than a fixed ¥2 threshold

## Replay status

Focused replay work completed in this worktree:

- Regenerated `results/issue-207/`
- Verified regenerated package under the new semantic verifier
- Notebook is executed cleanly: 6 of 6 code cells have execution counts and no error outputs

Final R7 independent EV at the exact merged HEAD reported: focused #207 `65 passed`; #206+#207 regression `103 passed`; 12/12 auditor-owned adversarial probes; notebook 6/6 clean run; semantic verifier PASS; and fresh replay with all 22 payloads plus the manifest byte-identical. The canonical package has 68,880 active requests, 13,560 capital rows, 4,785 matched issue rows and 129,360 matched ticket/tax-lot rows under manifest `48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6`.

R7 closes the final illegal-settlement, nullable-boolean, negative-payout, per-cell source-trace and malformed-JSON boundaries without changing the legal-input terminal decisions. Earlier round receipts remain available in PR #226 and `HANDOFF.md`, but are superseded for terminal provenance by the R7 receipt above.

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj207_bankroll.py
```

#208 was activated by PI after #207 merged and the live graph was read back. This package remains a research-only handoff and did not grant that authority itself.
