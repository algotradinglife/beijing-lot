test_that("cohort scalar rows preserve the complete legacy tibble contract", {
  cases <- readRDS(test_path("fixtures", "role-cohort-row-parity.rds"))
  for (case in cases) {
    actual <- do.call(beidan:::.parlay_ranked_cohort, case$args)
    expect_identical(actual, case$expected)
    expect_s3_class(actual$role_legs, "tbl_df")
    expect_s3_class(actual$trace, "tbl_df")
    expect_s3_class(actual$substitutions, "tbl_df")
  }
  expect_gt(nrow(cases$fallback$expected$substitutions), 0L)
  expect_equal(nrow(cases$empty$expected$role_legs), 0L)
  expect_true(all(cases$empty$expected$trace$action == "unfilled"))
})
