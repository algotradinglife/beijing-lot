#' Reallocate fixture categories for an adaptive parlay structure
#'
#' Keep original probabilities and filtering, and change only enough category
#' assignments to fill the target structure. The fixed greedy allocation is
#' descriptive, not a learned or globally optimal policy. Changed fixtures use
#' primary TopN masks; untouched fixtures keep their original protected choices.
#'
#' @param ranked_selections Receipt-bound tibble returned by
#'   [rank_outcome_selections()]. Its embedded cutoff is required and replayed.
#' @param n_legs Positive whole number of fixtures required by the structure.
#' @param pattern Optional vector of roles 1:3 of length n_legs. NULL uses
#'   [parlay_suggest_pattern()] with the supplied max_role1.
#' @param max_role1 Maximum singles in the suggested pattern; default one.
#' @param requested_groups Positive whole target group count for supply planning.
#' @param max_reuse Optional positive whole per-fixture reuse cap, all roles count.
#' @return List with ranked selection tibble `ranked`, cutoff-bound `allocation`
#'   ledger and integer `pattern`. Insufficient fixtures produce an unchanged
#'   ledger with explicit status; no fixtures are fabricated. No IO, labels,
#'   fitting, normalization or changes to the input object.
#' @export
AdaptOutcomeSelections <- function(ranked_selections, n_legs, pattern = NULL,
                                   max_role1 = 1L, requested_groups = 1L, max_reuse = NULL) {
  checkmate::assert_count(requested_groups, positive = TRUE)
  if (!is.null(max_reuse)) checkmate::assert_count(max_reuse, positive = TRUE)
  receipt <- .parlay_ranked_validate_receipt(ranked_selections)
  suggested <- parlay_suggest_pattern(ranked_selections, n_legs, max_role1)
  if (is.null(pattern)) pattern <- suggested$pattern
  if (length(pattern) != n_legs) stop("pattern must have n_legs entries", call. = FALSE)
  snapshot <- receipt$input_snapshot
  if (!is.null(attr(snapshot, "role_allocation", exact = TRUE))) {
    stop("AdaptOutcomeSelections requires original unallocated selections", call. = FALSE)
  }
  source_columns <- setdiff(names(snapshot), .prepare_outcome_derived_columns())
  matches <- snapshot[!duplicated(snapshot$fixture_id), source_columns, drop = FALSE]
  attr(matches, "filter_receipt") <- attr(snapshot, "filter_receipt", exact = TRUE)
  threshold <- attr(snapshot, "single_threshold", exact = TRUE)
  role_minimums <- if (is.null(max_reuse)) NULL else {
    planned_groups <- min(requested_groups, floor(nrow(matches) * max_reuse / n_legs))
    as.integer(ceiling(tabulate(as.integer(pattern), 3L) * planned_groups / max_reuse))
  }
  allocation <- AdaptiveRoleAllocation(matches, receipt$cutoff, pattern, threshold, role_minimums)
  selections <- prepare_outcome_selections(
    matches, threshold, attr(snapshot, "dc_protection", exact = TRUE), allocation)
  ranked <- rank_outcome_selections(selections, receipt$cutoff, receipt$priority)
  return(list(ranked = ranked, allocation = allocation, pattern = allocation$pattern))
}
