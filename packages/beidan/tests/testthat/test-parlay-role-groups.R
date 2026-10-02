# Package tests for the ranked-selection role candidate-pool stage
# (parlay_construct_role_groups), its fixed-cohort round-robin trajectory, its
# generational termination and its triple-shortage double fallback. The pool is
# exercised through the real classify -> prepare -> rank -> construct chain and only
# through the public entry point.

rc_cutoff <- function(issue_id = "26098") {
  list(issue_id = issue_id,
       cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
}

rc_settings <- function(n_legs) {
  settings <- parlay_settings()
  settings$n_legs <- as.integer(n_legs)
  settings
}

# One fixture per row; `p` is the canonical win/draw/lose triple.
rc_matches <- function(ids, p) {
  p <- lapply(p, as.numeric)
  tibble::tibble(
    fixture_id = as.character(ids),
    win = vapply(p, `[[`, numeric(1), 1L),
    draw = vapply(p, `[[`, numeric(1), 2L),
    lose = vapply(p, `[[`, numeric(1), 3L))
}

rc_triple <- c(0.40, 0.30, 0.30)
rc_double <- c(0.50, 0.30, 0.20)
rc_double_pair <- c(0.50, 0.21, 0.29)

rc_ranked <- function(matches, cutoff = rc_cutoff()) {
  rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
}

rc_fixtures <- function(kinds) {
  n <- length(kinds)
  ids <- sprintf("F%02d", seq_len(n))
  p <- lapply(kinds, function(kind) switch(kind,
    triple = rc_triple,
    double = rc_double,
    double_pair = rc_double_pair,
    stop("unknown kind")))
  # Identical probabilities are fine: ranks tie-break deterministically by fixture_id.
  rc_matches(ids, p)
}

rc_actual_pattern <- function(pool, slot) {
  unlist(pool$group_patterns$actual_pattern[[slot]])
}

rc_pattern_3332222 <- c(3L, 3L, 3L, 2L, 2L, 2L, 2L)

test_that("triple shortage falls back to a double with the real actual pattern", {
  matches <- rc_fixtures(c("triple", "triple", rep("double", 5)))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 1L)
  legs <- pool$role_legs
  expect_identical(nrow(legs), 7L)
  expect_identical(anyDuplicated(legs$fixture_id), 0L)
  # Two triples, then one substitution to a double, then four ordinary doubles.
  expect_identical(rc_actual_pattern(pool, 1L),
                   c(3L, 3L, 2L, 2L, 2L, 2L, 2L))
  expect_identical(legs$base_role, c(3L, 3L, 2L, 2L, 2L, 2L, 2L))
  expect_identical(nrow(pool$substitutions), 1L)
  expect_identical(unique(pool$substitutions$target_role), 3L)
  expect_identical(unique(pool$substitutions$base_role), 2L)
  expect_identical(unique(pool$substitutions$reason),
                   "target_role_shortage_board_fallback")
  # Both triples are consumed before the first fallback; the fallback happens in
  # round 3 once no unused triple is left.
  expect_identical(pool$substitutions$round[[1]], 3L)
  # Support of the physical package is 3^2 * 2^5.
  expect_identical(prod(lengths(legs$allowed_outcomes)), 288)
  expect_true(all(pool$groups$complete))
  # The target pattern stays the audit pattern and is never rewritten.
  expect_identical(pool$pattern, rc_pattern_3332222)
  expect_identical(unlist(pool$group_patterns$target_pattern[[1]]),
                   rc_pattern_3332222)
})

test_that("no triples makes every round fall back to a double", {
  matches <- rc_fixtures(rep("double", 7))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 1L)
  expect_identical(rc_actual_pattern(pool, 1L), rep(2L, 7))
  expect_identical(anyDuplicated(pool$role_legs$fixture_id), 0L)
  expect_identical(nrow(pool$substitutions), 3L)
  expect_identical(prod(lengths(pool$role_legs$allowed_outcomes)), 128)
})

test_that("enough triples need no substitution", {
  matches <- rc_fixtures(c(rep("triple", 4), rep("double", 4)))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 1L)
  expect_identical(rc_actual_pattern(pool, 1L), rc_pattern_3332222)
  expect_identical(nrow(pool$substitutions), 0L)
  expect_identical(pool$role_legs$base_role, rc_pattern_3332222)
})

test_that("a triple already used in the group is not duplicated", {
  matches <- rc_fixtures(c("triple", rep("double", 6)))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 1L)
  expect_identical(anyDuplicated(pool$role_legs$fixture_id), 0L)
  expect_identical(pool$role_legs$base_role[[1]], 3L)
  expect_identical(sum(pool$role_legs$base_role == 3L), 1L)
  expect_identical(nrow(pool$substitutions), 2L)
})

test_that("complementary directions are consumed in the first queue cycle", {
  matches <- rc_matches("P", list(rc_double_pair))
  fitted <- rc_ranked(matches)
  # One round, two groups: the paired directions of fixture P become the two legs.
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(1L), pattern = 2L, max_candidates = 2L)
  legs <- pool$role_legs[order(pool$role_legs$group_slot), , drop = FALSE]
  expect_identical(nrow(legs), 2L)
  expect_true(all(legs$fixture_id == "P"))
  masks <- lapply(legs$allowed_outcomes, as.character)
  expect_identical(masks[[1]], c("W", "L"))
  expect_identical(masks[[2]], c("W", "D"))
  # The chosen row's own mass is preserved, not an averaged or upgraded mask.
  expect_equal(legs$retained_probability[[1]], 0.50 + 0.29, tolerance = 1e-12)
  expect_equal(legs$retained_probability[[2]], 0.50 + 0.21, tolerance = 1e-12)
  # Same fixture set, DIFFERENT directions => different packages, so both survive.
  expect_identical(sum(pool$groups$complete), 2L)
  expect_identical(pool$generation_status$generated_count, 2L)
})

test_that("cohorts use a fixed snake round-robin independent of the ceiling", {
  matches <- rc_fixtures(c(rep("triple", 12), rep("double", 12)))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 3L)
  width <- pool$generation_status$cohort_width
  expect_identical(width, 12L)
  selected <- pool$trace[pool$trace$action == "selected", , drop = FALSE]
  # The whole cohort is built: every round turns `width` slots, numbered 1..width in
  # the turn order, and the first cohort starts on the forward (phase 0) direction.
  expect_identical(selected$round, rep(1:7, each = width))
  expect_identical(selected$turn, rep(seq_len(width), times = 7L))
  expect_identical(selected$role, rep(c(3L, 3L, 3L, 2L, 2L, 2L, 2L),
                                      each = width))
  # Only emitted slots carry a stable id; the rest are audited with NA.
  emitted_turns <- selected[!is.na(selected$group_slot), , drop = FALSE]
  expect_identical(sort(unique(emitted_turns$group_slot)), 1:3)
  expect_identical(sort(unique(emitted_turns$turn)),
                   c(1L, 2L, 3L, 10L, 11L, 12L))
  expect_true(all(pool$groups$complete))
  # Deterministic ties: a second run reproduces the legs and pattern exactly.
  again <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 3L)
  expect_identical(pool$role_legs, again$role_legs)
  expect_identical(pool$group_patterns, again$group_patterns)
  expect_identical(pool$generation_status, again$generation_status)
})

test_that("identical physical packages are de-duplicated", {
  matches <- rc_matches("S", list(rc_double))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(1L), pattern = 2L, max_candidates = 3L)
  # Only one distinct package exists; the repeat is reported, not emitted.
  expect_identical(sum(pool$groups$complete), 1L)
  expect_identical(nrow(pool$role_legs), 1L)
  expect_true(any(pool$shortages$reason == "duplicate_candidate_package"))
  expect_identical(pool$generation_status$generated_count, 1L)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
})

test_that("too few distinct fixtures stop with insufficient_fixtures", {
  matches <- rc_matches("S", list(rc_double))
  fitted <- rc_ranked(matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 1L)
  expect_identical(pool$generation_status$stop_reason, "insufficient_fixtures")
  expect_identical(pool$generation_status$generated_count, 0L)
  expect_identical(nrow(pool$groups), 0L)
  expect_identical(nrow(pool$role_legs), 0L)
  expect_identical(nrow(pool$shortages), 0L)
})

test_that("a target-1 round selects from the base-role-1 board", {
  # Role 1 IS a real board: a target-1 round takes the next unused single (or its
  # protected double) instead of stopping. No anchor is invented and nothing is
  # upgraded to a higher board.
  matches <- rc_fixtures(c("double", "double"))
  singles <- rc_matches(c("S1", "S2"),
                        list(c(0.60, 0.20, 0.20), c(0.60, 0.20, 0.20)))
  fitted <- rc_ranked(rbind(matches, singles))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(1L, 2L), max_candidates = 1L)
  expect_identical(pool$generation_status$generated_count, 1L)
  # Rounds are ordered by the pattern sorted descending, so round 1 is target 2 and
  # round 2 is the role-1 board.
  expect_identical(as.integer(pool$role_legs$round), c(1L, 2L))
  expect_identical(as.integer(pool$role_legs$base_role), c(2L, 1L))
  expect_true(any(pool$role_legs$base_role == 1L))
  expect_identical(as.integer(pool$role_legs$n_outcomes[2L]), 1L)
})

test_that("an empty ranked table returns a typed-empty pool", {
  empty_matches <- rc_matches(character(0), list())
  fitted <- rc_ranked(empty_matches)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 3L)
  expect_identical(pool$generation_status$stop_reason, "empty_inputs")
  expect_identical(pool$generation_status$generated_count, 0L)
  expect_identical(nrow(pool$groups), 0L)
  expect_identical(nrow(pool$role_legs), 0L)
  expect_identical(nrow(pool$group_patterns), 0L)
  expect_identical(nrow(pool$substitutions), 0L)
  expect_identical(names(pool$role_legs),
                   c("group_slot", "group_id", "fixture_id", "selection_id",
                     "round", "base_role", "n_outcomes", "allowed_outcomes",
                     "retained_probability"))
  expect_identical(names(pool$group_patterns),
                   c("group_slot", "group_id", "target_pattern", "actual_pattern"))
  expect_identical(names(pool$substitutions),
                   c("group_slot", "group_id", "round", "fixture_id",
                     "selection_id", "target_role", "base_role", "n_outcomes",
                     "reason"))
  expect_identical(names(pool$generation_status),
                   c("generated_count", "stop_reason", "max_candidates",
                     "cohort_width", "attempted_count"))
})

test_that("the derived probabilities and provenance are frozen explicitly", {
  matches <- rc_fixtures(c("triple", rep("double", 3)))
  cutoff <- rc_cutoff()
  fitted <- rc_ranked(matches, cutoff)
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(4L), pattern = c(3L, 2L, 2L, 2L), max_candidates = 1L)
  expect_identical(pool$cutoff, cutoff)
  expect_identical(pool$pattern, c(3L, 2L, 2L, 2L))
  expect_identical(pool$ranked_selections, fitted)
  expect_identical(pool$ranked_selections_hash, rlang::hash(fitted))
  expect_identical(pool$probability_hash, rlang::hash(pool$probabilities))
  expect_identical(names(pool$probabilities),
                   c("fixture_id", "outcome", "probability"))
  expect_true(all(pool$probabilities$outcome %in% c("W", "D", "L")))
  expect_identical(pool$prematch_sp, match_typed_empty("prematch_sp"))
  expect_identical(pool$prematch_sp_hash, rlang::hash(pool$prematch_sp))
  expect_identical(pool$cutoff_hash,
                   rlang::hash(list(as.character(cutoff$issue_id),
                                    as.numeric(cutoff$cutoff_utc))))
})

test_that("the pool freezes a strictly pre-cutoff SP table and rejects leakage", {
  matches <- rc_fixtures(c("double", "double", "double"))
  cutoff <- rc_cutoff()
  fitted <- rc_ranked(matches, cutoff)
  sp <- tibble::tibble(
    fixture_id = matches$fixture_id, outcome = "W",
    quote_at = cutoff$cutoff_utc - 60, sp_raw = 12, source_url = "test")
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 1L,
    prematch_sp = sp)
  expect_identical(pool$prematch_sp, sp)
  at_cutoff <- sp
  at_cutoff$quote_at <- cutoff$cutoff_utc
  expect_error(parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 1L,
    prematch_sp = at_cutoff), "strictly")
})

test_that("settings, pattern and candidate-ceiling validation fail closed", {
  fitted <- rc_ranked(rc_fixtures(c("double", "double")))
  expect_error(parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 1L, 3L), max_candidates = 1L), "pattern")
  expect_error(parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(0L, 1L), max_candidates = 1L), "pattern")
  expect_error(parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 0L),
    "max_candidates")
  expect_error(parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 1.5),
    "max_candidates")
})

test_that("max_candidates rejects every non-NULL non-positive-integer form", {
  fitted <- rc_ranked(rc_fixtures(c("double", "double")))
  settings <- rc_settings(2L)
  pattern <- c(2L, 2L)
  for (bad in list(0L, -1L, 1.5, -0.5, Inf, -Inf, c(1L, 2L), "2", TRUE, NA_integer_,
                   numeric(0))) {
    expect_error(parlay_construct_role_groups(
      fitted, settings, pattern, max_candidates = bad), "max_candidates")
  }
  # NULL is the explicit no-ceiling default and produces a valid pool.
  pool <- parlay_construct_role_groups(fitted, settings, pattern,
                                       max_candidates = NULL)
  expect_null(pool$generation_status$max_candidates)
  expect_true(pool$generation_status$generated_count >= 0L)
})

test_that("the obsolete n_candidates parameter is rejected", {
  fitted <- rc_ranked(rc_fixtures(c("double", "double")))
  expect_error(parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(2L, 2L), n_candidates = 2L),
    "unused argument")
})

test_that("max NULL terminates on degenerate finite queues", {
  # A single fixture under a one-leg role-2 pattern yields exactly one distinct
  # physical package, then the generation state repeats.
  fitted <- rc_ranked(rc_matches("S", list(rc_double)))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(1L), pattern = 2L, max_candidates = NULL)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
  expect_identical(pool$generation_status$generated_count, 1L)

  # A role-3 pattern with no triples terminates through the fallback and repeated
  # doubles rather than looping.
  fitted2 <- rc_ranked(rc_matches("S", list(rc_double)))
  pool2 <- parlay_construct_role_groups(
    fitted2, rc_settings(1L), pattern = 3L, max_candidates = NULL)
  expect_identical(pool2$generation_status$stop_reason, "state_repeated")
  expect_true(pool2$generation_status$generated_count >= 1L)
})

test_that("positive ceilings emit prefixes of the NULL trajectory", {
  fitted <- rc_ranked(rc_fixtures(c(rep("triple", 12), rep("double", 12))))
  settings <- rc_settings(7L)
  full <- parlay_construct_role_groups(fitted, settings,
                                       pattern = rc_pattern_3332222,
                                       max_candidates = NULL)
  expect_identical(full$generation_status$stop_reason, "state_repeated")
  expect_gt(full$generation_status$generated_count, 3L)
  for (ceiling in 1:3) {
    capped <- parlay_construct_role_groups(fitted, settings,
                                           pattern = rc_pattern_3332222,
                                           max_candidates = ceiling)
    expect_identical(capped$generation_status$stop_reason, "max_candidates")
    expect_identical(capped$generation_status$generated_count, as.integer(ceiling))
    # Same group ids, same legs, same masks, same actual patterns as the prefix.
    expect_identical(capped$groups$group_id,
                     full$groups$group_id[seq_len(ceiling)])
    keep <- full$role_legs$group_slot <= ceiling
    expect_identical(capped$role_legs$fixture_id, full$role_legs$fixture_id[keep])
    expect_identical(capped$role_legs$base_role, full$role_legs$base_role[keep])
    expect_identical(lapply(capped$role_legs$allowed_outcomes, as.character),
                     lapply(full$role_legs$allowed_outcomes[keep], as.character))
    expect_identical(lapply(capped$group_patterns$actual_pattern, unlist),
                     lapply(full$group_patterns$actual_pattern[seq_len(ceiling)],
                            unlist))
    # Same initial cohort layout as NULL: identical cohort width and turn traces.
    expect_identical(capped$generation_status$cohort_width,
                     full$generation_status$cohort_width)
  }
})

test_that("a bigger positive ceiling reproduces the whole NULL cycle", {
  fitted <- rc_ranked(rc_fixtures(c(rep("triple", 12), rep("double", 12))))
  settings <- rc_settings(7L)
  full <- parlay_construct_role_groups(fitted, settings,
                                       pattern = rc_pattern_3332222,
                                       max_candidates = NULL)
  huge <- parlay_construct_role_groups(fitted, settings,
                                       pattern = rc_pattern_3332222,
                                       max_candidates = 100000L)
  # The ceiling is far above the trajectory length, so it must NOT act as a limit:
  # the full state_repeated cycle is produced with identical group identities.
  expect_identical(huge$generation_status$stop_reason, "state_repeated")
  expect_identical(huge$groups$group_id, full$groups$group_id)
  expect_identical(huge$role_legs, full$role_legs)
  expect_identical(huge$group_patterns, full$group_patterns)
  expect_identical(huge$generation_status$generated_count,
                   full$generation_status$generated_count)
})

test_that("the ceiling counts unique complete groups only, not attempts", {
  # Two distinct fixtures with a two-leg role-2 pattern can produce several unique
  # packages, but duplicates and incomplete slots must never count toward the cap.
  fitted <- rc_ranked(rc_fixtures(c("double", "double", "double", "double")))
  settings <- rc_settings(2L)
  pool <- parlay_construct_role_groups(fitted, settings, pattern = c(2L, 2L),
                                       max_candidates = 2L)
  expect_identical(pool$generation_status$generated_count, 2L)
  expect_identical(sum(pool$groups$complete), 2L)
  expect_identical(nrow(pool$groups), 2L)
  expect_identical(pool$generation_status$attempted_count > 1L, TRUE)
  expect_identical(nrow(pool$role_legs) %% 2L, 0L)
})

test_that("group ids are stable, unique and bind the canonical mask and cutoff", {
  fitted <- rc_ranked(rc_matches("P", list(rc_double_pair)))
  cutoff <- rc_cutoff()
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(1L), pattern = 2L, max_candidates = 2L)
  ids <- pool$groups$group_id
  expect_identical(anyDuplicated(ids), 0L)
  expect_true(all(grepl("@", ids, fixed = TRUE)))
  expect_true(all(grepl(as.character(as.numeric(cutoff$cutoff_utc)), ids,
                        fixed = TRUE)))
  # Both complementary packages share the fixture identity prefix but differ in the
  # canonical mask hash, so the two ids are distinct.
  prefixes <- sub("@.*$", "", ids)
  expect_identical(length(unique(prefixes)), 1L)
  expect_identical(pool$role_legs$group_id,
                   ids[match(pool$role_legs$group_slot, pool$groups$group_slot)])
})

test_that("the audit tables are remapped onto the stable emitted slots", {
  fitted <- rc_ranked(rc_fixtures(c("triple", rep("double", 6))))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(7L), pattern = rc_pattern_3332222, max_candidates = 1L)
  expect_identical(sort(unique(pool$role_legs$group_slot)), 1L)
  expect_identical(sort(unique(pool$group_patterns$group_slot)), 1L)
  expect_identical(pool$generation_status$generated_count, 1L)
  if (nrow(pool$substitutions)) {
    expect_true(all(pool$substitutions$group_slot %in% pool$groups$group_slot))
    expect_identical(pool$substitutions$group_id,
                     pool$groups$group_id[match(pool$substitutions$group_slot,
                                                pool$groups$group_slot)])
  }
  # The actual pattern records the real roles in round order, substitutions included.
  expect_identical(rc_actual_pattern(pool, 1L), c(3L, 2L, 2L, 2L, 2L, 2L, 2L))
})

test_that("a tampered or missing receipt is refused, not obeyed", {
  fitted <- rc_ranked(rc_fixtures(c("triple", rep("double", 5))))
  settings <- rc_settings(7L)
  pattern <- rc_pattern_3332222

  missing_cutoff <- fitted
  attr(missing_cutoff, "cutoff") <- NULL
  expect_error(parlay_construct_role_groups(
    missing_cutoff, settings, pattern, 1L), "cutoff")

  missing_rank <- fitted[, setdiff(names(fitted), "rank"), drop = FALSE]
  expect_error(parlay_construct_role_groups(
    missing_rank, settings, pattern, 1L), "rank")

  tampered_rank <- fitted
  tampered_rank$rank[[1]] <- 99L
  expect_error(parlay_construct_role_groups(
    tampered_rank, settings, pattern, 1L), "rank")

  tampered_metric <- fitted
  tampered_metric$coverage_probability[[1]] <- tampered_metric$coverage_probability[[1]] + 1
  expect_error(parlay_construct_role_groups(
    tampered_metric, settings, pattern, 1L), "receipt")

  tampered_probability <- fitted
  tampered_probability$win[[1]] <- 0.99
  expect_error(parlay_construct_role_groups(
    tampered_probability, settings, pattern, 1L), "receipt")

  missing_code <- fitted
  attr(missing_code, "code_hash") <- NULL
  expect_error(parlay_construct_role_groups(
    missing_code, settings, pattern, 1L), "receipt")

  malformed_input <- fitted
  attr(malformed_input, "input_hash") <- "deadbeef"
  expect_error(parlay_construct_role_groups(
    malformed_input, settings, pattern, 1L), "receipt")
})

# --- regressions: generational termination, substitution scope, receipt binding ---

test_that("a retimed or swapped cutoff receipt is refused before recomputation", {
  # The rank receipt freezes the cutoff identity AND instant with the pool's own
  # authoritative scheme. Retiming the `cutoff` attribute alone must fail closed,
  # because the ranking columns do not depend on it and neither `input_hash` nor
  # `code_hash` carries it. The constructor is exercised with settings that carry
  # NO cutoff, so nothing else can mask the defect.
  matches <- rc_fixtures(c("triple", rep("double", 3)))
  cutoff <- rc_cutoff()
  fitted <- rc_ranked(matches, cutoff)
  settings <- rc_settings(4L)
  pattern <- c(3L, 2L, 2L, 2L)
  expect_null(settings$cutoff)

  expect_identical(attr(fitted, "cutoff_hash"),
                   rlang::hash(list(as.character(cutoff$issue_id),
                                    as.numeric(cutoff$cutoff_utc))))
  expect_silent(parlay_construct_role_groups(
    fitted, settings, pattern, max_candidates = 1L))

  # Retimed instant: the cutoff is valid and the ranking rows are unchanged.
  retimed_instant <- fitted
  attr(retimed_instant, "cutoff") <- list(
    issue_id = "26098",
    cutoff_utc = as.POSIXct("2026-09-26 13:30:00", tz = "UTC"))
  expect_error(parlay_construct_role_groups(
    retimed_instant, settings, pattern, 1L), "cutoff_hash")

  # Retimed issue: likewise a valid cutoff the ranking was never built for.
  retimed_issue <- fitted
  attr(retimed_issue, "cutoff") <- rc_cutoff("26099")
  expect_error(parlay_construct_role_groups(
    retimed_issue, settings, pattern, 1L), "cutoff_hash")

  # A missing receipt is refused rather than inferred from the carried cutoff.
  missing_receipt <- fitted
  attr(missing_receipt, "cutoff_hash") <- NULL
  expect_error(parlay_construct_role_groups(
    missing_receipt, settings, pattern, 1L), "cutoff_hash")

  # A malformed receipt is refused, not truncated or coerced.
  malformed_receipt <- fitted
  attr(malformed_receipt, "cutoff_hash") <- "deadbeef"
  expect_error(parlay_construct_role_groups(
    malformed_receipt, settings, pattern, 1L), "cutoff_hash")

  # A swapped cutoff receipt (another valid ranking's hash) is refused.
  other_receipt <- fitted
  attr(other_receipt, "cutoff_hash") <-
    attr(rc_ranked(matches, rc_cutoff("26099")), "cutoff_hash")
  expect_error(parlay_construct_role_groups(
    other_receipt, settings, pattern, 1L), "cutoff_hash")

  # Only a fresh rank function call rebuilds the receipt: the ranking rebuilt for
  # the retimed cutoff is accepted on its own terms and freezes that cutoff.
  retimed_cutoff <- attr(retimed_issue, "cutoff")
  rebuilt <- rank_outcome_selections(attr(fitted, "input_snapshot"), retimed_cutoff)
  pool <- parlay_construct_role_groups(
    rebuilt, settings, pattern, max_candidates = 1L)
  expect_identical(pool$cutoff, retimed_cutoff)
  expect_identical(pool$cutoff_hash, attr(rebuilt, "cutoff_hash"))
})

test_that("an empty ranking's cutoff receipt is verified too", {
  # Empty ranked inputs reach `empty_inputs` only AFTER the receipt is verified, so
  # a retimed cutoff on an empty ranking must still fail closed even though no
  # group could ever be built from it.
  empty <- prepare_outcome_selections(tibble::tibble(
    fixture_id = character(0), win = numeric(0),
    draw = numeric(0), lose = numeric(0)))
  settings <- rc_settings(2L)
  pattern <- c(2L, 2L)
  expect_null(settings$cutoff)

  fitted <- rank_outcome_selections(empty, rc_cutoff())
  expect_identical(
    parlay_construct_role_groups(fitted, settings, pattern, 1L)$generation_status$stop_reason,
    "empty_inputs")

  retimed <- fitted
  attr(retimed, "cutoff") <- rc_cutoff("26099")
  expect_error(parlay_construct_role_groups(
    retimed, settings, pattern, 1L), "cutoff_hash")

  missing_receipt <- fitted
  attr(missing_receipt, "cutoff_hash") <- NULL
  expect_error(parlay_construct_role_groups(
    missing_receipt, settings, pattern, 1L), "cutoff_hash")
})

test_that("a no-emission cohort does not terminate before the start state repeats", {
  # Four triples under a role-2 pattern: no role-2 queue exists, so no cohort can
  # emit anything, but the cursors still walk. The generator must NOT stop merely
  # because the first cohort emitted nothing; it stops only once a cohort would
  # START from an already-seen cursor-plus-phase state.
  fitted <- rc_ranked(rc_fixtures(rep("triple", 4)))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(1L), pattern = 2L, max_candidates = NULL)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
  expect_identical(pool$generation_status$generated_count, 0L)
  # Two full width-4 cohorts ran before the start state repeated, not one.
  expect_identical(pool$generation_status$cohort_width, 4L)
  expect_identical(pool$generation_status$attempted_count, 8L)
  # Termination is not claimed to be an exhaustion of all combinations.
  expect_identical(nrow(pool$groups), 0L)
})

test_that("role-3 target triples-only reaches the correct termination phase", {
  # Three distinct triples with a three-round role-3 pattern and width 3: the first
  # cohort is diagonal, the second reverses, and the third would repeat the start
  # state. Nothing is emitted after the first complete group is found at width 3.
  fitted <- rc_ranked(rc_fixtures(rep("triple", 3)))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(3L), pattern = c(3L, 3L, 3L), max_candidates = NULL)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
  expect_true(pool$generation_status$generated_count >= 1L)
  # Attempted work covers whole cohorts only, in multiples of the cohort width.
  expect_identical(pool$generation_status$attempted_count %% 3L, 0L)
  expect_gt(pool$generation_status$attempted_count,
            pool$generation_status$cohort_width)
})

test_that("successive cohorts keep advancing instead of re-emitting the same package", {
  # Two double fixtures with a two-round role-3 pattern. Every cohort falls back to
  # the double board, and the per-board cursors keep advancing so the trajectory
  # explores the finite state space rather than collapsing onto one package. The
  # walk always terminates on a repeated start state with no duplicate emitted
  # group.
  fitted <- rc_ranked(rc_matches(c("S", "T"), list(rc_double, rc_double)))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(3L, 3L), max_candidates = NULL)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
  expect_identical(pool$generation_status$cohort_width, 2L)
  # No emitted group is a duplicate physical package.
  ids <- as.character(pool$groups$group_id)
  signatures <- vapply(ids, function(g) {
    beidan:::.parlay_ranked_candidate_signature(
      pool$role_legs[as.character(pool$role_legs$group_id) == g, , drop = FALSE])
  }, character(1))
  expect_identical(anyDuplicated(signatures), 0L)
  expect_true(pool$generation_status$attempted_count %% 2L == 0L)
})

test_that("substitutions are scoped to their own cohort and never duplicated", {
  # One double fixture, one round, role-3 target: the single emitted candidate has
  # exactly ONE fallback. The later duplicate cohort also falls back, but its
  # substitution belongs to no emitted group and must be discarded, not attached to
  # the first emitted group by a global source-slot match.
  fitted <- rc_ranked(rc_matches("S", list(rc_double)))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(1L), pattern = 3L, max_candidates = NULL)
  expect_identical(pool$generation_status$stop_reason, "state_repeated")
  expect_identical(pool$generation_status$generated_count, 1L)
  expect_identical(nrow(pool$substitutions), 1L)
  expect_identical(pool$substitutions$group_slot, 1L)
  expect_identical(pool$substitutions$group_id, pool$groups$group_id)
  expect_identical(pool$substitutions$fixture_id, "S")
  expect_identical(pool$substitutions$round, 1L)
})

test_that("multi-cohort substitutions keep exact fixture/group/round consistency", {
  # Four double fixtures, two rounds, role-3 targets: two distinct cohorts each emit
  # two complete groups. Each emitted group must carry exactly its own cohort's
  # fallbacks, in round order, bound to its own group id; no group may receive
  # another group's fixture or round.
  fitted <- rc_ranked(rc_matches(c("S", "T", "U", "V"),
                                 rep(list(rc_double), 4L)))
  pool <- parlay_construct_role_groups(
    fitted, rc_settings(2L), pattern = c(3L, 3L), max_candidates = 2L)
  expect_identical(pool$generation_status$stop_reason, "max_candidates")
  expect_identical(pool$generation_status$generated_count, 2L)
  expect_identical(nrow(pool$substitutions), 4L)
  for (slot in pool$groups$group_slot) {
    subs <- pool$substitutions[pool$substitutions$group_slot == slot, ,
                               drop = FALSE]
    legs <- pool$role_legs[pool$role_legs$group_slot == slot, , drop = FALSE]
    # Every substitution's round/fixture must exist in this group's own legs and must
    # agree with the leg recorded at that round.
    expect_identical(nrow(subs), 2L)
    expect_identical(sort(subs$round), c(1L, 2L))
    for (i in seq_len(nrow(subs))) {
      leg <- legs[legs$round == subs$round[[i]], , drop = FALSE]
      expect_identical(nrow(leg), 1L)
      expect_identical(leg$fixture_id, subs$fixture_id[[i]])
      expect_identical(leg$base_role, 2L)
    }
    expect_identical(unique(subs$group_id), pool$groups$group_id[slot])
  }
  # Each group uses each fixture exactly once: no fallback is double-counted.
  for (slot in pool$groups$group_slot) {
    legs <- pool$role_legs[pool$role_legs$group_slot == slot, , drop = FALSE]
    expect_identical(anyDuplicated(legs$fixture_id), 0L)
  }
})

test_that("fractional and non-finite ranks are rejected before coercion", {
  fitted <- rc_ranked(rc_matches(c("P", "Q"), list(rc_double_pair, rc_double_pair)))
  primary <- which(fitted$fixture_id == fitted$fixture_id[[1L]] &
                     fitted$selection_id == 1L)
  expect_length(primary, 1L)

  fractional <- fitted
  fractional$rank[[primary]] <- 1.5
  expect_error(parlay_construct_role_groups(
    fractional, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 2L),
    "whole numbers")

  not_finite <- fitted
  not_finite$rank[[primary]] <- Inf
  expect_error(parlay_construct_role_groups(
    not_finite, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 2L),
    "finite")

  missing_rank <- fitted
  missing_rank$rank[[primary]] <- NA_integer_
  expect_error(parlay_construct_role_groups(
    missing_rank, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 2L),
    "non-missing")

  # A whole numeric rank that matches the recomputation is still accepted.
  numeric_rank <- fitted
  numeric_rank$rank <- as.numeric(fitted$rank)
  expect_silent(parlay_construct_role_groups(
    numeric_rank, rc_settings(2L), pattern = c(2L, 2L), max_candidates = 2L))
})

test_that("the input snapshot and its hash are verified, not merely shaped", {
  fitted <- rc_ranked(rc_fixtures(c("triple", rep("double", 5))))
  settings <- rc_settings(7L)
  pattern <- rc_pattern_3332222

  # The snapshot is carried, is the exact original pre-rank table, and verifies.
  snapshot <- attr(fitted, "input_snapshot")
  expect_s3_class(snapshot, "tbl_df")
  expect_false("rank" %in% names(snapshot))
  expect_identical(rlang::hash(snapshot), attr(fitted, "input_hash"))

  # A swapped 32-hex hash no longer verifies against the snapshot.
  swapped_hash <- fitted
  attr(swapped_hash, "input_hash") <- paste(rep("a", 32L), collapse = "")
  expect_error(parlay_construct_role_groups(
    swapped_hash, settings, pattern, 1L), "verify")

  # A swapped snapshot is detected against the unchanged hash.
  swapped_snapshot <- fitted
  tampered_source <- snapshot
  tampered_source$win[[1L]] <- tampered_source$win[[1L]] + 0.05
  attr(swapped_snapshot, "input_snapshot") <- tampered_source
  expect_error(parlay_construct_role_groups(
    swapped_snapshot, settings, pattern, 1L), "verify")

  # A missing snapshot is refused rather than falling back to the ranked table.
  no_snapshot <- fitted
  attr(no_snapshot, "input_snapshot") <- NULL
  expect_error(parlay_construct_role_groups(
    no_snapshot, settings, pattern, 1L), "input_snapshot")

  # A rank-neutral probability tamper still changes the derived probability table.
  probability_tamper <- fitted
  row <- which(probability_tamper$fixture_id == probability_tamper$fixture_id[[1L]] &
                 probability_tamper$selection_id == 1L)
  probability_tamper$win[[row]] <- probability_tamper$win[[row]] - 1e-6
  expect_error(parlay_construct_role_groups(
    probability_tamper, settings, pattern, 1L), "receipt")
})

test_that("a permuted ranked table with canonical data still verifies", {
  fitted <- rc_ranked(rc_fixtures(c("triple", rep("double", 5))))
  settings <- rc_settings(7L)
  pattern <- rc_pattern_3332222
  reference <- parlay_construct_role_groups(fitted, settings, pattern, 1L)
  set.seed(42L)
  permuted <- fitted[sample(nrow(fitted)), , drop = FALSE]
  # The snapshot rides along unchanged; only the ranked row order moved.
  expect_identical(attr(permuted, "input_snapshot"), attr(fitted, "input_snapshot"))
  result <- parlay_construct_role_groups(permuted, settings, pattern, 1L)
  expect_identical(result$groups$group_id, reference$groups$group_id)
  expect_identical(result$role_legs, reference$role_legs)
  expect_identical(result$group_patterns, reference$group_patterns)

  # A snapshot produced from a permuted SOURCE order is a different receipt and is
  # still accepted on its own terms.
  source <- attr(fitted, "input_snapshot")
  permuted_source <- source[sample(nrow(source)), , drop = FALSE]
  re_ranked <- rank_outcome_selections(permuted_source, rc_cutoff())
  expect_false(identical(attr(re_ranked, "input_hash"), attr(fitted, "input_hash")))
  expect_silent(parlay_construct_role_groups(re_ranked, settings, pattern, 1L))
})

test_that("a ceiling above the integer maximum is rejected clearly and silently", {
  fitted <- rc_ranked(rc_fixtures(c("double", "double")))
  settings <- rc_settings(2L)
  pattern <- c(2L, 2L)

  expect_warning(
    tryCatch(
      parlay_construct_role_groups(fitted, settings, pattern,
                                   max_candidates = 2147483648),
      error = function(e) NULL),
    NA)
  expect_error(parlay_construct_role_groups(
    fitted, settings, pattern, max_candidates = 2147483648),
    "2147483647")

  expect_error(parlay_construct_role_groups(
    fitted, settings, pattern, max_candidates = .Machine$integer.max + 1),
    "integer")
  expect_error(parlay_construct_role_groups(
    fitted, settings, pattern, max_candidates = 1e12), "integer")

  # The exact integer maximum is representable and is not treated as a ceiling.
  at_max <- parlay_construct_role_groups(
    fitted, settings, pattern, max_candidates = .Machine$integer.max)
  expect_identical(at_max$generation_status$max_candidates, .Machine$integer.max)
  expect_identical(at_max$generation_status$stop_reason, "state_repeated")
})
