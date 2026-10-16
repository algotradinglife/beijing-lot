# Diagnostic implementation check, not a performance backtest.
# Rscript r/fm18_alpha_smoke.R ROOT OUTPUT
args <- commandArgs(TRUE); stopifnot(length(args) == 2L)
root <- normalizePath(args[1], mustWork = TRUE); out <- args[2]
suppressPackageStartupMessages(library(tidyverse))
library(beidan, lib.loc = file.path(root, "results/fm17-diagnostic-iterations-20261013/library"))
env <- new.env(parent = asNamespace("beidan"))
sys.source(file.path(root, "packages/beidan/R/alpha_top3_draw.R"), env)
reticulate::use_python(file.path(root, ".venv/bin/python"), required = TRUE)
reticulate::import("sys", convert = FALSE)$path$insert(0L, file.path(root, "packages/beidan/inst/python"))
shared <- reticulate::import("beidan_backend.temporal_learning", convert = FALSE)
backend <- reticulate::import("beidan_backend.fundamental_probability", convert = FALSE)
path <- file.path(root, "results/fm17-three-issues-20261013/forecasts.rds")
manifest <- jsonlite::fromJSON(file.path(dirname(path), "manifest.json"))
stopifnot(digest::digest(file = path, algo = "sha256") == manifest$forecast_sha256)
parent <- readRDS(path)
outputs <- list(); probabilities <- list()
for (id in c("26098:104", "26101:81", "26101:91")) {
  e <- parent$entries[[id]]; base <- e$results[["FM-1.7.0"]]$base
  handicap <- unique(parent$probabilities$handicap[parent$probabilities$fixture_id == id])
  hashes <- list(alpha_input = beidan:::.score_margin_hash(list(base = base, handicap = handicap,
    fixture = e$fixture, cutoff = e$cutoff)), alpha_code = digest::digest(list(body(env$AlphaTop3Draw),
      body(beidan:::.score_margin_hash), body(beidan:::match_require_cutoff),
      body(beidan:::match_check_character_id)), algo = "sha256"))
  context <- backend$build_adjustment_evidence_context(e$evidence_rows, as.list(e$fixture),
    shared$Cutoff$decision_epoch(e$fixture$issue_id, format(e$cutoff$cutoff_utc, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")),
    hashes, shared$AvailabilityPolicy$historical_proxy("FM18_ALPHA_IMPLEMENTATION_SMOKE"),
    "HISTORICAL_DIAGNOSTIC", root)
  result <- env$AlphaTop3Draw(base, handicap, e$fixture, e$cutoff, context, root)
  outputs[[id]] <- result
  probabilities[[id]] <- result$probabilities |> mutate(fixture_id = id,
    triggered = result$receipt$triggered, .before = 1)
}
dir.create(out, recursive = TRUE, showWarnings = FALSE)
saveRDS(outputs, file.path(out, "smoke.rds"))
readr::write_csv(bind_rows(probabilities), file.path(out, "probabilities.csv"))
jsonlite::write_json(list(status = "IMPLEMENTATION_SMOKE_NOT_PERFORMANCE_VALIDATION",
  model_id = "FM-1.8.0-alpha.1", formal_model = "FM-1.7.0", labels_opened_by_client = FALSE,
  prior_outcomes_known = TRUE, parent_sha256 = manifest$forecast_sha256,
  config_sha256 = digest::digest(file = file.path(root, "config/fundamental-models/FM-1.8.0-alpha.1.json"), algo = "sha256"),
  alpha_sha256 = digest::digest(file = file.path(root, "packages/beidan/R/alpha_top3_draw.R"), algo = "sha256"),
  client_sha256 = digest::digest(file = file.path(root, "r/fm18_alpha_smoke.R"), algo = "sha256"),
  output_sha256 = digest::digest(file = file.path(out, "smoke.rds"), algo = "sha256"),
  code_binding = "Alpha body + imported hash and cutoff bodies; shared context transitive implementation receipt",
  fixture_cutoffs = lapply(outputs, function(x) x$receipt$cutoff)),
  file.path(out, "receipt.json"), pretty = TRUE, auto_unbox = TRUE)
print(bind_rows(probabilities))
