testthat::expect_true(all(c("raw_dir", "backend", "pages") %in% names(formals(beidan::fetch_issue_schedule))))
# Developer-only checks. Run after evaluating the walkthrough in the same environment.
# Analysis QMD intentionally does not source this file.
if (!is.null(schedule)) {
  testthat::expect_s3_class(schedule, "tbl_df")
  testthat::expect_identical(names(schedule), beidan::issue_schedule_columns())
  testthat::expect_true(all(schedule$issue_id == issue_id))
  testthat::expect_equal(anyDuplicated(schedule$fixture_key), 0L)
  testthat::expect_false(anyNA(schedule$kickoff_at))
  testthat::expect_false(anyNA(schedule$observed_at))
  known_end <- !is.na(schedule$sale_end_at)
  testthat::expect_true(all(schedule$kickoff_at[known_end] >= schedule$sale_end_at[known_end]))
  # 用户指出的真实跨午夜回归，不以代码自己的推导结果作为预期。
  testthat::expect_equal(
    as.numeric(schedule$kickoff_at[schedule$slot == 11L]),
    as.numeric(lubridate::ymd_hms("2026-09-26 00:00:00", tz = "Asia/Shanghai"))
  )
}
if (!is.null(inputs)) {
  testthat::expect_true(all(inputs$fixtures$issue_id == issue_id))
}
if (!is.null(projected)) {
  p_sums <- projected$probabilities |>
    dplyr::group_by(fixture_id) |>
    dplyr::summarise(total = sum(probability), .groups = "drop")
  testthat::expect_true(all(abs(p_sums$total - 1) < 1e-8))
}
if (!is.null(result)) {
  testthat::expect_equal(anyDuplicated(result$funded$purchases$ticket_id), 0L)
  testthat::expect_true(sum(result$funded$purchases$stake_cny) <= strategy_config$budget_cny)
}
