#' Diagnose ticket depth within frozen purchased groups
#'
#' Vary per-group spending over the saved legal ticket ranking without changing
#' fixtures, outcome masks, selected groups, or ranking. This is a fixed-group
#' diagnostic, not a portfolio allocation or a probability of any portfolio hit.
#'
#' @param plans Uniquely named list of current [parlay_evaluate_portfolio()] results.
#'   Source, cutoff, code, purchased ledger and frozen plan bindings are checked.
#'   Names label patterns; selected groups and actual outcome masks remain fixed.
#' @param group_budgets_cny Plain finite nonnegative numeric vector of CNY caps.
#'   Caps are floored to whole ticket units and saturated at legal support size.
#'   Repeated caps are allowed and retain their input order.
#' @return Tibble with pattern, group_id, group_budget_cny, support_size,
#'   structure_probability, purchased_tickets, cost_cny, coverage_probability,
#'   retained_fraction, expected_net_cny. One row per purchased group and cap;
#'   pattern, first purchased group occurrence, then input cap determine row order.
#'   Zero depth has zero cost, coverage and net. Missing selected ticket EV makes
#'   expected net NA. Zero structure mass makes retained_fraction NA. Empty plans,
#'   caps or purchases produce the same typed empty schema.
#' @details Invalid saved ledgers, schemas, ranks or probabilities error. Candidate
#'   The cutoff must match its mandatory saved provenance hash. Sources must match saved provenance hashes and all plans must share cutoff,
#'   probabilities, SP and business constants (excluding issue budget). Complete
#'   selected support is rebuilt and revalued with authoritative helpers. Candidate
#'   and group identities jointly select support; shared physical tickets in other
#'   candidates cannot change the curve. No fitting, writes or purchases occur.
#' @export
parlay_fixed_depth_curve <- function(plans, group_budgets_cny) {
  checkmate::assert_list(plans, any.missing = FALSE)
  if (length(plans)) {
    checkmate::assert_character(names(plans), len = length(plans),
      any.missing = FALSE, min.chars = 1L, unique = TRUE)
  }
  if (!is.numeric(group_budgets_cny) || is.object(group_budgets_cny) ||
      !is.null(dim(group_budgets_cny))) stop("caps must be a plain numeric vector")
  checkmate::assert_numeric(group_budgets_cny, lower = 0, finite = TRUE,
                            any.missing = FALSE)
  empty <- tibble::tibble(pattern = character(), group_id = character(),
    group_budget_cny = double(), support_size = integer(),
    structure_probability = double(), purchased_tickets = integer(),
    cost_cny = double(), coverage_probability = double(),
    retained_fraction = double(), expected_net_cny = double())
  rows <- list()
  context <- NULL
  for (pattern in names(plans)) {
    plan <- plans[[pattern]]
    pool <- .parlay_ranked_validate_evaluation(plan)
    shared_settings <- pool$settings
    shared_settings$issue_budget_cny <- NULL
    current <- list(cutoff=pool$cutoff, probabilities=pool$probabilities,
      prematch_sp=pool$prematch_sp, settings=shared_settings)
    if (is.null(context)) context <- current
    if (!identical(context,current)) stop("fixed depth plans must share cutoff, sources and business settings")
    unit <- pool$settings$unit_cny
    for (group in unique(plan$purchases$group_id)) {
      block <- plan$final$role_legs[plan$final$role_legs$group_id==group,,drop=FALSE]
      space <- .parlay_ranked_group_space(group,block,pool$probabilities,
        pool$prematch_sp,pool$cutoff,pool$settings,pool$settings$n_legs)
      support <- space$ranked[order(space$ranked$rank),,drop=FALSE]
      mass <- sum(support$probability)
      if (mass > (1 + 1e-9)^pool$settings$n_legs) stop("saved support probability exceeds one")
      for (cap in group_budgets_cny) {
        count <- as.integer(min(nrow(support), floor(cap / unit)))
        selected <- support[seq_len(count), ]
        coverage <- sum(selected$probability)
        rows[[length(rows) + 1L]] <- tibble::tibble(pattern = pattern,
          group_id = group, group_budget_cny = as.double(cap),
          support_size = as.integer(nrow(support)), structure_probability = mass,
          purchased_tickets = count, cost_cny = as.double(count * unit),
          coverage_probability = coverage,
          retained_fraction = if (mass == 0) NA_real_ else coverage / mass,
          expected_net_cny = sum(selected$ev_net_est))
      }
    }
  }
  return(if (length(rows)) dplyr::bind_rows(rows) else empty)
}
