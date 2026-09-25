#' Beijing parlay research pipeline
#'
#' Explicit-input functions for reproducible parlay research: generic match
#' inputs/probabilities, a session-scoped parlay parameter block, and
#' parlay group/ticket/strategy contracts. Loading the package does not
#' initialize Python, fetch data or write to databases.
#' @importFrom rlang .data
#' @keywords internal
"_PACKAGE"

#' @export parlay_settings
#' @export match_table_schemas
#' @export match_typed_empty
#' @export match_validate_table
#' @export make_example_issue
#' @export example_match_source
#' @export read_match_inputs
#' @export match_status_levels
#' @export match_select_status
#' @export prepare_match_inputs
#' @export estimate_match_probabilities
#' @export parlay_construct_groups
#' @export parlay_apply_structure
#' @export parlay_enumerate_tickets
#' @export parlay_value_tickets
#' @export parlay_rank_tickets
#' @export parlay_settle_plan
#' @export parlay_diagnose_plan
#' @export parlay_replay_issue
#' @export parlay_allocation_configs
#' @export parlay_build_plan
#' @export match_outcomes
#' @export bounded_market_lambdas
#' @export market_score_projection
#' @export asian_total_probability
#' @export total_market_constraint
#' @export total_constrained_projection
NULL
