# R / Quarto workflow

## Start and restore

- Start from the repository root and open `beijing-lot.Rproj` for interactive work.
- Preserve and read the [migration handoff](../handoffs/ubuntu-migration-project-handoff.md) and [acceptance record](../handoffs/ubuntu-migration-acceptance-2026-08-27.md) before restoring data.
- R 4.6.1, Python 3.14.4, Quarto 1.10.18 are the verified runtime baseline.
- `DESCRIPTION` lists direct R dependencies; `renv.lock` records their transitive versions.
- Use [renv restore](https://rstudio.github.io/renv/reference/restore.html) during setup; reports never install dependencies.

```bash
Rscript --vanilla r/bootstrap.R
export R_LIBS_USER="$PWD/r_lib"
export BEIJING_LOT_PROJECT_ROOT="$PWD"
export BEIJING_LOT_VENV_PYTHON="$PWD/.venv/bin/python"
export TZ=UTC
# Set BEIJING_LOT_DATA_ROOT explicitly to the operator-selected restored data directory.
```

- `.Rprofile` only adds the existing project R library for interactive use; it no longer supplies personal data paths or changes PATH.
- Put `quarto` on PATH during setup. On the current Ubuntu host it is available at `/usr/lib/rstudio-server/bin/quarto/bin/quarto`.
- Restore Python dependencies into `.venv` using the existing `requirements.txt`; do not replace that environment with a system interpreter.

## Reports

- `00_environment.qmd`: explicit external-data environment and schema inspection.
- `01_mapping_quality.qmd`: read-only discovery ledger audit.
- `02_snapshot_quality.qmd`: read-only historical snapshot diagnostics; R returns tibbles and source receipts.
- `03_500_nowscore_datatable_demo.qmd`: offline mapping contract report; filename retained, implementation now uses tidyverse.
- `07_delivery_contract.qmd`: owner-mandated QMD, review and tibble delivery rules.
- `08_issue_413_delivery.qmd`: this infrastructure delivery and its acceptance evidence.
- QMD 04–06 belong to concurrent settlement/fundamentals tasks and are excluded from this delivery; preserve their working files until those tasks publish them.

```bash
quarto render quarto/03_500_nowscore_datatable_demo.qmd --execute --no-cache
# To analyze captured responses, add explicit parameters:
# -P issue:120711 -P raw_500:/absolute/capture/500.html -P raw_nowscore:/absolute/capture/nowscore.html
```

- Default mapping inputs are synthetic fixtures, not historical match evidence.
- `_quarto.yml` disables freezing and makes execution errors fatal.
- External-data reports require their declared databases/receipts; the offline mapping report is the general CI render target.
- Historical market-time proxies remain diagnostic only. No report can authorize prospective use from those timestamps.

## Mapping operations

- `r/mapping_engine.R` owns shared R parsing and identity alignment.
- `r/mapping_report.R` reads saved responses and produces typed report tables without network or database writes.
- `r/python_bridge.R` imports the authoritative Python store without generated Python code strings.
- Preflight captures one explicitly supplied issue into a new output directory; it does not write the database.
- Rebuild writes only one explicitly supplied issue; no hardcoded list of historical issues runs automatically.

```bash
Rscript --vanilla r/run_preflight.R ISSUE NEW_CAPTURE_DIRECTORY "$PWD"
Rscript --vanilla r/run_rebuild.R DATA_ROOT ISSUE CAPTURE_KEY RECEIVED_AT_UTC "$PWD" "$BEIJING_LOT_VENV_PYTHON"
```

- Use `run_issue_mapping()` with saved `raw_500`/`raw_ns` for exact replay; pass explicit conflict resolutions when evidence supports them.
- Reusing a capture key requires identical content, time, and alignment; new captures require new keys.
- Rebuild database changes are atomic; immutable raw files may remain after failure.
- This repair did not execute live collection, rebuild production mappings, or change systemd services.

## Verification

```bash
Rscript --vanilla tests/testthat.R
.venv/bin/python -m pytest tests/titan_clean -q
.venv/bin/python scripts/check_cutoff_governance.py
quarto render quarto/03_500_nowscore_datatable_demo.qmd --execute --no-cache
```

- Routine tests use saved responses and temporary SQLite databases.
- R/Python bridge tests cover original bytes, retries, rollback, IDs, nulls, timestamps, empty tables, and source receipts.
- CI configuration is in `.github/workflows/analysis-contracts.yml`; server-side required-check settings must be verified separately from local results.
