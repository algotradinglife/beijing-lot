# HANDOFF — Issue #207

[SESSION] 20260812_170059_68d3d4

Current branch: `analyst/bj207-active-n7-bankroll-r3` (push target: `analyst/bj207-issue`)

Current HEAD: resolve locally with `git rev-parse HEAD`.

## Completed — EV round 3

- Reworked `src/bankroll_policy/fixed_n7.py` against the independent REJECT at `a8b0443b1cef0d56993706faa7360184e2beddc4`.
- Made matched reference replay accept an explicit split. SIMPLE/NEURAL selection now uses CV_2022 candidate schedules and CV_2022 comparator outcomes only; CV_2023 remains terminal-only.
- Materialized decisive matched comparator summary, issue ledger and ticket/tax-lot replay artifacts.
- Corrected rolling 5/10/20 maximum drawdown to use each window's starting capital and window-local running peak.
- Added `candidate_controller` to matched ticket/tax-lot identities and schema primary keys. Schema generation fails on every declared non-unique primary key.
- Replaced cyclic notebook byte binding with a canonical cell-type/source contract digest. Clean execution may update outputs/executor metadata while provenance and package verification remain valid.
- Added recoverable post-rename parent-directory-fsync failure semantics: a failed publication receipt removes the target and permits retry.
- Preserved corrected ticket-identity HHI and completed-recovery versus terminal-open-underwater accounting.
- Preserved complete schema/provenance/handoff/report semantic verification, invalid-state guards, BaseException cleanup and mandatory tamper attacks.
- Regenerated `results/issue-207/` and clean-executed the notebook.

## Terminal outcome

- `ENGINE_VALID=true`
- `ACTIVE_OVERLAY_EVIDENCE=false`
- `DEPLOYABLE_POLICY=false`
- `frozen_learned_controller_choice=BOUNDED_NEURAL`
- `negative_freeze=NATIVE_2_YUAN`

The prior positive `MARKET_WOR/SIMPLE_LOGISTIC` matched lift is sensitivity-only and non-evidentiary. Cash/NO_BET remain `LOWER_EXPOSURE_ONLY`.

The verified package manifest is:

`661a3a8f57cf7a78d374fa6a8a399c397a27780adc5620a38a9dcebaeaef1ccd`

Artifact counts:

- active request rows: 68,880
- capital ledger rows: 13,560
- matched comparator issue rows: 2,475
- matched ticket/tax-lot rows: 92,400
- matched tax-lot declared-PK duplicate rows: 0

## Key evidence

- `results/issue-207/frozen_learned_controller_choice.csv`
- `results/issue-207/matched_comparisons.csv`
- `results/issue-207/matched_comparator_issue_ledger.parquet`
- `results/issue-207/matched_ticket_tax_lot_ledger.parquet`
- `results/issue-207/rolling_window_metrics.csv`
- `results/issue-207/schema.json`
- `results/issue-207/provenance.json`
- `results/issue-207/decision.json`
- `results/issue-207/DECISION_REPORT.md`
- `notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb` (6/6 code cells, no errors)

## Verification receipts

- Package semantic/hash verifier PASS before and after notebook clean execution; manifest `661a3a8f57cf7a78d374fa6a8a399c397a27780adc5620a38a9dcebaeaef1ccd`.
- Focused #207: `27 passed in 788.62s (0:13:08)`.
- #206 + #207 regression: `65 passed in 930.53s (0:15:30)`.
- Notebook: `PASS cells=6 executed=6 kernel=python3`; package verifier still PASS afterward without restoring notebook bytes.
- Independent new-directory replay: verifier PASS; 22/22 payload hashes byte-identical.
- Ruff, compileall and `git diff --check`: PASS.
- Mandatory tamper coverage: settlement/payout; internally self-consistent ledger; rewritten manifest; source trace/label/future; schema/attribution/provenance/decision/model-choice; KeyboardInterrupt and post-rename fsync failure.

## Constraints preserved

- No owner or Project membership changes.
- #208 remains blocked and receives schema/evidence only.
- No merge or issue closure performed.

## Next state

Next state must be `EV Review`.

Independent EV should:

- recompute the split-local CV_2022 learned-choice freeze and ensure CV_2023 never enters model choice;
- recompute true local-window drawdown, ticket-identity HHI and completed/open recovery semantics;
- validate declared PK uniqueness and matched tax-lot identity;
- execute the notebook and re-run package verification without restoring notebook bytes;
- inject post-rename parent fsync failure and confirm the target remains absent/retryable;
- rerun all four mandatory tamper classes and immutable replay;
- confirm #208 remains blocked and receives no activation authority.
