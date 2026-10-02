#' Diagnose ticket depth within frozen purchased groups
#'
#' Vary per-group spending over the saved legal ticket ranking without changing
#' fixtures, outcome masks, selected groups, or ranking. This is a fixed-group
#' diagnostic, not a portfolio allocation or a probability of any portfolio hit.
#'
#' @param plans Uniquely named list of role evaluator final plans, one per pattern,
#'   with frozen probability-descending ticket ranking and canonical tie breaks.
#'   Each result is checked with [parlay_check_saved_result()]. Names label patterns.
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
    parlay_check_saved_result(plan)
    parlay_validate_settings(plan$constants)
    match_require_cutoff(plan$cutoff)
    cutoff_hash <- rlang::hash(list(as.character(plan$cutoff$issue_id),
                                   as.numeric(plan$cutoff$cutoff_utc)))
    if (!identical(plan$provenance$cutoff_hash, cutoff_hash)) {
      stop("fixed depth cutoff provenance mismatch")
    }
    if (!identical(plan$constants, plan$plan$constants)) stop("frozen settings mismatch")
    probabilities <- match_validate_table(plan$probabilities, "probabilities",
      keys = c("fixture_id", "outcome"))
    parlay_probability_wide(probabilities)
    sp <- .parlay_role_validate_prematch_sp(plan$prematch_sp, plan$cutoff)
    hashes <- list(probability_hash = rlang::hash(probabilities),
                   prematch_sp_hash = rlang::hash(sp))
    for (field in names(hashes)) {
      if (!identical(plan$provenance[[field]], hashes[[field]])) {
        stop("fixed depth source provenance mismatch: ", field)
      }
    }
    current <- list(cutoff = plan$cutoff, hashes = hashes,
      settings = plan$constants[setdiff(names(plan$constants), "issue_budget_cny")])
    if (is.null(context)) context <- current
    if (!identical(context, current)) stop("fixed depth plans must share cutoff, sources and business settings")
    unit <- plan$constants$unit_cny
    ranked <- match_validate_table(plan$ranked, "ranked")
    links <- match_validate_table(plan$built$tickets$candidate_tickets, "candidate_tickets")
    keys <- c("candidate_id", "ticket_id")
    if (nrow(dplyr::anti_join(ranked, links, by = keys)) ||
        nrow(dplyr::anti_join(links, ranked, by = keys))) {
      stop("saved support and ranking disagree")
    }
    purchases <- plan$funded$purchases
    if (nrow(dplyr::anti_join(purchases, ranked,
                            by = c(keys, "group_id")))) {
      stop("purchased candidate/group is missing from ranking")
    }
    for (group in unique(purchases$group_id)) {
      candidate <- unique(purchases$candidate_id[purchases$group_id == group])
      if (length(candidate) != 1L) stop("multiple purchased candidates in one group")
      support <- ranked[ranked$candidate_id == candidate & ranked$group_id == group, ]
      support <- support[order(support$rank), ]
      if (!nrow(support) || !identical(support$rank, seq_len(nrow(support)))) {
        stop("saved support ranks must be contiguous starting at one")
      }
      checkmate::assert_numeric(support$probability, lower = 0, upper = 1,
                                finite = TRUE, any.missing = FALSE)
      if (any(is.nan(support$ev_net_est)) || any(is.infinite(support$ev_net_est))) {
        stop("saved EV must be finite or NA")
      }
      # Rebuild the complete legal support from frozen masks and authoritative
      # inputs, including tickets beyond the originally purchased prefix.
      group_legs <- plan$plan$group_legs
      group_legs <- group_legs[group_legs$group_id == group, ]
      masks <- plan$built$structure$supports
      masks <- masks[masks$candidate_id == candidate, ]
      rebuilt <- parlay_enumerate_tickets(group_legs, probabilities, plan$cutoff,
        masks, n_legs = plan$constants$n_legs)
      valued <- parlay_value_tickets(rebuilt$tickets, rebuilt$ticket_legs, sp,
        plan$cutoff, plan$constants$sp_threshold, plan$constants$sp_replacement,
        unit, plan$constants$payout_factor)
      if (!setequal(support$ticket_id, valued$ticket_id)) {
        stop("saved ranked support disagrees with frozen legal masks")
      }
      expected_ranking <- parlay_rank_tickets(valued, rebuilt$candidate_tickets,
        plan$cutoff, "probability_desc")
      expected_ranking <- expected_ranking[order(expected_ranking$rank), ]
      if (!identical(support$ticket_id, expected_ranking$ticket_id)) {
        stop("saved ticket rank order disagrees with probability ranking")
      }
      index <- match(support$ticket_id, valued$ticket_id)
      for (field in c("probability", "ev_net_est")) {
        if (!isTRUE(all.equal(support[[field]], valued[[field]][index],
                              tolerance = 1e-12, check.attributes = FALSE))) {
          stop("saved ranked ", field, " disagrees with authoritative inputs")
        }
      }
      mass <- sum(support$probability)
      if (mass > 1 + 1e-10) stop("saved support probability exceeds one")
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
