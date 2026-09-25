testthat::test_that('backend validates its explicit interpreter before initialization', {
  testthat::expect_error(python_backend(NA_character_))
  testthat::expect_error(python_backend('/nonexistent/beidan-python'))
  testthat::expect_error(learning_cutoff('00123', Sys.time(), list()), 'backend')
})

testthat::test_that('bundled Python cutoff preserves issue identity and UTC', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  backend <- python_backend(python)
  cutoff <- learning_cutoff('00123', as.POSIXct('2026-09-22 12:00:00', tz='UTC'), backend)
  testthat::expect_identical(reticulate::py_to_r(cutoff$target_issue), '00123')
  testthat::expect_identical(reticulate::py_to_r(cutoff$cutoff_ts$isoformat()), '2026-09-22T12:00:00+00:00')
  testthat::expect_error(learning_cutoff('', as.POSIXct('2026-09-22',tz='UTC'), backend))
  testthat::expect_error(learning_cutoff('00123', as.POSIXct(NA,tz='UTC'), backend), 'nonmissing')
  testthat::expect_error(learning_cutoff('00123', as.POSIXct('2026-09-22',tz='Asia/Shanghai'), backend), 'UTC')
})

testthat::test_that('table roundtrips preserve identifiers, UTC, missing and empty schemas', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  backend <- python_backend(python)
  issue <- make_example_issue('00123', match_kickoff_window('2026-09-22', 7L))
  for (name in c('fixtures', 'euro', 'totals', 'prematch_sp', 'match_status')) {
    input <- tibble::as_tibble(lapply(issue[[name]], unname))
    testthat::expect_equal(r_table(python_table(input, name, backend), name), input)
    empty <- match_typed_empty(name)
    testthat::expect_equal(r_table(python_table(empty, name, backend), name), empty)
  }
  nullable <- match_typed_empty('tickets')
  nullable[1, ] <- list('00123', '00001', 0.5, NA_real_, NA_real_)
  testthat::expect_equal(r_table(python_table(nullable, 'tickets', backend), 'tickets'), nullable)
  bad <- issue$fixtures
  bad$fixture_id <- as.numeric(seq_len(nrow(bad)))
  testthat::expect_error(python_table(bad, 'fixtures', backend), 'character')
  testthat::expect_error(r_table(list(), 'fixtures'), 'pandas')
})

testthat::test_that('Python conversion rejects integer overflow and naive timestamps', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  backend <- python_backend(python)
  input <- make_example_issue('00123', match_kickoff_window('2026-09-22', 7L))$fixtures
  data <- python_table(input, 'fixtures', backend)
  builtins <- reticulate::import_builtins(convert=FALSE)
  data$`__setitem__`('slot', builtins$int('9007199254740993'))
  testthat::expect_error(r_table(data, 'fixtures'), 'integer range')
  data <- python_table(input, 'fixtures', backend)
  data$`__setitem__`('kickoff_at', data$`__getitem__`('kickoff_at')$dt$tz_localize(NULL))
  testthat::expect_error(r_table(data, 'fixtures'), 'timezone')
})


testthat::test_that('a clean process loads the package without Python or file writes', {
  result <- callr::r(function(lib) {
    .libPaths(lib)
    directory <- tempfile('beidan-load-')
    dir.create(directory)
    setwd(directory)
    before <- list.files('.', all.files=TRUE)
    library(beidan)
    list(python=reticulate::py_available(initialize=FALSE),
         files_unchanged=identical(before, list.files('.', all.files=TRUE)),
         api=is.function(parlay_settings))
  }, args=list(lib=.libPaths()))
  testthat::expect_false(result$python)
  testthat::expect_true(result$files_unchanged)
  testthat::expect_true(result$api)
})


testthat::test_that('an initialized backend rejects a different interpreter', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  python_backend(python)
  alternate <- tempfile('other-python-')
  file.create(alternate)
  on.exit(unlink(alternate))
  testthat::expect_error(python_backend(alternate), 'another interpreter')
})


testthat::test_that('nullable integers and booleans remain missing in both languages', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  backend <- python_backend(python)
  input <- make_example_issue('00123', match_kickoff_window('2026-09-22', 7L))$fixtures
  input$handicap[1] <- NA_integer_
  data <- python_table(input, 'fixtures', backend)
  testthat::expect_true(reticulate::py_to_r(data$handicap$isna()$iloc$`__getitem__`(0L)))
  testthat::expect_equal(r_table(data, 'fixtures'), input)
  input <- tibble::tibble(candidate_id=c('c','c','c'), fixture_id=c('f1','f2','f3'),
    outcome=c('W','W','W'), allowed=c(NA, FALSE, TRUE), preference=c(NA_integer_,0L,1L))
  data <- python_table(input, 'supports', backend)
  testthat::expect_true(reticulate::py_to_r(data$allowed$isna()$iloc$`__getitem__`(0L)))
  testthat::expect_equal(r_table(data, 'supports'), input)
  for (name in names(match_table_schemas())) {
    empty <- match_typed_empty(name)
    testthat::expect_equal(r_table(python_table(empty, name, backend), name), empty)
  }
})


testthat::test_that('environment override cannot falsify interpreter identity', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  error <- callr::r(function(lib, python) {
    .libPaths(lib)
    library(beidan)
    alias <- tempfile('beidan-python-alias-')
    stopifnot(file.symlink(python, alias))
    on.exit(unlink(alias))
    Sys.setenv(RETICULATE_PYTHON=python)
    tryCatch({suppressWarnings(python_backend(alias)); 'incorrectly accepted'},
             error=function(e) conditionMessage(e))
  }, args=list(lib=.libPaths(), python=python))
  testthat::expect_match(error, 'another interpreter')
})
