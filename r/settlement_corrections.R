# Historical score overlay only; never writes source tables or changes SP.
exclude_void_play_corrections <- function(corrections, decisions, play) {
  keys <- vapply(Filter(function(x) play %in% unlist(x$plays), decisions),
                 function(x) paste(x$issue_code, x$issue_slot, sep = "/"), "")
  corrections[!paste(corrections$issue_code, corrections$issue_slot, sep = "/") %in% keys, , drop = FALSE]
}

apply_manual_void_decisions <- function(data, decisions) {
  domains <- list(spf = c("胜", "平", "负"), jq = c(as.character(0:6), "7+"),
                  ds = c("上+单", "上+双", "下+单", "下+双"))
  keys <- paste(data$issue_code, data$issue_slot, sep = "/")
  decision_keys <- vapply(decisions, function(d) paste(d$issue_code, d$issue_slot, sep = "/"), "")
  stopifnot(length(decisions) > 0L, !anyDuplicated(keys), !anyDuplicated(decision_keys),
            !anyDuplicated(vapply(decisions, function(d) d$decision_id, "")))
  for (play in names(domains)) {
    field <- paste0("settlement_state_", play)
    if (!field %in% names(data)) data[[field]] <- data$settlement_state
  }
  options <- list()
  receipt <- list()
  for (d in decisions) {
    stopifnot(identical(d$review_status, "user_confirmed"),
              identical(d$evidence_class, "user_settlement_assumption"),
              identical(d$official_notice_verified, FALSE),
              setequal(unlist(d$plays), names(domains)), length(d$plays) == 3L)
    i <- match(paste(d$issue_code, d$issue_slot, sep = "/"), keys)
    if (is.na(i)) stop("人工无效结算目标不存在")
    for (field in c("local_500_fid", "home_score", "away_score")) {
      if (is.na(data[[field]][i]) || data[[field]][i] != d[[field]]) stop("人工无效结算ID或比分冲突")
    }
    for (play in unlist(d$plays)) {
      opt <- paste0("winning_option_", play)
      sp <- paste0("winning_sp_", play)
      for (field in c(opt, sp)) {
        expected <- d$original_record[[field]]
        stopifnot(field %in% names(d$original_record))
        current <- data[[field]][i]
        matches <- if (is.null(expected)) is.na(current) else !is.na(current) && current == expected
        if (!isTRUE(matches)) {
          stop("人工无效结算原选项/SP冲突")
        }
      }
      receipt[[length(receipt) + 1L]] <- data.frame(
        decision_id = d$decision_id, issue_code = d$issue_code, issue_slot = d$issue_slot,
        play_type = play, old_option = data[[opt]][i], old_sp = data[[sp]][i],
        new_option = "ALL", new_sp = 1, new_state = "manual_void",
        evidence_class = d$evidence_class)
      options[[length(options) + 1L]] <- data.frame(
        decision_id = d$decision_id, issue_code = d$issue_code, issue_slot = d$issue_slot,
        local_500_fid = d$local_500_fid, play_type = play, option = domains[[play]],
        sp = 1, parlay_pass = TRUE, single_refund_per_unit = 1,
        settlement_state = "manual_void", evidence_class = d$evidence_class,
        official_notice_verified = FALSE)
      data[[opt]][i] <- NA_character_  # No unique winner: use the option-level table.
      data[[sp]][i] <- 1
      data[[paste0("settlement_state_", play)]][i] <- "manual_void"
    }
    data$result_code_spf[i] <- NA_character_
    # Partial because BF/BQ were not authorized; never classify the whole row as settled.
    data$settlement_state[i] <- "manual_void_partial"
  }
  list(data = data, options = do.call(rbind, options), receipt = do.call(rbind, receipt))
}

apply_settlement_corrections <- function(data, corrections) {
  key <- function(x) paste(x$issue_code, x$issue_slot, sep = "/")
  stopifnot(nrow(corrections) > 0L,
            !anyDuplicated(corrections$correction_id),
            !anyDuplicated(key(corrections)), !anyDuplicated(key(data)),
            all(corrections$review_status == "user_confirmed"))
  idx <- match(key(corrections), key(data))
  if (anyNA(idx)) stop("更正目标不存在")
  before <- data[idx, , drop = FALSE]
  same <- function(a, b) !anyNA(a) && !anyNA(b) && all(a == b)
  if (!same(before$local_500_fid, corrections$local_500_fid) ||
      !same(before$home_score, corrections$old_home_score) ||
      !same(before$away_score, corrections$old_away_score)) {
    stop("更正目标ID或原比分冲突；停止应用，需重新审核")
  }
  h <- corrections$new_home_score
  a <- corrections$new_away_score
  if (anyNA(c(h, a)) || any(c(h, a) < 0 | c(h, a) != floor(c(h, a)))) {
    stop("非法更正比分")
  }
  jq <- ifelse(h + a >= 7, "7+", as.character(h + a))
  ds <- paste0(ifelse(h + a >= 3, "上", "下"), "+",
               ifelse((h + a) %% 2 == 1, "单", "双"))
  if (!same(before$winning_option_jq, jq) || !same(before$winning_option_ds, ds)) {
    stop("总进球或上下单双不支持更正比分；停止应用")
  }
  after <- before
  after$home_score <- h
  after$away_score <- a
  # Only correct already present result fields; do not invent missing coverage.
  present <- !is.na(before$result_code_spf)
  if (anyNA(before$handicap_line[present])) stop("SPF让球数缺失")
  delta <- h + before$handicap_line - a
  code <- ifelse(delta > 0, "3", ifelse(delta == 0, "1", "0"))
  after$result_code_spf[present] <- code[present]
  after$winning_option_spf[present] <- c("0" = "负", "1" = "平", "3" = "胜")[code[present]]
  present_bf <- !is.na(before$winning_option_bf)
  after$winning_option_bf[present_bf] <- paste(h, a, sep = ":")[present_bf]
  fields <- c("home_score", "away_score", "result_code_spf",
              "winning_option_spf", "winning_option_bf")
  receipt <- do.call(rbind, lapply(fields, function(field) {
    old <- as.character(before[[field]])
    new <- as.character(after[[field]])
    changed <- (is.na(old) != is.na(new)) | (!is.na(old) & !is.na(new) & old != new)
    data.frame(correction_id = corrections$correction_id[changed],
               issue_code = corrections$issue_code[changed],
               issue_slot = corrections$issue_slot[changed],
               field = rep(field, sum(changed)),
               before = old[changed], after = new[changed])
  }))
  data[idx, ] <- after
  list(data = data, receipt = receipt)
}

# Explicit, user-confirmed Nowscore play option/SP overrides; no state inference.
apply_play_corrections <- function(data, corrections, play) {
  stopifnot(length(play) == 1L, play %in% c("ds", "jq"))
  option_field <- paste0("winning_option_", play)
  sp_field <- paste0("winning_sp_", play)
  key <- function(x) paste(x$issue_code, x$issue_slot, sep = "/")
  stopifnot(nrow(corrections) > 0L,
            !anyDuplicated(corrections$correction_id),
            !anyDuplicated(key(corrections)), !anyDuplicated(key(data)),
            all(corrections$review_status == "user_confirmed"))
  idx <- match(key(corrections), key(data))
  if (anyNA(idx)) stop("玩法更正目标不存在")
  before <- data[idx, , drop = FALSE]
  same <- function(a, b) !anyNA(a) && !anyNA(b) && all(a == b)
  if (!same(before$local_500_fid, corrections$local_500_fid) ||
      !same(before$home_score, corrections$home_score) ||
      !same(before$away_score, corrections$away_score) ||
      !same(before[[option_field]], corrections$old_option) ||
      !same(before[[sp_field]], corrections$old_sp)) {
    stop("玩法目标ID、比分或原选项/SP冲突")
  }
  total <- before$home_score + before$away_score
  expected <- paste0(ifelse(total >= 3, "上", "下"), "+",
                     ifelse(total %% 2 == 1, "单", "双"))
  if (play == "jq") expected <- ifelse(total >= 7, "7+", as.character(total))
  stopifnot(same(corrections$new_option, expected),
            same(corrections$ns_home, before$home_score),
            same(corrections$ns_away, before$away_score),
            all(corrections$nowscore_status == "完场"),
            all(is.finite(corrections$new_sp) & corrections$new_sp >= 1))
  data[[option_field]][idx] <- corrections$new_option
  data[[sp_field]][idx] <- corrections$new_sp
  receipt <- data.frame(correction_id = corrections$correction_id,
                        issue_code = corrections$issue_code,
                        issue_slot = corrections$issue_slot,
                        play_type = play,
                        old_option = before[[option_field]],
                        new_option = corrections$new_option,
                        old_sp = before[[sp_field]],
                        new_sp = corrections$new_sp,
                        nowscore_status = corrections$nowscore_status,
                        special_sp_review = corrections$new_sp == 1,
                        source_url = corrections$source_url)
  list(data = data, receipt = receipt)
}
