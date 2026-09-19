# Rank already-constructed seven-fixture combinations under one fixed budget.
# This is a prediction-only utility: it does not fit probabilities or read labels.

rank_candidate_combinations <- function(candidates, budget_cny = 1024,
                                        unit_cny = 2, hit_weight = 0.5,
                                        legal_mass_min = 0) {
  required <- c("combo_id", "hit_probability", "expected_gross",
    "stake_cny", "legal_mass")
  stopifnot(is.data.frame(candidates), all(required %in% names(candidates)),
    budget_cny > 0, budget_cny %% unit_cny == 0, unit_cny == 2,
    hit_weight >= 0, hit_weight <= 1, legal_mass_min >= 0, legal_mass_min <= 1,
    !anyDuplicated(candidates$combo_id))
  x <- candidates[candidates$legal_mass >= legal_mass_min, , drop = FALSE]
  stopifnot(all(is.finite(as.matrix(x[required[-1]]))), all(x$hit_probability >= 0),
    all(x$hit_probability <= 1), all(x$legal_mass >= 0), all(x$legal_mass <= 1),
    all(x$stake_cny > 0), all(x$stake_cny %% unit_cny == 0))
  x$copies <- floor(budget_cny / x$stake_cny)
  x$funded_stake <- x$copies * x$stake_cny
  # Repeating a ticket does not increase the event probability; it scales only
  # the payout. This makes the fixed-budget convention explicit.
  x$budget_hit_probability <- x$hit_probability
  x$budget_expected_gross <- x$copies * x$expected_gross
  x$budget_expected_net <- x$budget_expected_gross - x$funded_stake
  x$budget_roi <- x$budget_expected_net / pmax(1, x$funded_stake)
  x$hit_rank <- rank(-x$budget_hit_probability, ties.method = "min")
  x$ev_rank <- rank(-x$budget_expected_net, ties.method = "min")
  n <- nrow(x)
  x$hit_rank_norm <- if (n == 1) 0 else (x$hit_rank - 1) / (n - 1)
  x$ev_rank_norm <- if (n == 1) 0 else (x$ev_rank - 1) / (n - 1)
  x$average_rank <- hit_weight * x$hit_rank_norm +
    (1 - hit_weight) * x$ev_rank_norm
  dominated <- vapply(seq_len(n), function(i) any(
    x$budget_hit_probability >= x$budget_hit_probability[i] &
      x$budget_expected_net >= x$budget_expected_net[i] &
      (x$budget_hit_probability > x$budget_hit_probability[i] |
        x$budget_expected_net > x$budget_expected_net[i])), logical(1))
  x$pareto_frontier <- !dominated
  x[order(x$average_rank, -x$budget_hit_probability,
    -x$budget_expected_net, x$combo_id), , drop = FALSE]
}

rank_role_combinations <- function(combos, metrics, budget_cny = 1024,
                                   unit_cny = 2, hit_weight = 0.5,
                                   legal_mass_min = 0) {
  x <- attach_combo_metrics(combos, metrics)
  rank_candidate_combinations(x, budget_cny, unit_cny, hit_weight, legal_mass_min)
}

select_combo_portfolio <- function(ranked, n_groups = 8L, max_fixture_reuse = 4L,
                                   max_pair_overlap = 5L) {
  stopifnot(is.data.frame(ranked), all(c("combo_id", "fixtures", "average_rank") %in% names(ranked)),
    n_groups >= 1, max_fixture_reuse >= 1, max_pair_overlap >= 0)
  all_f <- unique(unlist(strsplit(ranked$fixtures, ",", fixed = TRUE)))
  usage <- setNames(integer(length(all_f)), all_f); chosen <- integer()
  for (i in order(ranked$average_rank, -ranked$budget_hit_probability,
                  -ranked$budget_expected_net, ranked$combo_id)) {
    f <- strsplit(ranked$fixtures[[i]], ",", fixed = TRUE)[[1]]
    if (any((usage[f] + 1L) > max_fixture_reuse, na.rm = TRUE)) next
    if (length(chosen) && any(vapply(chosen, function(j) {
      length(intersect(f, strsplit(ranked$fixtures[[j]], ",", fixed = TRUE)[[1]])) > max_pair_overlap
    }, logical(1)))) next
    chosen <- c(chosen, i); usage[f] <- usage[f] + 1L
    if (length(chosen) == n_groups) break
  }
  out <- ranked[chosen, , drop = FALSE]
  out$portfolio_order <- seq_len(nrow(out)); out$fixture_reuse <- vapply(seq_len(nrow(out)), function(i) usage[strsplit(out$fixtures[[i]], ",", fixed = TRUE)[[1]]][1], integer(1))
  out
}
