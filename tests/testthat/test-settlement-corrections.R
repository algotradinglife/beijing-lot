source(testthat::test_path("..", "..", "r", "settlement_corrections.R"))

testthat::test_that("confirmed manual void decisions expand all 90 options without changing BF/BQ", {
  decisions <- jsonlite::fromJSON(testthat::test_path("..", "..", "quarto", "settlement_void_decisions.json"),
                                  simplifyVector = FALSE)
  d <- do.call(rbind, lapply(decisions, function(x) as.data.frame(lapply(x$original_record, function(v) if (is.null(v)) NA else v))))
  untouched <- d[1, ]; untouched$issue_slot <- 999L
  d <- rbind(d, untouched)
  x <- apply_manual_void_decisions(d, decisions)
  testthat::expect_equal(nrow(x$options), 90L)
  testthat::expect_equal(nrow(x$receipt), 18L)
  testthat::expect_true(all(x$options$sp == 1 & x$options$parlay_pass))
  testthat::expect_true(all(x$options$single_refund_per_unit == 1))
  testthat::expect_true(all(!x$options$official_notice_verified))
  testthat::expect_true(all(is.na(x$data$result_code_spf[1:6])))
  testthat::expect_equal(x$data$settlement_state[1:6], rep("manual_void_partial", 6))
  testthat::expect_equal(x$data[7, names(d)], d[7, ])
  preserved <- c("home_score", "away_score", "winning_option_bf", "winning_sp_bf",
                  "winning_option_bq", "winning_sp_bq")
  testthat::expect_identical(x$data[preserved], d[preserved])
  testthat::expect_identical(x, apply_manual_void_decisions(d, decisions))
  testthat::expect_equal(table(x$options$play_type), table(rep(c("spf", "jq", "ds"), c(18, 48, 24))))
  for (play in c("spf", "jq", "ds")) {
    testthat::expect_true(all(is.na(x$data[[paste0("winning_option_", play)]][1:6])))
    testthat::expect_equal(x$data[[paste0("settlement_state_", play)]][1:6], rep("manual_void", 6))
  }
  # Refund is principal, not 2*0.65; neutral leg leaves the remaining SP product unchanged.
  testthat::expect_equal(2 * x$options$single_refund_per_unit[1], 2)
  testthat::expect_equal(2 * x$options$sp[1] * 3 * 4 * 0.65, 15.6)
  testthat::expect_error(apply_manual_void_decisions(x$data, decisions), "冲突")
  bad <- decisions; bad[[1]]$review_status <- "pending"
  testthat::expect_error(apply_manual_void_decisions(d, bad))
  bad <- decisions; bad[[1]]$local_500_fid <- 0
  testthat::expect_error(apply_manual_void_decisions(d, bad), "冲突")
  testthat::expect_error(apply_manual_void_decisions(d, c(decisions, decisions[1])))
  ds <- jsonlite::fromJSON(testthat::test_path("..", "..", "quarto", "settlement_ds_corrections.json"))
  jq <- jsonlite::fromJSON(testthat::test_path("..", "..", "quarto", "settlement_jq_corrections.json"))
  testthat::expect_equal(nrow(exclude_void_play_corrections(ds, decisions, "ds")), 26L)
  testthat::expect_equal(nrow(exclude_void_play_corrections(jq, decisions, "jq")), 1L)
})

testthat::test_that("DS overrides option and SP only with strict evidence guards", {
  d <- data.frame(issue_code = "1", issue_slot = 1L, local_500_fid = 9L,
                  home_score = 0L, away_score = 0L,
                  winning_option_ds = "上+双", winning_sp_ds = 1,
                  winning_option_jq = "0", settlement_state = "settled")
  c <- data.frame(issue_code = "1", issue_slot = 1L, local_500_fid = 9L,
                  correction_id = "ds1", review_status = "user_confirmed",
                  home_score = 0L, away_score = 0L, ns_home = 0L, ns_away = 0L,
                  old_option = "上+双", old_sp = 1, new_option = "下+双",
                  new_sp = 3.5377, nowscore_status = "完场", source_url = "test")
  x <- apply_play_corrections(d, c, "ds")
  testthat::expect_equal(x$data$winning_sp_ds, 3.5377)
  testthat::expect_equal(x$data$winning_option_ds, "下+双")
  testthat::expect_identical(x$data[names(d)[!names(d) %in% c("winning_option_ds", "winning_sp_ds")]],
                             d[names(d)[!names(d) %in% c("winning_option_ds", "winning_sp_ds")]])
  testthat::expect_identical(x, apply_play_corrections(d, c, "ds"))
  testthat::expect_error(apply_play_corrections(x$data, c, "ds"), "冲突")
  bad <- c; bad$old_sp <- 2
  testthat::expect_error(apply_play_corrections(d, bad, "ds"), "冲突")
  bad <- c; bad$new_option <- "上+单"
  testthat::expect_error(apply_play_corrections(d, bad, "ds"))
  bad <- c; bad$review_status <- "pending"
  testthat::expect_error(apply_play_corrections(d, bad, "ds"))
  bad <- c; bad$new_sp <- 1
  testthat::expect_true(apply_play_corrections(d, bad, "ds")$receipt$special_sp_review)
  jq_data <- d
  jq_data$winning_option_jq <- "7+"
  jq_data$winning_sp_jq <- 1
  jq <- c
  jq$old_option <- "7+"
  jq$new_option <- "0"
  jq$new_sp <- 1
  j <- apply_play_corrections(jq_data, jq, "jq")
  testthat::expect_equal(j$data$winning_option_jq, "0")
  testthat::expect_equal(j$data$winning_sp_jq, 1)
  testthat::expect_identical(j$data$winning_option_ds, jq_data$winning_option_ds)
  testthat::expect_true(j$receipt$special_sp_review)
  testthat::expect_error(apply_play_corrections(jq_data, jq, "bf"))
  jq$new_option <- "2"
  testthat::expect_error(apply_play_corrections(jq_data, jq, "jq"))
})

testthat::test_that("overlay is guarded, reproducible and preserves SP", {
  d <- data.frame(issue_code = "1", issue_slot = 1L, local_500_fid = 5L,
                  home_score = 0L, away_score = 2L, handicap_line = 0L,
                  result_code_spf = "0", winning_option_spf = "负",
                  winning_option_bf = "0:2", winning_sp_bf = 13.53,
                  winning_option_jq = "3", winning_option_ds = "上+单")
  c <- data.frame(correction_id = "x", issue_code = "1", issue_slot = 1L,
                  local_500_fid = 5L, old_home_score = 0L, old_away_score = 2L,
                  new_home_score = 2L, new_away_score = 1L,
                  review_status = "user_confirmed")
  result <- apply_settlement_corrections(d, c)
  testthat::expect_equal(result$data$winning_option_bf, "2:1")
  testthat::expect_equal(result$data$result_code_spf, "3")
  testthat::expect_identical(result$data$winning_sp_bf, d$winning_sp_bf)
  testthat::expect_identical(result, apply_settlement_corrections(d, c))
  testthat::expect_equal(d$home_score, 0L)
  testthat::expect_error(apply_settlement_corrections(result$data, c), "原比分冲突")
  bad <- c; bad$local_500_fid <- 6L
  testthat::expect_error(apply_settlement_corrections(d, bad), "ID")
  bad <- c; bad$review_status <- "pending"
  testthat::expect_error(apply_settlement_corrections(d, bad))
  bad <- d; bad$winning_option_jq <- "2"
  testthat::expect_error(apply_settlement_corrections(bad, c), "总进球")
  testthat::expect_error(apply_settlement_corrections(d, rbind(c, c)))
  missing <- d; missing$winning_option_bf <- NA_character_
  testthat::expect_true(is.na(apply_settlement_corrections(missing, c)$data$winning_option_bf))
})
