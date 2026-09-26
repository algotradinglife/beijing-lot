testthat::test_that('issue schedule column and type contracts are aligned', {
  columns <- issue_schedule_columns()
  types <- issue_schedule_types()
  testthat::expect_identical(names(types), columns)
  testthat::expect_identical(types[["slot"]], 'integer')
  testthat::expect_identical(types[["handicap"]], 'double')
  testthat::expect_identical(types[["kickoff_at"]], 'POSIXct')
  testthat::expect_true('kickoff_group_date' %in% columns)
  testthat::expect_true(all(c('match_status', 'match_status_raw', 'raw_display_nowscore') %in% columns))
  testthat::expect_true(all(c('sale_end_raw_500', 'sale_end_raw_nowscore') %in% columns))
  testthat::expect_identical(types[['sale_end_raw_500']], 'character')
  testthat::expect_identical(types[['sale_end_raw_nowscore']], 'character')
  empty <- issue_schedule_empty()
  testthat::expect_s3_class(empty, 'tbl_df')
  testthat::expect_identical(nrow(empty), 0L)
  testthat::expect_identical(names(empty), columns)
  testthat::expect_s3_class(empty$kickoff_at, 'POSIXct')
  testthat::expect_identical(attr(empty$kickoff_at, 'tzone'), 'Asia/Shanghai')
})

testthat::test_that('rows with real None fields become an equal-length tibble', {
  rows <- list(
    list(issue_id = '26098', slot = 1, kickoff_at = NULL, handicap = 1, score = NULL),
    list(issue_id = '26098', slot = 2, kickoff_at = NULL, handicap = NULL, score = '3-0')
  )
  table <- beidan:::issue_schedule_rows_to_tibble(rows)
  testthat::expect_identical(nrow(table), 2L)
  testthat::expect_identical(names(table), c('issue_id', 'slot', 'kickoff_at', 'handicap', 'score'))
  testthat::expect_true(is.na(table$kickoff_at[[1]]))
  testthat::expect_true(is.na(table$handicap[[2]]))
  testthat::expect_error(beidan:::issue_schedule_rows_to_tibble(list()), 'non-empty')
})

testthat::test_that('coerce rejects fractional slots, bad numbers and non-character ids', {
  base <- as.list(stats::setNames(rep(NA, length(issue_schedule_columns())), issue_schedule_columns()))
  base$issue_id <- '26098'
  base$slot <- 1L
  good <- beidan:::issue_schedule_coerce(as.data.frame(base, stringsAsFactors = FALSE))
  testthat::expect_identical(good$issue_id, '26098')

  fractional <- base
  fractional$slot <- 1.5
  testthat::expect_error(beidan:::issue_schedule_coerce(as.data.frame(fractional, stringsAsFactors = FALSE)),
                         'whole number')

  bad_handicap <- base
  bad_handicap$handicap <- 'not-a-number'
  testthat::expect_error(beidan:::issue_schedule_coerce(as.data.frame(bad_handicap, stringsAsFactors = FALSE)),
                         'non-numeric')

  numeric_id <- base
  numeric_id$issue_id <- 26098
  testthat::expect_error(beidan:::issue_schedule_coerce(as.data.frame(numeric_id, stringsAsFactors = FALSE)),
                         'corrupt identifiers')

  missing <- base
  missing$fixture_key <- NULL
  testthat::expect_error(beidan:::issue_schedule_coerce(as.data.frame(missing, stringsAsFactors = FALSE)),
                         'missing columns')
})

testthat::test_that('timestamp parsing keeps NA and refuses unparsable instants', {
  parsed <- beidan:::issue_schedule_timestamp(c('2026-09-25T05:00:00Z', NA, ''), 'kickoff_at')
  testthat::expect_identical(attr(parsed, 'tzone'), 'Asia/Shanghai')
  testthat::expect_true(is.na(parsed[[2]]))
  testthat::expect_true(is.na(parsed[[3]]))
  testthat::expect_identical(format(parsed[[1]], '%Y-%m-%dT%H:%M:%S', tz = 'UTC'), '2026-09-25T05:00:00')
  testthat::expect_error(beidan:::issue_schedule_timestamp('not-a-time', 'kickoff_at'), 'parseable ISO-8601')
})

testthat::test_that('invalid numeric and identifier inputs fail loudly', {
  testthat::expect_error(fetch_issue_schedule('26A98', tempfile(), structure(list(), class = 'python_backend')),
                         'digits only')
  testthat::expect_error(fetch_issue_schedule('26098', tempfile(), list()), 'python_backend')
  testthat::expect_error(beidan:::issue_schedule_module(list()), 'python_backend')
})

testthat::test_that('the issue_schedule backend is imported from the explicit root', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  backend <- python_backend(python)
  # backend$module is temporal_learning and has no issue_schedule attribute.
  testthat::expect_false(reticulate::py_has_attr(backend$module, 'issue_schedule'))
  module <- beidan:::issue_schedule_module(backend)
  loaded <- reticulate::py_to_r(module$`__file__`)
  expected <- file.path(backend$root, 'beidan_backend', 'issue_schedule', '__init__.py')
  testthat::expect_identical(normalizePath(loaded), normalizePath(expected))
})

testthat::test_that('offline replay through reticulate returns the canonical tibble', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  fixtures <- testthat::test_path('..', 'python', 'fixtures')
  nowscore <- file.path(fixtures, 'nowscore.mini.html')
  page500 <- file.path(fixtures, '500.mini.html')
  testthat::skip_if(!file.exists(nowscore) || !file.exists(page500),
                    'saved issue-schedule fixtures are not installed')
  backend <- python_backend(python)
  raw_dir <- tempfile('issue-schedule-')
  result <- fetch_issue_schedule(
    '26098', raw_dir, backend,
    pages = list('500_observed_at' = '2026-09-25T13:38:55.362121+00:00',
                 'nowscore_observed_at' = '2026-09-25T13:44:39.900629+00:00',
                 '500' = readBin(page500, 'raw', file.info(page500)$size),
                 'nowscore' = readBin(nowscore, 'raw', file.info(nowscore)$size))
  )
  testthat::expect_s3_class(result, 'tbl_df')
  testthat::expect_identical(names(result), issue_schedule_columns())
  testthat::expect_identical(nrow(result), 4L)
  testthat::expect_identical(result$identity_method[result$slot == 1L], 'slot')
  testthat::expect_identical(result$issue_id, rep('26098', 4L))
  testthat::expect_type(result$slot, 'integer')
  testthat::expect_s3_class(result$kickoff_at, 'POSIXct')

  for (column in c('kickoff_at', 'sale_end_at', 'observed_at')) {
    testthat::expect_identical(attr(result[[column]], 'tzone'), 'Asia/Shanghai')
  }
  slot11 <- result[result$slot == 11L, ]
  testthat::expect_identical(format(slot11$kickoff_at, '%Y-%m-%dT%H:%M:%S',
                                    tz = 'Asia/Shanghai'), '2026-09-26T00:00:00')
  testthat::expect_identical(slot11$kickoff_date_source, 'js-kickoff-date')

  # Each source's own sale cutoff is preserved separately and verbatim.
  testthat::expect_true('sale_end_raw_500' %in% names(result))
  testthat::expect_type(result$sale_end_raw_500, 'character')
  testthat::expect_type(result$sale_end_raw_nowscore, 'character')
  testthat::expect_true(any(nzchar(result$sale_end_raw_500)))
  testthat::expect_true(any(nzchar(result$sale_end_raw_nowscore)))

  slot6 <- result[result$slot == 6L, ]
  testthat::expect_identical(slot6$match_status, 'unknown')
  testthat::expect_true(is.na(slot6$match_status_raw))

  finished <- result[result$slot == 1L, ]
  testthat::expect_identical(finished$match_status, 'finished')
  testthat::expect_identical(finished$score, '3-0')

  # Raw evidence is on disk and no CSV was produced by the fetch.
  testthat::expect_true(length(attr(result, 'written')$`500_raw`) == 1L)
  testthat::expect_true(file.exists(attr(result, 'written')$`500_raw`))
  testthat::expect_length(list.files(raw_dir, pattern = '\\.csv$', recursive = TRUE), 0L)
})

testthat::test_that('the offline bridge rejects a wrong-issue page', {
  python <- Sys.getenv('BEIDAN_TEST_PYTHON')
  testthat::skip_if(!nzchar(python), 'Set BEIDAN_TEST_PYTHON for cross-language checks')
  fixtures <- testthat::test_path('..', 'python', 'fixtures')
  wrong <- file.path(fixtures, 'nowscore.wrong-issue.html')
  testthat::skip_if(!file.exists(wrong), 'saved issue-schedule fixtures are not installed')
  backend <- python_backend(python)
  testthat::expect_error(
    fetch_issue_schedule(
      '26098', tempfile(), backend,
      pages = list('500_observed_at' = '2026-09-25T13:38:55.362121+00:00',
                 'nowscore_observed_at' = '2026-09-25T13:44:39.900629+00:00',
                 '500' = readBin(file.path(fixtures, '500.mini.html'), 'raw',
                                   file.info(file.path(fixtures, '500.mini.html'))$size),
                   'nowscore' = readBin(wrong, 'raw', file.info(wrong)$size))
    ),
    '26097'
  )
})

testthat::test_that('the CSV export uses readr directly on the canonical tibble', {
  testthat::skip_if_not_installed('readr')
  empty <- issue_schedule_empty()
  path <- tempfile(fileext = '.csv')
  readr::write_csv(empty, path)
  testthat::expect_true(file.exists(path))
  header <- strsplit(readLines(path, n = 1), ',', fixed = TRUE)[[1]]
  testthat::expect_identical(header, issue_schedule_columns())
})


testthat::test_that('Python row conversion rejects vector fields and preserves metadata', {
  testthat::expect_error(beidan:::issue_schedule_rows_to_tibble(
    list(list(issue_id = c('26098', '26099')))), 'scalars')
  testthat::expect_error(fetch_issue_schedule('26098', tempfile(),
    structure(list(), class='python_backend'), timeout=0))
})

testthat::test_that('Python mixed identifiers and nonfinite numbers fail conversion', {
  testthat::expect_error(beidan:::issue_schedule_rows_to_tibble(
    list(list(issue_id='026098'), list(issue_id=26098))), 'inconsistent')
  for (value in c(Inf, NaN, .Machine$integer.max + 1)) {
    testthat::expect_error(beidan:::issue_schedule_integer(value, 'slot'))
  }
  testthat::expect_error(beidan:::issue_schedule_double(Inf, 'handicap'), 'nonfinite')
  testthat::expect_error(beidan:::issue_schedule_double(NaN, 'handicap'), 'nonfinite')
})


testthat::test_that("all public schedule time columns use Beijing without shifting instants", {
  empty <- issue_schedule_empty()
  for (column in c("kickoff_at", "sale_end_at", "observed_at")) {
    testthat::expect_identical(attr(empty[[column]], "tzone"), "Asia/Shanghai")
  }
  instant <- lubridate::ymd_hms("2026-09-25 16:00:00", tz = "UTC")
  actual <- beidan:::issue_schedule_timestamp(instant, "kickoff_at")
  testthat::expect_identical(attr(actual, "tzone"), "Asia/Shanghai")
  testthat::expect_equal(as.numeric(actual), as.numeric(instant))
  testthat::expect_identical(format(actual, "%Y-%m-%d %H:%M:%S"), "2026-09-26 00:00:00")
})
