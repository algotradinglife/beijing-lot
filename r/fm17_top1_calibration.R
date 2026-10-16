# Descriptive, cutoff-preserving analysis; no fit, policy or threshold selection.
# Rscript r/fm17_top1_calibration.R ROOT OUTPUT
args <- commandArgs(TRUE)
stopifnot(length(args) == 2L)
root <- normalizePath(args[1], mustWork = TRUE)
out <- args[2]
suppressPackageStartupMessages(library(tidyverse))
library(beidan, lib.loc = file.path(root, "results/fm17-diagnostic-iterations-20261013/library"))
# The new pure helper uses the installed authoritative scorer; no backend setup.
implementation <- new.env(parent = asNamespace("beidan"))
sys.source(file.path(root, "packages/beidan/R/top1_reliability.R"), envir = implementation)
parent_root <- file.path(root, "results/fm17-three-issues-20261013")
event_root <- file.path(root, "results/fm17-event-types-20261015")
eval <- jsonlite::fromJSON(file.path(parent_root, "evaluation.json"))
event <- jsonlite::fromJSON(file.path(event_root, "receipt.json"))
sources <- c(forecast = file.path(parent_root, "forecasts.rds"),
  labels = file.path(parent_root, "labels.csv"), sp = file.path(root, eval$sp_path),
  coverage = file.path(event_root, "coverage.csv"))
hashes <- map_chr(sources, ~digest::digest(file = .x, algo = "sha256"))
stopifnot(hashes[["forecast"]] == eval$forecast_sha256,
  hashes[["labels"]] == eval$labels_csv_sha256, hashes[["sp"]] == eval$sp_sha256,
  hashes[["coverage"]] == event$output_hashes$coverage)
frozen <- readRDS(sources[["forecast"]])
coverage <- read_csv(sources[["coverage"]], col_types = cols(.default = col_character())) |>
  select(fixture_id, issue_id, event_type, selected_source, cutoff_utc)
labels <- read_csv(sources[["labels"]], col_types = cols(.default = col_character())) |>
  select(fixture_id, actual_outcome)
stopifnot(!anyDuplicated(coverage$fixture_id), nrow(labels) == 345L)
sp <- read_csv(sources[["sp"]], show_col_types = FALSE) |>
  filter(fixture_id %in% frozen$audit$fixture_id) |>
  inner_join(coverage |> select(fixture_id, cutoff_utc), by = "fixture_id", relationship = "many-to-one")
sp <- sp |> mutate(cutoff_utc = lubridate::ymd_hms(cutoff_utc, tz = "UTC"))
stopifnot(!anyNA(sp$cutoff_utc), !anyDuplicated(sp[c("fixture_id", "mode")]),
  all(sp$sp_w > 0 & sp$sp_d > 0 & sp$sp_l > 0),
  all(sp$quote_at < sp$selection_cutoff), all(sp$quote_at < sp$kickoff_utc),
  all(sp$selection_cutoff[sp$mode == "same_cutoff"] == sp$cutoff_utc[sp$mode == "same_cutoff"]))
bd <- sp |> transmute(fixture_id, comparison = mode, W = 1/sp_w, D = 1/sp_d, L = 1/sp_l) |>
  mutate(mass = W + D + L, across(c(W, D, L), ~.x/mass)) |>
  select(-mass) |> pivot_longer(c(W, D, L), names_to = "outcome", values_to = "probability") |>
  mutate(model = if_else(comparison == "same_cutoff", "BEIDAN_T24", "BEIDAN_LATER"))
breaks <- c(1/3, .4, .5, .6, .7, .8, .9, 1)
all_fixtures <- bins <- summaries <- list()
for (comparison in c("same_cutoff", "near_sale")) {
  ids <- Reduce(intersect, list(labels$fixture_id, frozen$probabilities$fixture_id,
    bd$fixture_id[bd$comparison == comparison]))
  probabilities <- bind_rows(
    frozen$probabilities |> filter(model %in% c("FM-1.7.0", "FM17-source-before-tail")) |>
      select(fixture_id, model, outcome, probability),
    bd |> filter(.data$comparison == .env$comparison) |> select(fixture_id, model, outcome, probability)) |>
    filter(fixture_id %in% ids)
  strata <- bind_rows(coverage |> filter(fixture_id %in% ids) |> mutate(dimension = "all", stratum = "ALL"),
    coverage |> filter(fixture_id %in% ids) |> mutate(dimension = "issue", stratum = issue_id),
    coverage |> filter(fixture_id %in% ids) |> mutate(dimension = "source", stratum = selected_source),
    coverage |> filter(fixture_id %in% ids) |> mutate(dimension = "event_type", stratum = event_type))
  stopifnot(!anyNA(strata), all(nzchar(strata$cutoff_utc)))
  for (key in unique(paste(strata$dimension, strata$stratum, sep = ":"))) {
    subset <- strata |> filter(paste(dimension, stratum, sep = ":") == key)
    result <- implementation$Top1Reliability(probabilities |> filter(fixture_id %in% subset$fixture_id),
      labels |> filter(fixture_id %in% subset$fixture_id), breaks)
    index <- paste(comparison, key)
    bins[[index]] <- result$bins |> mutate(comparison = comparison,
      dimension = subset$dimension[1], stratum = subset$stratum[1], .before = 1)
    summaries[[index]] <- result$summary |> mutate(comparison = comparison,
      dimension = subset$dimension[1], stratum = subset$stratum[1], .before = 1)
    if (key == "all:ALL") all_fixtures[[comparison]] <- result$fixtures |>
      left_join(coverage, by = "fixture_id", relationship = "many-to-one") |>
      mutate(comparison = comparison, .before = 1)
  }
}
tables <- list(bins = bind_rows(bins), summary = bind_rows(summaries), fixtures = bind_rows(all_fixtures))
dir.create(out, showWarnings = FALSE, recursive = TRUE)
for (name in names(tables)) write_csv(tables[[name]], file.path(out, paste0(name, ".csv")))
receipt <- list(mode = "POSTHOC_DESCRIPTION_NO_CALIBRATION_FIT", breaks = breaks,
  sources = as.list(sources), source_hashes = as.list(hashes),
  implementation_hashes = as.list(map_chr(c("r/fm17_top1_calibration.R", "packages/beidan/R/top1_reliability.R"),
    ~digest::digest(file = file.path(root, .x), algo = "sha256")) |>
    set_names(c("client", "helper"))),
  output_hashes = as.list(map_chr(names(tables), ~digest::digest(file = file.path(out, paste0(.x, ".csv")), algo = "sha256")) |> set_names(names(tables))),
  historical_learning_inventory = "No new fitting/tuning/calibration/selection or ranking policy. DcAccuracyDiagnostic describes frozen ranks with original W,D,L ties; source/cutoff routes unchanged. Historical timestamp proxies remain diagnostic only.",
  inference = "Three known issues; no independent validation, binomial CI or significance claim. Source strata classify FM routing even for BD comparator.",
  package_version = as.character(packageVersion("beidan")),
  runtime = list(R = as.character(getRversion()),
    libraries = as.list(map_chr(c("tidyverse", "dplyr", "tidyr", "readr", "purrr", "tibble", "lubridate", "jsonlite", "digest"),
      ~as.character(packageVersion(.x))) |>
      set_names(c("tidyverse", "dplyr", "tidyr", "readr", "purrr", "tibble", "lubridate", "jsonlite", "digest")))),
  scorer_sha256 = digest::digest(body(beidan:::DcAccuracyDiagnostic), algo = "sha256"),
  generated_at = format(Sys.time(), tz = "UTC", usetz = TRUE))
jsonlite::write_json(receipt, file.path(out, "receipt.json"), pretty = TRUE, auto_unbox = TRUE)
print(tables$bins |> filter(comparison == "near_sale", dimension == "all", model == "FM-1.7.0"), width = Inf)
print(tables$summary |> filter(comparison == "near_sale", dimension %in% c("all", "issue"), model == "FM-1.7.0"), width = Inf)
