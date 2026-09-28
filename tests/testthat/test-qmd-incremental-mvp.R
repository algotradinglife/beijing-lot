# Contract tests for the #501 incremental QMD R functions.
#
# Deterministic and offline. The reticulate tests use the project interpreter
# explicitly (.venv/bin/python) and never touch the network or a database.
library(testthat)

project_root <- normalizePath(testthat::test_path("..", ".."))
source(file.path(project_root, "r", "python_bridge.R"))
source(file.path(project_root, "r", "qmd_incremental_mvp.R"))

project_python <- file.path(project_root, ".venv", "bin", "python")
python_module <- file.path(project_root, "src", "qmd_incremental_mvp.py")
bridge_helper <- file.path(project_root, "r", "python_bridge.R")

fixture_valid <- function() {
  tibble::tibble(
    fixture_id = c("001", "002", "003"),
    league = c("英超", "英超", "西甲"),
    predicted = c(0.25, 0.5, 1.0),
    observed = c(0, 1, NA_real_)
  )
}

test_that("mvp_validate accepts a valid table and returns it unchanged", {
  x <- fixture_valid()
  out <- mvp_validate(x)
  expect_identical(out, x)
  expect_true(tibble::is_tibble(out))
})

test_that("mvp_validate accepts a typed empty tibble", {
  empty <- tibble::tibble(
    fixture_id = character(0),
    league = character(0),
    predicted = double(0),
    observed = double(0)
  )
  expect_identical(mvp_validate(empty), empty)
})

test_that("mvp_validate rejects malformed shapes and wrong types", {
  x <- fixture_valid()
  expect_error(mvp_validate(as.data.frame(x)), "tibble")
  expect_error(mvp_validate(x[, c("fixture_id", "league", "predicted")]), "columns")
  expect_error(mvp_validate(dplyr::mutate(x, extra = 1L)), "columns")
  expect_error(mvp_validate(dplyr::mutate(x, fixture_id = 1:3)), "fixture_id must be character")
  expect_error(mvp_validate(dplyr::mutate(x, league = 1:3)), "league must be character")
  expect_error(mvp_validate(dplyr::mutate(x, predicted = as.integer(round(predicted * 10)))),
               "predicted must be double")
  expect_error(mvp_validate(dplyr::mutate(x, observed = as.integer(observed))),
               "observed must be double")
})

test_that("mvp_validate rejects invalid ids and leagues", {
  x <- fixture_valid()
  expect_error(mvp_validate(dplyr::mutate(x, fixture_id = c("001", "001", "003"))), "unique")
  expect_error(mvp_validate(dplyr::mutate(x, fixture_id = c("001", "", "003"))), "nonempty")
  expect_error(mvp_validate(dplyr::mutate(x, fixture_id = c("001", NA, "003"))), "not be missing")
  expect_error(mvp_validate(dplyr::mutate(x, league = c("英超", "", "西甲"))), "nonempty")
  expect_error(mvp_validate(dplyr::mutate(x, league = c("英超", NA, "西甲"))), "not be missing")
})

test_that("mvp_validate rejects nonfinite and out-of-range values", {
  x <- fixture_valid()
  expect_error(mvp_validate(dplyr::mutate(x, predicted = c(0.1, NaN, 0.3))), "NaN")
  expect_error(mvp_validate(dplyr::mutate(x, predicted = c(0.1, NA, 0.3))), "not be missing")
  expect_error(mvp_validate(dplyr::mutate(x, predicted = c(0.1, Inf, 0.3))), "finite")
  expect_error(mvp_validate(dplyr::mutate(x, predicted = c(0.1, 1.2, 0.3))), "\\[0, 1\\]")
  expect_error(mvp_validate(dplyr::mutate(x, observed = c(0, NaN, NA_real_))), "NaN")
  expect_error(mvp_validate(dplyr::mutate(x, observed = c(0, Inf, NA_real_))), "finite")
  expect_error(mvp_validate(dplyr::mutate(x, observed = c(0, 2, NA_real_))), "0, 1, or NA")
})

test_that("mvp_read reads explicit types and validates", {
  path <- tempfile(fileext = ".csv")
  on.exit(unlink(path), add = TRUE)
  writeLines(
    c("fixture_id,league,predicted,observed", "001,英超,0.25,0", "002,西甲,0.5,1", "003,西甲,1,NA"),
    path
  )
  out <- mvp_read(path)
  expect_true(tibble::is_tibble(out))
  expect_identical(out$fixture_id, c("001", "002", "003"))
  expect_identical(out$league, c("英超", "西甲", "西甲"))
  expect_identical(out$predicted, c(0.25, 0.5, 1.0))
  expect_identical(out$observed, c(0, 1, NA_real_))
  expect_type(out$observed, "double")
})

test_that("mvp_read treats a literal NA field as missing", {
  path <- tempfile(fileext = ".csv")
  on.exit(unlink(path), add = TRUE)
  writeLines(c("fixture_id,league,predicted,observed", "1,英超,0.5,NA"), path)
  out <- mvp_read(path)
  expect_true(is.na(out$observed))
})

test_that("mvp_read rejects a malformed observed field instead of reading NA", {
  path <- tempfile(fileext = ".csv")
  on.exit(unlink(path), add = TRUE)
  writeLines(c("fixture_id,league,predicted,observed", "001,英超,0.5,not_a_label"), path)
  # Fatal, and the error names the parse problem rather than passing NA through.
  expect_error(suppressWarnings(mvp_read(path)), "parse problems")
})

test_that("mvp_read rejects a blank observed field rather than conflating it with NA", {
  path <- tempfile(fileext = ".csv")
  on.exit(unlink(path), add = TRUE)
  # A blank numeric field is a readr parse problem (not the na token); it must
  # stop the read even though a literal NA in the same position is accepted.
  writeLines(c("fixture_id,league,predicted,observed", "001,英超,0.5,", "002,英超,0.5,1"), path)
  expect_error(suppressWarnings(mvp_read(path)), "parse problems")

  blank_predicted <- tempfile(fileext = ".csv")
  on.exit(unlink(blank_predicted), add = TRUE)
  writeLines(c("fixture_id,league,predicted,observed", "001,英超,,0"), blank_predicted)
  expect_error(suppressWarnings(mvp_read(blank_predicted)), "parse problems")
})

test_that("mvp_read rejects a blank text field as nonempty, not as NA", {
  path <- tempfile(fileext = ".csv")
  on.exit(unlink(path), add = TRUE)
  writeLines(c("fixture_id,league,predicted,observed", "001,,0.5,1"), path)
  # A blank text field is the empty string (not the na token), so it reaches the
  # contract check and stops there rather than becoming a valid missing league.
  expect_error(mvp_read(path), "league must be nonempty")
})

test_that("mvp_read is fatal on parse errors and contract violations", {
  missing_file <- tempfile(fileext = ".csv")
  expect_error(mvp_read(missing_file), "does not exist")

  bad_number <- tempfile(fileext = ".csv")
  on.exit(unlink(bad_number), add = TRUE)
  writeLines(c("fixture_id,league,predicted,observed", "001,英超,not_a_number,0"), bad_number)
  expect_error(suppressWarnings(mvp_read(bad_number)), "parse problems")

  bad_contract <- tempfile(fileext = ".csv")
  on.exit(unlink(bad_contract), add = TRUE)
  writeLines(c("fixture_id,league,predicted,observed", "001,英超,1.5,0"), bad_contract)
  expect_error(mvp_read(bad_contract), "\\[0, 1\\]")

  expect_error(mvp_read(NA_character_), "nonempty")
})

test_that("mvp_errors uses the project .venv interpreter through reticulate", {
  skip_if_not(file.exists(project_python), "project .venv python is unavailable")
  out <- mvp_errors(
    fixture_valid(),
    python = project_python,
    project_root = project_root,
    source_files = c(python_module, bridge_helper)
  )
  expect_true(tibble::is_tibble(out))
  expect_identical(names(out), c("fixture_id", "league", "squared_error"))
  expect_identical(out$fixture_id, c("001", "002", "003"))
  expect_identical(out$league, c("英超", "英超", "西甲"))
  expect_equal(out$squared_error[1], 0.0625)
  expect_equal(out$squared_error[2], 0.25)
  expect_true(is.na(out$squared_error[3]))
})

test_that("mvp_errors keeps all-missing labels as NA and empty input typed", {
  skip_if_not(file.exists(project_python), "project .venv python is unavailable")
  all_na <- tibble::tibble(
    fixture_id = c("a", "b"),
    league = c("英超", "西甲"),
    predicted = c(0.2, 0.8),
    observed = c(NA_real_, NA_real_)
  )
  out <- mvp_errors(all_na, project_python, project_root, c(python_module, bridge_helper))
  expect_identical(out$squared_error, c(NA_real_, NA_real_))

  empty <- tibble::tibble(
    fixture_id = character(0),
    league = character(0),
    predicted = double(0),
    observed = double(0)
  )
  out_empty <- mvp_errors(empty, project_python, project_root, c(python_module, bridge_helper))
  expect_true(tibble::is_tibble(out_empty))
  expect_equal(nrow(out_empty), 0)
  expect_type(out_empty$squared_error, "double")
})

test_that("mvp_errors rejects bad interpreters, roots, and source files", {
  expect_error(
    mvp_errors(fixture_valid(), tempfile(), project_root, c(python_module, bridge_helper)),
    "interpreter"
  )
  expect_error(
    mvp_errors(fixture_valid(), project_python, tempfile(), c(python_module, bridge_helper)),
    "project_root"
  )
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, character(0)),
    "source_files"
  )
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, tempfile()),
    "missing source files"
  )
})

test_that("mvp_errors requires the bridge to be sourced by the caller", {
  # Remove the visible top-level dependency and confirm the failure is loud
  # rather than a silent fallback.
  saved <- project_python_module
  on.exit(assign("project_python_module", saved, envir = globalenv()), add = TRUE)
  rm("project_python_module", envir = globalenv())
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "source r/python_bridge.R"
  )
})

test_that("mvp_errors re-validates its input", {
  bad <- dplyr::mutate(fixture_valid(), predicted = c(0.1, 1.5, 0.3))
  expect_error(
    mvp_errors(bad, file.path(project_root, ".venv", "bin", "python"), project_root,
               c(python_module, bridge_helper)),
    "\\[0, 1\\]"
  )
})

# --- mvp_errors boundary contract, exercised against a fake imported module ---
#
# These tests substitute the module the bridge returns, so they do not depend on
# reticulate or the interpreter. The authoritative bridge (r/python_bridge.R) is
# unchanged; only the `project_python_module` binding that `mvp_errors` resolves
# is swapped for the duration of a test. These functions are sourced into the
# global environment rather than a package namespace, so the binding is restored
# explicitly with `on.exit` (the same pattern as the bridge-removal test below).
fake_module <- function(records) {
  list(squared_errors = function(ids, predicted, observed) records)
}
mock_python_module <- function(records, envir = globalenv()) {
  saved <- get("project_python_module", envir = envir)
  assign("project_python_module", function(module, root, python) fake_module(records), envir = envir)
  withr::defer(assign("project_python_module", saved, envir = envir), envir = parent.frame())
  invisible(NULL)
}
expected_records <- function() {
  list(
    list(fixture_id = "001", squared_error = 0),
    list(fixture_id = "002", squared_error = 1),
    list(fixture_id = "003", squared_error = NULL)
  )
}

test_that("mvp_errors accepts a well-formed fake module result", {
  mock_python_module(expected_records())
  out <- mvp_errors(
    fixture_valid(), project_python, project_root, c(python_module, bridge_helper)
  )
  expect_identical(names(out), c("fixture_id", "league", "squared_error"))
  expect_identical(out$fixture_id, c("001", "002", "003"))
  expect_identical(out$squared_error, c(0, 1, NA_real_))
})

test_that("mvp_errors rejects a string squared_error instead of coercing it", {
  records <- expected_records()
  records[[1]]$squared_error <- "0.0625"
  mock_python_module(records)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "squared_error must be a single number"
  )
})

test_that("mvp_errors rejects logical, list, and vector squared_error values", {
  as_logical <- expected_records()
  as_logical[[1]]$squared_error <- TRUE
  mock_python_module(as_logical)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "squared_error must be a single number"
  )

  as_list <- expected_records()
  as_list[[1]]$squared_error <- list(0.0625)
  mock_python_module(as_list)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "squared_error must be a single number"
  )

  as_vector <- expected_records()
  as_vector[[1]]$squared_error <- c(0.0625, 0.25)
  mock_python_module(as_vector)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "squared_error must be a single number"
  )
})

test_that("mvp_errors rejects a missing pattern that does not match observed NA", {
  # Input row 3 is NA but the module returns a score: mismatch must stop.
  scored_missing <- expected_records()
  scored_missing[[3]]$squared_error <- 0.25
  mock_python_module(scored_missing)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "missing-value pattern"
  )

  # Input row 1 is known but the module returns NULL: the converse mismatch.
  # `[<- list(NULL)` keeps the field present with a NULL value; `$<- NULL`
  # would delete the field and trip the field-set check instead.
  null_known <- expected_records()
  null_known[[1]]["squared_error"] <- list(NULL)
  mock_python_module(null_known)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "missing-value pattern"
  )
})

test_that("mvp_errors rejects records with missing or extra fields", {
  missing_field <- expected_records()
  missing_field[[1]] <- list(fixture_id = "001")
  mock_python_module(missing_field)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "fields must be exactly"
  )

  extra_field <- expected_records()
  extra_field[[1]]$extra <- 1
  mock_python_module(extra_field)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "fields must be exactly"
  )
})

test_that("mvp_errors rejects a wrong id, row count, and non-record rows", {
  wrong_id <- expected_records()
  wrong_id[[2]]$fixture_id <- "999"
  mock_python_module(wrong_id)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "fixture_ids do not match"
  )

  mock_python_module(expected_records()[1:2])
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "rows for"
  )

  mock_python_module(list(0.1, 0.2, 0.3))
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "must be records"
  )
})

test_that("mvp_errors rejects nonfinite and out-of-range fake scores", {
  nan_score <- expected_records()
  nan_score[[1]]$squared_error <- NaN
  mock_python_module(nan_score)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "must not be NaN"
  )

  inf_score <- expected_records()
  inf_score[[1]]$squared_error <- Inf
  mock_python_module(inf_score)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "must be finite"
  )

  range_score <- expected_records()
  range_score[[1]]$squared_error <- 1.5
  mock_python_module(range_score)
  expect_error(
    mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper)),
    "\\[0, 1\\]"
  )
})

test_that("mvp_errors passes NA labels to the module as NULL", {
  captured <- NULL
  saved <- get("project_python_module", envir = globalenv())
  assign("project_python_module", function(module, root, python) {
    list(squared_errors = function(ids, predicted, observed) {
      captured <<- observed
      expected_records()
    })
  }, envir = globalenv())
  withr::defer(assign("project_python_module", saved, envir = globalenv()))
  mvp_errors(fixture_valid(), project_python, project_root, c(python_module, bridge_helper))
  expect_identical(captured, list(0, 1, NULL))
})

test_that("mvp_summary groups by league with explicit counts", {
  errors <- tibble::tibble(
    fixture_id = c("001", "002", "003", "004"),
    league = c("英超", "英超", "西甲", "西甲"),
    squared_error = c(0.04, 0.16, NA_real_, 0.25)
  )
  out <- mvp_summary(errors)
  expect_true(tibble::is_tibble(out))
  expect_identical(names(out), c("league", "n_total", "n_scored", "n_missing", "mean_error"))
  expect_identical(out$league, c("英超", "西甲"))
  expect_identical(out$n_total, c(2L, 2L))
  expect_identical(out$n_scored, c(2L, 1L))
  expect_identical(out$n_missing, c(0L, 1L))
  expect_equal(out$mean_error[1], 0.1)
  expect_equal(out$mean_error[2], 0.25)
  expect_type(out$n_total, "integer")
  expect_type(out$mean_error, "double")
})

test_that("mvp_summary reports all-missing league as NA, never zero", {
  errors <- tibble::tibble(
    fixture_id = c("001", "002"),
    league = c("英超", "英超"),
    squared_error = c(NA_real_, NA_real_)
  )
  out <- mvp_summary(errors)
  expect_identical(out$n_scored, 0L)
  expect_identical(out$n_missing, 2L)
  expect_true(is.na(out$mean_error))
  expect_false(is.nan(out$mean_error))
  expect_identical(out$mean_error, NA_real_)
})

test_that("mvp_summary returns a typed empty tibble for empty input", {
  empty <- tibble::tibble(
    fixture_id = character(0),
    league = character(0),
    squared_error = double(0)
  )
  out <- mvp_summary(empty)
  expect_true(tibble::is_tibble(out))
  expect_equal(nrow(out), 0)
  expect_identical(names(out), c("league", "n_total", "n_scored", "n_missing", "mean_error"))
  expect_type(out$league, "character")
  expect_type(out$n_total, "integer")
  expect_type(out$n_scored, "integer")
  expect_type(out$n_missing, "integer")
  expect_type(out$mean_error, "double")
})

test_that("mvp_summary rejects schema and value violations", {
  good <- tibble::tibble(
    fixture_id = c("001", "002"),
    league = c("英超", "西甲"),
    squared_error = c(0.04, NA_real_)
  )
  expect_error(mvp_summary(as.data.frame(good)), "tibble")
  expect_error(mvp_summary(good[, c("fixture_id", "league")]), "squared_error")
  expect_error(mvp_summary(dplyr::mutate(good, squared_error = as.integer(1))),
               "squared_error must be double")
  expect_error(mvp_summary(dplyr::mutate(good, fixture_id = c("001", "001"))), "unique")
  expect_error(mvp_summary(dplyr::mutate(good, league = c("英超", ""))), "nonempty")
  expect_error(mvp_summary(dplyr::mutate(good, squared_error = c(NaN, 0.1))), "NaN")
  expect_error(mvp_summary(dplyr::mutate(good, squared_error = c(1.5, 0.1))), "\\[0, 1\\]")
  expect_error(mvp_summary(dplyr::mutate(good, squared_error = c(Inf, 0.1))), "finite")
})

test_that("mvp_summary integrates with mvp_errors output", {
  skip_if_not(file.exists(project_python), "project .venv python is unavailable")
  errors <- mvp_errors(
    fixture_valid(),
    python = project_python,
    project_root = project_root,
    source_files = c(python_module, bridge_helper)
  )
  out <- mvp_summary(errors)
  expect_identical(out$league, c("英超", "西甲"))
  expect_identical(out$n_total, c(2L, 1L))
  expect_identical(out$n_missing, c(0L, 1L))
  expect_equal(out$mean_error[1], (0.0625 + 0.25) / 2)
  expect_identical(out$mean_error[2], NA_real_)
  expect_false(any(is.nan(out$mean_error)))
})


test_that("mvp_errors rejects integers and numeric NA for a known label", {
  for (bad_score in list(0L, NA_real_)) {
    records <- expected_records()
    records[[1]]$squared_error <- bad_score
    mock_python_module(records)
    expect_error(mvp_errors(fixture_valid(), project_python, project_root,
                            c(python_module, bridge_helper)),
                 "single number|numeric missing score")
  }
})


test_that("numeric contracts reject matrix and classed columns", {
  x <- fixture_valid()
  for (column in c("predicted", "observed")) {
    bad <- x
    bad[[column]] <- matrix(c(0, 1, 0, 1, 0, 1), nrow = 3)
    expect_error(mvp_validate(bad), "plain vectors")
    bad[[column]] <- as.Date(c(0, 1, 0), origin = "1970-01-01")
    expect_error(mvp_validate(bad), "plain vectors")
  }
  bad <- x
  bad$fixture_id <- matrix(x$fixture_id, ncol = 1)
  expect_error(mvp_validate(bad), "plain vectors")
  for (scores in list(matrix(c(0.1, 0.9), nrow = 1),
                      as.difftime(0.5, units = "secs"))) {
    errors <- tibble::tibble(fixture_id = "001", league = "A", squared_error = scores)
    expect_error(mvp_summary(errors), "plain vectors")
  }
  records <- expected_records()
  records[[1]]$squared_error <- matrix(0.25, nrow = 1)
  mock_python_module(records)
  expect_error(mvp_errors(x, project_python, project_root, c(python_module, bridge_helper)),
               "single number")
})
