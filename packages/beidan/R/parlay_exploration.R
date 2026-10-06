#' Explore explicit budget scenarios over frozen role candidate pools
#'
#' Evaluate every scenario using the marginal-coverage group selector. Nothing is
#' fitted, fetched, persisted, or purchased. Coverage is the exact union probability
#' that at least one purchased ticket wins; EV uses raw SP.
#'
#' @param portfolios Nonempty uniquely named list of objects returned by
#'   [parlay_construct_role_groups()]. Every pool must have valid bound inputs and
#'   the same cutoff issue/time, probability snapshot and pre-match SP snapshot. Names identify structures in `scenarios$pattern`.
#' @param scenarios A tibble, one row per scenario, with unique nonempty character
#'   `scenario_id`, character `pattern` matching a pool name, unclassed finite
#'   numeric `group_budget_cny` (CNY, nonnegative), optional `budget_cny` with
#'   the same finite nonnegative contract, and unclassed
#'   whole numeric `max_reuse` (at least one) and `max_overlap` (at least zero).
#'   Missing values are forbidden in required columns. Extra descriptive columns
#'   are retained, but may not collide with output metric names.
#' @return List with `summary` (input columns plus final metric columns), `results`
#'   (evaluation objects named by scenario_id), and the shared `cutoff`. Summary
#'   metrics include selected_groups, new_ticket_count, spent_cny, actual_coverage,
#'   nominal_coverage, ev_net_cny, ev_available and unspent_cny. EV is
#'   missing when unavailable. Zero scenarios return the same typed empty summary
#'   and an empty named list; all pools and input schemas are still validated.
#' @details Invalid schemas, conflicting metric names, altered pool hashes, or
#'   differing decision contexts raise errors. Total and group budgets are explicit
#'   finite amounts when supplied; omit the total budget column for unlimited
#'   spending. Summary then reports budget_cny = NA_real_ and
#'   budget_unlimited = TRUE (FALSE when a cap is supplied). Group budgets
#'   remain finite; full coverage is expressed as its numeric cost. Pool
#'   validation delegates to a zero-budget selection, avoiding duplicate chronology
#'   rules. Results preserve selector receipts and never run local improvement.
#' @export
parlay_explore_portfolios <- function(portfolios, scenarios) {
  checkmate::assert_list(portfolios, min.len = 1L, any.missing = FALSE)
  checkmate::assert_character(names(portfolios), len = length(portfolios),
                             any.missing = FALSE, min.chars = 1L, unique = TRUE)
  checkmate::assert_true(tibble::is_tibble(scenarios))
  checkmate::assert_character(names(scenarios), any.missing = FALSE,
                             min.chars = 1L, unique = TRUE)
  required <- c("scenario_id", "pattern", "group_budget_cny",
                "max_reuse", "max_overlap")
  if (!all(required %in% names(scenarios))) stop("scenarios is missing required columns")
  checkmate::assert_character(scenarios$scenario_id, any.missing = FALSE,
                             min.chars = 1L, unique = TRUE)
  checkmate::assert_character(scenarios$pattern, any.missing = FALSE, min.chars = 1L)
  if (any(!scenarios$pattern %in% names(portfolios))) stop("unknown scenario pattern")
  budget_unlimited <- !"budget_cny" %in% names(scenarios)
  if ("budget_unlimited" %in% names(scenarios)) stop("scenario columns collide with output metrics")
  numeric_columns <- c(required[3:5], if (!budget_unlimited) "budget_cny")
  for (column in numeric_columns) {
    values <- scenarios[[column]]
    checkmate::assert_true(is.numeric(values) && !is.object(values) && is.null(dim(values)),
                          .var.name = column)
    checkmate::assert_numeric(values, lower = if (column == "max_reuse") 1 else 0,
                             finite = TRUE, any.missing = FALSE, .var.name = column)
    if (column %in% c("max_reuse", "max_overlap") && any(values != floor(values))) {
      stop(column, " must contain whole integers")
    }
  }
  # Reuse the authoritative selector even for unused pools and zero scenarios.
  # Coverage objective here validates structure without requiring optional SP.
  probes <- lapply(portfolios, function(pool) {
    parlay_select_groups(pool, objective = "coverage", group_budget_cny = 0,
      budget_cny = 0, reuse_policy = list(max_reuse = 1L),
      overlap_policy = list(max_overlap = 0L))$evaluation
  })
  cutoff <- portfolios[[1L]][["cutoff"]]
  if (any(!vapply(portfolios, function(pool) {
    identical(as.character(pool$cutoff$issue_id), as.character(cutoff$issue_id)) &&
      identical(as.numeric(pool$cutoff$cutoff_utc), as.numeric(cutoff$cutoff_utc))
  }, logical(1)))) stop("portfolios must share the same cutoff issue and time")
  if (any(!vapply(portfolios, function(pool) {
    identical(pool$probability_hash, portfolios[[1L]]$probability_hash) &&
      identical(pool$prematch_sp_hash, portfolios[[1L]]$prematch_sp_hash)
  }, logical(1)))) stop("portfolios must share the same probability and pre-match SP context")
  if (budget_unlimited) scenarios$budget_cny <- rep(NA_real_, nrow(scenarios))
  scenarios$budget_cny <- as.double(scenarios$budget_cny)
  scenarios$budget_unlimited <- rep(budget_unlimited, nrow(scenarios))
  canonical <- c("scenario_id", "pattern", "group_budget_cny", "budget_cny",
                 "max_reuse", "max_overlap")
  scenarios <- scenarios[c(canonical, setdiff(names(scenarios), canonical))]
  template <- tibble::as_tibble(probes[[1L]]$summary[names(probes[[1L]]$summary) != "group_budget_cny"])
  template <- template[0, , drop = FALSE]
  if (any(names(template) %in% names(scenarios))) stop("scenario columns collide with output metrics")
  results <- stats::setNames(vector("list", nrow(scenarios)), scenarios$scenario_id)
  rows <- vector("list", nrow(scenarios))
  for (i in seq_len(nrow(scenarios))) {
    row <- scenarios[i, , drop = FALSE]
    evaluation <- parlay_select_groups(portfolios[[row$pattern]],
      objective = "coverage",
      group_budget_cny = row$group_budget_cny, budget_cny = if (budget_unlimited) NULL else row$budget_cny,
      reuse_policy = list(max_reuse = row$max_reuse),
      overlap_policy = list(max_overlap = row$max_overlap))$evaluation
    results[[i]] <- evaluation
    metrics <- tibble::as_tibble(evaluation$summary[names(template)])
    rows[[i]] <- dplyr::bind_cols(row, metrics)
  }
  summary <- if (length(rows)) dplyr::bind_rows(rows) else dplyr::bind_cols(scenarios, template)
  return(list(summary = summary, results = results, cutoff = cutoff))
}
