# beidan

N7 research functions with tibble interfaces and a bundled Python temporal-learning backend. Loading the R package does not initialize Python, collect data or write databases.

## Install

From the repository root, install R dependencies and the local package during environment setup:

```r
pak::local_install("packages/beidan")
```

Prepare an explicit Python environment separately:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ./packages/beidan/inst/python
```

For the full repository environment, use its pinned `requirements.txt`, which includes the same backend package. No installation occurs during analysis or rendering.

## Use

```r
library(beidan)
constants <- n7_pipeline_constants()
# kickoff_at is an explicit UTC POSIXct vector; the fixture count follows from it.
kickoffs <- as.POSIXct("2026-09-23 04:00:00", tz = "UTC") + seq(0, by = 900, length.out = 14L)
fixture <- n7_make_fixture_issue("00123", kickoffs)
backend <- n7_python_backend("/absolute/path/to/.venv/bin/python")
cutoff <- n7_learning_cutoff(
  "00123", as.POSIXct("2026-09-22 12:00:00", tz = "UTC"), backend
)
# Reading is whole-issue: no cutoff argument, no date filtering.
inputs <- n7_read_inputs(n7_fixture_source(fixture), "00123")
```

`n7_read_inputs()` returns `fixtures`, `euro`, `totals`, `prematch_sp` and the required `match_status` observation ledger. A missing ledger is an input-contract error; an explicitly empty ledger excludes every fixture. Match visibility is decided solely by the shared `n7_select_match_status()` selector at each decision cutoff, and `n7_prepare_epoch()` owns the D+1 decision window.

The measured status feed carries `status_at` (when the source says the event happened) and `available_at` (when it was actually observed). Only reports with both instants strictly before the cutoff are visible, and only `scheduled` admits a fixture.

`n7_python_table()` and `n7_r_table()` validate named table schemas at the language boundary. Character IDs are never parsed as numbers. Timestamp conversion explicitly retains the instant in UTC. Python integers outside R's supported integer range are rejected before conversion.

The only Python implementation is `inst/python/beidan_backend`. Repository Python consumers import `beidan_backend.temporal_learning` after installation. Provenance accepts an explicit repository root or installed Python resource root and never reads another checkout implicitly.

## Develop and verify

```r
roxygen2::roxygenise("packages/beidan")
pkgload::load_all("packages/beidan")
```

Set `BEIDAN_TEST_PYTHON` to an absolute prepared Python executable to run cross-language tests. Run `R CMD build packages/beidan` then `R CMD check --no-manual beidan_0.1.0.tar.gz`. Run backend tests with that interpreter: `python -m pytest packages/beidan/tests/python`.

The pipeline report is `quarto/n7_pipeline_contracts.qmd`. This is a synthetic engineering baseline, not an empirical profitability claim. Historical model fitting continues to require the shared cutoff, receipt and replay contracts.
