# All-single N7 fixed grid

QMD entry point: `quarto/128_n7_single_ticket_grid.qmd`.
Domain functions: `src/n7_single_ticket_sampling.py::single_ticket_plan` and
`settle_single_tickets`; both mapped to `tests/test_n7_single_ticket_sampling.py`.
The CLI `python -m scripts.replay_n7_single_ticket_grid --output <new-directory>`
freezes plans before opening the audit snapshot. Imports have no data side effects.

## Contract

100 exposed historical issues, 100608–101120; calibrated market probabilities,
no strength consensus gate, no Top1 admission threshold, no expert retraining.
Third outcome threshold 0/20/25%; outcome and fixture powers independently 1/2/4;
seeds 41901–41905. Seven different fixtures per all-single ticket, replacement
across tickets, identical complete tickets rejected. CNY1024 per issue, CNY2 per
ticket, 4096 proposal cap. Every one of 13,500 plans bought 512 tickets.

Fixture probabilities derive from original Top2 mass; outcome probabilities
derive from thresholding only the original third outcome then applying the power.
Expected value uses original calibrated probabilities and inverse raw-market
probabilities as estimated SP, and is recorded only. Settlement applies 0.65 once
per ticket. Explicit native fixture cutoff objects come from frozen controls;
there is no new historical fitting. This exposed diagnostic is not prospective
issue-level walk-forward acceptance or proof of common ticket purchase time.
Live #419 remains blocked by #421; neither lifecycle changed.

## Results

Only 2/27 cells have positive median ROI over seeds. Best median cell is
threshold25%, outcome power1, fixture power1: median +3.5697%, mean −1.6332%,
range −22.3708% to +9.7443%, 3/5 profitable seeds. Median hit issues42/100;
median maximum drawdown CNY16858.62; median ROI excluding each seed's best issue
−1.8737%. Original CAL_U3/CAL_U6 ROI +12.9263%/+22.5264%, hit issues54/56,
maximum drawdown CNY12583.07/14449.85. No evidence here to replace the controls.

## Validation and provenance

Accepted output: `data/derived/fundamentals_417/n7-single-ticket-grid-v2`.
v1 is superseded: Codex review found implementation closure captured too late
and audit bytes potentially read twice across an external refresh. v2 captures
the closure before dispatch, verifies it afterward, and hashes/parses the same
immutable audit/control bytes. Follow-up Codex review found no remaining actionable
defects; its initially unavailable pytest was subsequently run with the configured
research interpreter.

- Python: `/home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python -m pytest tests/test_n7_single_ticket_sampling.py tests/test_market_foundation_n7.py tests/test_fundamentals_n7_single.py -q`: **47 passed**.
- New tests compare 1536 tickets through the pre-existing settlement implementation,
  including mixed W/D/L winners, deterministic duplicates, exact threshold boundary,
  reordered outcome ranks, budget, pending SP, identity and seal failures.
- Independent audit replay: **13,500/13,500** ticket plans and settlements reconciled;
  seven unique fixtures, unique complete tickets, fixed budget, winning ticket count,
  gross and net checked against the saved audit snapshot.
- `python scripts/check_cutoff_governance.py`: **PASS**.
- Fresh execution of QMD128 with source bindings and separately with the committed
  archived accounting fixture; the report includes 27-cell heatmap, all seed equity
  and drawdown curves, and per-issue ROI. The archive preserves accounting only,
  not causal admission or full raw-source replay.
- Targeted R summary tests and report execution exercise unchanged R helpers.
  Full repository Python/R suites are not run: unrelated collectors and models
  are outside this bounded comparison. CI adds the new function tests and archive render.

Source data, all frozen plans, transitive code identities and evaluation snapshots
are bound by receipts. Derived runtime output is local; the compressed accounting
fixture makes the QMD table/figure calculation reproducible after checkout.
