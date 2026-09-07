source(testthat::test_path("..", "..", "r", "nowscore_query.R"))

nowscore_query_fixture <- function(path) {
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  DBI::dbWriteTable(con, "receipt", data.frame(payload_json =
    '{"source":"nowscore","production_enabled":false}'))
  DBI::dbWriteTable(con, "observation", data.frame(
    observation_id = 1:3, issue = rep("00123", 3), slot = c(1L, 1L, 2L),
    play = c("bf", "spf", "bf"), native_match_id = rep("00042", 3),
    status = c("取消", "取消", "完场"), score = c("-", "-", "0-0"),
    halftime_score = c("-", "-", "0-0"), expected_option = c(NA, NA, "0:0"),
    source_url = "https://example.invalid", source_sha256 = "hash",
    received_at = "2026-09-07T00:00:00+00:00",
    payload_json = '{"home":"主队","away":"客队","handicap_raw":"0"}'))
  DBI::dbWriteTable(con, "option_sp", data.frame(
    observation_id = c(1L, 1L, 1L, 2L), option = c("0:0", "1:0", "2:0", "胜"),
    raw_sp = c("1.00", "", "bad", "0.00"), sp = c(1, NA, NA, 0)))
  DBI::dbWriteTable(con, "finding", data.frame(issue = "00123", slot = c(1L, 3L),
    play = "bf", code = c("invalid_sp", "source_roster_conflict"),
    detail = c("invalid", "quarantined"), source_sha256 = "hash"))
}

testthat::test_that("queries preserve source cells, keys and missing options read-only", {
  path <- tempfile(fileext = ".sqlite")
  nowscore_query_fixture(path)
  before <- tools::md5sum(path)
  x <- query_nowscore_settlement(path, "00123", 1, "bf")
  testthat::expect_s3_class(x$settlement, "tbl_df")
  testthat::expect_identical(x$settlement$raw_sp, c("1.00", "", "bad"))
  testthat::expect_equal(x$settlement$sp, c(1, NA, NA))
  testthat::expect_true(all(x$settlement$issue == "00123"))
  testthat::expect_true(all(x$settlement$native_match_id == "00042"))
  testthat::expect_true(all(x$settlement$home == "主队"))
  testthat::expect_equal(nrow(x$findings), 1)
  testthat::expect_identical(x$receipt$source, "nowscore")
  testthat::expect_identical(query_nowscore_settlement(path, "00123", 1, "bf"), x)
  testthat::expect_equal(nrow(query_nowscore_settlement(path, "00123")$settlement), 5)
  testthat::expect_equal(nrow(query_nowscore_settlement(path, "00123", play = "spf")$settlement), 1)
  testthat::expect_equal(query_nowscore_settlement(path, "00123", 1, "spf")$settlement$sp, 0)
  testthat::expect_true(is.na(query_nowscore_settlement(path, "00123", 2)$settlement$option))
  q <- query_nowscore_settlement(path, "00123", 3)
  testthat::expect_equal(nrow(q$settlement), 0)
  testthat::expect_equal(nrow(q$findings), 1)
  empty <- query_nowscore_settlement(path, "99999")
  testthat::expect_equal(nrow(empty$settlement), 0)
  testthat::expect_equal(nrow(empty$findings), 0)
  testthat::expect_type(empty$settlement$issue, "character")
  testthat::expect_type(empty$settlement$sp, "double")
  testthat::expect_identical(tools::md5sum(path), before)
})

testthat::test_that("invalid inputs cannot create files or inject SQL", {
  path <- tempfile(fileext = ".sqlite")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "path")
  testthat::expect_false(file.exists(path))
  nowscore_query_fixture(path)
  for (issue in list(123, NA_character_, "", "00123' OR 1=1", c("1", "2"))) {
    testthat::expect_error(query_nowscore_settlement(path, issue), "issue")
  }
  for (slot in list(0, -1, 1.5, NA_real_, Inf, "1", c(1, 2), 2^31)) {
    testthat::expect_error(query_nowscore_settlement(path, "00123", slot), "slot")
  }
  for (play in list("bad", NA_character_, c("bf", "spf"))) {
    testthat::expect_error(query_nowscore_settlement(path, "00123", play = play), "play")
  }
})

testthat::test_that("receipt, schema and duplicate failures release the connection", {
  path <- tempfile(fileext = ".sqlite")
  nowscore_query_fixture(path)
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  DBI::dbExecute(con, "INSERT INTO option_sp SELECT * FROM option_sp LIMIT 1")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "Duplicate option")
  DBI::dbExecute(con, "DELETE FROM option_sp WHERE rowid=(SELECT MAX(rowid) FROM option_sp)")
  DBI::dbExecute(con, "INSERT INTO observation SELECT * FROM observation LIMIT 1")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "Duplicate observation")
  DBI::dbExecute(con, "DELETE FROM observation WHERE rowid=(SELECT MAX(rowid) FROM observation)")
  DBI::dbExecute(con, "UPDATE receipt SET payload_json='{}'")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "Nowscore")
  DBI::dbExecute(con, "DELETE FROM receipt")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "exactly one")
  DBI::dbExecute(con, "DROP TABLE receipt")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "receipt")
  testthat::expect_silent(DBI::dbWriteTable(con, "after_error", data.frame(x = 1)))
})
