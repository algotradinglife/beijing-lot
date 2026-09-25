# beidan

Match and configurable-parlay research functions with tibble interfaces and a bundled Python temporal-learning backend. Loading the R package does not initialize Python, collect data or write databases.

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
constants <- parlay_settings()
# kickoff_at is an explicit UTC POSIXct vector; the fixture count follows from it.
kickoffs <- lubridate::with_tz(lubridate::ymd_hms("2026-09-23 12:00:00", tz = "Asia/Shanghai"), "UTC") + lubridate::dminutes(seq(0, by = 15, length.out = 14L))
fixture <- make_example_issue("00123", kickoffs)
decision_at <- lubridate::ymd_hms("2026-09-22 20:00:00", tz = "Asia/Shanghai")
# Reading is whole-issue: no cutoff argument, no date filtering.
inputs <- read_match_inputs(example_match_source(fixture), "00123")
```

`read_match_inputs()` returns `fixtures`, `euro`, `totals`, `prematch_sp` and the required `match_status` observation ledger. A missing ledger is an input-contract error; an explicitly empty ledger excludes every fixture. Match visibility is decided solely by the shared `match_select_status()` selector at each decision cutoff, and `prepare_match_inputs()` owns the D+1 decision window.

## Normal public path

One authoritative private engine sits behind thin public facades. The normal path binds the decision context once and carries it forward, so no entrypoint can silently pair a plan with another instant's tables:

```r
market_policy <- list(
  euro = list(members = c("c01", "c02", "c03"), missing = "error"),
  totals = list(companies = NULL, line = "nearest_main", watermark = "decimal"))
model_config <- list(rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)

parlay_settings(reset = TRUE)
settings <- parlay_settings(n_legs = 7L)
epoch <- prepare_match_inputs(inputs, decision_at, market_policy)  # infers the issue
projected <- estimate_match_probabilities(epoch, model_config)
config <- parlay_allocation_configs(settings)$C
result <- parlay_build_plan(projected, config)

settlements <- match_typed_empty("settlements")  # replace with observed settlements
as_of <- lubridate::with_tz(
  lubridate::ymd_hms("2026-09-24 20:00:00", tz = "Asia/Shanghai"), "UTC")
settled <- parlay_settle_plan(result$plan, settlements, as_of)
depth <- parlay_diagnose_plan(result, settlements, as_of)
```

`prepare_match_inputs()` takes a decision INSTANT (any explicit timezone, normalized to UTC) and derives the issue from the fixtures; zero or multiple issues are refused so a caller must choose one issue first. `estimate_match_probabilities()` returns a bound projection carrying its cutoff, selected fixtures, status ledger, pre-match SP and probabilities; `model_config` states `rho`, `total_bounds` and `tail_tolerance` explicitly. `parlay_build_plan()` consumes that projection with one strategy configuration and returns `history`, which the next decision for the same issue must be handed back as `prior_purchases` (purchases and their fixture sets always travel together). `parlay_settle_plan()` and `parlay_diagnose_plan()` read the frozen plan's own constants, so a later session change cannot re-price an already frozen plan. `parlay_replay_issue()` replays exactly one issue; replay each issue separately and combine the ledgers explicitly.

### Lower-level engine entrypoints

`parlay_construct_groups()`, `parlay_apply_structure()`, `parlay_enumerate_tickets()`, `parlay_value_tickets()`, `parlay_rank_tickets()` remain explicit-table helpers for standalone research on pre-projected tables. They take tables and a cutoff directly and never assemble a plan on their own.

The measured status feed carries `status_at` (when the source says the event happened) and `available_at` (when it was actually observed). Only reports with both instants strictly before the cutoff are visible, and only `scheduled` admits a fixture.

`python_table()` and `r_table()` validate named table schemas at the language boundary. Character IDs are never parsed as numbers. Timestamp conversion explicitly retains the instant in UTC. Python integers outside R's supported integer range are rejected before conversion.

The only Python implementation is `inst/python/beidan_backend`. Repository Python consumers import `beidan_backend.temporal_learning` after installation. Provenance accepts an explicit repository root or installed Python resource root and never reads another checkout implicitly.

## Develop and verify

```r
roxygen2::roxygenise("packages/beidan")
devtools::load_all("packages/beidan")
```

Set `BEIDAN_TEST_PYTHON` to an absolute prepared Python executable to run cross-language tests. Run `R CMD build packages/beidan` then `R CMD check --no-manual beidan_0.2.0.tar.gz`. Run backend tests with that interpreter: `python -m pytest packages/beidan/tests/python`.

The current interface delivery report is `quarto/parlay_api_contract.qmd`; the detailed pipeline examples are in `quarto/n7_pipeline_contracts.qmd`. This is a synthetic engineering baseline, not an empirical profitability claim. Historical model fitting continues to require the shared cutoff, receipt and replay contracts.
