# Role round-robin (#537), stage 2: shared validation and packaging helpers.
#
# The candidate-pool GENERATOR now lives in parlay_ranked_group_construction.R and
# consumes the ranked-selection table produced by rank_outcome_selections(), not the
# older all-fixtures/all-roles score table. This file keeps the helpers that other
# stages still use: settings/pattern/bound validation, the frozen pre-match SP check,
# the score-table validator used by the evaluator, and the canonical package key.
#
# Vocabulary:
#   * group_slot -- the 1-based position of a generated candidate in the output.
#   * role       -- the number of retained outcomes for a leg (1, 2 or 3).
#   * round      -- GLOBAL round index; round r fills leg r of every group.
#   * turn       -- 1-based position of a group inside one round's turn order.

# --- feasibility -------------------------------------------------------------

#' Within-group feasibility of one fixture
#'
#' Internal. Generation only forbids a duplicate fixture INSIDE the group being
#' built. Cross-group reuse and overlap are explicitly allowed at this stage: they
#' are enforced by [parlay_evaluate_portfolio()] when packages are selected.
#' @param fixture_id Single fixture identifier under test.
#' @param set Fixtures already assigned to THIS group, partial or complete.
#' @return A list(feasible, reason). `reason` is `""` when feasible and otherwise
#'   `duplicate_fixture_in_group`.
#' @noRd
.parlay_role_feasible <- function(fixture_id, set) {
  if (fixture_id %in% set) {
    return(list(feasible = FALSE, reason = "duplicate_fixture_in_group"))
  }
  list(feasible = TRUE, reason = "")
}

# --- validation --------------------------------------------------------------

#' Validate a role planning settings snapshot
#'
#' Internal. Reuses the authoritative session-settings validator so a role plan is
#' driven by exactly the parameter block the rest of the pipeline consumes.
#' @param settings Complete settings snapshot, normally from [parlay_settings()].
#' @return `TRUE` invisibly; an invalid snapshot raises an error.
#' @noRd
.parlay_role_validate_settings <- function(settings) {
  parlay_validate_settings(settings)
  invisible(TRUE)
}

#' Validate the structural pattern
#'
#' Internal. The pattern is one integer 1..3 per leg in leg order; its length must
#' equal the plan width.
#' @param pattern Candidate integer vector.
#' @param n_legs Plan width the pattern must match.
#' @return The pattern as an integer vector; a wrong length, a non-whole value or a
#'   value outside 1..3 raises an error.
#' @noRd
.parlay_role_validate_pattern <- function(pattern, n_legs) {
  if (!is.numeric(pattern) || is.object(pattern) || !is.null(dim(pattern)) ||
      length(pattern) != n_legs || anyNA(pattern) ||
      any(!is.finite(pattern)) || any(pattern != trunc(pattern)) ||
      any(pattern < 1) || any(pattern > 3)) {
    stop("parlay_construct_role_groups: pattern must be ", n_legs,
         " whole numbers drawn from 1, 2, 3")
  }
  as.integer(pattern)
}

#' Validate the emitted-candidate ceiling
#'
#' Internal. `max_candidates` is either `NULL`, meaning the caller sets no ceiling
#' and the deterministic trajectory runs to its own termination, or a single
#' positive whole number: the maximum number of UNIQUE COMPLETE candidate groups to
#' emit. It bounds emitted groups rather than attempted slots, and it is never a
#' budget-derived count. A non-positive, non-whole, infinite, empty, vector-valued or
#' non-numeric value errors, as does a whole number above `.Machine$integer.max`
#' that the returned integer ceiling cannot represent: the bound is rejected before
#' conversion rather than silently becoming `NA`.
#' @param max_candidates `NULL` or a single positive whole number.
#' @return `NULL` or `max_candidates` as an integer.
#' @noRd
.parlay_role_validate_max_candidates <- function(max_candidates) {
  if (is.null(max_candidates)) return(NULL)
  if (!is.numeric(max_candidates) || is.object(max_candidates) ||
      !is.null(dim(max_candidates)) || length(max_candidates) != 1L ||
      is.na(max_candidates) || !is.finite(max_candidates) ||
      max_candidates != trunc(max_candidates) || max_candidates < 1) {
    stop("parlay_construct_role_groups: max_candidates must be NULL or a single ",
         "positive whole number")
  }
  if (max_candidates > .Machine$integer.max) {
    stop("parlay_construct_role_groups: max_candidates must not exceed ",
         format(.Machine$integer.max, scientific = FALSE),
         "; a larger ceiling cannot be represented as an integer")
  }
  as.integer(max_candidates)
}

#' Validate the frozen pre-match SP carried by a candidate pool
#'
#' Internal. The SP table is schema-validated and every quote must be STRICTLY
#' before the decision cutoff: a quote at or after the cutoff was not visible to the
#' decision and must not enter the frozen pool. An empty table is the explicit
#' historical "SP missing" state and is allowed here; whether EV is available is
#' decided downstream by [parlay_value_tickets()].
#' @param prematch_sp Candidate SP tibble.
#' @param cutoff Explicit decision cutoff with `cutoff_utc`.
#' @return The validated SP tibble.
#' @noRd
.parlay_role_validate_prematch_sp <- function(prematch_sp, cutoff) {
  prematch_sp <- match_validate_table(prematch_sp, "prematch_sp")
  if (nrow(prematch_sp)) {
    if (anyNA(prematch_sp$quote_at)) {
      stop("parlay_construct_role_groups: prematch_sp$quote_at must not be missing")
    }
    if (any(prematch_sp$quote_at >= cutoff$cutoff_utc)) {
      stop("parlay_construct_role_groups: prematch_sp quotes must be strictly ",
           "before the cutoff; a quote at or after the decision instant would leak ",
           "future information into the frozen pool")
    }
  }
  prematch_sp
}

#' Validate a role score table against the authoritative probabilities
#'
#' Internal. The table may come from [parlay_role_scores()] or from a caller, but its
#' columns and its score/rank/retained values are re-derived from `probabilities`, so
#' a tampered score or rank cannot steer the plan and attributes are never trusted
#' alone. Kept for the evaluator, which still re-validates a `scores` block.
#' @param role_scores Candidate tibble with `fixture_id`, `role`, `score`, `rank`,
#'   `retained_probability` and `allowed_outcomes`.
#' @param probabilities Authoritative probability tibble the scores must agree with.
#' @return `TRUE` invisibly; a missing column, an unpriced fixture/role, or a score,
#'   retained mass or rank that disagrees with the probabilities raises an error.
#' @noRd
.parlay_role_validate_scores <- function(role_scores, probabilities) {
  if (is.null(role_scores) || !is.data.frame(role_scores)) {
    stop("parlay_construct_role_groups: role_scores must be a role score tibble")
  }
  required <- c("fixture_id", "role", "score", "rank", "retained_probability",
                "allowed_outcomes")
  checkmate::assert_names(names(role_scores), must.include = required,
                          .var.name = "names(role_scores)")
  checkmate::assert_character(role_scores$fixture_id, any.missing = FALSE,
                              min.chars = 1, .var.name = "role_scores$fixture_id")
  checkmate::assert_integerish(role_scores$role, any.missing = FALSE,
                               .var.name = "role_scores$role")
  if (any(!role_scores$role %in% 1:3)) {
    stop("parlay_construct_role_groups: role_scores$role must be 1, 2 or 3")
  }
  checkmate::assert_numeric(role_scores$score, any.missing = FALSE, finite = TRUE,
                            .var.name = "role_scores$score")
  checkmate::assert_integerish(role_scores$rank, any.missing = FALSE,
                               .var.name = "role_scores$rank")
  expected <- parlay_role_scores(probabilities,
                                 list(issue_id = "validation",
                                      cutoff_utc = as.POSIXct(0, origin = "1970-01-01",
                                                              tz = "UTC")))
  # Require exactly the authoritative fixture/role grid, including masks and ranks.
  key <- function(x) paste(x$fixture_id, x$role)
  expected_key <- key(expected)
  if (anyDuplicated(key(role_scores)) || !setequal(key(role_scores), expected_key)) {
    stop("role_scores must contain each fixture/role exactly once")
  }
  checkmate::assert_numeric(role_scores$retained_probability, any.missing=FALSE, finite=TRUE)
  position <- match(key(role_scores), expected_key)
  if (anyNA(position)) {
    stop("parlay_construct_role_groups: role_scores names a fixture/role that the ",
         "supplied probabilities do not price")
  }
  if (!identical(unname(role_scores$allowed_outcomes), unname(expected$allowed_outcomes[position]))) {
    stop("role_scores allowed_outcomes disagree with authoritative role masks")
  }
  if (any(abs(role_scores$score - expected$score[position]) > 1e-12) ||
      any(abs(role_scores$retained_probability -
              expected$retained_probability[position]) > 1e-12) ||
      any(role_scores$rank != expected$rank[position])) {
    stop("parlay_construct_role_groups: role_scores disagree with the authoritative ",
         "probabilities; re-derive them with parlay_role_scores() instead of ",
         "trusting mutable attributes")
  }
  invisible(TRUE)
}

#' Canonical de-duplication key of a candidate package
#'
#' Internal. The key is the SORTED set of `(fixture_id, role, mask)` tuples and it
#' deliberately contains NO group slot, rank offset or round order: two candidates
#' that buy the same physical package under the same roles and masks from the same
#' admitted fixtures are the same package and only one may enter the pool. The mask
#' participates because the same fixture under a different role OR a different
#' complementary direction is a different leg.
#' @param block Leg rows of one candidate (group_slot, fixture_id, role,
#'   allowed_outcomes).
#' @return A single character key.
#' @noRd
.parlay_role_package_key <- function(block) {
  if (!nrow(block)) return(NA_character_)
  tuples <- vapply(seq_len(nrow(block)), function(i) {
    mask <- paste(sort(as.character(block$allowed_outcomes[[i]])), collapse = "+")
    paste(as.character(block$fixture_id[i]), as.integer(block$role[i]), mask,
          sep = ":")
  }, character(1))
  paste(sort(tuples), collapse = "|")
}
