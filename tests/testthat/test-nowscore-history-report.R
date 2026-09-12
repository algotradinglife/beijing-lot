source(testthat::test_path("..", "..", "r", "nowscore_history_report.R"))

history_report_fixture <- function(path) {
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  DBI::dbWriteTable(con, "receipt", data.frame(payload_json =
    '{"source":"nowscore","production_enabled":false,"capture_count":2,"observations":2,"options":3,"matches":2}'))
  DBI::dbWriteTable(con, "capture", data.frame(issue = c("00123", "00123"), typeid = c(5L, 6L),
    sha256 = c("first", "second"), source_url = c("https://example.invalid/1", "https://example.invalid/2"),
    received_at = rep("2026-09-06T00:00:00+00:00", 2)))
  DBI::dbWriteTable(con, "observation", data.frame(
    observation_id = 1:2, issue = c("00123", "00123"), slot = 1:2, play = c("spf", "jq"),
    source_sha256 = c("first", "second"), status = c("推迟", "完场"), score = c("-", "0-0"),
    halftime_score = c("-", "0-0"), expected_option = c(NA_character_, "0球"),
    source_url = c("https://example.invalid/1", "https://example.invalid/2"),
    received_at = rep("2026-09-06T00:00:00+00:00", 2)))
  DBI::dbWriteTable(con, "option_sp", data.frame(
    observation_id = c(1L, 1L, 2L), option = c("胜", "平", "0球"),
    raw_sp = c("0.00", "", "2.00"), sp = c(NA_real_, NA_real_, 2)))
  DBI::dbWriteTable(con, "finding", data.frame(
    issue = rep("00123", 3), slot = c(1L, 1L, 2L), play = c("spf", "spf", "jq"),
    source_sha256 = c("first", "first", "second"), code = c("invalid_sp", "abnormal", "mismatch"),
    detail = c("原始零值", "异常状态", "测试")))
}

testthat::test_that("full report aggregates globally and bounds complete option details", {
  path <- tempfile(fileext = ".sqlite")
  history_report_fixture(path)
  before <- tools::md5sum(path)
  a <- read_nowscore_history_report(path, 1L)
  testthat::expect_equal(a$counts$findings, 3)
  testthat::expect_equal(sum(a$findings$findings), 3)
  testthat::expect_equal(a$details_shown, 1)
  testthat::expect_equal(a$details_omitted, 2)
  testthat::expect_equal(nrow(a$quarantined_pages), 0L)
  testthat::expect_identical(a$details$issue, "00123")
  testthat::expect_match(a$details$option_vector, "0.00", fixed = TRUE)
  testthat::expect_match(a$details$option_vector, "∅", fixed = TRUE)
  testthat::expect_identical(tools::md5sum(path), before)
  testthat::expect_equal(read_nowscore_history_report(path, 10)$details_shown, 3)
  for (limit in list(0, 1.5, NA_real_, Inf, -1)) {
    testthat::expect_error(read_nowscore_history_report(path, limit))
  }
})

testthat::test_that("report handles zero findings and fails on duplicate observations", {
  path <- tempfile(fileext = ".sqlite")
  history_report_fixture(path)
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(con, "DELETE FROM finding")
  DBI::dbDisconnect(con)
  a <- read_nowscore_history_report(path, 2)
  testthat::expect_equal(nrow(a$details), 0)
  testthat::expect_equal(a$details_omitted, 0)
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(con, "INSERT INTO observation SELECT * FROM observation WHERE observation_id=1")
  DBI::dbDisconnect(con)
  testthat::expect_error(read_nowscore_history_report(path, 2))
})

testthat::test_that("quarantined findings retain receipt links without invented observations", {
  path <- tempfile(fileext = ".sqlite")
  history_report_fixture(path)
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(con, "INSERT INTO finding VALUES('00123',3,'jq','second','source_roster_conflict','quarantined')")
  DBI::dbExecute(con, "INSERT INTO finding VALUES('00123',4,'jq','second','source_roster_conflict','quarantined')")
  DBI::dbDisconnect(con)
  a <- read_nowscore_history_report(path, 10)
  row <- a$details[a$details$slot == 3L, ]
  testthat::expect_equal(nrow(row), 1L)
  testthat::expect_identical(row$source_url, "https://example.invalid/2")
  testthat::expect_identical(row$received_at, "2026-09-06T00:00:00+00:00")
  testthat::expect_true(is.na(row$observation_id))
  testthat::expect_true(is.na(row$status))
  testthat::expect_true(is.na(row$option_vector))
  testthat::expect_equal(nrow(a$quarantined_pages), 1L)
  testthat::expect_identical(a$quarantined_pages$issue, "00123")
  testthat::expect_equal(a$quarantined_pages$conflict_findings, 2L)
  testthat::expect_identical(a$quarantined_pages$source_url, "https://example.invalid/2")
  testthat::expect_equal(nrow(read_nowscore_history_report(path, 1)$quarantined_pages), 1L)
})

testthat::test_that("raw report rejects corrected SP builds", {
  path <- tempfile(fileext=".sqlite")
  history_report_fixture(path)
  con <- DBI::dbConnect(RSQLite::SQLite(),path)
  receipt <- jsonlite::fromJSON(DBI::dbReadTable(con,"receipt")$payload_json[[1]])
  receipt$source_pure <- FALSE
  DBI::dbExecute(con,"UPDATE receipt SET payload_json=?",params=list(jsonlite::toJSON(receipt,auto_unbox=TRUE)))
  DBI::dbDisconnect(con)
  testthat::expect_error(read_nowscore_history_report(path,1L),"rejects corrected")
})
