#' Reprice a structure on the funded groups of a frozen proposal
#' @param source Validated saved plan result. Only its funded groups are retained.
#'   Must have no earlier purchases; this produces an alternative, not an addition.
#' @param cutoff Explicit cutoff object, required to equal the source cutoff.
#' @param pattern Integer vector of allowed outcome counts, one per leg (1..3).
#'   Roles are assigned within each fixed group by the authoritative role scores:
#'   sorted roles 3->2->1, each taking the highest-scoring unassigned member.
#' @param group_budget_cny Positive finite scalar CNY budget for each group,
#'   divisible by the source unit cost. Combined budgets cannot exceed issue budget.
#' @return A plan result consumable by parlay_betting_sheet(), with provenance
#'   identifying the source hash and alternative-plan semantics. Empty source
#'   purchases, mismatched cutoff or invalid budgets error. A small support leaves
#'   money unspent; no other group receives that remainder.
#' @details No fetching, model fitting, fixture search, settlement or persistence.
#'   The probabilities and cutoff are copied unchanged. Existing structure,
#'   enumeration, ranking and funding functions select top tickets independently
#'   within each group. SP/EV are explicitly unavailable on this probability-only
#'   path; no source ticket values are reused for newly introduced outcomes.
#' @export
parlay_restructure_plan <- function(source, cutoff, pattern, group_budget_cny) {
  parlay_check_saved_result(source)
  match_require_cutoff(cutoff)
  if (!identical(cutoff, source$cutoff)) stop("cutoff must equal source cutoff")
  settings <- source$constants
  parlay_validate_settings(settings)
  if (nrow(source$history$purchases) != nrow(source$funded$purchases)) {
    stop("alternative requires no earlier purchases")
  }
  ids <- sort(unique(source$funded$purchases$group_id))
  if (!length(ids)) stop("source needs funded groups")
  checkmate::assert_integerish(pattern, len = settings$n_legs,
    lower = 1, upper = 3, any.missing = FALSE)
  checkmate::assert_number(group_budget_cny, lower = settings$unit_cny, finite = TRUE)
  units <- group_budget_cny / settings$unit_cny
  if (units != floor(units)) stop("group budget must be divisible by unit cost")
  total <- length(ids) * group_budget_cny
  if (total > settings$issue_budget_cny) stop("group budgets exceed issue budget")
  legs <- dplyr::filter(source$plan$group_legs, group_id %in% ids)
  label <- paste0("p", paste(pattern, collapse = ""))
  patterns <- stats::setNames(list(as.integer(pattern)), label)
  structure <- parlay_apply_structure(legs, source$probabilities, cutoff,
    as.integer(pattern), candidate_label = label)
  tickets <- parlay_enumerate_tickets(legs, source$probabilities, cutoff,
    structure$supports, n_legs = settings$n_legs)
  valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs,
    match_typed_empty("prematch_sp"), cutoff, settings$sp_threshold,
    settings$sp_replacement, settings$unit_cny, settings$payout_factor)
  ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, cutoff,
    "probability_desc")
  funded <- .FundGroups(legs, ranked, patterns, total, settings,
    max_reuse = source$config$max_reuse, max_overlap = source$config$max_overlap,
    unit_cap = units, issue_id = cutoff$issue_id, epoch_at = cutoff$cutoff_utc)
  if (!setequal(funded$purchases$group_id, ids)) {
    stop("source groups cannot all be funded under source constraints")
  }
  funded$diagnostics$cost_cny <- sum(funded$purchases$stake_cny)
  funded$diagnostics$unspent_cny <- total - funded$diagnostics$cost_cny
  funded$diagnostics$units_bought <- nrow(funded$purchases)
  config <- parlay_strategy_config(settings, name = "fixed-groups-alternative",
    patterns = patterns, objective = "probability",
    max_reuse = source$config$max_reuse, max_overlap = source$config$max_overlap,
    spend_limit_cny = total)
  policies <- list(allocation = "equal-budget-fixed-groups", objective = "probability",
    model_config = source$plan$policies$model_config,
    market_policy = source$plan$policies$market_policy,
    max_reuse = config$max_reuse, max_overlap = config$max_overlap)
  plan <- .FreezeParlayPlan(cutoff$issue_id, cutoff$cutoff_utc, legs, structure,
    tickets, valued, funded$funded, funded$purchases, settings, policies)
  history <- list(purchases = funded$purchases, fixture_sets = funded$fixture_sets)
  result <- list(config = config, cutoff = cutoff, constants = settings,
    built = list(groups = list(group_legs = legs), structure = structure,
      tickets = tickets, valued = valued), probabilities = source$probabilities,
    ranked = ranked, funded = funded, plan = plan, history = history,
    budget_state = parlay_budget_state(settings, NULL, cutoff, spend_limit_cny = total),
    frontier = list(group_legs = legs, supports = structure$supports,
      ranked = ranked, candidate_tickets = tickets$candidate_tickets,
      ticket_legs = tickets$ticket_legs),
    provenance = list(mode = "alternative_not_additional_purchase",
      source_hash = rlang::hash(source), group_budget_cny = group_budget_cny,
      reused_groups = ids, probability_method = "unchanged_source_probabilities"))
  result$summary <- parlay_plan_summary(result)
  parlay_check_saved_result(result)
  return(result)
}
