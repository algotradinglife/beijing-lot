#' Correlation of two model Bernoulli events
#' @param p,q Event probabilities between zero and one, inclusive.
#' @param joint Probability of their intersection.
#' @return Pearson correlation, or NA_real_ for a constant event.
#' @details Inputs are numeric scalars; no labels, fitting or side effects.
#' @noRd
.ParlayBernoulliCorrelation <- function(p, q, joint) {
  for (value in list(p, q, joint)) {
    checkmate::assert_number(value, lower = 0, upper = 1, finite = TRUE)
  }
  if (joint < max(0, p + q - 1) - 1e-10 || joint > min(p, q) + 1e-10) {
    stop("invalid joint event probability")
  }
  variance <- p * (1 - p) * q * (1 - q)
  if (variance == 0) return(NA_real_)
  return(max(-1, min(1, (joint - p * q) / sqrt(variance))))
}

#' Exact pair dependence of validated legal outcome masks
#' @param legs Validated candidate role legs, one row per group/fixture.
#' @param probabilities Validated complete fixture/outcome probabilities.
#' @return Tibble, one row per unordered group pair. Correlation concerns full
#'   legal supports, not purchased depth or empirical historical returns.
#' @details Assumes independent fixtures and shares the outcome on reused
#'   fixtures. Empty or one-group inputs return a typed empty tibble; no IO.
#' @noRd
.ParlayMaskPairs <- function(legs, probabilities) {
  empty <- tibble::tibble(group_a = character(), group_b = character(),
    shared_fixtures = integer(), shared_restricted_fixtures = integer(),
    probability_a = double(), probability_b = double(),
    joint_probability = double(), mask_correlation = double())
  ids <- sort(unique(legs$group_id), method = "radix")
  if (length(ids) < 2L) return(empty)
  keys <- paste(probabilities$fixture_id, probabilities$outcome)
  blocks <- split(legs, legs$group_id)
  rows <- list()
  for (a in seq_len(length(ids) - 1L)) {
    for (b in seq.int(a + 1L, length(ids))) {
      left <- blocks[[ids[a]]]; right <- blocks[[ids[b]]]
      shared <- intersect(left$fixture_id, right$fixture_id)
      restricted <- sum(lengths(left$allowed_outcomes[match(shared, left$fixture_id)]) < 3L &
        lengths(right$allowed_outcomes[match(shared, right$fixture_id)]) < 3L)
      joint <- 1
      for (fixture in union(left$fixture_id, right$fixture_id)) {
        i <- match(fixture, left$fixture_id); j <- match(fixture, right$fixture_id)
        mask <- if (is.na(i)) right$allowed_outcomes[[j]] else if (is.na(j))
          left$allowed_outcomes[[i]] else intersect(left$allowed_outcomes[[i]], right$allowed_outcomes[[j]])
        if (!length(mask)) { joint <- 0; break }
        joint <- joint * sum(probabilities$probability[match(paste(fixture, mask), keys)])
      }
      p <- prod(left$retained_probability); q <- prod(right$retained_probability)
      rows[[length(rows) + 1L]] <- tibble::tibble(group_a = ids[a], group_b = ids[b],
        shared_fixtures = as.integer(length(shared)), shared_restricted_fixtures = as.integer(restricted),
        probability_a = p, probability_b = q, joint_probability = joint,
        mask_correlation = .ParlayBernoulliCorrelation(p, q, joint))
    }
  }
  return(dplyr::bind_rows(rows))
}

#' Diagnose dependence and single-fixture fragility of an immutable plan
#'
#' @param evaluation Receipt-bound evaluation from [parlay_select_groups()].
#'   Its embedded cutoff, source inputs and purchases are independently validated.
#' @param n_draws Positive integer Monte Carlo sample count for the existing
#'   joint-return risk engine; default 100000. Analytic pair/conditional metrics
#'   remain exact. No parameter is tuned from historical or target labels.
#' @param seed Explicit nonnegative simulation seed, default 1729.
#' @return List of candidate_pairs and bought_pairs tibbles, a fixture/outcome
#'   exposure tibble, the authoritative joint risk result, cutoff and receipt.
#'   Pair correlations are model Bernoulli correlations, not historical return
#'   correlations. Empty pair sets have typed schemas. A constant event has NA
#'   correlation; zero-probability conditional outcomes have NA conditional risk.
#'   Missing purchased SP leaves financial expectation NA, not zero.
#' @details Different fixtures are assumed independent, with a shared outcome
#'   for every reuse of the same fixture. Candidate correlation concerns complete
#'   masks; bought correlation concerns owner groups' actual physical ticket sets,
#'   which may be disjoint despite identical masks. Conditional risk fixes each
#'   fixture to each W/D/L outcome as an explicit hypothetical stress scenario;
#'   original probabilities and immutable decisions are never changed. Exact
#'   event unions reuse the package's authoritative Rcpp union kernel. This is
#'   label-free descriptive risk analysis, not a learned gate or recommendation.
#'   No history, labels, files, network, fitting or writes are accessed.
#' @export
DiagnoseParlayDependence <- function(evaluation, n_draws = 100000L, seed = 1729L) {
  prepared <- .ParlayRiskPrepare(evaluation, evaluation$cutoff)
  pool <- evaluation$portfolio
  probabilities <- prepared$probabilities
  candidate_pairs <- .ParlayMaskPairs(pool$role_legs, probabilities)
  ids <- sort(unique(prepared$purchases$group_id), method = "radix")
  bought_pairs <- candidate_pairs |>
    dplyr::filter(group_a %in% ids, group_b %in% ids)
  bought_pairs$owned_probability_a <- numeric(nrow(bought_pairs))
  bought_pairs$owned_probability_b <- numeric(nrow(bought_pairs))
  bought_pairs$owned_joint_probability <- numeric(nrow(bought_pairs))
  bought_pairs$owned_correlation <- numeric(nrow(bought_pairs))
  for (i in seq_len(nrow(bought_pairs))) {
    a <- bought_pairs$group_a[i]; b <- bought_pairs$group_b[i]
    tickets_a <- prepared$tickets$ticket_id[prepared$tickets$group_id == a]
    tickets_b <- prepared$tickets$ticket_id[prepared$tickets$group_id == b]
    p <- sum(prepared$tickets$probability[prepared$tickets$group_id == a])
    q <- sum(prepared$tickets$probability[prepared$tickets$group_id == b])
    union <- .parlay_ranked_union_coverage(c(tickets_a, tickets_b), prepared$legs, probabilities)
    joint <- max(0, min(p, q, p + q - union))
    bought_pairs$owned_probability_a[i] <- p
    bought_pairs$owned_probability_b[i] <- q
    bought_pairs$owned_joint_probability[i] <- joint
    bought_pairs$owned_correlation[i] <- .ParlayBernoulliCorrelation(p, q, joint)
  }
  joint_risk <- parlay_compare_risk(list(cutoff = evaluation$cutoff,
    summary = tibble::tibble(scenario_id = "frozen"), results = list(frozen = evaluation)),
    method = "mc", n_draws = n_draws, seed = seed, include_group_prefixes = FALSE)
  exposure <- tibble::tibble(fixture_id = character(), outcome = character(),
    probability = double(), ticket_fraction = double(), knockout_fraction = double(),
    surviving_tickets = integer(), conditional_hit_probability = double(),
    conditional_expected_net_cny = double())
  fixtures <- sort(unique(prepared$legs$fixture_id), method = "radix")
  rows <- list(); purchases <- prepared$purchases
  total_cost <- sum(purchases$stake_cny)
  for (fixture in fixtures) {
    local <- prepared$legs[prepared$legs$fixture_id == fixture, , drop = FALSE]
    touched <- purchases$ticket_id %in% local$ticket_id
    for (outcome in match_outcomes()) {
      p <- probabilities$probability[probabilities$fixture_id == fixture & probabilities$outcome == outcome]
      compatible <- !touched | purchases$ticket_id %in% local$ticket_id[local$outcome == outcome]
      knockout <- sum(purchases$stake_cny[!compatible]) / total_cost
      conditional_hit <- conditional_net <- NA_real_
      if (p > 0) {
        hypothetical <- probabilities
        hypothetical$probability[hypothetical$fixture_id == fixture] <-
          as.numeric(hypothetical$outcome[hypothetical$fixture_id == fixture] == outcome)
        conditional_hit <- .parlay_ranked_union_coverage(purchases$ticket_id[compatible],
          prepared$legs, hypothetical)
        conditional_probability <- prepared$tickets$probability
        conditional_probability[touched] <- conditional_probability[touched] / p
        conditional_probability[!compatible] <- 0
        # SP-incomplete plans retain an unknown financial expectation even when
        # a particular stress scenario knocks out all their unpriced tickets.
        if (all(is.finite(prepared$tickets$payout_cny))) {
          conditional_net <- sum(conditional_probability * prepared$tickets$payout_cny) - total_cost
        }
      }
      rows[[length(rows) + 1L]] <- tibble::tibble(fixture_id = fixture, outcome = outcome,
        probability = p, ticket_fraction = sum(purchases$stake_cny[touched]) / total_cost,
        knockout_fraction = knockout, surviving_tickets = as.integer(sum(compatible)),
        conditional_hit_probability = conditional_hit, conditional_expected_net_cny = conditional_net)
    }
  }
  if (length(rows)) exposure <- dplyr::bind_rows(rows)
  receipt <- list(cutoff = evaluation$cutoff, source_hash = rlang::hash(evaluation),
    probability_hash = rlang::hash(probabilities), plan_hash = rlang::hash(evaluation$plan),
    implementation_hash = .ParlayRiskCodeHash(), kernel_identity = ComponentUnionKernelIdentity(),
    n_draws = as.integer(n_draws), seed = as.integer(seed), historical_learning = FALSE,
    model = "independent fixtures; shared fixture outcomes; fixed-SP return proxy",
    conditional_scenarios = "every purchased fixture fixed to each W/D/L; no realized labels")
  result <- list(candidate_pairs = candidate_pairs, bought_pairs = bought_pairs,
    exposure = exposure, joint_risk = joint_risk, cutoff = evaluation$cutoff)
  receipt$output_hash <- rlang::hash(result)
  result$receipt <- receipt
  return(result)
}
