source(testthat::test_path('..', '..', 'r', 'mapping_engine.R'))

testthat::test_that('fetch_raw accepts encoding and preserves original bytes', {
  bytes <- charToRaw('<html>saved</html>')
  transport <- function(url, handle) list(status_code = 200L, content = bytes)
  result <- fetch_raw('https://example.invalid', encoding = 'UTF-8', transport = transport)
  testthat::expect_identical(result$payload, bytes)
  testthat::expect_identical(result$text, '<html>saved</html>')
})

testthat::test_that('resolve_alignment preserves sparse slot identities and rejects absent matches', {
  x <- tibble::tibble(slot = c(28L, 90L), home_500 = c('A','B'), away_500 = c('C','D'))
  y <- tibble::tibble(slot = c(29L, 91L), home_ns = c('A','B'), away_ns = c('C','D'))
  testthat::expect_identical(resolve_alignment(x, y, '120711'), c('28'=29L, '90'=91L))
  testthat::expect_error(resolve_alignment(x, y[0, ], '120711'))
})

source(testthat::test_path('..', '..', 'r', 'python_bridge.R'))
source(testthat::test_path('..', '..', 'r', 'mapping_report.R'))

testthat::test_that('decode_source fails closed and fetch retries only transient errors', {
  testthat::expect_error(decode_source(as.raw(255), 'UTF-8'), 'decoding failed')
  testthat::expect_error(decode_source(raw(), 'UTF-8'))
  testthat::expect_identical(decode_source(charToRaw('abc'), 'UTF-8'), 'abc')
  n <- 0L
  transport <- function(url, handle) {
    n <<- n + 1L
    list(status_code = if (n == 1L) 503L else 200L, content = charToRaw('ok'))
  }
  testthat::expect_identical(fetch_raw('https://example.invalid', 'UTF-8', transport = transport,
    sleep = function(seconds) NULL)$text, 'ok')
  testthat::expect_identical(n, 2L)
  bad <- function(url, handle) list(status_code = 404L)
  testthat::expect_error(fetch_raw('https://example.invalid', 'UTF-8', transport = bad), 'HTTP 404')
})

testthat::test_that('RateLimiter waits until capacity expires and rejects excessive requests', {
  now <- 0
  rl <- RateLimiter$new(2L, 60, clock = function() now, sleep = function(seconds) now <<- now + seconds)
  rl$acquire(2L)
  rl$acquire()
  testthat::expect_equal(now, 60)
  testthat::expect_equal(length(rl$timestamps), 1L)
  testthat::expect_error(rl$acquire(3L))
})

testthat::test_that('saved report is typed, deterministic and bound to its input bytes', {
  fixture <- testthat::test_path('..', 'fixtures', 'mapping')
  report <- mapping_report(file.path(fixture,'500.html'), file.path(fixture,'nowscore.html'), '120711')
  testthat::expect_s3_class(report$data, 'tbl_df')
  testthat::expect_s3_class(report$data$deadline_ns, 'POSIXct')
  testthat::expect_equal(report$data$cutoff_gap_minutes, 0)
  testthat::expect_identical(report$data$merge_status, 'exact_team')
  testthat::expect_identical(report$data$status, 'finished')
  testthat::expect_true(all(nchar(report$inputs$sha256) == 64))
  testthat::expect_error(mapping_report(file.path(fixture,'500.html'), file.path(fixture,'nowscore.html'), '120712'), 'declared issue')
})

testthat::test_that('R capture bridge preserves bytes and supports idempotent replay', {
  project <- normalizePath(testthat::test_path('..', '..'))
  python <- Sys.getenv('BEIJING_LOT_VENV_PYTHON')
  if (!nzchar(python)) python <- file.path(project, '.venv', 'bin', 'python')
  fixture <- file.path(project, 'tests', 'fixtures', 'mapping')
  root <- tempfile(); dir.create(root)
  raw500 <- readBin(file.path(fixture,'500.html'), 'raw', n = 100000)
  rawns <- readBin(file.path(fixture,'nowscore.html'), 'raw', n = 100000)
  run <- function() run_issue_mapping('120711', root, 'test', '2026-09-05T00:00:00Z',
    project, python, raw_500 = raw500, raw_ns = rawns)
  a <- run()
  testthat::expect_identical(run(), a)
  testthat::expect_equal(a$mapped_slots, 1L)
  testthat::expect_identical(a$raw_500_sha256, digest::digest(raw500, 'sha256', serialize = FALSE))
  testthat::expect_error(project_python_module('src.titan_clean.historical_id_map', project, '/missing/python'))
  con <- DBI::dbConnect(RSQLite::SQLite(), file.path(root,'control','external_id_discovery','discovery.sqlite'), flags=RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(con), add=TRUE)
  testthat::expect_equal(DBI::dbGetQuery(con,'SELECT COUNT(*) AS n FROM source_receipt')$n, 2)
})
