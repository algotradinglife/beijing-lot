# Selection walk-forward: choose WHICH baskets to play, not how to split tickets.
#
# jb_walk_forward_rule moves a fixed ticket pool WITHIN one issue. Selection is a
# different decision: a basket is either played or dropped, and the drop decision
# uses ex-ante basket weights only. Because gross_if_hit is fixed per basket,
# dropping a basket changes the realised return purely by removing stake and the
# payout it would have carried.

# Keep the top k baskets per issue by key, dropping the rest. Rows in input order.
jb_select_top_k <- function(data, k, key = "mass") {
  need <- c("issue", key)
  missing_cols <- setdiff(need, names(data))
  if (length(missing_cols)) stop("jb_select_top_k: missing columns: ", paste(missing_cols, collapse = ", "))
  if (anyNA(data[[key]])) stop("jb_select_top_k: key must be non-missing")
  if (length(k) != 1L || is.na(k) || k < 1L) stop("jb_select_top_k: k must be >= 1")
  if (anyNA(data$issue)) stop("jb_select_top_k: issue must be non-missing")
  ix_by_issue <- split(seq_len(nrow(data)), data$issue)
  # k may be Inf (play every basket); clamp before integer coercion.
  k_int <- if (is.infinite(k)) .Machine$integer.max else as.integer(k)
  keep <- logical(nrow(data))
  for (ix in ix_by_issue) {
    v <- data[[key]][ix]
    n <- min(k_int, length(ix))
    ord <- order(-v, ix)
    keep[ix[ord[seq_len(n)]]] <- TRUE
  }
  data[keep, , drop = FALSE]
}

# Realised return of a selection rule. Dropped baskets contribute no stake and
# no payout; surviving baskets keep their recorded allocation.
jb_select_return <- function(data, k, key = "mass", unit_cny = 2) {
  need <- c("issue", key, "tickets0", "unit_gross", "hit")
  missing_cols <- setdiff(need, names(data))
  if (length(missing_cols)) stop("jb_select_return: missing columns: ", paste(missing_cols, collapse = ", "))
  sel <- jb_select_top_k(data, k, key)
  jb_alloc_realised(sel$tickets0, sel$unit_gross, sel$hit, unit_cny)
}

# Expanding-window walk-forward over selection depth k. The k with the best
# realised return on all issues STRICTLY BEFORE the fold is applied to the fold.
jb_walk_forward_select <- function(data, ks, key = "mass", n_folds = 5L, unit_cny = 2) {
  issue_order <- sort(unique(data$issue))
  folds <- jb_walk_forward_folds(issue_order, n_folds)
  out <- list()
  pooled_stake <- 0; pooled_payout <- 0
  pooled_base_stake <- 0; pooled_base_payout <- 0
  for (i in seq_along(folds)[-1]) {
    past <- issue_order[issue_order %in% unlist(folds[seq_len(i - 1)])]
    fut <- folds[[i]]
    dp <- data[data$issue %in% past, , drop = FALSE]
    df <- data[data$issue %in% fut, , drop = FALSE]
    past_ret <- vapply(ks, function(k) jb_select_return(dp, k, key, unit_cny), numeric(1))
    chosen <- ks[which.max(past_ret)]
    oos <- jb_select_return(df, chosen, key, unit_cny)
    bl <- jb_alloc_realised(df$tickets0, df$unit_gross, df$hit, unit_cny)
    sel <- jb_select_top_k(df, chosen, key)
    stake <- sum(sel$tickets0) * unit_cny
    payout <- sum(ifelse(sel$hit, sel$tickets0 * unit_cny * sel$unit_gross, 0))
    bstake <- sum(df$tickets0) * unit_cny
    bpayout <- sum(ifelse(df$hit, df$tickets0 * unit_cny * df$unit_gross, 0))
    pooled_stake <- pooled_stake + stake; pooled_payout <- pooled_payout + payout
    pooled_base_stake <- pooled_base_stake + bstake; pooled_base_payout <- pooled_base_payout + bpayout
    out[[length(out) + 1L]] <- data.frame(
      fold = i, k = chosen, past_return = max(past_ret),
      n_past_issues = length(past), oos_return = oos, baseline_return = bl,
      n_oos_issues = length(fut), stringsAsFactors = FALSE)
  }
  res <- do.call(rbind, out)
  attr(res, "pooled_return") <- pooled_payout / pooled_stake - 1
  attr(res, "pooled_baseline") <- pooled_base_payout / pooled_base_stake - 1
  res
}
