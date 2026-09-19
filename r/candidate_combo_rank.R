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
