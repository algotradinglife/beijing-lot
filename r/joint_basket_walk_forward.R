# Walk-forward evaluation of an ex-ante ticket-allocation rule.
#
# The rule family is a weight shape w_i = mass_i^exponent, and the exponent is
# chosen on an expanding window of issues STRICTLY BEFORE the evaluation fold.
# This is the same cutoff discipline used elsewhere in the project: no fold may
# see its own outcomes when its exponent is selected.

# Split issue ids, ordered oldest-first, into `n_folds` contiguous blocks.
jb_walk_forward_folds <- function(issue_order, n_folds = 5L) {
  if (anyNA(issue_order)) stop("jb_walk_forward_folds: issue_order must be non-missing")
  if (anyDuplicated(issue_order)) stop("jb_walk_forward_folds: issue_order must be unique")
  if (length(n_folds) != 1L || is.na(n_folds) || n_folds < 2L) stop("jb_walk_forward_folds: n_folds must be >= 2")
  split(issue_order, cut(seq_along(issue_order), breaks = n_folds, labels = FALSE))
}

# Realised return of one allocation rule applied to a frame of baskets.
# `data` needs columns: issue, mass, tickets0 (the recorded allocation),
# unit_gross and hit. `exponent` NA means use the recorded allocation.
# Tickets each row receives under a rule. `exponent` NA means the recorded
# allocation is returned unchanged. Rows are returned in the input row order.
jb_rule_tickets <- function(data, exponent, tickets_per_issue = 128L) {
  need <- c("issue", "mass", "tickets0")
  missing_cols <- setdiff(need, names(data))
  if (length(missing_cols)) stop("jb_rule_tickets: missing columns: ", paste(missing_cols, collapse = ", "))
  if (anyNA(data$mass) || anyNA(data$tickets0)) stop("jb_rule_tickets: missing input")
  if (is.na(exponent)) return(as.numeric(data$tickets0))
  # `split` orders groups by sorted key; map each row back through that order.
  ix_by_issue <- split(seq_len(nrow(data)), data$issue)
  tk <- numeric(nrow(data))
  for (ix in ix_by_issue) tk[ix] <- jb_alloc_by_mass(data$mass[ix], tickets_per_issue, exponent)
  tk
}

# Realised return of one allocation rule applied to a frame of baskets.
jb_rule_return <- function(data, exponent, tickets_per_issue = 128L, unit_cny = 2) {
  need <- c("issue", "mass", "tickets0", "unit_gross", "hit")
  missing_cols <- setdiff(need, names(data))
  if (length(missing_cols)) stop("jb_rule_return: missing columns: ", paste(missing_cols, collapse = ", "))
  if (anyNA(data$unit_gross) || anyNA(data$hit)) stop("jb_rule_return: missing input")
  jb_alloc_realised(jb_rule_tickets(data, exponent, tickets_per_issue), data$unit_gross, data$hit, unit_cny)
}

# Expanding-window walk-forward: for each fold after the first, pick the exponent
# with the best realised return on all issues before it, then score that exponent
# on the fold. Returns one row per evaluated fold plus a pooled row.
jb_walk_forward_rule <- function(data, exponents, n_folds = 5L,
                                 tickets_per_issue = 128L, unit_cny = 2) {
  issue_order <- sort(unique(data$issue))
  folds <- jb_walk_forward_folds(issue_order, n_folds)
  out <- list()
  pooled_stake <- 0; pooled_payout <- 0
  for (i in seq_along(folds)[-1]) {
    past <- issue_order[issue_order %in% unlist(folds[seq_len(i - 1)])]
    fut <- folds[[i]]
    dp <- data[data$issue %in% past, , drop = FALSE]
    df <- data[data$issue %in% fut, , drop = FALSE]
    past_ret <- vapply(exponents, function(e) jb_rule_return(dp, e, tickets_per_issue, unit_cny), numeric(1))
    chosen <- exponents[which.max(past_ret)]
    oos <- jb_rule_return(df, chosen, tickets_per_issue, unit_cny)
    bl <- jb_rule_return(df, NA_real_, tickets_per_issue, unit_cny)
    tk <- jb_rule_tickets(df, chosen, tickets_per_issue)
    stake <- sum(tk) * unit_cny
    payout <- sum(ifelse(df$hit, tk * unit_cny * df$unit_gross, 0))
    pooled_stake <- pooled_stake + stake; pooled_payout <- pooled_payout + payout
    out[[length(out) + 1L]] <- data.frame(
      fold = i, exponent = chosen, past_return = max(past_ret),
      n_past_issues = length(past), oos_return = oos, baseline_return = bl,
      n_oos_issues = length(fut), stringsAsFactors = FALSE)
  }
  res <- do.call(rbind, out)
  attr(res, "pooled_return") <- pooled_payout / pooled_stake - 1
  res
}
