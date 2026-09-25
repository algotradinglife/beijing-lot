# Execute the actual walkthrough code with missing optional data and a BJT
# settlement parameter; its public settlement API must receive the same UTC instant.
project_root <- Sys.getenv("BEIDAN_PROJECT_ROOT")
stopifnot(nzchar(project_root))
Sys.setenv(BEIDAN_PROJECT_DIR = project_root,
           BEIDAN_SCHEDULE_RDS = tempfile("missing-schedule-"),
           BEIDAN_SETTLEMENT_AT = "2026-09-30 20:00:00")
script <- tempfile(fileext = ".R")
knitr::purl(file.path(project_root, "quarto/26098_walkthrough.qmd"),
            output = script, quiet = TRUE)
walkthrough <- new.env(parent = globalenv())
sys.source(script, envir = walkthrough)
testthat::expect_null(walkthrough$schedule)
testthat::expect_null(walkthrough$result)
testthat::expect_null(walkthrough$settled)
testthat::expect_identical(attr(walkthrough$settlement_at, "tzone"), "UTC")
testthat::expect_equal(as.numeric(walkthrough$settlement_at),
  as.numeric(lubridate::ymd_hms("2026-09-30 12:00:00", tz = "UTC")))
cat("Walkthrough missing-input gate and real configuration timezone regression passed.\n")
