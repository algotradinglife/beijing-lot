# Strategy Validation Gate

This gate is the default first check for any strategy candidate that looks profitable in a backtest.

## Purpose

The gate prevents three recurring false positives:

- Choosing legs with `final` market odds and implicitly removing SP drift.
- Summing multiple train-window sensitivity runs into one inflated result.
- Treating one lucky issue as stable edge.

## Default Command

```bash
python3 scripts/validate_combo_candidate_gate.py \
  --candidate-name n7_combo_cold_tail \
  --output-dir results/combo_candidate_validation_gate \
  --train-windows 12 \
  --snapshots final,1h,10h
```

Additional evaluator options can be appended after the command. They are forwarded to `scripts/evaluate_combo_main_cold_tail.py`.

## Hard Gates

`final` is diagnostic only. A candidate passes only if every non-final snapshot passes:

- at least 60 evaluated issues
- ROI >= 0
- leave-one-out ROI >= 0 after removing the best issue
- best issue profit share <= 0.50
- profitable issue rate >= 20%
- max drawdown / total profit <= 1.50

These defaults are intentionally blunt. If a candidate cannot survive them, it should not enter paper tracking as an edge.

## Outputs

The script writes:

- `gate_metrics.csv`
- `gate_verdict.csv`
- `gate_commands.csv`
- `validation_gate_report.md`

Results remain under `results/` and are not committed.
