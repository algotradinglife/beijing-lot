source(file.path("..", "..", "r", "market_sqlite_report.R"))

testthat::test_that("market report preserves identity, types and empty inputs", {
  x <- market_sqlite_record_table(list(list(issue = "001", kind = "quote",
      import_state = "IMPORTED_PENDING_ACCEPTANCE", data = list(value = NULL))))
  testthat::expect_s3_class(x, "tbl_df")
  testthat::expect_identical(x$issue, "001")
  empty <- market_sqlite_record_table(list())
  testthat::expect_identical(names(empty), c("issue", "kind", "import_state"))
  testthat::expect_equal(nrow(empty), 0L)
  testthat::expect_true(all(vapply(empty, is.character, logical(1))))
  testthat::expect_error(market_sqlite_record_table("bad"), "list")
  testthat::expect_error(market_sqlite_record_table(list(list(issue = "001"))), "invalid")
  testthat::expect_error(market_sqlite_record_table(list(list(issue = NA_character_,
      kind = "quote", import_state = "pending"))), "invalid")
})
