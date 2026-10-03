#' Stage one candidate against the actually admitted purchase ledger
#' @param state Shared temporary funding state.
#' @param space Frozen enumerated group space.
#' @param nominal One-row group quota tibble.
#' @param pool Validated pool.
#' @param budget_cny Total CNY cap or NULL.
#' @param reuse Resolved fixture reuse policy.
#' @param overlap Resolved pairwise overlap policy.
#' @param ev_floor Net expectation floor or -Inf for no gate.
#' @return Tentative state, exact new purchases, marginal EV and rejection reason.
#' No state is committed here; missing SP fails only an enabled EV gate.
#' @noRd
.StageSelectedGroup <- function(state, space, nominal, pool, budget_cny,
                                reuse, overlap, ev_floor) {
  if (!is.null(budget_cny) &&
      floor((budget_cny - state$spent + 1e-9) / pool$settings$unit_cny) == 0) {
    return(list(reason = "budget_exhausted"))
  }
  attempt <- .parlay_ranked_stage_group(state, space, nominal, pool,
    budget_cny, reuse, overlap)
  if (!identical(attempt$reason, "admitted")) return(attempt)
  owned <- attempt$state$purchases[[length(attempt$state$purchases)]]
  ev <- if (all(is.finite(owned$ev_net_est))) sum(owned$ev_net_est) else NA_real_
  if (is.finite(ev_floor)) {
    if (is.na(ev)) return(list(reason = "ev_unavailable"))
    if (ev <= ev_floor) return(list(reason = "group_ev_floor"))
  }
  attempt$new_ev <- ev
  attempt$owned <- owned
  return(attempt)
}

#' Typed empty selector audit
#' @return Tibble with one row per committed group, CNY costs and probability mass.
#' @noRd
.EmptySelectedGroups <- function() {
  return(tibble::tibble(group_slot = integer(), group_id = character(),
    order = integer(), group_units = integer(), new_ticket_count = integer(),
    new_cost_cny = numeric(), new_ev_cny = numeric(), marginal_coverage = numeric(),
    cumulative_cost_cny = numeric(), cumulative_ev_cny = numeric(),
    cumulative_coverage = numeric()))
}

#' Dynamically select and fund groups using the authoritative purchase transaction
#' @param pool Validated candidate pool.
#' @param objective ev or coverage, evaluated on actual new physical tickets.
#' @param budget_cny Total CNY cap or NULL.
#' @param group_budget_cny Per-group CNY cap or NULL for full support.
#' @param reuse Resolved fixture reuse policy.
#' @param overlap Resolved pairwise overlap policy.
#' @param ev_floor Strict net EV floor or -Inf for no gate.
#' @return Funding ledger, admission audit and rejected group table.
#' Each round commits only the eligible group with the largest marginal objective.
#' Rejected tentative states never affect ranking. No fitting, labels or IO.
#' @noRd
.SelectRankedFunding <- function(pool, objective, budget_cny, group_budget_cny,
                                 reuse, overlap, ev_floor) {
  prepared <- .PrepareRankedFunding(pool, group_budget_cny)
  nominal <- prepared$nominal
  spaces <- prepared$spaces
  state <- list(bought = character(), spent = 0, admitted = list(),
                purchases = list(), ticket_legs = list(), selection = list())
  remaining <- as.character(nominal$group_id)
  audit <- list()
  rejected <- .parlay_ranked_empty_rejections()
  coverage <- 0
  cumulative_ev <- 0
  while (length(remaining)) {
    attempts <- stats::setNames(vector("list", length(remaining)), remaining)
    scores <- stats::setNames(rep(-Inf, length(remaining)), remaining)
    for (id in remaining) {
      row <- nominal[match(id, nominal$group_id), , drop = FALSE]
      attempt <- .StageSelectedGroup(state, spaces[[id]], row, pool, budget_cny,
                                    reuse, overlap, ev_floor)
      if (identical(attempt$reason, "admitted")) {
        attempt$coverage <- .parlay_ranked_union_coverage(attempt$state$bought,
          dplyr::bind_rows(attempt$state$ticket_legs), pool$probabilities)
        scores[id] <- if (identical(objective, "ev")) attempt$new_ev else
          attempt$coverage - coverage
      }
      attempts[[id]] <- attempt
    }
    eligible <- remaining[is.finite(scores[remaining])]
    if (!length(eligible)) {
      rejected <- dplyr::bind_rows(lapply(remaining, function(id) {
        tibble::tibble(group_slot = as.integer(nominal$group_slot[
          match(id, nominal$group_id)]), group_id = id,
          reason = attempts[[id]]$reason,
          detail = "not admitted; no tickets, cash or constraints consumed")
      }))
      break
    }
    id <- eligible[order(-scores[eligible], eligible, method = "radix")][1L]
    attempt <- attempts[[id]]
    state <- attempt$state
    cumulative_ev <- cumulative_ev + attempt$new_ev
    row <- nominal[match(id, nominal$group_id), , drop = FALSE]
    audit[[length(audit) + 1L]] <- tibble::tibble(
      group_slot = as.integer(row$group_slot), group_id = id,
      order = as.integer(length(audit) + 1L), group_units = row$group_units,
      new_ticket_count = as.integer(nrow(attempt$owned)),
      new_cost_cny = as.numeric(sum(attempt$owned$cost_cny)),
      new_ev_cny = as.numeric(attempt$new_ev),
      marginal_coverage = as.numeric(attempt$coverage - coverage),
      cumulative_cost_cny = as.numeric(state$spent),
      cumulative_ev_cny = as.numeric(cumulative_ev),
      cumulative_coverage = as.numeric(attempt$coverage))
    coverage <- attempt$coverage
    remaining <- setdiff(remaining, id)
  }
  selection <- if (length(audit)) dplyr::bind_rows(audit) else .EmptySelectedGroups()
  admitted <- if (length(state$selection)) dplyr::bind_rows(state$selection) else
    .parlay_ranked_empty_selection()
  skipped <- dplyr::anti_join(nominal, dplyr::select(admitted, group_id), by = "group_id") |>
    dplyr::left_join(dplyr::select(rejected, group_id, reason), by = "group_id",
                     relationship = "one-to-one") |>
    dplyr::mutate(admitted = FALSE, tickets = 0L, spent_cny = 0,
                  actual_coverage = 0)
  fund <- list(spaces = spaces, nominal = nominal,
    purchases = if (length(state$purchases)) dplyr::bind_rows(state$purchases) else
      .parlay_ranked_empty_purchases(),
    ticket_legs = if (length(state$ticket_legs)) dplyr::bind_rows(state$ticket_legs) else
      match_typed_empty("ticket_legs"),
    selection = dplyr::bind_rows(admitted, skipped), rejections = rejected,
    bought = state$bought, spent = state$spent,
    selected_groups = as.character(selection$group_id))
  return(list(fund = fund, selection = selection, excluded = rejected,
    ended_by = if (!length(remaining)) "pool_exhausted" else "no_admissible_groups"))
}

#' Select groups and return their exact frozen purchase evaluation
#'
#' Each round stages every remaining candidate against the ACTUAL admitted ticket
#' ledger. The shared purchase transaction removes physical duplicates BEFORE
#' refilling the per-group quota and applies remaining budget, fixture reuse and
#' pairwise overlap. Only the eligible group with the largest marginal net EV
#' (`ev`) or union probability gain (`coverage`) is committed. Ties use group_id.
#' Rejected groups do not influence subsequent ranking or consume constraints.
#'
#' The returned `evaluation` is the final plan: do not pass a selected subgroup
#' through a second purchase walk. This avoids reordering or changing its tickets.
#' This is a deterministic greedy heuristic, not a global optimum. No fitting,
#' scraping, settlement access or hidden clock is involved. Inputs carry cutoff.
#' @param portfolio Candidate pool from parlay_construct_role_groups().
#' @param objective ev (default) or coverage; marginal objective in each round.
#' @param budget_cny Total CNY cap, NULL for unlimited. Remaining whole ticket
#'   units may partially fund the last group; cash below one unit remains unspent.
#' @param min_group_ev_cny Strict floor for each group's NEW ticket net EV in CNY.
#'   NULL means 0 for ev and no gate for coverage. Missing SP blocks an EV gate,
#'   but coverage without a gate retains tickets and reports unknown EV as NA.
#' @param group_budget_cny Per-group CNY cap, default 256; NULL for full support.
#'   Zero allows no purchases and returns typed empty ledgers.
#' @param reuse_policy List(max_reuse); NULL limit means unlimited, all roles count.
#' @param overlap_policy List(max_overlap); NULL limit means unlimited. Shared
#'   actual full triples are exempt, other shared fixtures count.
#' @return List(evaluation, selection, summary, excluded, receipt, diagnostics).
#'   evaluation is the standard frozen evaluation accepted by settlement/risk APIs.
#'   selection is a tibble of actual marginal/cumulative costs, EV and coverage;
#'   summary is a one-row tibble. excluded contains every unadmitted group once.
#'   Empty-purchase EV is NA, coverage and cost are zero. No side effects.
#' @export
parlay_select_groups <- function(portfolio, objective = c("ev", "coverage"),
  budget_cny = NULL, min_group_ev_cny = NULL, group_budget_cny = 256,
  reuse_policy = list(max_reuse = NULL),
  overlap_policy = list(max_overlap = NULL)) {
  objective <- match.arg(objective)
  pool <- .parlay_ranked_validate_pool(portfolio)
  budget_cny <- .parlay_role_validate_budget(budget_cny, "budget_cny")
  group_budget_cny <- .parlay_role_validate_budget(group_budget_cny, "group_budget_cny")
  reuse <- .parlay_ranked_validate_reuse_policy(reuse_policy)
  overlap <- .parlay_ranked_validate_overlap_policy(overlap_policy)
  if (!is.null(min_group_ev_cny)) checkmate::assert_number(min_group_ev_cny,
    finite = TRUE, .var.name = "min_group_ev_cny")
  floor <- if (is.null(min_group_ev_cny)) {
    if (identical(objective, "ev")) 0 else -Inf
  } else min_group_ev_cny
  selected <- .SelectRankedFunding(pool, objective, budget_cny, group_budget_cny,
                                   reuse, overlap, floor)
  evaluation <- .FinalizeRankedEvaluation(portfolio, pool, selected$fund,
    budget_cny, group_budget_cny, reuse, overlap, improve = FALSE,
    producer = "parlay_select_groups", objective = objective,
    order_rule = "dynamic marginal objective of actual new purchases; group_id tie",
    dynamic_resort = TRUE, selection_policy = list(min_group_ev_cny = floor))
  summary <- tibble::tibble(objective = objective, planned_groups = nrow(pool$groups),
    selected_groups = evaluation$summary$selected_groups,
    cost_cny = evaluation$summary$spent_cny,
    model_ev_cny = evaluation$summary$ev_net_cny,
    coverage = evaluation$summary$actual_coverage,
    ended_by = selected$ended_by,
    budget_cny = if (is.null(budget_cny)) NA_real_ else budget_cny,
    min_group_ev_cny = if (is.finite(floor)) floor else NA_real_,
    group_budget_cny = if (is.null(group_budget_cny)) NA_real_ else group_budget_cny)
  receipt <- list(cutoff = pool$cutoff, cutoff_hash = pool$cutoff_hash,
    portfolio_hash = rlang::hash(portfolio),
    code_hash = .rank_outcome_code_hash(roots = "parlay_select_groups"),
    objective = objective, budget_cny = budget_cny, group_budget_cny = group_budget_cny,
    min_group_ev_cny = floor, reuse_policy = reuse, overlap_policy = overlap,
    selection_hash = rlang::hash(selected$selection),
    evaluation_receipt_hash = rlang::hash(evaluation$receipt))
  return(list(evaluation = evaluation, selection = selected$selection,
    summary = summary, excluded = selected$excluded, receipt = receipt,
    diagnostics = evaluation$diagnostics))
}
