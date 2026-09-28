# Thin CLI. Run from repository root; installs nothing.
args <- commandArgs(trailingOnly = TRUE)
action <- if (length(args)) args[[1L]] else "report"
stopifnot(action %in% c("prototype", "compute", "report", "verify"))
if (action == "verify") {
  source("scripts/verify_qmd_incremental_mvp.R")
} else {
  store <- if (action == "prototype") "results/qmd_incremental_mvp/prototype-store" else
    "results/qmd_incremental_mvp/store"
  config <- "config/qmd_incremental_mvp/run.json"
  if (action == "prototype") {
    dir.create("results/qmd_incremental_mvp", recursive = TRUE, showWarnings = FALSE)
    cfg <- jsonlite::read_json(config)
    cfg$mode <- "prototype"
    config <- "results/qmd_incremental_mvp/prototype.json"
    jsonlite::write_json(cfg, config, auto_unbox = TRUE)
  }
  Sys.setenv(MVP_STORE = store, MVP_CONFIG = config)
  if (action == "compute") {
    targets::tar_make(names = summary_table, script = "config/qmd_incremental_mvp/pipeline.R", store = store)
  } else {
    targets::tar_make(script = "config/qmd_incremental_mvp/pipeline.R", store = store)
  }
}
