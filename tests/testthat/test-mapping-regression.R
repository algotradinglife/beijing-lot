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

testthat::test_that('Nowscore identifiers retain digits and invalid matrix values fail', {
  html <- readr::read_file(testthat::test_path('..', 'fixtures', 'mapping', 'nowscore.html'))
  for (id in c('00123', '9007199254740993')) {
    changed <- sub('M\\[1\\]\\[0\\]\\s*=\\s*[^;]+;', paste0('M[1][0]="', id, '";'), html)
    testthat::expect_identical(parse_nowscore(changed, '120711')$candidates$provider_id, id)
  }
  malformed <- sub('M\\[1\\]\\[0\\]\\s*=\\s*[^;]+;', 'M[1][0]="bad123";', html)
  testthat::expect_error(parse_nowscore(malformed, '120711'), 'provider')
})

testthat::test_that('each membership row requires complete identity and date fields', {
  html <- readr::read_file(testthat::test_path('..', 'fixtures', 'mapping', 'nowscore.html'))
  incomplete <- paste0(html, '<script>M[2][0]=123;M[2][16]=2;M[2][3]=new Date(2012,6,30,20,45,00);</script>')
  testthat::expect_error(parse_nowscore(incomplete, '120711'), 'required.*row')
  testthat::expect_error(parse_nowscore(sub('"Alpha"', '""', html), '120711'), 'team')
  testthat::expect_error(parse_nowscore(sub('new Date\\([^)]*\\)', 'null', html), '120711'), 'datetime')
})

testthat::test_that('500 parsing refuses malformed candidate identity instead of dropping it', {
  html <- readr::read_file(testthat::test_path('..', 'fixtures', 'mapping', '500.html'))
  testthat::expect_error(parse_500('<html>unavailable</html>', '120711'), 'absent')
  testthat::expect_error(parse_500(sub('fid="[0-9]+"', 'fid="bad"', html), '120711'), 'fixture ID')
  testthat::expect_error(parse_500(sub("homeTeam:'[^']*'", "homeTeam:''", html), '120711'), 'identity')
  testthat::expect_equal(attr(parse_500(html, '120711'), 'excluded_rows')$count, 0)
})

testthat::test_that('500 source issue and nonempty date conversions are validated', {
  html <- readr::read_file(testthat::test_path('..', 'fixtures', 'mapping', '500.html'))
  testthat::expect_error(parse_500(sub('value="120711"', 'value="120712"', html), '120711'), 'declared issue')
  testthat::expect_error(parse_500(sub('endTime:', 'missingTime:', html), '120712'), 'declared issue')
  testthat::expect_error(parse_500(sub('2012-07-30 20:45', 'not-a-date', html, fixed=TRUE), '120711'), 'cutoff date')
  testthat::expect_error(parse_schedule_date('not-a-date'), 'schedule date')
  testthat::expect_true(all(is.na(parse_cutoff(c(NA_character_, '')))))
  testthat::expect_true(all(is.na(parse_schedule_date(c(NA_character_, '')))))
})

testthat::test_that('an all-cancelled 500 membership returns a typed empty table', {
  html <- readr::read_file(testthat::test_path('..', 'fixtures', 'mapping', '500.html'))
  populated <- parse_500(html, '120711')
  empty <- parse_500(sub('fid="123"', 'fid="-1"', html, fixed=TRUE), '120711')
  testthat::expect_equal(nrow(empty), 0)
  testthat::expect_identical(lapply(empty, class), lapply(populated, class))
  testthat::expect_identical(attr(empty, 'excluded_rows')$count, 1L)
})
