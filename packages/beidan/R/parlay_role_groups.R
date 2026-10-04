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
#' are enforced by [parlay_select_groups()] when packages are selected.
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

# --- pattern suggestion -------------------------------------------------------

#' Suggest a group pattern from the role distribution of a ranked table
#'
#' Derives a `pattern` from the roles actually present in `ranked_selections`
#' instead of assuming a fixed quota. `pattern` is a target-role vector: round `i`
#' draws from the board of target role `pattern[i]` (see
#' [parlay_construct_role_groups()]). A quota the pool cannot fill is not neutral:
#' an unfilled target-3 round falls back to the double board and silently degrades
#' the whole group, and a target-1 round that is never declared leaves every
#' base-role-1 protected double unreachable. Matching the quota to the pool avoids
#' both.
#'
#' The rule is:
#'   * `t3` (target-3 rounds) is `min(<role-3 fixture count>, n_legs)`, so no
#'     three-outcome round is requested that the pool cannot fill with a genuine
#'     triple;
#'   * `t1` (target-1 rounds) is `min(<role-1 fixture count>, max_role1)`, so
#'     protected doubles become reachable without spending the whole pattern on
#'     them;
#'   * `t2` takes the remaining slots.
#'
#' `pattern` is returned sorted descending, which is the order
#' [parlay_construct_role_groups()] applies internally. No fitting, IO or clock is
#' involved: the result is a pure function of the role counts in the supplied
#' table.
#' @param ranked_selections Ranked tibble from [rank_outcome_selections()], carrying
#'   `fixture_id` and integer `base_role` in `1:3`. One fixture may emit several
#'   variants; only the distinct `(fixture_id, base_role)` pairs are counted, so a
#'   fixture is never counted twice through its variants.
#' @param n_legs Single positive whole number: the leg count the pattern must have,
#'   normally `settings$n_legs`.
#' @param max_role1 Single non-negative whole number, default `1`: the ceiling on
#'   target-1 rounds. `0` suppresses them entirely when base-role-1 reliability is
#'   not wanted.
#' @return A list:
#'   * `pattern` -- the suggested integer vector of length `n_legs`;
#'   * `role1`, `role2`, `role3` -- distinct fixture counts per base role;
#'   * `target3`, `target2`, `target1` -- the rounds allocated to each role;
#'   * `unused_role1` -- base-role-1 fixtures that still have no round, which is the
#'     reachability loss the ceiling accepted;
#'   * `degraded_target3` -- target-3 rounds the pool cannot fill with a genuine
#'     triple; non-zero means the pattern will fall back to the double board.
#' @section Errors:
#' `ranked_selections` is an error when it is not a tibble, when `fixture_id` or
#' `base_role` is missing, when `base_role` is not whole and within `1:3`, or when
#' a fixture carries two different base roles (its role would then be ambiguous).
#' `n_legs` and `max_role1` are errors when they are not single finite whole
#' numbers of the required sign; `max_role1` may not exceed `n_legs`.
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
#' matches <- tibble::tibble(
#'   fixture_id = c("A", "B", "C"),
#'   win = c(0.34, 0.40, 0.52), draw = c(0.33, 0.30, 0.28), lose = c(0.33, 0.30, 0.20))
#' ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
#' parlay_suggest_pattern(ranked, n_legs = 7L)$pattern
#' @export
parlay_suggest_pattern <- function(ranked_selections, n_legs, max_role1 = 1L) {
  checkmate::assert_true(tibble::is_tibble(ranked_selections),
    .var.name = "ranked_selections must be a tibble")
  missing_columns <- setdiff(c("fixture_id", "base_role"), names(ranked_selections))
  if (length(missing_columns) > 0L) {
    stop("parlay_suggest_pattern: ranked_selections is missing required column(s): ",
         paste(missing_columns, collapse = ", "))
  }
  checkmate::assert_number(n_legs, lower = 1, finite = TRUE,
    .var.name = "n_legs")
  checkmate::assert_true(n_legs == trunc(n_legs), .var.name = "n_legs must be whole")
  checkmate::assert_number(max_role1, lower = 0, finite = TRUE,
    .var.name = "max_role1")
  checkmate::assert_true(max_role1 == trunc(max_role1),
    .var.name = "max_role1 must be whole")
  checkmate::assert_true(max_role1 <= n_legs,
    .var.name = "max_role1 must not exceed n_legs")

  fixture_id <- as.character(ranked_selections$fixture_id)
  base_role <- ranked_selections$base_role
  if (!is.numeric(base_role) || is.object(base_role) || !is.null(dim(base_role)) ||
      anyNA(base_role) || any(!is.finite(base_role)) ||
      any(base_role != trunc(base_role)) || any(!base_role %in% 1:3)) {
    stop("parlay_suggest_pattern: ranked_selections$base_role must be whole and ",
         "within 1, 2 or 3")
  }
  if (any(nchar(fixture_id) == 0L)) {
    stop("parlay_suggest_pattern: ranked_selections$fixture_id must not be empty")
  }
  # One fixture must carry exactly one base role, or its role is ambiguous and the
  # count would depend on which variant happened to be read first.
  roles <- split(as.integer(base_role), fixture_id)
  ambiguous <- names(roles)[vapply(roles, function(x) length(unique(x)) != 1L, logical(1))]
  if (length(ambiguous) > 0L) {
    stop("parlay_suggest_pattern: fixture(s) carry more than one base role: ",
         paste(utils::head(ambiguous, 5L), collapse = ", "))
  }
  fixture_role <- vapply(roles, function(x) unique(x), integer(1))
  role1 <- sum(fixture_role == 1L)
  role2 <- sum(fixture_role == 2L)
  role3 <- sum(fixture_role == 3L)

  n_legs <- as.integer(n_legs)
  max_role1 <- as.integer(max_role1)
  target3 <- min(role3, n_legs)
  target1 <- min(role1, max_role1, n_legs - target3)
  target2 <- n_legs - target3 - target1
  pattern <- sort(c(rep(3L, target3), rep(2L, target2), rep(1L, target1)),
                  decreasing = TRUE)
  return(list(pattern = pattern, role1 = role1, role2 = role2, role3 = role3,
    target3 = target3, target2 = target2, target1 = target1,
    unused_role1 = max(0L, role1 - target1),
    degraded_target3 = max(0L, target3 - role3)))
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
