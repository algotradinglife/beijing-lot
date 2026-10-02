# Role round-robin (#537), stage 3: shared internal helpers.
#
# The rank-table evaluator that used to live here is OBSOLETE and has been deleted.
# Its successor is parlay_evaluate_portfolio() in parlay_ranked_portfolio.R, which
# consumes the ranked candidate pool and the mature ticket/freeze APIs. The two
# helpers kept here are the ones other package stages and the entry point still use:
# the optional-CNY budget validator and the frozen-mask refresh used to rebuild a
# leg's retained outcomes from the authoritative probabilities.

#' Validate an optional CNY budget
#'
#' Internal. `NULL` means "unspecified" and is preserved: an unlimited decision is
#' represented by `NULL`, never by an infinite number. A supplied value must be a
#' single non-negative finite number; negative, `NA` and infinite values are refused.
#' @param value Candidate budget.
#' @param name Parameter name used in the error message.
#' @return The numeric scalar, or `NULL`.
#' @noRd
.parlay_role_validate_budget <- function(value, name) {
  if (is.null(value)) return(NULL)
  checkmate::assert_number(value, lower = 0, finite = TRUE, .var.name = name)
  checkmate::assert_true(!is.object(value) && is.null(dim(value)),
    .var.name = paste(name, "must be an unclassed numeric scalar"))
  as.numeric(value)
}

#' Refresh a frozen leg's retained mask from the authoritative probabilities
#'
#' Internal. Rebuilds `allowed_outcomes` and `retained_probability` from the role
#' definition of the leg's fixture and role. Uses the shared
#' [.parlay_role_definition()] so a mask can never be re-derived by a private rule.
#' @param legs Legs tibble with `fixture_id` and `role`.
#' @param probabilities Authoritative probability tibble.
#' @return `legs` with refreshed masks.
#' @noRd
.parlay_role_refresh_masks <- function(legs, probabilities) {
  wide <- parlay_probability_wide(probabilities)
  out <- legs
  for (i in seq_len(nrow(out))) {
    role <- as.integer(out$role[i])
    fixture_id <- as.character(out$fixture_id[i])
    triple <- as.numeric(wide[wide$fixture_id == fixture_id, match_outcomes()])
    definition <- .parlay_role_definition(triple, role)
    out$allowed_outcomes[[i]] <- definition$allowed
    out$retained_probability[i] <- as.numeric(definition$retained)
  }
  out
}
