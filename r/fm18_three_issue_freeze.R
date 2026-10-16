# Freeze or independently replay alpha on every previously frozen FM17 fixture.
# Rscript r/fm18_three_issue_freeze.R ROOT OUTPUT freeze|replay
args <- commandArgs(TRUE); stopifnot(length(args) == 3L, args[3] %in% c("freeze", "replay"))
root <- normalizePath(args[1], mustWork = TRUE); out <- args[2]; replay <- args[3] == "replay"
suppressPackageStartupMessages(library(tidyverse))
library(beidan, lib.loc = file.path(root, "results/fm17-diagnostic-iterations-20261013/library"))
env <- new.env(parent = asNamespace("beidan"))
sys.source(file.path(root, "packages/beidan/R/alpha_top3_draw.R"), env)
registration <- jsonlite::fromJSON(file.path(root, "results/fm18-alpha1-20261017/acceptance.json"))
registered <- registration$files |> as_tibble() |>
  filter(path %in% c("packages/beidan/R/alpha_top3_draw.R", "config/fundamental-models/FM-1.8.0-alpha.1.json"))
stopifnot(registration$status == "ACCEPTED", nrow(registered) == 2L,
  all(map_chr(file.path(root, registered$path), ~digest::digest(file = .x, algo = "sha256")) == registered$sha256))
parent_path <- file.path(root, "results/fm17-three-issues-20261013/forecasts.rds")
pm <- jsonlite::fromJSON(file.path(dirname(parent_path), "manifest.json"))
stopifnot(digest::digest(file = parent_path, algo = "sha256") == pm$forecast_sha256)
parent <- readRDS(parent_path)
stopifnot(length(parent$entries) == 346L, parent$model_id == "FM-1.7.0")
reticulate::use_python(file.path(root, ".venv/bin/python"), required = TRUE)
reticulate::import("sys", convert = FALSE)$path$insert(0L, file.path(root, "packages/beidan/inst/python"))
shared <- reticulate::import("beidan_backend.temporal_learning", convert = FALSE)
backend <- reticulate::import("beidan_backend.fundamental_probability", convert = FALSE)
entries <- probabilities <- audit <- list()
for (id in names(parent$entries)) {
  e <- parent$entries[[id]]; base <- e$results[["FM-1.7.0"]]$base
  h <- unique(parent$probabilities$handicap[parent$probabilities$fixture_id == id])
  stopifnot(length(h) == 1L, identical(e$cutoff, base$cutoff))
  binding <- list(alpha_input = beidan:::.score_margin_hash(list(base = base, handicap = h, fixture = e$fixture, cutoff = e$cutoff)),
    alpha_code = digest::digest(list(body(env$AlphaTop3Draw), body(beidan:::.score_margin_hash),
      body(beidan:::match_require_cutoff), body(beidan:::match_check_character_id)), algo = "sha256"))
  context <- backend$build_adjustment_evidence_context(e$evidence_rows, as.list(e$fixture),
    shared$Cutoff$decision_epoch(e$fixture$issue_id, format(e$cutoff$cutoff_utc, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")),
    binding, shared$AvailabilityPolicy$historical_proxy("FM18_ALPHA_FIXED_THREE_ISSUE_DIAGNOSTIC"), "HISTORICAL_DIAGNOSTIC", root)
  result <- env$AlphaTop3Draw(base, h, e$fixture, e$cutoff, context, root)
  entries[[id]] <- result
  probabilities[[id]] <- result$probabilities |> mutate(fixture_id = id, model = "FM-1.8.0-alpha.1", .before = 1)
  audit[[id]] <- tibble(fixture_id = id, issue_id = e$fixture$issue_id, home = e$fixture$home, away = e$fixture$away,
    handicap = h, cutoff_utc = e$cutoff$cutoff_utc, selected_source = e$parent_selection$selected_source,
    triggered = result$receipt$triggered, draw_atom_rank = result$receipt$draw_atom_rank,
    core_mass = result$receipt$core_mass, core_margins = paste(result$receipt$core_margins, collapse = ","),
    source_context_cache_key = result$receipt$source_context$cache_key,
    alpha_cache_key = result$receipt$cache_key, input_hash = result$receipt$input_hash,
    output_hash = result$receipt$output_hash)
  if (length(entries) %% 50L == 0L) message("Processed ", length(entries), "/346")
}
result <- list(model_id = "FM-1.8.0-alpha.1", parent_sha256 = pm$forecast_sha256,
  entries = entries, probabilities = bind_rows(probabilities), audit = bind_rows(audit))
dir.create(out, recursive = TRUE, showWarnings = FALSE)
path <- file.path(out, "forecasts.rds")
if (replay) {
  manifest <- jsonlite::fromJSON(file.path(out, "manifest.json"))
  stopifnot(digest::digest(file = path, algo = "sha256") == manifest$forecast_sha256,
    identical(result, readRDS(path)))
  jsonlite::write_json(list(status = "FULL_IDENTICAL_REPLAY", fixtures = 346L,
    forecast_sha256 = manifest$forecast_sha256), file.path(out, "replay.json"), pretty = TRUE, auto_unbox = TRUE)
} else {
  if (file.exists(path)) stopifnot(identical(result, readRDS(path))) else saveRDS(result, path)
  write_csv(result$probabilities, file.path(out, "probabilities.csv")); write_csv(result$audit, file.path(out, "audit.csv"))
  jsonlite::write_json(list(model_id = result$model_id, fixtures = length(entries),
    intended_use = "POSTHOC_HISTORICAL_DIAGNOSTIC", target_labels_opened_by_client = FALSE, prior_outcomes_known = TRUE,
    forecast_sha256 = digest::digest(file = path, algo = "sha256"), parent_sha256 = pm$forecast_sha256,
    registered_policy_hashes = registered,
    client_sha256 = digest::digest(file = file.path(root, "r/fm18_three_issue_freeze.R"), algo = "sha256"),
    probabilities_sha256 = digest::digest(file = file.path(out, "probabilities.csv"), algo = "sha256"),
    audit_sha256 = digest::digest(file = file.path(out, "audit.csv"), algo = "sha256"),
    generated_at = format(file.info(path)$mtime, tz = "UTC", usetz = TRUE)),
    file.path(out, "manifest.json"), pretty = TRUE, auto_unbox = TRUE)
}
