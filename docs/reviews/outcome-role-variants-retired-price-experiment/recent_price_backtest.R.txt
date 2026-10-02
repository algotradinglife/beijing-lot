#' Validate original decision artifacts before label-free price experiments
#' @param x List with named outputs, each containing pool and evaluated objects.
#' @return The first pool, after verifying every original and shared snapshot.
#' @details Uses the authoritative cutoff/risk validators; never reads labels.
.RecentPriceSource <- function(x) {
  checkmate::assert_list(x$outputs, min.len = 1L, names = "unique")
  first <- x$outputs[[1]]$pool
  beidan:::match_require_cutoff(first$cutoff)
  for (original in x$outputs) {
    pool <- original$pool
    beidan:::.ParlayRiskPrepare(original$evaluated, first$cutoff)
    bindings <- list(cutoff_hash = pool$cutoff_hash,
      settings_hash = rlang::hash(pool$settings),
      probability_hash = rlang::hash(pool$probabilities),
      prematch_sp_hash = rlang::hash(pool$prematch_sp))
    for (name in names(bindings)) {
      if (is.null(bindings[[name]]) ||
          !identical(bindings[[name]], original$evaluated$receipt[[name]]))
        stop("pool and original evaluation binding mismatch: ", name)
    }
    if (!identical(pool$cutoff, first$cutoff) ||
        !identical(pool$probabilities, first$probabilities) ||
        !identical(pool$prematch_sp, first$prematch_sp) ||
        !identical(pool$settings, first$settings)) stop("mixed source snapshots")
  }
  beidan:::.parlay_role_validate_scores(first$scores, first$probabilities)
  beidan:::.parlay_role_validate_prematch_sp(first$prematch_sp, first$cutoff)
  return(first)
}

#' Promote model/SP-disputed fixtures into existing three-outcome positions
#' @param pool Valid role candidate pool.
#' @param market Valid model/raw-SP comparison tibble from the shared helper.
#' @return Pool with unchanged fixture sets and pattern, refreshed model masks.
#' @details Within each group, highest-minimum-probability disputed lower-role
#' fixtures swap with lowest-minimum-probability consistent role3 fixtures.
#' Unknown market agreement does not authorize a swap. No labels or I/O.
.RecentPricePromote <- function(pool, market) {
  legs <- pool$role_legs
  disputed <- unique(market$fixture_id[!is.na(market$disagreement) & market$disagreement])
  consistent <- unique(market$fixture_id[!is.na(market$disagreement) & !market$disagreement])
  scores <- dplyr::filter(pool$scores, .data$role == 3L)
  for (group in unique(legs$group_id)) {
    targets <- which(legs$group_id == group & legs$role < 3L & legs$fixture_id %in% disputed)
    donors <- which(legs$group_id == group & legs$role == 3L & legs$fixture_id %in% consistent)
    targets <- targets[order(-scores$score[match(legs$fixture_id[targets], scores$fixture_id)], legs$fixture_id[targets])]
    donors <- donors[order(scores$score[match(legs$fixture_id[donors], scores$fixture_id)], legs$fixture_id[donors])]
    for (i in seq_len(min(length(targets), length(donors)))) {
      pair <- c(targets[i], donors[i])
      legs$fixture_id[pair] <- rev(legs$fixture_id[pair])
    }
  }
  pool$role_legs <- beidan:::.parlay_role_refresh_masks(legs, pool$probabilities)
  return(pool)
}

#' Calculate candidate-level price admission evidence before portfolio selection
#' @param pool Valid candidate pool.
#' @param packages Shared package enumeration from the authoritative constructor.
#' @param market Model/raw-SP comparison tibble.
#' @param low_sp_threshold Positive raw SP threshold; p(top1) is fixed at 0.5.
#' @return Tibble, one row per candidate, with EV, coverage, and role1 exclusion.
#' @details Missing candidate EV cannot pass the nonnegative-EV gate. Empty
#' purchased packages have zero cost/coverage/EV and undefined conditional payout.
.RecentPriceEvidence <- function(pool, packages, market, low_sp_threshold) {
  checkmate::assert_number(low_sp_threshold, lower = 0, finite = TRUE)
  if (low_sp_threshold <= 0) stop("low_sp_threshold must be positive")
  low <- dplyr::filter(market, .data$model_rank == 1L,
    .data$model_probability >= 0.5, !is.na(.data$sp_raw),
    .data$sp_raw <= low_sp_threshold)$fixture_id
  forbidden <- unique(pool$role_legs$group_id[pool$role_legs$role > 1L &
    pool$role_legs$fixture_id %in% low])
  rows <- lapply(packages$packages$group_id, function(id) {
    bought <- packages$stack[[id]]
    cost <- nrow(bought) * pool$settings$unit_cny
    mass <- sum(bought$probability)
    ev <- sum(bought$ev_net_est)
    tibble::tibble(group_id = id, cost_cny = as.numeric(cost),
      coverage_probability = as.numeric(mass), expected_net_cny = as.numeric(ev),
      conditional_payout_cny = if (mass > 0) (ev + cost) / mass else NA_real_,
      required_payout_cny = if (mass > 0) cost / mass else NA_real_,
      ev_allowed = is.finite(ev) && ev >= 0,
      role1_allowed = !id %in% forbidden)
  })
  if (!length(rows)) return(tibble::tibble(group_id = character(), cost_cny = double(),
    coverage_probability = double(), expected_net_cny = double(),
    conditional_payout_cny = double(), required_payout_cny = double(),
    ev_allowed = logical(), role1_allowed = logical()))
  return(dplyr::bind_rows(rows))
}

#' Apply candidate gates before the shared selector admits any groups
#' @param packages Shared enumeration list.
#' @param evidence Candidate price-evidence tibble.
#' @param gate One of none, nonnegative_ev, role1_low_sp, nonnegative_ev_role1_low_sp.
#' @return Enumeration list with filtered package rows; stack is unchanged.
.RecentPriceGate <- function(packages, evidence, gate) {
  checkmate::assert_choice(gate, c("none", "nonnegative_ev", "role1_low_sp",
    "nonnegative_ev_role1_low_sp"))
  keep <- rep(TRUE, nrow(evidence))
  if (grepl("nonnegative_ev", gate, fixed = TRUE)) keep <- keep & evidence$ev_allowed
  if (grepl("role1_low_sp", gate, fixed = TRUE)) keep <- keep & evidence$role1_allowed
  packages$packages <- dplyr::filter(packages$packages,
    .data$group_id %in% evidence$group_id[keep])
  return(packages)
}

#' Evaluate recent frozen inputs under fixed price-aware experimental policies
#' @param x List with named outputs, each carrying a validated pool/evaluated pair.
#' @param group_budget_cny Nonnegative finite CNY per group; actual cost saturates
#' at legal full support and is floored to whole units. Default 256.
#' @param budget_cny Nonnegative finite CNY total cap, default 512; unspent is cash.
#' @param low_sp_threshold Positive raw SP bound for p(top1)>=0.5 role1-only
#' exclusion, default 2. This is declared sensitivity, not fitted on outcomes.
#' @return List(results named evaluations, metadata and candidate_evidence tibbles,
#' market tibble, cutoff, receipt). Twenty-four configurations use four patterns,
#' original/disagreement-first roles and fixed gates. No labels, fitting, writes,
#' network, or persistent cache. Invalid original bindings fail closed.
#' @details Role1 exclusion filters an existing candidate pool; it does not prove
#' no alternative legal pool exists. Each pool has at most 12 candidates, uses
#' probability TopN, max reuse/overlap2, and no local improvement. Enumeration is
#' reused within this call. Counterfactual policies are not original frozen bets.
RecentPriceBacktest <- function(x, group_budget_cny = 256, budget_cny = 512,
                                low_sp_threshold = 2) {
  checkmate::assert_number(group_budget_cny, lower = 0, finite = TRUE)
  checkmate::assert_number(budget_cny, lower = 0, finite = TRUE)
  checkmate::assert_number(low_sp_threshold, lower = 0, finite = TRUE)
  if (low_sp_threshold <= 0) stop("low_sp_threshold must be positive")
  source <- .RecentPriceSource(x)
  cutoff <- source$cutoff
  if (source$settings$n_legs != 7L) stop("four-pattern experiment requires seven legs")
  market <- beidan:::.ParlayLossMarketComparison(source$probabilities, source$prematch_sp, cutoff)
  constraints <- list(max_reuse = 2L, max_overlap = 2L)
  patterns <- c("3333222", "3332222", "3322221", "3222221")
  results <- list(); metadata <- list(); ledger <- list()
  implementation <- rlang::hash(list(
    lapply(list(.RecentPriceSource, .RecentPricePromote, .RecentPriceEvidence,
      .RecentPriceGate, RecentPriceBacktest), function(fn) list(formals(fn), body(fn))),
    beidan:::.ParlayRiskCodeHash(), beidan:::.parlay_role_code_hash()))
  for (pattern in patterns) {
    original <- beidan::parlay_construct_role_groups(source$scores, cutoff,
      source$settings, as.integer(strsplit(pattern, "")[[1]]), n_candidates = 12L,
      probabilities = source$probabilities, prematch_sp = source$prematch_sp)
    for (role_policy in c("original", "disagreement_role3")) {
      pool <- if (role_policy == "original") original else .RecentPricePromote(original, market)
      packages <- beidan:::.parlay_role_packages(pool, pool$probabilities,
        pool$prematch_sp, cutoff, group_budget_cny, "probability")
      evidence <- .RecentPriceEvidence(pool, packages, market, low_sp_threshold)
      ledger[[length(ledger) + 1L]] <- dplyr::mutate(evidence, pattern = pattern,
        role_policy = role_policy, .before = 1L)
      gates <- if (role_policy == "original") c("none", "nonnegative_ev", "role1_low_sp",
        "nonnegative_ev_role1_low_sp") else c("none", "nonnegative_ev")
      frozen_results <- list()
      for (gate in gates) {
        filtered <- .RecentPriceGate(packages, evidence, gate)
        selected <- beidan:::.parlay_role_select(filtered$packages, filtered$stack,
          pool$settings$unit_cny, budget_cny, constraints, filtered$fixture_sets)
        key <- rlang::hash(selected$new_purchases)
        if (is.null(frozen_results[[key]])) frozen_results[[key]] <-
          beidan:::.parlay_role_result(pool, selected$new_purchases, pool$prematch_sp,
            cutoff, "probability", budget_cny, constraints)
        final <- frozen_results[[key]]
        id <- paste(pattern, role_policy, gate, sep = ":")
        receipt <- list(cutoff = cutoff, cutoff_hash = pool$cutoff_hash,
          probability_hash = pool$probability_hash, prematch_sp_hash = pool$prematch_sp_hash,
          settings_hash = rlang::hash(pool$settings), portfolio_hash = rlang::hash(pool),
          code_hash = implementation, source_hash = rlang::hash(x),
          group_budget_cny = group_budget_cny, budget_cny = budget_cny,
          constraints = constraints, improve = FALSE, role_policy = role_policy,
          gate = gate, low_sp_threshold = low_sp_threshold,
          mode = "retrospective_label_free_policy_diagnostic", settlement_used = FALSE)
        results[[id]] <- list(initial = final, final = final, cutoff = cutoff,
          receipt = receipt, selection = selected$selection,
          group_summary = beidan:::.parlay_role_group_summary(selected$new_purchases,
            pool, selected$selected_ids, group_budget_cny))
        cost <- sum(final$plan$purchases$stake_cny)
        metadata[[id]] <- tibble::tibble(scenario_id = id, pattern = pattern,
          role_policy = role_policy, gate = gate, status = if (cost > 0) "funded" else "cash",
          cost_cny = as.numeric(cost), unspent_cny = as.numeric(budget_cny - cost),
          n_groups = as.integer(length(selected$selected_ids)),
          candidates_before = as.integer(nrow(packages$packages)),
          candidates_after = as.integer(nrow(filtered$packages)),
          group_budget_cny = as.numeric(group_budget_cny), budget_cny = as.numeric(budget_cny),
          low_sp_threshold = as.numeric(low_sp_threshold))
      }
    }
  }
  return(list(results = results, metadata = dplyr::bind_rows(metadata),
    candidate_evidence = dplyr::bind_rows(ledger), market = market, cutoff = cutoff,
    receipt = list(source_hash = rlang::hash(x), code_hash = implementation,
      cutoff = cutoff, cutoff_hash = source$cutoff_hash, settlement_used = FALSE,
      n_candidates = 12L, group_budget_cny = group_budget_cny, budget_cny = budget_cny,
      low_sp_threshold = low_sp_threshold, probability_threshold = 0.5,
      constraints = constraints)))
}
