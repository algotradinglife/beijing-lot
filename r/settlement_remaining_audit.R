# Audit raw jq/ds rows with only explicitly changed wide-table fields projected.
# No network or database writes; missing chronology is not an availability claim.
audit_remaining_settlements <- function(raw, before, after) {
  key <- function(x) paste(x$issue_code, x$issue_slot, sep = "/")
  stopifnot(!anyDuplicated(key(before)), identical(key(before), key(after)))
  same <- function(a, b) (is.na(a) & is.na(b)) | (!is.na(a) & !is.na(b) & a == b)
  expected <- function(h, a, play) {
    total <- h + a
    if (play == "jq") return(ifelse(total >= 7, "7+", as.character(total)))
    paste0(ifelse(total >= 3, "上", "下"), "+", ifelse(total %% 2 == 1, "单", "双"))
  }
  result <- lapply(c("jq", "ds"), function(play) {
    x <- raw[raw$play_type == play, , drop = FALSE]
    if (nrow(x) == 0L) return(NULL)
    stopifnot(!anyDuplicated(key(x)))
    idx <- match(key(x), key(before))
    x$old_expected <- expected(x$home_score, x$away_score, play)
    complete_old <- !is.na(x$home_score) & !is.na(x$away_score) & !is.na(x$winning_option)
    x$original_mismatch <- x$settlement_state == "settled" & complete_old &
      x$winning_option != x$old_expected
    x$original_option <- x$winning_option
    x$original_sp <- x$winning_sp
    for (field in c("home_score", "away_score", "winning_option", "winning_sp")) {
      wide <- if (startsWith(field, "winning_")) paste0(field, "_", play) else field
      change <- !is.na(idx) & !same(before[[wide]][idx], after[[wide]][idx])
      if (any(change & (!same(x[[field]], before[[wide]][idx]) |
                        !same(x$local_500_fid, before$local_500_fid[idx])))) {
        stop("原玩法表与更正前宽表冲突，不能投射更正")
      }
      x[[field]][change] <- after[[wide]][idx[change]]
    }
    state_field <- paste0("settlement_state_", play)
    is_void <- !is.na(idx) & after[[state_field]][idx] == "manual_void"
    is_void[is.na(is_void)] <- FALSE
    x$settlement_state[is_void] <- "manual_void"
    x$expected_option <- expected(x$home_score, x$away_score, play)
    complete <- !is.na(x$home_score) & !is.na(x$away_score) & !is.na(x$winning_option)
    x$current_mismatch <- x$settlement_state == "settled" & complete &
      x$winning_option != x$expected_option
    incomplete <- x$settlement_state == "settled" & (!complete | is.na(x$winning_sp))
    x$audit_class <- ifelse(is_void, "人工无效结算",
      ifelse(incomplete, "待核查：字段缺失",
      ifelse(x$current_mismatch, "待核查：选项与比分不符",
      ifelse(x$original_mismatch, "已由更正解决", "无本轮异常"))))
    x
  })
  do.call(rbind, result)
}
