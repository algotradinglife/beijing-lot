# Package tests for the outcome-role ranked construction and purchase selector
# (#553 unit 3).
#
# The chain under test is the real classify -> prepare -> rank -> construct ->
# select pipeline reached only through the public entry points. The tests bind the
# OBSERVABLE contract:
#   * construction selects each round from the board named by `base_role` (always
#     listing `base_role` and `n_outcomes` with their distinct meanings), carries an
#     independent cursor per board, wraps at the tail, and records target/actual
#     boards;
#   * protective variants are selectable and never mandatory, and a fixture only
#     gets the overlap exemption when it ACTUALLY selects all three outcomes in both
#     groups;
#   * the evaluator prices every group from its own frozen masks, charges each
#     physical ticket once, and honours the budget/reuse/overlap policies.
#
# Coverage expectations are hand-computed from the fixture probabilities and the
# realized outcome counts, never from the implementation's own output.

rp_cutoff <- function(issue_id = "26098") {
  list(issue_id = issue_id,
       cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
}

rp_settings <- function(n_legs) {
  settings <- parlay_settings()
  settings$n_legs <- as.integer(n_legs)
  settings
}

# One fixture per row; `p` is the canonical win/draw/lose triple.
rp_matches <- function(ids, p) {
  p <- lapply(p, as.numeric)
  tibble::tibble(
    fixture_id = as.character(ids),
    win = vapply(p, `[[`, numeric(1), 1L),
    draw = vapply(p, `[[`, numeric(1), 2L),
    lose = vapply(p, `[[`, numeric(1), 3L))
}

rp_ranked <- function(matches, cutoff = rp_cutoff()) {
  rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
}

# `triple`  .40/.30/.30 -> base_role 3, one selection of all three outcomes.
# `double`  .50/.30/.20 -> base_role 2, one selection of top1+top2.
# `single`  .55/.23/.22 -> base_role 1 with a protected top1+top3 (p3 > .20).
rp_triple <- c(0.40, 0.30, 0.30)
rp_double <- c(0.50, 0.30, 0.20)
rp_single <- c(0.55, 0.23, 0.22)

rp_fixtures <- function(kinds) {
  ids <- sprintf("F%02d", seq_along(kinds))
  p <- lapply(kinds, function(kind) switch(kind,
    triple = rp_triple,
    double = rp_double,
    single = rp_single,
    stop("unknown kind")))
  rp_matches(ids, p)
}

rp_pool <- function(kinds, n_legs = 2L, pattern = c(3L, 2L), max_candidates = 3L,
                    prematch_sp = match_typed_empty("prematch_sp")) {
  parlay_construct_role_groups(
    rp_ranked(rp_fixtures(kinds)), rp_settings(n_legs), pattern = pattern,
    max_candidates = max_candidates, prematch_sp = prematch_sp)
}

#' Select and freeze a deterministic coverage test plan
#' @param portfolio Bound candidate pool from the test fixture.
#' @param budget_cny Total CNY cap; NULL is unlimited.
#' @param group_budget_cny Per-group CNY cap; NULL buys full support.
#' @param reuse_policy Explicit fixture reuse limit.
#' @param overlap_policy Explicit shared-fixture limit.
#' @return Frozen evaluation; missing SP keeps EV as NA, no side effects.
rp_evaluate <- function(portfolio, budget_cny = NULL, group_budget_cny = 256,
                        reuse_policy = list(max_reuse = NULL),
                        overlap_policy = list(max_overlap = NULL)) {
  return(parlay_select_groups(portfolio, objective="coverage", budget_cny = budget_cny,
                            group_budget_cny = group_budget_cny,
                            reuse_policy = reuse_policy,
                            overlap_policy = overlap_policy)$evaluation)
}

# The reference construction fixture: three true triples, three genuine doubles and
# one base-1 protected double. Its realized 3332222 space is exactly 432 tickets.
rp_reference_matches <- function() {
  rp_matches(
    c(sprintf("T%d", 1:3), sprintf("D%d", 1:3), "P1"),
    c(rep(list(rp_triple), 3), rep(list(rp_double), 3), list(rp_single)))
}

# ---------------------------------------------------------------------------
# Construction: board selection, cursors and realized outcome accounting
# ---------------------------------------------------------------------------

test_that("construction selects by base_role board and reports n_outcomes truthfully", {
  ranked <- rp_ranked(rp_reference_matches())
  settings <- rp_settings(7L)
  pool <- parlay_construct_role_groups(
    ranked, settings, pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)

  legs <- pool$role_legs
  expect_identical(nrow(legs), 7L)
  # The boards that selected each round: 3,3,3,2,2,2 then the base-1 board.
  expect_identical(as.integer(legs$base_role), c(3L, 3L, 3L, 2L, 2L, 2L, 1L))
  # n_outcomes is the REALIZED size of each chosen direction, and it need not equal
  # base_role at all: the base-1 protected double really carries two outcomes.
  expect_identical(as.integer(legs$n_outcomes), c(3L, 3L, 3L, 2L, 2L, 2L, 2L))
  expect_equal(prod(as.integer(legs$n_outcomes)), 432, tolerance = 0)
  expect_identical(prod(as.integer(legs$n_outcomes)) * 2, 864)
  # The protected double is NOT reported as a single.
  protected <- legs[legs$base_role == 1L, , drop = FALSE]
  expect_identical(nrow(protected), 1L)
  expect_identical(as.integer(protected$n_outcomes), 2L)
  expect_length(protected$allowed_outcomes[[1L]], 2L)
})

test_that("a base-1 protected double lands in the round whose target board is role 1", {
  # The single fixture is placed in round 7 (target role 1) and never upgraded: the
  # same target pattern 3332221 is realized with base_role sequence 3332221.
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  patterns <- pool$group_patterns
  expect_identical(as.integer(patterns$target_pattern[[1L]]),
                   c(3L, 3L, 3L, 2L, 2L, 2L, 1L))
  expect_identical(as.integer(patterns$actual_pattern[[1L]]),
                   c(3L, 3L, 3L, 2L, 2L, 2L, 2L))
  # No substitution is needed: every round filled its own target board.
  expect_identical(nrow(pool$substitutions), 0L)
})

test_that("a target-3 shortage falls back to a double and records the substitution", {
  # Only two true triples, so the third target-3 round must fall back to a double.
  kinds <- c("triple", "triple", "double", "double", "double")
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_fixtures(kinds)), rp_settings(3L),
    pattern = c(3, 3, 3), max_candidates = 1L)
  legs <- pool$role_legs
  expect_identical(nrow(legs), 3L)
  expect_identical(as.integer(legs$base_role), c(3L, 3L, 2L))
  expect_identical(as.integer(legs$n_outcomes), c(3L, 3L, 2L))
  subs <- pool$substitutions
  expect_identical(nrow(subs), 1L)
  expect_identical(as.integer(subs$target_role), 3L)
  expect_identical(as.integer(subs$base_role), 2L)
  expect_identical(as.integer(subs$n_outcomes), 2L)
  expect_identical(as.character(subs$reason), "target_role_shortage_board_fallback")
  # The fallback leg's mask is kept exactly: a double stays a double and is never
  # widened into a triple.
  expect_length(legs$allowed_outcomes[[3L]], 2L)
})

test_that("each board has its own continuous cursor that wraps instead of resetting", {
  # Three triples and three doubles; cohort width is the largest distinct-fixture
  # board (3). Successive cohorts must keep moving through the boards rather than
  # restarting at the head.
  kinds <- c("triple", "triple", "triple", "double", "double", "double")
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_fixtures(kinds)), rp_settings(2L),
    pattern = c(3, 2), max_candidates = 6L)
  legs <- pool$role_legs
  triples <- vapply(sort(unique(as.character(legs$group_id))), function(g) {
    as.character(legs$fixture_id[as.character(legs$group_id) == g &
                                    legs$base_role == 3L])
  }, character(1))
  # At least three distinct triple fixtures appear across the emitted groups: a
  # board that reset to its head every group could never produce all three.
  expect_gte(length(unique(triples)), 3L)
  # Every emitted group still keeps fixture uniqueness inside itself.
  for (g in unique(as.character(legs$group_id))) {
    ids <- as.character(legs$fixture_id[as.character(legs$group_id) == g])
    expect_identical(anyDuplicated(ids), 0L)
  }
})

test_that("max_candidates NULL terminates on a finite state space without duplicate groups", {
  kinds <- c("triple", "triple", "double", "double")
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_fixtures(kinds)), rp_settings(2L), pattern = c(3, 2),
    max_candidates = NULL)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
  ids <- as.character(pool$groups$group_id)
  expect_identical(anyDuplicated(ids), 0L)
  # The candidate signature covers the realized outcome combination, so no two
  # emitted groups are the same physical package.
  signatures <- vapply(seq_len(nrow(pool$groups)), function(i) {
    block <- pool$role_legs[as.character(pool$role_legs$group_id) == ids[i], ,
                            drop = FALSE]
    beidan:::.parlay_ranked_candidate_signature(block)
  }, character(1))
  expect_identical(anyDuplicated(signatures), 0L)
})

test_that("max_candidates must be a positive whole number or NULL", {
  ranked <- rp_ranked(rp_fixtures(c("triple", "double", "double")))
  settings <- rp_settings(2L)
  expect_error(parlay_construct_role_groups(ranked, settings, c(3, 2), 0L),
               "max_candidates")
  expect_error(parlay_construct_role_groups(ranked, settings, c(3, 2), -1L),
               "max_candidates")
  expect_error(parlay_construct_role_groups(ranked, settings, c(3, 2), 1.5),
               "max_candidates")
  expect_silent(parlay_construct_role_groups(ranked, settings, c(3, 2), 1L))
  expect_silent(parlay_construct_role_groups(ranked, settings, c(3, 2), NULL))
})

# ---------------------------------------------------------------------------
# Independent numeric acceptance: spaces, cost and the group cap
# ---------------------------------------------------------------------------

test_that("the reference family realizes 216/432 and the protected variant 432/864", {
  # Base 3332221: three triples (3 outcomes each), three doubles and a genuine
  # SINGLE (1 outcome) -> 3^3 * 2^3 * 1 = 216 tickets = 432 CNY.
  base_kinds <- c(rep("triple", 3), rep("double", 3), "single")
  base_matches <- rp_matches(
    c(sprintf("T%d", 1:3), sprintf("D%d", 1:3), "P1"),
    c(rep(list(rp_triple), 3), rep(list(rp_double), 3),
      list(c(0.60, 0.20, 0.20))))
  base_ranked <- rp_ranked(base_matches)
  base_pool <- parlay_construct_role_groups(
    base_ranked, rp_settings(7L), pattern = c(3, 3, 3, 2, 2, 2, 1),
    max_candidates = 1L)
  # The last round really is a genuine single: base 1 with ONE outcome.
  expect_identical(as.integer(base_pool$role_legs$n_outcomes),
                   c(3L, 3L, 3L, 2L, 2L, 2L, 1L))
  expect_equal(prod(as.integer(base_pool$role_legs$n_outcomes)), 216, tolerance = 0)

  base_eval <- rp_evaluate(base_pool, budget_cny = NULL, group_budget_cny = NULL)
  expect_identical(base_eval$summary$tickets, 216L)
  expect_equal(base_eval$summary$spent_cny, 432, tolerance = 0)
  expect_identical(base_eval$group_selection$legal_space, 216L)

  # Protected variant: the SAME target pattern but the round takes the base-1
  # protected double -> 3^3 * 2^3 * 2 = 432 tickets = 864 CNY.
  protected_pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  expect_equal(prod(as.integer(protected_pool$role_legs$n_outcomes)), 432, tolerance = 0)
  protected_eval <- rp_evaluate(protected_pool, budget_cny = NULL,
                                group_budget_cny = NULL)
  expect_identical(protected_eval$summary$tickets, 432L)
  expect_equal(protected_eval$summary$spent_cny, 864, tolerance = 0)
})

test_that("the 3333221 family realizes 324/648 and its protected variant 648/1296", {
  matches <- rp_matches(
    c(sprintf("T%d", 1:4), sprintf("D%d", 1:2), sprintf("S%d", 1:2)),
    c(rep(list(rp_triple), 4), rep(list(rp_double), 2),
      rep(list(c(0.60, 0.20, 0.20)), 2)))
  ranked <- rp_ranked(matches)
  pool <- parlay_construct_role_groups(
    ranked, rp_settings(7L), pattern = c(3, 3, 3, 3, 2, 2, 1),
    max_candidates = 1L)
  expect_identical(as.integer(pool$role_legs$n_outcomes),
                   c(3L, 3L, 3L, 3L, 2L, 2L, 1L))
  expect_equal(prod(as.integer(pool$role_legs$n_outcomes)), 324, tolerance = 0)
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = NULL)
  expect_identical(evaluation$summary$tickets, 324L)
  expect_equal(evaluation$summary$spent_cny, 648, tolerance = 0)

  # The base-1 protected double doubles the last round: 3^3 * 3^2 * 2 = 648 / 1296.
  protected_matches <- rp_matches(
    c(sprintf("T%d", 1:4), sprintf("D%d", 1:2), "P1"),
    c(rep(list(rp_triple), 4), rep(list(rp_double), 2), list(rp_single)))
  protected_pool <- parlay_construct_role_groups(
    rp_ranked(protected_matches), rp_settings(7L),
    pattern = c(3, 3, 3, 3, 2, 2, 1), max_candidates = 1L)
  expect_equal(prod(as.integer(protected_pool$role_legs$n_outcomes)), 648, tolerance = 0)
  protected_eval <- rp_evaluate(protected_pool, budget_cny = NULL,
                                group_budget_cny = NULL)
  expect_identical(protected_eval$summary$tickets, 648L)
  expect_equal(protected_eval$summary$spent_cny, 1296, tolerance = 0)
})

test_that("a group cap of 256 buys exactly 128 rank-ordered tickets", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = 256,
                            reuse_policy = list(max_reuse = 4L),
                            overlap_policy = list(max_overlap = 3L))
  expect_identical(evaluation$summary$tickets, 128L)
  expect_equal(evaluation$summary$spent_cny, 256, tolerance = 0)
  expect_identical(evaluation$group_selection$group_units, 128L)
  expect_identical(evaluation$group_selection$legal_space, 432L)
  # The 128 bought tickets are the TOP of the probability-descending ranking. The
  # comparison is against the tickets that were actually LEFT UNBOUGHT in the same
  # group: the least likely bought ticket must not be less likely than the most
  # likely unbought one. Equal probabilities are allowed (stable tie), so the bound
  # is >= with a numerical tolerance rather than a strict >.
  full <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = NULL,
                      reuse_policy = list(max_reuse = 4L),
                      overlap_policy = list(max_overlap = 3L))
  expect_identical(full$summary$tickets, 432L)
  unbought <- full$purchases[!full$purchases$ticket_id %in%
                               evaluation$purchases$ticket_id, , drop = FALSE]
  expect_identical(nrow(unbought), 432L - 128L)
  expect_gte(min(evaluation$purchases$probability),
             max(unbought$probability) - 1e-12)
  # The bought set is exactly the 128 highest-probability tickets.
  ordered <- full$purchases[order(-full$purchases$probability,
                                  full$purchases$ticket_id), , drop = FALSE]
  expect_setequal(as.character(evaluation$purchases$ticket_id),
                  as.character(ordered$ticket_id[seq_len(128L)]))
})

# ---------------------------------------------------------------------------
# Overlap and reuse: all actual fixtures count
# ---------------------------------------------------------------------------

test_that("overlap counts all shared fixtures including triples", {
  counted <- beidan:::.parlay_ranked_counted_overlap
  expect_identical(counted(c("A","C"),c("A","B")),1L)
  expect_identical(counted(c("A","B"),c("A","B")),2L)
  expect_identical(counted(character(),c("A")),0L)
})

test_that("actual triple metadata keys on n_outcomes, not on base_role", {
  # Two groups over the same fixture set where the shared fixture P1 is a base-1
  # protected double in BOTH groups: the exemption must NOT apply.
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 2L)
  # The contract's own actual-triple derivation must ignore the base-1 leg.
  block <- pool$role_legs[as.character(pool$role_legs$group_id) ==
                            pool$groups$group_id[1], , drop = FALSE]
  triples <- as.character(block$fixture_id[as.integer(block$n_outcomes) == 3L])
  expect_false("P1" %in% triples)
  expect_true(all(c("T1", "T2", "T3") %in% triples))
})

test_that("reuse admits exactly 4 and refuses 5", {
  admit <- beidan:::.parlay_ranked_admit
  admitted <- list(list(fixture_set = c("A", "B", "C", "D"), group_id = "g1",
                        triple_fixtures = character(0)))
  # A fifth appearance of A reaches the cap of 4 only: A appears once in the
  # candidate and once in the admitted group, so the total count matters.
  four <- admit(c("A"), admitted, list(max_reuse = 2L),
                list(max_overlap = NULL))
  expect_true(four$allowed)
  five <- admit(c("A"), list(
      list(fixture_set = c("A", "A2"), group_id = "g1"),
      list(fixture_set = c("A", "A3"), group_id = "g2"),
      list(fixture_set = c("A", "A4"), group_id = "g3"),
      list(fixture_set = c("A", "A5"), group_id = "g4")),
    list(max_reuse = 4L), list(max_overlap = NULL))
  expect_false(five$allowed)
  expect_identical(five$reason, "reuse_cap_exceeded")
})

test_that("a shared actual triple counts toward overlap and reuse", {
  counted <- beidan:::.parlay_ranked_counted_overlap
  admit <- beidan:::.parlay_ranked_admit
  admitted <- list(list(fixture_set = c("A", "B"), group_id = "g1",
                        triple_fixtures = "A"))
  # Overlap cap 0 refuses shared A, including when both select all outcomes.
  exempt <- admit(c("A", "C"), admitted, list(max_reuse = NULL),
                  list(max_overlap = 0L))
  expect_false(exempt$allowed)
  expect_identical(exempt$reason,"overlap_cap_exceeded")
  # Reuse still counts A, so a cap of 1 refuses it.
  reused <- admit(c("A", "C"), admitted, list(max_reuse = 1L),
                  list(max_overlap = NULL))
  expect_false(reused$allowed)
  expect_identical(reused$reason, "reuse_cap_exceeded")
  expect_identical(counted(c("A", "B"), c("A", "B")), 2L)
})

# ---------------------------------------------------------------------------
# Budget, charging and de-duplication
# ---------------------------------------------------------------------------

test_that("every physical ticket is charged exactly once", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  evaluation <- rp_evaluate(pool, budget_cny = 32, group_budget_cny = 8)
  expect_identical(anyDuplicated(evaluation$purchases$ticket_id), 0L)
  expect_equal(evaluation$summary$spent_cny,
               nrow(evaluation$purchases) * as.numeric(parlay_settings()$unit_cny),
               tolerance = 0)
  expect_lte(evaluation$summary$spent_cny, 32)
  expect_equal(evaluation$summary$unspent_cny,
               32 - evaluation$summary$spent_cny, tolerance = 1e-9)
})

test_that("an unlimited total budget reports NA unspent rather than a fake zero", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = 4)
  expect_true(is.na(evaluation$summary$unspent_cny))
})

test_that("a zero or sub-unit budget buys nothing and consumes no constraint", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  zero <- rp_evaluate(pool, budget_cny = 1, group_budget_cny = 256)
  expect_identical(zero$summary$tickets, 0L)
  expect_equal(zero$summary$spent_cny, 0, tolerance = 0)
  # A later group is not blocked by the earlier empty one: an unlimited run still
  # buys the full space.
  full <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = NULL)
  expect_identical(full$summary$tickets, 432L)
})

test_that("group_budget NULL buys the full legal support space", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = NULL)
  expect_identical(evaluation$group_selection$group_units,
                   evaluation$group_selection$legal_space)
})

# ---------------------------------------------------------------------------
# Heterogeneous actual structures and provenance
# ---------------------------------------------------------------------------

test_that("a pool with heterogeneous actual structures is evaluated, not refused", {
  # A SINGLE target pattern c(3, 1) whose cycling emits groups with genuinely
  # different realized structures at the same target: the triple round pairs with a
  # base-1 protected double (3*2 = 6 tickets) in some groups and with a base-1
  # singleton (3*1 = 3 tickets) in others. Nothing here mixes several target
  # presets: the divergence comes from the base-1 board's own cycling.
  matches <- rp_matches(
    sprintf("F%02d", 1:7),
    list(c(0.40, 0.30, 0.30),   # base-3 triple
         c(0.60, 0.20, 0.20),   # base-1 singleton (n = 1)
         c(0.55, 0.23, 0.22),   # base-1 with a protected pair (n = 2)
         c(0.54, 0.24, 0.22),   # base-1 with a protected pair (n = 2)
         rp_double, rp_double, rp_double))
  pool <- parlay_construct_role_groups(
    rp_ranked(matches), rp_settings(2L), pattern = c(3, 1), max_candidates = 6L)
  targets <- vapply(pool$group_patterns$target_pattern, paste, character(1),
                    collapse = ",")
  expect_true(all(targets == "3,1"))
  spaces <- vapply(seq_len(nrow(pool$groups)), function(i) {
    block <- pool$role_legs[as.character(pool$role_legs$group_id) ==
                              pool$groups$group_id[i], , drop = FALSE]
    prod(as.integer(block$n_outcomes))
  }, numeric(1))
  # The SAME target pattern really produced different realized spaces.
  expect_setequal(unique(spaces), c(6, 3))
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = NULL,
                            reuse_policy = list(max_reuse = 4L),
                            overlap_policy = list(max_overlap = 3L))
  # Every group is priced from its OWN realized space and the pool is funded as a
  # whole: the heterogeneous structures are neither refused nor silently dropped.
  selection <- evaluation$group_selection
  expect_setequal(unique(selection$legal_space), c(6, 3))
  expect_gt(evaluation$summary$tickets, 0L)
  expect_gt(evaluation$summary$actual_coverage, 0)
  expect_true(all(evaluation$summary$actual_coverage <= 1 + 1e-12))
})

test_that("the historical 333 target realizes 333 or 322 and both are purchasable", {
  # Only one true triple against three doubles, with a target-3 pattern of width 3:
  # the first round takes the triple and the later rounds fall back to doubles, so
  # the single pool legitimately mixes the target 333 with the actual 322.
  kinds <- c("triple", "double", "double", "double")
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_fixtures(kinds)), rp_settings(3L),
    pattern = c(3, 3, 3), max_candidates = 4L)
  expect_gt(nrow(pool$substitutions), 0L)
  target <- paste(pool$group_patterns$target_pattern[[1L]], collapse = ",")
  actual <- paste(pool$group_patterns$actual_pattern[[1L]], collapse = ",")
  expect_identical(target, "3,3,3")
  expect_identical(actual, "3,2,2")
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = 4,
                            reuse_policy = list(max_reuse = 4L),
                            overlap_policy = list(max_overlap = 3L))
  expect_gt(evaluation$summary$tickets, 0L)
  expect_true(all(evaluation$summary$actual_coverage > 0))
})

test_that("the evaluator never mutates the source portfolio", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  before <- rlang::hash(pool)
  invisible(rp_evaluate(pool, budget_cny = 32, group_budget_cny = 8))
  expect_identical(rlang::hash(pool), before)
})

test_that("the frozen plan records all-shared-fixture overlap scope", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  evaluation <- rp_evaluate(pool, budget_cny = 32, group_budget_cny = 8,
                            reuse_policy = list(max_reuse = 4L),
                            overlap_policy = list(max_overlap = 3L))
  expect_identical(evaluation$plan$policies$overlap_scope, "all_shared_fixtures")
  expect_null(evaluation$plan$policies$forced_complement)
  expect_null(evaluation$receipt$forced_complement)
  expect_identical(evaluation$receipt$overlap_scope,
                   "all_shared_fixtures")
  expect_identical(evaluation$receipt$issue_id, "26098")
})

test_that("protective variants are selectable and never forced into a pair", {
  # Two groups each carrying the SAME base-1 protected double fixture P1. Under no
  # complement obligation both may be admitted independently; nothing requires a
  # main/protect pair and no rejection mentions an unavailable complement.
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 2L)
  evaluation <- rp_evaluate(pool, budget_cny = NULL, group_budget_cny = 4,
                            reuse_policy = list(max_reuse = 2L),
                            overlap_policy = list(max_overlap = 3L))
  expect_false("complement" %in% names(evaluation))
  expect_false(any(grepl("complement", evaluation$rejections$reason)))
})

test_that("malformed inputs fail closed before any funding", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  # A tampered leg count is refused.
  broken <- pool
  broken$role_legs$n_outcomes[1] <- 9L
  expect_error(rp_evaluate(broken), "n_outcomes")
  # A tampered mask is refused.
  broken2 <- pool
  broken2$role_legs$allowed_outcomes[[1]] <- c("W")
  expect_error(rp_evaluate(broken2))
  # A retimed cutoff is refused by the embedded receipt.
  broken3 <- pool
  broken3$cutoff <- list(issue_id = "26098",
                         cutoff_utc = as.POSIXct("2026-09-26 13:00:00", tz = "UTC"))
  expect_error(rp_evaluate(broken3), "cutoff")
})

# ---------------------------------------------------------------------------
# Funding-safety regressions retained from the obsolete suite
# ---------------------------------------------------------------------------

test_that("missing pre-match SP leaves EV unavailable while coverage stays usable", {
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L)
  evaluation <- rp_evaluate(pool, budget_cny = 32, group_budget_cny = 8)
  expect_false(evaluation$summary$ev_available)
  expect_true(is.na(evaluation$summary$ev_net_cny))
  expect_gt(evaluation$summary$actual_coverage, 0)
  expect_gt(evaluation$summary$tickets, 0L)
})

test_that("a raw pre-match SP above 10 is preserved rather than replaced", {
  matches <- rp_reference_matches()
  sp <- tidyr::expand_grid(fixture_id = matches$fixture_id,
    outcome = c("W", "D", "L")) |>
    dplyr::mutate(quote_at = rp_cutoff()$cutoff_utc - 3600,
      sp_raw = 12, source_url = "synthetic://complete-SP")
  pool <- parlay_construct_role_groups(
    rp_ranked(matches), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 1L, prematch_sp = sp)
  evaluation <- rp_evaluate(pool, budget_cny = 8, group_budget_cny = 8)
  expect_gt(evaluation$summary$tickets, 0L)
  # The raw 12 survives untouched: the SP policy never replaces above 10.
  expect_equal(evaluation$purchases$sp_product_est,
    rep(12^7, nrow(evaluation$purchases)))
  expect_true(evaluation$summary$ev_available)
})

test_that("down-rank continuation buys past an already-bought ticket", {
  # Two groups that share an actual triple fixture and overlap in their bought
  # tickets: the walk must continue DOWN the rank rather than repurchase or stop.
  pool <- parlay_construct_role_groups(
    rp_ranked(rp_reference_matches()), rp_settings(7L),
    pattern = c(3, 3, 3, 2, 2, 2, 1), max_candidates = 3L)
  evaluation <- rp_evaluate(pool, budget_cny = 24, group_budget_cny = 8,
                            reuse_policy = list(max_reuse = 4L),
                            overlap_policy = list(max_overlap = 3L))
  expect_identical(anyDuplicated(evaluation$purchases$ticket_id), 0L)
  expect_gt(evaluation$summary$tickets, 0L)
  expect_equal(evaluation$summary$spent_cny,
               nrow(evaluation$purchases) * 2, tolerance = 0)
})

