# #396 — 2025 Settlement Truth Recovery, v1

Contract: `BJ-DATA-2025-SETTLEMENT-BACKFILL-001/v1`

## Result

The recovery is fail-closed and currently **BLOCKED**. It acquired one immutable
500.com result page for every issue in the fixed 2025 census (`25011` through
`25125`, 57 issues) and parsed 16,237 advertised source rows.

| Measure | Value |
|---|---:|
| Fully source-bound canonical settlement records | 16,117 |
| Source rows with `改期` and no native settlement | 97 |
| Source rows lacking native result/SP without a postpone/cancel marker | 23 |
| Target issues with at least one residual | 36 |
| Strategy execution authorized | No |

The 23 unresolved rows are the release blocker. No score-derived label, odds
proxy, or inferred payout was substituted for their absent native result/SP.

## Evidence package

`results/bj396_2025_settlement_backfill_v1/` contains:

- `raw/pages/*.html`: the 57 GB18030 source pages;
- `raw/acquisition_receipts.csv`: one terminal, SHA-256-bound receipt per issue;
- `canonical_settlements.parquet`: only native-result/native-SP records;
- `exclusion_ledger.csv`: every non-canonical row, raw-page hash and row text;
- `issue_ledger.csv`, `source_inventory.csv`, `decision.json`, and `MANIFEST.json`.

The package verifier re-hashes the complete package, re-parses every raw page,
rebuilds both canonical and exclusion tables, validates identity uniqueness and
handicap semantics, and rejects a mismatched manifest, ledger, outcome, source
trace, or winning SP. `winning_sp == 1.0` rows whose published result conflicts
with the score are explicitly retained as `VOID_REFUND_NATIVE_SP_1`; the native
SP is the settlement authority in that case.

## Reproduction

```bash
PYTHONPATH=. python scripts/fetch_bj396_2025_settlements.py \
  --raw-root artifacts/bj396_raw_500_2025 --rate-seconds 0.4
PYTHONPATH=. python scripts/build_bj396_2025_settlement_package.py \
  --raw-root artifacts/bj396_raw_500_2025 \
  --package-root results/bj396_2025_settlement_backfill_v1
PYTHONPATH=. python scripts/verify_bj396_2025_settlement_package.py \
  --package-root results/bj396_2025_settlement_backfill_v1
python -m pytest tests/test_bj396_settlement.py -q
```

`notebooks/bj396_settlement_recovery.ipynb` is rendered from the same package by
`scripts/render_bj396_settlement_notebook.py` and stores the verifier result.

## PI decision requested

Keep #396 blocked until an authoritative settlement lane supplies the missing
native result/SP for the 23 rows, or PI explicitly approves a contract amendment
that defines their settlement treatment. The existing evidence does not support
an automatic `改期`/void conversion for those 23 rows.
