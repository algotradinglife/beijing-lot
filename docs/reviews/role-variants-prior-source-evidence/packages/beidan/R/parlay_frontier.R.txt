#' Validate one required numeric summary column
#'
#' Checks that a column is a plain numeric vector (no class attribute and no
#' matrix-like dimensions), rejects NaN/Inf and, unless missing values are
#' allowed, NA, and enforces optional bounds and whole-number values. The
#' original values are returned so callers keep the input typing.
#'
#' @param values Candidate column vector from the summary tibble.
#' @param column Column name, used only in error messages.
#' @param lower Inclusive lower bound, or NULL for no lower bound.
#' @param upper Inclusive upper bound, or NULL for no upper bound.
#' @param allow_na Whether NA is permitted alongside finite values.
#' @param whole Whether every non-missing value must be a whole number.
#' @return The validated `values` vector, unchanged.
#' @noRd
.parlay_frontier_numeric <- function(values, column, lower = NULL, upper = NULL,
                                     allow_na = FALSE, whole = FALSE) {
  if (!is.numeric(values) || is.object(values) || !is.null(dim(values))) {
    stop("parlay_frontier: ", column, " must be a plain numeric column")
  }
  if (any(is.nan(values)) || any(is.infinite(values))) {
    stop("parlay_frontier: ", column, " must not contain NaN or infinite values")
  }
  if (!allow_na && anyNA(values)) {
    stop("parlay_frontier: ", column, " must not contain missing values")
  }
  if (!is.null(lower) && any(values < lower, na.rm = TRUE)) {
    stop("parlay_frontier: ", column, " must be at least ", lower)
  }
  if (!is.null(upper) && any(values > upper, na.rm = TRUE)) {
    stop("parlay_frontier: ", column, " must be at most ", upper)
  }
  if (whole && any(values != floor(values), na.rm = TRUE)) {
    stop("parlay_frontier: ", column, " must contain whole numbers")
  }
  return(values)
}

#' Mark Pareto frontiers over parlay scenario summaries
#'
#' Classify each evaluated scenario as coverage-frontier and/or return-frontier.
#' A scenario is dominated when another eligible scenario in the same
#' `(max_reuse, max_overlap)` constraint profile costs no more (coverage and
#' return objectives both minimise `cost_cny`) and is no worse on the objective
#' (`hit_probability` for coverage, `expected_net_cny` for return), with at
#' least one of the two comparisons strictly better. Exact ties are never
#' dominated, so every tied scenario is retained. Scenarios in different
#' constraint profiles are never compared, regardless of `pattern`.
#'
#' Rows with `cost_cny == 0` or `prefix_groups == 0` are excluded from both
#' frontier flags and do not dominate other rows: a free or empty prefix is a
#' degenerate baseline, not a selectable budget scenario. A missing
#' `expected_net_cny` always yields `return_frontier = FALSE` and is excluded
#' from return comparisons. All comparison columns must be plain numeric
#' columns, not classed or matrix-like columns. No fitting, fetching, or
#' persistence occurs. These are model point-estimate frontiers, not historical
#' guarantees; no champion is selected.
#'
#' @param summary A tibble with one row per unique
#'   `(scenario_id, prefix_groups)` pair and the required columns
#'   `scenario_id`, `prefix_groups`, `cost_cny`, `hit_probability`,
#'   `expected_net_cny`, `max_reuse`, and `max_overlap`. `scenario_id` must be
#'   nonempty and non-missing character; `prefix_groups` whole and nonnegative;
#'   `cost_cny` finite and nonnegative (CNY); `hit_probability` finite and in
#'   `[0, 1]`; `expected_net_cny` finite or `NA` (never NaN/Inf, CNY);
#'   `max_reuse` whole and at least one; `max_overlap` whole and at least zero.
#'   Additional columns such as `pattern` are preserved.
#' @return `summary` with its columns and row order unchanged and two logical
#'   columns appended: `coverage_frontier` and `return_frontier`. A zero-row
#'   input returns the same typed empty tibble with `logical(0)` flags.
#' @details Invalid schemas, duplicate `(scenario_id, prefix_groups)` keys,
#'   classed/dimensional numeric columns, and column names that collide with the
#'   appended flags raise errors. Coverage minimises cost and maximises hit
#'   probability; return minimises cost and maximises expected net. Dominance is
#'   evaluated only among eligible rows sharing a `(max_reuse, max_overlap)`
#'   profile.
#' @export
parlay_frontier <- function(summary) {
  if (!tibble::is_tibble(summary)) {
    stop("parlay_frontier: summary must be a tibble")
  }
  checkmate::assert_character(names(summary), any.missing = FALSE,
                             min.chars = 1L, unique = TRUE)
  required <- c("scenario_id", "prefix_groups", "cost_cny", "hit_probability",
                "expected_net_cny", "max_reuse", "max_overlap")
  missing <- setdiff(required, names(summary))
  if (length(missing) > 0L) {
    stop("parlay_frontier: summary is missing required columns: ",
         paste(missing, collapse = ", "))
  }
  if (!is.character(summary$scenario_id)) {
    stop("parlay_frontier: scenario_id must be a character column")
  }
  if (anyNA(summary$scenario_id) || any(!nzchar(summary$scenario_id))) {
    stop("parlay_frontier: scenario_id must be nonempty and non-missing")
  }
  if (anyDuplicated(summary[required[1:2]]) > 0L) {
    stop("parlay_frontier: (scenario_id, prefix_groups) must be unique")
  }
  if (any(c("coverage_frontier", "return_frontier") %in% names(summary))) {
    stop("parlay_frontier: summary already has a frontier flag column")
  }
  prefix <- .parlay_frontier_numeric(summary$prefix_groups, "prefix_groups",
                                    lower = 0, whole = TRUE)
  cost <- .parlay_frontier_numeric(summary$cost_cny, "cost_cny", lower = 0)
  hit <- .parlay_frontier_numeric(summary$hit_probability, "hit_probability",
                                  lower = 0, upper = 1)
  ev <- .parlay_frontier_numeric(summary$expected_net_cny, "expected_net_cny",
                                 allow_na = TRUE)
  reuse <- .parlay_frontier_numeric(summary$max_reuse, "max_reuse",
                                    lower = 1, whole = TRUE)
  overlap <- .parlay_frontier_numeric(summary$max_overlap, "max_overlap",
                                      lower = 0, whole = TRUE)

  coverage <- logical(nrow(summary))
  returns <- logical(nrow(summary))
  if (nrow(summary) > 0L) {
    profiles <- unique(summary[c("max_reuse", "max_overlap")])
    for (current in seq_len(nrow(profiles))) {
      in_profile <- which(reuse == profiles$max_reuse[current] &
                          overlap == profiles$max_overlap[current])
      eligible <- in_profile[cost[in_profile] > 0 & prefix[in_profile] > 0]
      for (i in eligible) {
        dominated <- FALSE
        for (j in eligible) {
          if (j == i) next
          if (cost[j] <= cost[i] && hit[j] >= hit[i] &&
              (cost[j] < cost[i] || hit[j] > hit[i])) {
            dominated <- TRUE
            break
          }
        }
        coverage[i] <- !dominated
      }
      with_ev <- eligible[!is.na(ev[eligible])]
      for (i in with_ev) {
        dominated <- FALSE
        for (j in with_ev) {
          if (j == i) next
          if (cost[j] <= cost[i] && ev[j] >= ev[i] &&
              (cost[j] < cost[i] || ev[j] > ev[i])) {
            dominated <- TRUE
            break
          }
        }
        returns[i] <- !dominated
      }
    }
  }
  summary$coverage_frontier <- coverage
  summary$return_frontier <- returns
  return(summary)
}
