# Execute the actual walkthrough with missing optional data and direct BJT configuration.
project_root <- Sys.getenv("BEIDAN_PROJECT_ROOT")
stopifnot(nzchar(project_root))
Sys.setenv(BEIDAN_PROJECT_DIR = project_root,
           BEIDAN_SCHEDULE_RDS = tempfile("missing-schedule-"))
script <- tempfile(fileext = ".R")
knitr::purl(file.path(project_root, "quarto/26098_walkthrough.qmd"),
            output = script, quiet = TRUE)
walkthrough <- new.env(parent = globalenv())
sys.source(script, envir = walkthrough)
testthat::expect_null(walkthrough$schedule)
testthat::expect_null(walkthrough$result)
testthat::expect_null(walkthrough$settled)
testthat::expect_null(walkthrough$settlement_at)
testthat::expect_identical(attr(walkthrough$decision_at, "tzone"), "Asia/Shanghai")
testthat::expect_equal(as.numeric(walkthrough$decision_at),
  as.numeric(lubridate::ymd_hms("2026-09-25 12:00:00", tz = "UTC")))
# Evaluate the actual as_of argument expression from both production call sites.
expressions <- parse(script)
calls <- list()
collect_calls <- function(x) {
  if (!is.call(x) && !is.expression(x)) return(invisible(NULL))
  if (is.call(x) && identical(x[[1]], quote(beidan::parlay_settle_plan))) {
    calls[[length(calls) + 1L]] <<- x
  }
  if (is.call(x) && identical(x[[1]], quote(beidan::parlay_diagnose_plan))) {
    calls[[length(calls) + 1L]] <<- x
  }
  for (part in as.list(x)) if (is.call(part) || is.expression(part)) collect_calls(part)
  invisible(NULL)
}
collect_calls(expressions)
testthat::expect_length(calls, 2L)
walkthrough$settlement_at <- lubridate::ymd_hms("2026-09-30 20:00:00", tz = "Asia/Shanghai")
for (call in calls) {
  actual <- eval(call$as_of, walkthrough)
  testthat::expect_identical(attr(actual, "tzone"), "UTC")
  testthat::expect_equal(as.numeric(actual), as.numeric(walkthrough$settlement_at))
}
cat("Walkthrough missing-input gate, direct BJT configuration and actual as_of boundary passed.\n")

# Real fixture checks run outside the analysis document.
Sys.setenv(BEIDAN_SCHEDULE_RDS = file.path(project_root,
  "packages/beidan/tests/testthat/fixtures/schedule_identity/schedule.rds"))
real_walkthrough <- new.env(parent = globalenv())
sys.source(script, envir = real_walkthrough)
sys.source(file.path(project_root, "scripts/acceptance/walkthrough_analysis_checks.R"),
           envir = real_walkthrough)
cat("Real schedule analysis checks passed outside QMD; missing markets remain untested.\n")
