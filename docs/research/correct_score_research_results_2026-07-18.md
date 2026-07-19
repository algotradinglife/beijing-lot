# Correct-score research-only results

Date: 2026-07-18
Status: `blocked fail-closed; no correct-score signal, selection, or ROI claim`

## Evidence inspected

- `scripts/evaluate_n7_matchpredict_integration.py` contains a walk-forward
  independent-Poisson team-form baseline, but only aggregates it to handicap
  3/1/0 probabilities.
- `docs/research/ah-to-1x2-methodology.md` reports a 377-match Pinnacle
  three-way reconstruction check (mean absolute per-outcome deviation 0.01117)
  and explicitly identifies an unmodelled low-score/Dixon-Coles degree of
  freedom.
- `docs/strategy/strategy_parallel_simple_runner_forward_contract_2026-07-16.md`
  defines G1 as a frozen three-way paper candidate, not a correct-score source.
- The committed file inventory contains no timestamped correct-score odds
  snapshots, provider coverage manifests, or historical correct-score price
  panel. The committed SQLite-related files are importer/runtime code, not a
  tracked timestamped correct-score odds dataset.

Therefore there is no admissible input for calibration, Top-k, or EV/q results.
Terminal/final odds were not sought, read, or substituted.

## Implemented paper controls

`research.correct_score` supplies:

- immutable pre-match quote/snapshot dataclasses and a fail-closed validation
  result;
- independent-Poisson exact-score grid probabilities that preserve omitted tail
  mass;
- deterministic temperature calibration for a fixed, previously settled score
  catalogue;
- Top-k plus diagnostic theoretical-edge/q filtering; an ineligible snapshot
  returns zero candidates.

The implementation has no CLI entry point, production imports, database I/O,
ticket output, payout calculation, stake sizing, or ROI calculation.

Focused synthetic tests verify fresh evidence acceptance, stale/live/terminal
rejection, tail preservation, chronological-calibration primitive, Top-k rank,
and fail-closed terminal handling. The test values are fixtures only and are
not market results.

## Reproduction

From this worktree, using the project's shared development virtual environment:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m pytest tests/research/test_correct_score_research.py -q
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m ruff check research/correct_score tests/research
```

No command against shared SQLite, collectors, scheduler, API, frontend, or
release files is required or permitted for this study.

## Result

The correct result at this point is **no experiment candidates**. The absence
of timestamped complete pre-match odds prevents a valid market comparison; any
terminal-price backfill would violate the contract and is rejected by design.
