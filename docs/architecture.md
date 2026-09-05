# Analysis architecture

- `quarto/`: parameterized analyses and reports; call reusable R functions.
- `r/`: tidyverse analysis, table contracts, diagnostic adapters, and explicit command entry points.
- `r/python_bridge.R`: import modules through a caller-supplied project root and Python interpreter.
- `src/titan_clean/`: authoritative capture/storage contracts and historical diagnostic snapshots.
- `scripts/`: operational command entry points; extraction of existing large scripts requires a domain-specific issue and regression evidence.
- `src/temporal_learning/`: sole authority for decision-facing chronology, learning contexts, receipts, and replay.
- `tests/testthat/`, `tests/titan_clean/`: deterministic R and Python contract tests.
- `tests/fixtures/mapping/`: synthetic source responses for offline report and bridge verification.
- `DESCRIPTION` and `renv.lock`: direct and transitive R dependencies; `requirements.txt`: Python project dependencies.
- `.github/workflows/analysis-contracts.yml`: offline R/Python contracts and clean mapping report render.

## Data flow

- Saved source bytes → strict decoding → shared R parsers → typed diagnostic tables → QMD.
- Explicit mapping capture → R alignment → Python `HistoricalIdMapStore.record_capture()` → atomic SQLite receipt/mapping writes.
- Mapping rebuilds replace only the selected issue's derived mapping; raw receipts are retained.
- Failed writes roll back database changes; unreferenced immutable raw files may remain as source evidence.
- Historical snapshot reads use SQLite read-only mode; R returns tibble tables with typed UTC timestamps and attached source receipts.
- Snapshot source timestamps are Asia/Shanghai wall-clock historical proxies, never prospective availability evidence.

## Existing historical code

- `research/` and `notebooks/` remain in place: their callers and evidence bindings must be inventoried before relocation or deletion.
- These directories do not become approved reusable learning interfaces through this organization change.
- Existing applications and unrelated collectors retain their current paths.
- Migration and handoff documents remain at original paths for cross-session continuity.
