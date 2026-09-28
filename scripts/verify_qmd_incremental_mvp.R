# Integration acceptance: mutate an isolated copy, never the developer's source.
# This script intentionally keeps orchestration at top level; domain logic is in r/.
root <- normalizePath(getwd())
work <- tempfile("qmd-mvp-verification-")
dir.create(work)
files <- c("r/qmd_incremental_mvp.R", "r/python_bridge.R", "src/qmd_incremental_mvp.py",
           "config/qmd_incremental_mvp/pipeline.R", "config/qmd_incremental_mvp/run.json",
           "config/qmd_incremental_mvp/display.json", "config/qmd_incremental_mvp/runtime.json",
           "config/qmd_incremental_mvp/packages.json",
           "docs/research/qmd_incremental_mvp/review.md",
           "quarto/qmd_incremental_mvp.qmd", "tests/fixtures/qmd_incremental_mvp/synthetic.csv")
for (f in files) {
  dir.create(dirname(file.path(work, f)), recursive = TRUE, showWarnings = FALSE)
  stopifnot(file.copy(f, file.path(work, f)))
}
writeLines(c("project:", "  type: default", "  execute-dir: project", "execute:",
             "  freeze: false", "  cache: false", "  error: false"), file.path(work, "_quarto.yml"))
cfg <- jsonlite::read_json(file.path(work, "config/qmd_incremental_mvp/run.json"))
cfg$python <- file.path(root, ".venv/bin/python")
cfg$mode <- "real"
jsonlite::write_json(cfg, file.path(work, "config/qmd_incremental_mvp/run.json"), auto_unbox = TRUE)
store <- file.path(work, "store")
script <- "config/qmd_incremental_mvp/pipeline.R"
oldwd <- getwd()
setwd(work)
Sys.setenv(MVP_STORE = store, MVP_CONFIG = "config/qmd_incremental_mvp/run.json")
records <- list()
previous <- NULL
original_r <- readLines("r/qmd_incremental_mvp.R")
original_python <- readLines("src/qmd_incremental_mvp.py")
original_csv <- readLines("tests/fixtures/qmd_incremental_mvp/synthetic.csv")
for (scenario in c("initial", "unchanged", "display", "r_function", "python_source", "python_behavior", "restored_python", "valid_input", "invalid_input", "repaired")) {
  if (scenario == "display") {
    writeLines('{"title":"Changed display only","digits":4}', "config/qmd_incremental_mvp/display.json")
  }
  if (scenario == "r_function") {
    # Change only the summary function body, preserving mathematical meaning.
    code <- sub('mvp_summary <- function(errors) {',
                'mvp_summary <- function(errors) {\n  errors <- dplyr::arrange(errors, fixture_id)',
                original_r, fixed = TRUE)
    stopifnot(!identical(code, original_r))
    writeLines(code, "r/qmd_incremental_mvp.R")
  }
  if (scenario == "python_source") {
    # A source edit, even one preserving results, must invalidate Python execution.
    writeLines(c(original_python, "# changed implementation identity"), "src/qmd_incremental_mvp.py")
  }
  if (scenario == "python_behavior") {
    code <- sub("return float((predicted - observed) ** 2)",
                "return float(0.5 * (predicted - observed) ** 2)", original_python, fixed = TRUE)
    stopifnot(!identical(code, original_python))
    writeLines(code, "src/qmd_incremental_mvp.py")
  }
  if (scenario == "restored_python") writeLines(original_python, "src/qmd_incremental_mvp.py")
  if (scenario == "valid_input") {
    writeLines(sub("0.8", "0.6", original_csv, fixed = TRUE),
               "tests/fixtures/qmd_incremental_mvp/synthetic.csv")
  }
  if (scenario == "invalid_input") {
    writeLines(sub("0.8", "invalid-number", original_csv, fixed = TRUE),
               "tests/fixtures/qmd_incremental_mvp/synthetic.csv")
  }
  if (scenario == "repaired") writeLines(original_csv, "tests/fixtures/qmd_incremental_mvp/synthetic.csv")
  before <- Sys.time()
  outcome <- tryCatch({
    targets::tar_make(script = script, store = store)
    "passed"
  }, error = function(e) conditionMessage(e))
  elapsed <- as.numeric(difftime(Sys.time(), before, units = "secs"))
  meta <- targets::tar_meta(store = store, targets_only = TRUE)
  changed <- if (is.null(previous)) meta$name else {
    joined <- dplyr::left_join(meta, previous, by = "name", suffix = c("", "_before"))
    joined$name[is.na(joined$time_before) | joined$time != joined$time_before]
  }
  if (scenario == "invalid_input") {
    stopifnot(outcome != "passed", "matches" %in% meta$name[!is.na(meta$error)])
  } else {
    stopifnot(outcome == "passed")
    value <- targets::tar_read(summary_table, store = store)
    stopifnot(isTRUE(all.equal(value$mean_error[value$league == "A"], if (scenario == "valid_input") 0.125 else if (scenario == "python_behavior") 0.0325 else 0.065)),
              identical(value$mean_error[value$league == "B"], NA_real_),
              identical(targets::tar_read(errors, store = store)$fixture_id,
                        c("001", "002", "003", "004", "005")))
    if (scenario == "unchanged") stopifnot(length(changed) == 0L)
    if (scenario == "display") stopifnot(!any(c("matches", "errors", "summary_table") %in% changed))
    if (scenario == "r_function") stopifnot("summary_table" %in% changed, !any(c("matches", "errors") %in% changed))
    if (scenario == "python_source") stopifnot("errors" %in% changed, !"matches" %in% changed)
    if (scenario %in% c("python_behavior", "restored_python")) {
      stopifnot(all(c("errors", "summary_table") %in% changed), !"matches" %in% changed)
    }
    if (scenario == "valid_input") stopifnot(all(c("matches", "errors", "summary_table") %in% changed))
    html <- readLines("quarto/qmd_incremental_mvp.html", warn = FALSE)
    stopifnot(any(grepl(if (scenario == "valid_input") "0.125" else if (scenario == "python_behavior") "0.0325" else "0.065", html, fixed = TRUE)), any(grepl("001", html, fixed = TRUE)))
  }
  records[[scenario]] <- list(outcome = outcome, elapsed_seconds = elapsed, changed = changed)
  previous <- meta
}
# A fresh independent store must actually rebuild and reproduce the same tables.
reference <- targets::tar_read(summary_table, store = store)
fresh_store <- file.path(work, "fresh-store")
Sys.setenv(MVP_STORE = fresh_store)
targets::tar_make(script = script, store = fresh_store)
stopifnot(identical(reference, targets::tar_read(summary_table, store = fresh_store)))
records$fresh_store <- list(outcome = "passed", matches_incremental = TRUE)
setwd(oldwd)
dir.create("results/qmd_incremental_mvp", recursive = TRUE, showWarnings = FALSE)
jsonlite::write_json(list(scenarios = records, sandbox = work,
                         generated_at = format(Sys.time(), tz = "UTC", usetz = TRUE)),
                    "results/qmd_incremental_mvp/verification.json", pretty = TRUE, auto_unbox = TRUE)
cat("PASS: incremental invalidation, rejection/recovery, and fresh-store reproduction\n")
