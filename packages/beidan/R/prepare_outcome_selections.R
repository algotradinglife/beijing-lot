# Expand admitted match probabilities into ranked-choice candidates (#553).
#
# The second stage of the outcome-role pipeline. It consumes the admitted
# `matches` tibble and delegates every classification decision to the single
# authoritative classifier, [classify_outcomes()]: the thresholds, the direction
# order and the fixture's base category are never restated here. One fixture
# expands to one row per allowed outcome choice, so a later stage ranks choices,
# not fixtures.

#' Name derived selection columns
#'
#' @return Character names reserved for classification-derived selection fields.
#' @noRd
.prepare_outcome_derived_columns <- function() {
  c("selection_id", "outcomes", "base_role", "n_outcomes",
    "coverage_probability", "entropy", "p3")
}

#' Prepare outcome selections from match probabilities
#'
#' Expand every row of a validated matches tibble into one row per outcome
#' choice allowed by the authoritative [classify_outcomes()] classifier.
#'
#' @param matches A `tibble` with one row per fixture. It must contain a
#'   unique, non-missing, non-empty character `fixture_id` column (leading zeros
#'   are preserved) and numeric `win`, `draw` and `lose` columns. Every other
#'   source column is preserved and replicated for each choice of its fixture.
#'   The derived columns `selection_id`, `outcomes`, `base_role`,
#'   `n_outcomes`, `coverage_probability`, `entropy` and `p3` must not already
#'   be present.
#'
#'   Any receipt attributes of `matches` (for example the `filter_receipt` of
#'   [filter_outcome_matches()]) are preserved unchanged on the result, so the
#'   provenance of the admitted fixtures is carried explicitly into every
#'   expanded row.
#'
#' @return A `tibble` with one row per `(fixture_id, selection_id)` pair, where
#'   `selection_id` is an integer sequence starting at `1` within each fixture.
#'   Rows keep the input row order; within a fixture they follow the
#'   [classify_outcomes()] direction order. No sorting is performed. The
#'   returned columns are the input columns followed by:
#'   * `selection_id`: integer selection key within the fixture.
#'   * `outcomes`: list column of unnamed character vectors naming the selected
#'     outcomes, taken verbatim from [classify_outcomes()].
#'   * `base_role`: integer base category of the fixture, `1`, `2` or `3`, read
#'     from the classifier's `base_role` attribute. It is the fixture's category,
#'     not the number of rows it produced: a base-role-`1` fixture emits one, two
#'     or three rows that all carry `1`.
#'   * `n_outcomes`: integer number of selected outcomes in this row, that is
#'     `length(outcomes)`. It is deliberately the length of `outcomes` and is
#'     never a second copy of `base_role`.
#'   * `coverage_probability`: double sum of the original selected
#'     probabilities; the probabilities are never renormalized.
#'   * `entropy`: double normalized Shannon entropy of the selected
#'     probabilities `q = p / sum(p)` computed as
#'     `-sum(q[q > 0] * log(q[q > 0])) / log(n_outcomes)`. A selection of one
#'     outcome is defined as `0`. When `coverage_probability` is `0` the entropy
#'     is undefined and returned as `NA_real_`.
#'   * `p3`: double minimum of the three original probabilities, carried per row
#'     exactly as supplied.
#'
#'   An empty input tibble returns a typed empty tibble with the same source
#'   columns plus integer `selection_id`, list `outcomes`, integer `base_role`
#'   and `n_outcomes`, and double `coverage_probability`, `entropy` and `p3`.
#'
#' @section Errors:
#' `matches` is an error when it is not a tibble, when a required column is
#' missing or has the wrong type, when `fixture_id` is duplicated, missing or
#' empty, when a derived column already exists, or when any row's `win`, `draw`
#' and `lose` values are rejected by [classify_outcomes()]. Values are never
#' coerced, imputed, renormalized or sorted.
#'
#' @details Pure transformation. The function reads no labels, clock or IO,
#'   performs no fitting and keeps no mutable state. It does not mutate
#'   `matches` and offers no compatibility or ranking arguments.
#'
#' @examples
#' matches <- tibble::tibble(
#'   fixture_id = c("001", "002"),
#'   win = c(0.45, 0.40),
#'   draw = c(0.22, 0.30),
#'   lose = c(0.33, 0.30)
#' )
#' prepare_outcome_selections(matches)
#' @export
prepare_outcome_selections <- function(matches) {
  if (!tibble::is_tibble(matches)) {
    stop("`matches` must be a tibble.", call. = FALSE)
  }

  required <- c("fixture_id", "win", "draw", "lose")
  missing_columns <- setdiff(required, names(matches))
  if (length(missing_columns) > 0L) {
    stop(
      sprintf(
        "`matches` is missing required column(s): %s.",
        paste(missing_columns, collapse = ", ")
      ),
      call. = FALSE
    )
  }

  collisions <- intersect(.prepare_outcome_derived_columns(), names(matches))
  if (length(collisions) > 0L) {
    stop(
      sprintf(
        "`matches` already contains derived column(s): %s; refusing to overwrite.",
        paste(collisions, collapse = ", ")
      ),
      call. = FALSE
    )
  }

  fixture_id <- matches[["fixture_id"]]
  if (!is.character(fixture_id)) {
    stop("`matches$fixture_id` must be a character vector.", call. = FALSE)
  }
  if (anyNA(fixture_id)) {
    stop("`matches$fixture_id` must be non-missing.", call. = FALSE)
  }
  if (any(!nzchar(fixture_id))) {
    stop("`matches$fixture_id` must be non-empty.", call. = FALSE)
  }
  if (anyDuplicated(fixture_id)) {
    stop("`matches$fixture_id` must be unique.", call. = FALSE)
  }

  n <- nrow(matches)
  for (column in c("win", "draw", "lose")) {
    values <- matches[[column]]
    if (!is.numeric(values) || !is.null(dim(values)) || length(values) != n) {
      stop(
        sprintf("`matches$%s` must be a numeric column.", column),
        call. = FALSE
      )
    }
  }

  win <- matches[["win"]]
  draw <- matches[["draw"]]
  lose <- matches[["lose"]]

  row_index <- integer(0)
  selection_id <- integer(0)
  base_role <- integer(0)
  outcomes <- list()
  selected <- list()
  p3 <- numeric(0)

  for (i in seq_len(n)) {
    probabilities <- c(win = win[[i]], draw = draw[[i]], lose = lose[[i]])
    choices <- classify_outcomes(
      probabilities[["win"]],
      probabilities[["draw"]],
      probabilities[["lose"]]
    )
    # The fixture's base category is the classifier's own attribute; the
    # thresholds that produced it are never restated here.
    role <- attr(choices, "base_role")
    for (j in seq_along(choices)) {
      row_index <- c(row_index, i)
      selection_id <- c(selection_id, j)
      base_role <- c(base_role, role)
      outcomes[[length(outcomes) + 1L]] <- choices[[j]]
      selected[[length(selected) + 1L]] <- probabilities[choices[[j]]]
      p3 <- c(p3, min(probabilities))
    }
  }

  coverage_probability <- vapply(selected, sum, numeric(1))
  n_outcomes <- lengths(outcomes)
  entropy <- vapply(
    seq_along(selected),
    function(index) {
      probabilities <- selected[[index]]
      total <- sum(probabilities)
      if (total == 0) {
        return(NA_real_)
      }
      count <- n_outcomes[[index]]
      if (count <= 1L) {
        return(0)
      }
      q <- probabilities / total
      q <- q[q > 0]
      -sum(q * log(q)) / log(count)
    },
    numeric(1)
  )

  result <- matches[row_index, , drop = FALSE]
  result[["selection_id"]] <- as.integer(selection_id)
  result[["outcomes"]] <- outcomes
  result[["base_role"]] <- as.integer(base_role)
  result[["n_outcomes"]] <- as.integer(n_outcomes)
  result[["coverage_probability"]] <- as.double(coverage_probability)
  result[["entropy"]] <- as.double(entropy)
  result[["p3"]] <- as.double(p3)
  # Tibble subsetting drops custom attributes. The caller's receipt context (the
  # filter receipt in particular) is explicit provenance, so it is re-attached
  # verbatim instead of being silently lost.
  for (attribute in setdiff(names(attributes(matches)),
                            c("names", "row.names", "class"))) {
    attr(result, attribute) <- attr(matches, attribute)
  }
  result
}
