source(testthat::test_path("..", "..", "r", "settlement_remaining_audit.R"))

testthat::test_that("remaining audit separates resolved, void, missing and unresolved", {
  before <- data.frame(issue_code = rep("1", 5), issue_slot = 1:5, local_500_fid = 11:15,
                       home_score = c(0, 1, 2, NA, 0), away_score = c(0, 0, 1, 0, 0),
                       winning_option_jq = c("1", "7+", "0", "0", "0"),
                       winning_sp_jq = rep(1, 5))
  raw <- data.frame(issue_code = before$issue_code, issue_slot = before$issue_slot,
                    local_500_fid = before$local_500_fid, play_type = "jq",
                    home_score = before$home_score, away_score = before$away_score,
                    winning_option = before$winning_option_jq, winning_sp = 1,
                    settlement_state = "settled")
  after <- before
  after$winning_option_jq[1:2] <- c("0", NA)
  after$settlement_state_jq <- c("settled", "manual_void", rep("settled", 3))
  x <- audit_remaining_settlements(raw, before, after)
  testthat::expect_equal(x$audit_class, c("已由更正解决", "人工无效结算",
                                         "待核查：选项与比分不符", "待核查：字段缺失", "无本轮异常"))
  testthat::expect_equal(sum(x$original_mismatch), 3)
  testthat::expect_equal(sum(x$current_mismatch), 1)
  testthat::expect_identical(x, audit_remaining_settlements(raw, before, after))
  bad <- raw; bad$winning_option[1] <- "2"
  testthat::expect_error(audit_remaining_settlements(bad, before, after), "冲突")
  testthat::expect_equal(raw$winning_option[1], "1")
})
