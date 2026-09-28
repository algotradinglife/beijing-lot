# Integration acceptance for the knitr alternative. All mutations are isolated.
# Existing targets acceptance is run separately and its raw evidence is retained.
root <- normalizePath(getwd())
work <- tempfile("qmd-knitr-comparison-")
dir.create(work)
files <- c("r/qmd_incremental_mvp.R", "r/python_bridge.R",
           "src/qmd_incremental_mvp.py", "config/qmd_incremental_mvp/run.json",
           "config/qmd_incremental_mvp/display.json", "config/qmd_incremental_mvp/runtime.json",
           "config/qmd_incremental_mvp/packages.json",
           "quarto/qmd_incremental_mvp_knitr.qmd",
           "tests/fixtures/qmd_incremental_mvp/synthetic.csv")
for (path in files) {
  dir.create(dirname(file.path(work, path)), recursive = TRUE, showWarnings = FALSE)
  stopifnot(file.copy(path, file.path(work, path)))
}
writeLines(c("project:", "  type: default", "  execute-dir: project",
             "execute:", "  freeze: false", "  error: false"), file.path(work, "_quarto.yml"))
cfg <- jsonlite::read_json(file.path(work, "config/qmd_incremental_mvp/run.json"))
cfg$python <- file.path(root, ".venv/bin/python")
jsonlite::write_json(cfg, file.path(work, "config/qmd_incremental_mvp/run.json"), auto_unbox = TRUE)
setwd(work)
dir.create("audit")
writeLines(c("audit_dir: audit"), "audit-params.yml")
original_r <- readLines("r/qmd_incremental_mvp.R")
original_python <- readLines("src/qmd_incremental_mvp.py")
original_csv <- readLines(cfg$input)
records <- list()
reference <- NULL
for (scenario in c("initial", "unchanged", "display", "r_function", "python_source", "python_behavior", "restored_python",
                   "valid_input", "invalid_input", "repaired", "clean")) {
  if (scenario == "display") {
    writeLines('{"title":"Changed display only","digits":4}', "config/qmd_incremental_mvp/display.json")
  }
  if (scenario == "r_function") {
    code <- sub("mvp_summary <- function(errors) {",
                "mvp_summary <- function(errors) {\n  errors <- dplyr::arrange(errors, fixture_id)",
                original_r, fixed = TRUE)
    stopifnot(!identical(code, original_r))
    writeLines(code, "r/qmd_incremental_mvp.R")
  }
  if (scenario == "python_source") {
    writeLines(c(original_python, "# changed implementation identity"), "src/qmd_incremental_mvp.py")
  }
  if (scenario == "python_behavior") {
    code <- sub("return float((predicted - observed) ** 2)",
                "return float(0.5 * (predicted - observed) ** 2)", original_python, fixed = TRUE)
    stopifnot(!identical(code, original_python))
    writeLines(code, "src/qmd_incremental_mvp.py")
  }
  if (scenario == "restored_python") writeLines(original_python, "src/qmd_incremental_mvp.py")
  if (scenario == "valid_input") writeLines(sub("0.8", "0.6", original_csv, fixed = TRUE), cfg$input)
  if (scenario == "invalid_input") writeLines(sub("0.8", "invalid-number", original_csv, fixed = TRUE), cfg$input)
  if (scenario == "repaired") writeLines(original_csv, cfg$input)
  unlink(c("audit/executed.txt", "audit/values.rds"))
  started <- proc.time()[["elapsed"]]
  args <- c("render", "quarto/qmd_incremental_mvp_knitr.qmd", "--execute-dir", shQuote(work),
            "--execute-params", "audit-params.yml")
  if (scenario == "clean") args <- c(args, "--no-cache")
  output <- system2("quarto", args, stdout = TRUE, stderr = TRUE)
  writeLines(output, paste0("audit/", scenario, ".log"))
  status <- attr(output, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L && scenario != "invalid_input") cat(output, sep = "\n")
  elapsed <- proc.time()[["elapsed"]] - started
  changed <- if (file.exists("audit/executed.txt")) readLines("audit/executed.txt") else character()
  if (scenario == "invalid_input") {
    stopifnot(status != 0L, !file.exists("audit/values.rds"),
              any(grepl("CSV parse problems", readLines(paste0("audit/", scenario, ".log")), fixed = TRUE)))
  } else {
    stopifnot(status == 0L, file.exists("audit/values.rds"))
    value <- readRDS("audit/values.rds")
    stopifnot(tibble::is_tibble(value$summary),
              isTRUE(all.equal(value$summary$mean_error[value$summary$league == "A"],
                               if (scenario == "valid_input") 0.125 else if (scenario == "python_behavior") 0.0325 else 0.065)),
              identical(value$summary$mean_error[value$summary$league == "B"], NA_real_),
              identical(value$errors$fixture_id, c("001", "002", "003", "004", "005")),
              identical(is.na(value$errors$squared_error), c(FALSE, FALSE, TRUE, TRUE, TRUE)))
    if (scenario %in% c("unchanged", "display")) stopifnot(length(changed) == 0L)
    if (scenario %in% c("initial", "r_function", "valid_input", "clean")) {
      stopifnot(identical(changed, c("matches", "errors", "summary")))
    }
    if (scenario %in% c("python_source", "python_behavior", "restored_python")) {
      stopifnot(identical(changed, c("errors", "summary")))
    }
    if (scenario == "repaired") reference <- value
    if (scenario == "clean") stopifnot(identical(reference, value))
    html <- readLines("quarto/qmd_incremental_mvp_knitr.html", warn = FALSE)
    stopifnot(any(grepl(if (scenario == "valid_input") "0.125" else if (scenario == "python_behavior") "0.0325" else "0.065", html, fixed = TRUE)),
              any(grepl("001", html, fixed = TRUE)))
  }
  records[[scenario]] <- list(exit_status = status, elapsed_seconds = elapsed, executed_blocks = changed)
  cat(scenario, ": PASS; executed =", paste(changed, collapse = ","), "\n")
}
setwd(root)
dir.create("docs/research/qmd_incremental_mvp/knitr-logs", recursive = TRUE, showWarnings = FALSE)
file.copy(list.files(file.path(work, "audit"), pattern = "[.]log$", full.names = TRUE),
          "docs/research/qmd_incremental_mvp/knitr-logs", overwrite = TRUE)
jsonlite::write_json(list(scenarios = records, input_md5 = unname(tools::md5sum(cfg$input)),
                         generated_at = format(lubridate::now(tzone = "UTC"), usetz = TRUE),
                         source_md5 = as.list(tools::md5sum(files))),
                    "docs/research/qmd_incremental_mvp/knitr-verification.json",
                    auto_unbox = TRUE, pretty = TRUE)
cat("PASS: knitr invalidation, rejection/recovery and uncached reconstruction\n")
