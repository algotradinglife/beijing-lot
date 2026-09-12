source(testthat::test_path("..", "..", "r", "nowscore_query.R"))

source(testthat::test_path("helper-nowscore-query.R"))

testthat::test_that("direct SQLite corrections show original values and source notes", {
  path <- tempfile(fileext=".sqlite")
  nowscore_query_fixture(path)
  original <- query_nowscore_settlement(path,"00123",1,"bf")$settlement
  oid <- original$observation_id[original$option=="1:0"]
  con <- DBI::dbConnect(RSQLite::SQLite(),path)
  DBI::dbWriteTable(con,"sp_correction",data.frame(
    observation_id=oid,option="1:0",new_raw_sp="13.03",new_sp=13.03,
    old_raw_sp="",old_sp=NA_real_,source="500.com",source_url="https://trade.500.com/",
    note="用户批准补缺"))
  DBI::dbExecute(con,"UPDATE option_sp SET raw_sp='13.03',sp=13.03 WHERE observation_id=? AND option='1:0'",params=list(oid))
  x <- query_nowscore_settlement(path,"00123",1,"bf")$settlement
  i <- which(x$option=="1:0")
  testthat::expect_equal(x$sp[i],13.03)
  testthat::expect_identical(x$sp_source[i],"500.com")
  testthat::expect_identical(x$correction_note[i],"用户批准补缺")
  testthat::expect_true(is.na(x$original_sp[i]))
  testthat::expect_identical(x$original_raw_sp[i],"")
  DBI::dbExecute(con,"UPDATE option_sp SET sp=99 WHERE observation_id=? AND option='1:0'",params=list(oid))
  testthat::expect_error(query_nowscore_settlement(path,"00123",1,"bf"),"audit/value")
  DBI::dbDisconnect(con)
})

testthat::test_that("queries preserve source cells, keys and missing options read-only", {
  path <- tempfile(fileext = ".sqlite")
  nowscore_query_fixture(path)
  before <- tools::md5sum(path)
  testthat::expect_error(nowscore_query_fixture(path))
  testthat::expect_identical(tools::md5sum(path), before)
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
  for (field in c("home", "away", "handicap_raw")) {
    testthat::expect_type(empty$settlement[[field]], "character")
  }
  testthat::expect_identical(dplyr::bind_rows(empty$settlement, x$settlement), x$settlement)
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
  DBI::dbExecute(con, "UPDATE observation SET payload_json='{}'")
  missing <- query_nowscore_settlement(path, "00123")$settlement
  for (field in c("home", "away", "handicap_raw")) {
    testthat::expect_type(missing[[field]], "character")
    testthat::expect_true(all(is.na(missing[[field]])))
  }
  DBI::dbExecute(con, "UPDATE receipt SET payload_json='{}'")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "Nowscore")
  DBI::dbExecute(con, "DELETE FROM receipt")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "exactly one")
  DBI::dbExecute(con, "DROP TABLE receipt")
  testthat::expect_error(query_nowscore_settlement(path, "00123"), "receipt")
  testthat::expect_silent(DBI::dbWriteTable(con, "after_error", data.frame(x = 1)))
})
