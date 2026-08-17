# Issue #250 R5 PI takeover handoff

## Delivery

- Replacement package: `results/bj250_source_census_v3`
- Executed decision notebook: `notebooks/research/issue-250/bj250_source_census.ipynb`
- Decision report: `docs/research/issue_250_source_census.md`
- Builder: `scripts/build_bj250_source_census.py`
- Notebook renderer/executor: `scripts/render_bj250_notebook.py`, `scripts/execute_bj250_notebook.py`
- Tests: `tests/test_bj250_source_census.py`

## R4 defect closure

1. Historical role is recomputed from a coherent same-source Euro 1X2 surface across `initial/10h/1h`, not unrelated counts.
2. Asian handicap and over/under are explicitly two-price-plus-line surfaces, not p34 three-outcome triplets.
3. Coverage reports separate match, vector-row, physical-cell, and non-null-cell denominators by period, market, and snapshot.
4. The two R8 field×market prohibitions are preserved in `hist40_scope_overrides.csv`.
5. Every payload is externally anchor-bound; non-selected evidence/report/figure tampering is covered.
6. Publication is staged, fsynced, atomic, and write-once.
7. The notebook now contains seven executable decision views instead of printing paths only.
8. R5 EV routing blocker is closed with an explicit lane table: historical proxy and strict-forward lanes advance to #252; identity support only to #251; settlement/derived lanes to neither.

## Recomputed evidence

- Historical common Euro proxy gate: 189,587 matches, 3/3 horizons.
- 2024: 16,192 matches; 3,206,016 vector rows; 9,618,048 physical cells; 8,438,821 non-null cells.
- Live native-key intersection: 1,748.
- Historical candidate-map range: 188,197–188,199, non-authoritative.
- Canonical causal intersection: not yet evaluated.
- Tests: 47 focused tests pass before independent EV.

## Required independent EV

Use a fresh checkout and an externally held anchor. Rebuild from the declared external data root, execute the notebook, verify exact 2024 denominators and the 189,587-match coherent proxy gate, tamper every payload class, and confirm the old #234 monolithic delivery is absent from the replacement PR.
