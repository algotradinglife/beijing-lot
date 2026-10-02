#' Classify North single-handicap win/draw/lose probabilities
#'
#' Rank the three probabilities by decreasing value, breaking equal
#' probabilities in the fixed order `win`, `draw`, `lose`. The values are the
#' North single-handicap W/D/L probabilities of one fixture; they are consumed
#' exactly as supplied and are never renormalized. `win`, `draw` and `lose` are
#' three independent scalar arguments: the caller's argument order is not an
#' ordering and never changes the result.
#'
#' @param win Numeric scalar, finite and within `[0, 1]`: the win probability.
#' @param draw Numeric scalar, finite and within `[0, 1]`: the draw probability.
#' @param lose Numeric scalar, finite and within `[0, 1]`: the lose probability.
#'   For every argument, `NA`, empty, vector, character and logical values are
#'   errors.
#'
#' @return An unnamed list of unnamed character vectors whose values are drawn
#'   from `"win"`, `"draw"` and `"lose"`. With `ranked` the decreasing
#'   probability order:
#'   * `list(ranked[1])` plus the protected pairs below when `ranked[1] > 0.50`
#'     strictly (single choice);
#'   * `list(c("win", "draw", "lose"))` when the largest minus the smallest
#'     probability is at most `0.10` plus a `1e-15` numerical boundary
#'     tolerance (triple, canonical order);
#'   * `list(ranked[1:2], ranked[c(1, 3)])` when `ranked[3] > 0.20` strictly;
#'   * `list(ranked[1:2])` otherwise.
#'
#'   The returned values name outcomes; they are never rankings or
#'   classification text.
#'
#'   The list carries one attribute, `base_role`, an integer scalar `1`, `2` or
#'   `3` describing the fixture's base category, not its selection count:
#'   * `1`: single choice. `ranked[1] > 0.50` strictly. Every protected entry is
#'     built ON TOP OF the base `ranked[1]`, which is never emitted alone as a
#'     disjoint alternative: the result is always `list(ranked[1])`, plus
#'     `c(ranked[1], ranked[2])` when `ranked[2] > 0.20` strictly, plus
#'     `c(ranked[1], ranked[3])` when `ranked[3] > 0.20` strictly, each added
#'     independently. So `(0.55, 0.23, 0.22)` returns
#'     `list("win", c("win", "draw"), c("win", "lose"))`.
#'   * `2`: double choice. Not a single, and `max - min > 0.10`. The result is
#'     `ranked[1:2]`, plus `ranked[c(1, 3)]` when `ranked[3] > 0.20` strictly.
#'     The added outcome is allowed to be the draw; no draw-complement rule
#'     applies.
#'   * `3`: triple choice. Not a single, and `max - min <= 0.10`. The result is
#'     the canonical `c("win", "draw", "lose")`.
#'
#'   A single-choice fixture can therefore return one, two or three vectors, and
#'   `2`/`3` label the base category a later stage ranks into, not the number of
#'   rows returned. Both `0.50` and `0.20` are boundaries of strict `>`
#'   comparisons: exactly `0.50` is not a single and exactly `0.20` adds
#'   nothing. The base entry is emitted once and each protected pair is unique,
#'   so returns are deduplicated and in a stable order.
#' @section Errors:
#' Each argument must be a finite numeric scalar in `[0, 1]`, and the three
#' values must sum to `1` within `1e-9`. Invalid input raises an error; values
#' are never normalized, imputed or silently coerced.
#' @section Empty input:
#' There is no empty-input form. Each argument must be a single number, so
#' `numeric(0)`, `NULL` and every other zero-length value are errors, never an
#' empty result.
#' @details Pure arithmetic. The function performs no fitting, reads no labels,
#'   clock or IO, and keeps no mutable state. It never reads a starting price or
#'   a cutoff; filtering by quote and decision time belongs to
#'   [filter_outcome_matches()], which runs before classification.
#' @examples
#' classify_outcomes(win = 0.45, draw = 0.22, lose = 0.33)
#' classify_outcomes(0.40, 0.30, 0.30)
#' classify_outcomes(0.45, 0.33, 0.22)
#' classify_outcomes(0.50, 0.20, 0.30)
#' classify_outcomes(0.38, 0.31, 0.31)
#' classify_outcomes(0.55, 0.23, 0.22)
#' @export
classify_outcomes <- function(win, draw, lose) {
  checkmate::assert_number(win, lower = 0, upper = 1, finite = TRUE)
  checkmate::assert_number(draw, lower = 0, upper = 1, finite = TRUE)
  checkmate::assert_number(lose, lower = 0, upper = 1, finite = TRUE)
  if (abs(win + draw + lose - 1) > 1e-9) {
    stop("win, draw and lose must sum to one within 1e-9", call. = FALSE)
  }
  probabilities <- c(win, draw, lose)
  ranknames <- c("win", "draw", "lose")[order(-probabilities, c(1L, 2L, 3L))]
  ranked <- probabilities[order(-probabilities, c(1L, 2L, 3L))]
  tripled <- max(probabilities) - min(probabilities) <= 0.10 + 1e-15
  if (!tripled && ranked[1L] > 0.50) {
    # Single choice: the base Top1 is always protected, so every extra entry
    # keeps it and is a pair. The base is never emitted as a standalone
    # alternative to its own protected pairs.
    choices <- list(ranknames[1L])
    if (ranked[2L] > 0.20) choices <- c(choices, list(ranknames[1:2]))
    if (ranked[3L] > 0.20) choices <- c(choices, list(ranknames[c(1L, 3L)]))
    result <- choices
  } else if (tripled) {
    result <- list(c("win", "draw", "lose"))
  } else if (ranked[3L] > 0.20) {
    result <- list(ranknames[1:2], ranknames[c(1L, 3L)])
  } else {
    result <- list(ranknames[1:2])
  }
  attr(result, "base_role") <- if (tripled) 3L else if (ranked[1L] > 0.50) 1L else 2L
  result
}
