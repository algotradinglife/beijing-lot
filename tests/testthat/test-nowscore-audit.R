source(testthat::test_path("..", "..", "r", "nowscore_audit.R"))

testthat::test_that("audit reader preserves identifiers, nulls and empty tables read-only", {
  path <- tempfile(fileext = ".sqlite")
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbWriteTable(con, "receipt", data.frame(payload_json = '{"source":"nowscore","production_enabled":false}'))
  DBI::dbWriteTable(con, "observation", data.frame(observation_id = 1L, issue = "00123", slot = 1L, play = "spf"))
  for (name in c("option_sp", "finding", "bf_derivation", "effective_finding", "effective_option_sp", "manual_all_one", "special_settlement_notice")) {
    DBI::dbWriteTable(con, name, data.frame(sp = c(NA_real_, 0, 1)))
  }
  for (name in c("derivation_receipt", "manual_all_one_receipt")) {
    DBI::dbWriteTable(con, name, data.frame(payload_json = '{"production_enabled":false}'))
  }
  DBI::dbDisconnect(con)
  before <- tools::md5sum(path)
  a <- read_nowscore_audit(path)
  testthat::expect_identical(a$observations$issue, "00123")
  testthat::expect_identical(a$options$sp, c(NA_real_, 0, 1))
  testthat::expect_identical(a$special_notices$sp, c(NA_real_, 0, 1))
  testthat::expect_identical(tools::md5sum(path), before)
  testthat::expect_identical(a, read_nowscore_audit(path))
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(con, "DELETE FROM manual_all_one")
  DBI::dbDisconnect(con)
  testthat::expect_equal(nrow(read_nowscore_audit(path)$manual_all_one), 0)
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(con, "INSERT INTO observation SELECT * FROM observation")
  DBI::dbDisconnect(con)
  testthat::expect_error(read_nowscore_audit(path))
  testthat::expect_error(read_nowscore_audit(paste0(path, ".absent")))
})
