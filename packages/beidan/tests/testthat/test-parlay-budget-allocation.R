# Block 8 stages 1-4: budget state, candidate generation, coverage frontier and
# constrained portfolio allocation.
#
# Every test below pins a HAND-CALCULATED number or an explicit contract rule, not
# merely an output shape. Small deterministic fixtures keep the arithmetic visible.
# The projected/fixture builders mirror the authoritative schema so the decision
# functions are exercised through their real validation boundaries.

# A minimal, fully explicit projection for the allocation contract. Fixtures are one
# issue, kickoffs AFTER the cutoff, and every fixture carries a visible 'scheduled'
# status strictly before the cutoff, so it is eligible. Probabilities are supplied
# per fixture so ticket masses can be hand-calculated. Kickoffs step by 1h from
# cutoff+5h, which is inside the authoritative half-open decision window
# [cutoff+4h, cutoff+28h) that candidate generation now enforces.
alloc_projection <- function(fixture_ids, probabilities, issue_id = "26097",
                             cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"),
                             status_at = as.POSIXct("2026-09-22 09:00:00", tz = "UTC"),
                             prematch_sp = NULL) {
  cutoff <- list(cutoff_utc = cutoff_utc, issue_id = issue_id)
  fixtures <- tibble::tibble(
    issue_id = rep(issue_id, length(fixture_ids)),
    fixture_id = fixture_ids,
    slot = as.integer(seq_along(fixture_ids)),
    provider_id = rep("synthetic", length(fixture_ids)),
    kickoff_at = cutoff_utc + 3600 * (4 + seq_along(fixture_ids)),
    handicap = rep(0L, length(fixture_ids)),
    sale_state = rep("open", length(fixture_ids)),
    source_url = rep("fixture://fixture", length(fixture_ids)))
  probs <- do.call(rbind, lapply(seq_along(fixture_ids), function(i) {
    tibble::tibble(fixture_id = fixture_ids[i], outcome = match_outcomes(),
                   probability = as.numeric(probabilities[[i]]))
  }))
  status <- tibble::tibble(
    issue_id = rep(issue_id, length(fixture_ids)),
    fixture_id = fixture_ids,
    status = rep("scheduled", length(fixture_ids)),
    status_at = status_at, available_at = status_at,
    source_url = rep("status://status", length(fixture_ids)))
  list(cutoff = cutoff, fixtures = fixtures, probabilities = probs,
       prematch_sp = prematch_sp %||% match_typed_empty("prematch_sp"),
       match_status = status)
}

# group_legs over given (group_id, fixture order) pairs, leg_order 1..n within group.
alloc_group_legs <- function(groups) {
  rows <- list()
  for (group_id in names(groups)) {
    members <- groups[[group_id]]
    for (i in seq_along(members)) {
      rows[[length(rows) + 1L]] <- tibble::tibble(
        group_id = group_id, fixture_id = members[i], leg_order = as.integer(i))
    }
  }
  dplyr::bind_rows(rows)
}

# --- stage 1: parlay_budget_state --------------------------------------------

testthat::test_that("budget state derives whole affordable units and cannot overspend", {
  # n_legs = 2 so the prior fixture sets below have the plan's leg width; the binding
  # helper checks chronology, issue identity and set width together.
  settings <- parlay_settings(n_legs = 2)
  cutoff <- list(cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"),
                 issue_id = "26097")
  # Contract example: 1024 - 1000 = 24 remaining -> 12 units at unit 2.
  prior <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "t1",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "g1", candidate_id = "g1|p2", stake_cny = 1000),
    fixture_sets = list(g1 = c("f1", "f2")))
  state <- parlay_budget_state(settings, prior, cutoff)
  testthat::expect_equal(state$issue_budget_cny, 1024)
  testthat::expect_equal(state$spent_before_cny, 1000)
  testthat::expect_equal(state$remaining_cny, 24)
  testthat::expect_equal(state$available_cny, 24)
  testthat::expect_equal(state$affordable_units, 12L)  # floor(24 / 2)
  testthat::expect_equal(state$unit_cny, 2)
  testthat::expect_equal(state$issue_id, "26097")

  # Optional per-decision cap 11 CNY -> floor(11/2) = 5 units, and it can never raise
  # the balance.
  capped <- parlay_budget_state(settings, prior, cutoff, spend_limit_cny = 11)
  testthat::expect_equal(capped$available_cny, 11)
  testthat::expect_equal(capped$affordable_units, 5L)

  # A cap LARGER than the balance is clamped down to the balance.
  clamped <- parlay_budget_state(settings, prior, cutoff, spend_limit_cny = 9999)
  testthat::expect_equal(clamped$available_cny, 24)
  testthat::expect_equal(clamped$affordable_units, 12L)
})

testthat::test_that("budget state ERRORS on prior overspending instead of hiding it", {
  settings <- parlay_settings(n_legs = 1)
  cutoff <- list(cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"),
                 issue_id = "26097")
  over <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "t1",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "g1", candidate_id = "g1|p2", stake_cny = 1200),
    fixture_sets = list(g1 = c("f1")))
  # 1200 > 1024 cap: invalid historical state is REJECTED, not returned as a negative
  # balance floored to zero available (which a caller could then re-spend around).
  testthat::expect_error(parlay_budget_state(settings, over, cutoff),
                         "exceeds the issue cap")
  # A legitimately exhausted issue (spent == cap) is still valid: zero units, no error.
  exact <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "t1",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "g1", candidate_id = "g1|p2", stake_cny = 1024),
    fixture_sets = list(g1 = c("f1")))
  state <- parlay_budget_state(settings, exact, cutoff)
  testthat::expect_equal(state$remaining_cny, 0)
  testthat::expect_equal(state$available_cny, 0)
  testthat::expect_equal(state$affordable_units, 0L)
})

testthat::test_that("budget state refuses another issue and future prior purchases", {
  settings <- parlay_settings()
  cutoff <- list(cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"),
                 issue_id = "26097")
  other_issue <- list(
    purchases = tibble::tibble(
      issue_id = "26098", ticket_id = "t1",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "g1", candidate_id = "g1|p2", stake_cny = 10),
    fixture_sets = list(g1 = c("f1")))
  testthat::expect_error(parlay_budget_state(settings, other_issue, cutoff),
                         "another issue|belong to issue")
  future <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "t1",
      epoch_at = as.POSIXct("2026-09-22 13:00:00", tz = "UTC"),
      group_id = "g1", candidate_id = "g1|p2", stake_cny = 10),
    fixture_sets = list(g1 = c("f1")))
  testthat::expect_error(parlay_budget_state(settings, future, cutoff),
                         "strictly before")
  # A bare purchases tibble is refused: fixture sets must travel with the ledger.
  testthat::expect_error(
    parlay_budget_state(settings, other_issue$purchases, cutoff),
    "fixture_sets")
  testthat::expect_error(parlay_budget_state(settings, NULL, NULL), "cutoff")
})

# --- stage 2: parlay_generate_candidates -------------------------------------

testthat::test_that("candidate generation is exhaustive when the space fits the bound", {
  projection <- alloc_projection(c("f1", "f2", "f3"),
                                 list(c(.5, .3, .2), c(.4, .35, .25), c(.6, .3, .1)))
  settings <- parlay_settings(n_legs = 2)
  result <- parlay_generate_candidates(projection, settings,
                                       list(max_candidates = 100L, seed = 1L))
  # C(3, 2) = 3 distinct fixture sets, all examined and all reported.
  testthat::expect_equal(result$diagnostics$theoretical_count, 3)
  testthat::expect_equal(result$diagnostics$examined_count, 3L)
  testthat::expect_true(result$diagnostics$exhaustive)
  testthat::expect_false(result$diagnostics$incomplete_search)
  testthat::expect_equal(length(unique(result$group_legs$group_id)), 3L)
  # Every group is one of the three hand-enumerable pairs.
  testthat::expect_setequal(unique(result$group_legs$group_id),
                            c("f1+f2", "f1+f3", "f2+f3"))
})

testthat::test_that("candidate generation flags a bounded incomplete search", {
  projection <- alloc_projection(sprintf("f%02d", 1:10),
                                 rep(list(c(.5, .3, .2)), 10))
  settings <- parlay_settings(n_legs = 3)
  result <- parlay_generate_candidates(projection, settings,
                                       list(max_candidates = 4L, seed = 7L))
  testthat::expect_equal(result$diagnostics$theoretical_count, choose(10, 3))
  testthat::expect_equal(result$diagnostics$examined_count, 4L)
  testthat::expect_false(result$diagnostics$exhaustive)
  testthat::expect_true(result$diagnostics$incomplete_search)
  testthat::expect_equal(length(unique(result$group_legs$group_id)), 4L)
})

testthat::test_that("bounded sampling is seed-reproducible and does not mutate caller RNG", {
  projection <- alloc_projection(sprintf("f%02d", 1:14),
                                 rep(list(c(.5, .3, .2)), 14))
  settings <- parlay_settings(n_legs = 4)
  set.seed(20240922)
  before <- .Random.seed
  first <- parlay_generate_candidates(projection, settings,
                                      list(max_candidates = 5L, seed = 99L))
  after <- .Random.seed
  # The caller's random stream is untouched by the bounded draw.
  testthat::expect_identical(before, after)
  second <- parlay_generate_candidates(projection, settings,
                                       list(max_candidates = 5L, seed = 99L))
  testthat::expect_identical(first$group_legs, second$group_legs)
})

testthat::test_that("candidate generation returns typed empty below n_legs eligible fixtures", {
  projection <- alloc_projection(c("f1", "f2"), list(c(.5, .3, .2), c(.4, .35, .25)))
  settings <- parlay_settings(n_legs = 3)
  result <- parlay_generate_candidates(projection, settings,
                                       list(max_candidates = 10L, seed = 1L))
  testthat::expect_equal(nrow(result$group_legs), 0L)
  testthat::expect_identical(result$group_legs, match_typed_empty("group_legs"))
  testthat::expect_equal(result$diagnostics$theoretical_count, 0)
  testthat::expect_equal(result$diagnostics$examined_count, 0L)
  # An unknown policy field is refused rather than silently ignored.
  testthat::expect_error(
    parlay_generate_candidates(projection, settings,
                               list(max_candidates = 10L, seed = 1L, n_groups = 2L)),
    "unknown construction_policy field")
})

testthat::test_that("candidate generation admits only the half-open decision window", {
  # The kickoff window is the authoritative [cutoff+4h, cutoff+28h) rule from
  # match_decision_window(), the same one parlay_construct_groups applies. The
  # fixture builder places f1 at cutoff+5h (valid) unless an offset is injected.
  cutoff_utc <- as.POSIXct("2026-09-22 12:00:00", tz = "UTC")
  settings <- parlay_settings(n_legs = 1)
  projection_at <- function(offset_seconds) {
    p <- alloc_projection("f1", list(c(.5, .3, .2)), cutoff_utc = cutoff_utc)
    p$fixtures$kickoff_at <- cutoff_utc + offset_seconds
    p
  }
  generate <- function(p) {
    parlay_generate_candidates(p, settings, list(max_candidates = 5L, seed = 1L))
  }
  # An already-started fixture (kickoff at or before the cutoff) is refused.
  testthat::expect_error(generate(projection_at(-3600)), "already kicked off")
  # One hour before the window opens (cutoff+1h < cutoff+4h) is refused.
  testthat::expect_error(generate(projection_at(3600)), "outside the decision window")
  # The window is half-open: cutoff+28h is the excluded end boundary.
  window <- match_decision_window(cutoff_utc)
  testthat::expect_equal(as.numeric(difftime(window$start_utc, cutoff_utc, units = "secs")),
                         4 * 3600)
  testthat::expect_equal(as.numeric(difftime(window$end_utc, cutoff_utc, units = "secs")),
                         28 * 3600)
  testthat::expect_error(generate(projection_at(28 * 3600)), "outside the decision window")
  # The included lower boundary (cutoff+4h) is accepted, and the resulting group is
  # formed over exactly that fixture.
  accepted <- generate(projection_at(4 * 3600))
  testthat::expect_equal(nrow(accepted$group_legs), 1L)
  testthat::expect_equal(unique(accepted$group_legs$fixture_id), "f1")
  # Just inside the end boundary (cutoff+28h-1s) is still accepted.
  inside <- generate(projection_at(28 * 3600 - 1))
  testthat::expect_equal(nrow(inside$group_legs), 1L)
})

# --- stage 3: parlay_coverage_frontier ---------------------------------------

testthat::test_that("frontier probabilities are unconditional and never renormalised", {
  # Mask keeps the two largest outcomes {0.60, 0.25}; support mass is 0.85. The first
  # ticket mass is 0.60 and the depth-1 coverage must be 0.60, NOT 0.60/0.85.
  projection <- alloc_projection("f1", list(c(.60, .25, .15)))
  group_legs <- alloc_group_legs(list(f1 = "f1"))
  settings <- parlay_settings(n_legs = 1)
  frontier <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                       settings, list())
  curve <- frontier$frontier[frontier$frontier$candidate_id == "f1|p2", ]
  testthat::expect_equal(curve$depth, 0:2)
  testthat::expect_equal(curve$marginal_probability, c(0, 0.60, 0.25))
  testthat::expect_equal(curve$cumulative_probability, c(0, 0.60, 0.85))
  testthat::expect_equal(curve$cost_cny, c(0, 2, 4))
  # Depth 0 is always present.
  testthat::expect_equal(curve$cumulative_probability[curve$depth == 0], 0)
  # No renormalisation inside the mask: 0.60 != 0.60 / 0.85.
  testthat::expect_false(isTRUE(all.equal(curve$cumulative_probability[2], 0.60 / 0.85)))
})

testthat::test_that("min_support_mass rejects candidates and reports them", {
  projection <- alloc_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.40, .30, .30)))
  group_legs <- alloc_group_legs(list(f1 = "f1", f2 = "f2"))
  settings <- parlay_settings(n_legs = 1)
  # Mask depth 2 support masses: f1 keeps {.60,.25} = .85, f2 keeps {.40,.30} = .70.
  frontier <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                       settings, list(min_support_mass = 0.75))
  testthat::expect_setequal(unique(frontier$frontier$group_id), "f1")
  testthat::expect_equal(nrow(frontier$rejected), 1L)
  testthat::expect_equal(frontier$rejected$group_id, "f2")
  testthat::expect_equal(frontier$rejected$support_mass, 0.70)
  testthat::expect_match(frontier$rejected$reason, "below min_support_mass")
})

testthat::test_that("frontier EV is NA under probability policy and typed empty on no groups", {
  projection <- alloc_projection("f1", list(c(.60, .25, .15)))
  group_legs <- alloc_group_legs(list(f1 = "f1"))
  settings <- parlay_settings(n_legs = 1)
  frontier <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                       settings, list())
  # No pre-cutoff SP -> every cumulative EV is NA (unavailable, not zero); depth 0 is 0.
  testthat::expect_true(all(is.na(frontier$frontier$cumulative_ev_net[
    frontier$frontier$depth > 0])))
  testthat::expect_equal(frontier$frontier$cumulative_ev_net[frontier$frontier$depth == 0], 0)

  empty <- parlay_coverage_frontier(projection, match_typed_empty("group_legs"),
                                    list(p2 = c(2)), settings, list())
  testthat::expect_identical(empty$frontier,
                             tibble::tibble(candidate_id = character(0),
                                            group_id = character(0), depth = integer(0),
                                            cost_cny = numeric(0),
                                            cumulative_probability = numeric(0),
                                            marginal_probability = numeric(0),
                                            cumulative_ev_net = numeric(0)))
  testthat::expect_identical(empty$rejected,
                             tibble::tibble(candidate_id = character(0),
                                            group_id = character(0),
                                            support_mass = numeric(0),
                                            reason = character(0)))
})

testthat::test_that("frontier EV mode fails on missing SP and ranks valid EV when present", {
  sp <- tibble::tibble(
    fixture_id = "f1", outcome = match_outcomes(),
    quote_at = as.POSIXct("2026-09-22 10:00:00", tz = "UTC"),
    sp_raw = c(3.0, 5.0, 9.0), source_url = "sp://sp")
  projection <- alloc_projection("f1", list(c(.60, .25, .15)), prematch_sp = sp)
  group_legs <- alloc_group_legs(list(f1 = "f1"))
  settings <- parlay_settings(n_legs = 1)
  ranked_ev <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                        settings, list(ranking = "ev_desc"))
  # Hand EV: gross = 2 * 0.65 * p * sp; net = gross - 2. For W: 2*.65*.60*3 = 2.34 -> .34.
  # For D: 2*.65*.25*5 = 1.625 -> -0.375. EV ranking puts W first.
  ranked <- ranked_ev$ranked[ranked_ev$ranked$candidate_id == "f1|p2", ]
  testthat::expect_equal(ranked$rank[1], 1L)
  testthat::expect_equal(ranked$ticket_id[1], "f1:1")
  testthat::expect_equal(ranked$ev_net_est[1], 0.34, tolerance = 1e-12)

  # Missing SP for the D outcome makes the D ticket EV NA; EV ranking must refuse.
  partial <- tibble::tibble(
    fixture_id = "f1", outcome = c("W", "L"),
    quote_at = as.POSIXct("2026-09-22 10:00:00", tz = "UTC"),
    sp_raw = c(3.0, 9.0), source_url = "sp://sp")
  projection_partial <- alloc_projection("f1", list(c(.60, .25, .15)),
                                         prematch_sp = partial)
  testthat::expect_error(
    parlay_coverage_frontier(projection_partial, group_legs, list(p2 = c(2)),
                             settings, list(ranking = "ev_desc")),
    "requires a complete valuation")
})

testthat::test_that("frontier depth is truncated to the affordable budget without touching legality", {
  # A 3-outcome fixture with a 2-outcome mask has 2 legal tickets, but a budget that
  # affords only one unit must cap the DEPTH curve at 1 while leaving the legal
  # supports, tickets and ranked space complete.
  projection <- alloc_projection("f1", list(c(.60, .25, .15)))
  group_legs <- alloc_group_legs(list(f1 = "f1"))
  settings <- parlay_settings(n_legs = 1)
  budget_units <- floor(settings$issue_budget_cny / settings$unit_cny)
  testthat::expect_equal(budget_units, 512)
  # Explicit small depth.
  frontier <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                       settings, list(max_depth = 1L))
  curve <- frontier$frontier[frontier$frontier$candidate_id == "f1|p2", ]
  testthat::expect_equal(curve$depth, 0:1)
  testthat::expect_equal(max(curve$depth), 1L)
  # Legality is NOT truncated: both tickets are still enumerated and ranked.
  testthat::expect_equal(nrow(frontier$ranked[frontier$ranked$candidate_id == "f1|p2", ]), 2L)
  testthat::expect_equal(nrow(frontier$tickets), 2L)
  # The legal mask is unchanged (2 of 3 outcomes allowed), not truncated by depth.
  testthat::expect_equal(sum(frontier$supports$allowed), 2L)
  # The bound records the exact cutoff/settings this frontier belongs to.
  testthat::expect_equal(frontier$bound$issue_id, "26097")
  testthat::expect_equal(frontier$bound$n_legs, 1L)
  testthat::expect_equal(frontier$bound$unit_cny, settings$unit_cny)
  testthat::expect_equal(frontier$bound$max_depth, 1L)
  testthat::expect_equal(frontier$bound$ranking, "probability_desc")

  # A depth policy cannot exceed what the issue budget actually affords.
  capped <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                     settings, list(max_depth = 9999L))
  testthat::expect_equal(unique(capped$bound$max_depth), as.integer(budget_units))
  testthat::expect_true(max(capped$frontier$depth) <= budget_units)

  # group_id comes from the validated ranked rows, not a candidate-label parse.
  testthat::expect_true(all(frontier$frontier$group_id %in% frontier$ranked$group_id))
})

testthat::test_that("a zero budget keeps a nonmissing canonical group id at depth 0", {
  # A zero-unit issue budget must not truncate the ranked block to nothing before the
  # canonical identity is read: depth 0 still names the group it belongs to.
  projection <- alloc_projection("f1", list(c(.60, .25, .15)))
  group_legs <- alloc_group_legs(list(f1 = "f1"))
  settings <- parlay_settings(n_legs = 1)
  settings$issue_budget_cny <- 0
  frontier <- parlay_coverage_frontier(projection, group_legs, list(p2 = c(2)),
                                       settings, list())
  testthat::expect_equal(frontier$bound$max_depth, 0L)
  testthat::expect_equal(frontier$frontier$depth, 0L)
  testthat::expect_equal(frontier$frontier$group_id, "f1")
  testthat::expect_false(anyNA(frontier$frontier$group_id))
  testthat::expect_equal(frontier$frontier$cost_cny, 0)
  # Legality is still complete: the two tickets remain enumerated and ranked.
  testthat::expect_equal(nrow(frontier$ranked), 2L)
})

testthat::test_that("frontier group_legs cannot bypass status, window or issue admission", {
  cutoff_utc <- as.POSIXct("2026-09-22 12:00:00", tz = "UTC")
  settings <- parlay_settings(n_legs = 1)
  # A directly supplied group_legs whose fixture is NOT in the projection's eligible
  # slate must be refused, never silently dropped from the frontier.
  projection <- alloc_projection(c("f1", "f2"),
                                 list(c(.60, .25, .15), c(.40, .30, .30)))
  stray <- alloc_group_legs(list(ghost = "f9"))
  testthat::expect_error(
    parlay_coverage_frontier(projection, stray, list(p2 = c(2)), settings, list()),
    "not eligible at this cutoff")
  # A fixture already kicked off at the cutoff is refused by the window check.
  early <- alloc_projection("f1", list(c(.60, .25, .15)), cutoff_utc = cutoff_utc)
  early$fixtures$kickoff_at <- cutoff_utc - 3600
  testthat::expect_error(
    parlay_coverage_frontier(early, alloc_group_legs(list(f1 = "f1")),
                             list(p2 = c(2)), settings, list()),
    "already kicked off")
  # A fixture before the window opens is refused.
  before <- alloc_projection("f1", list(c(.60, .25, .15)), cutoff_utc = cutoff_utc)
  before$fixtures$kickoff_at <- cutoff_utc + 3600
  testthat::expect_error(
    parlay_coverage_frontier(before, alloc_group_legs(list(f1 = "f1")),
                             list(p2 = c(2)), settings, list()),
    "outside the decision window")
  # A fixture with no visible scheduled status before the cutoff (only a live report)
  # is excluded by the shared selector, so its group is refused as ineligible.
  hidden <- alloc_projection("f1", list(c(.60, .25, .15)), cutoff_utc = cutoff_utc)
  hidden$match_status$status <- "live"
  testthat::expect_error(
    parlay_coverage_frontier(hidden, alloc_group_legs(list(f1 = "f1")),
                             list(p2 = c(2)), settings, list()),
    "not eligible at this cutoff")
  # The valid in-window fixture is accepted.
  ok <- parlay_coverage_frontier(alloc_projection("f1", list(c(.60, .25, .15)),
                                                  cutoff_utc = cutoff_utc),
                                 alloc_group_legs(list(f1 = "f1")), list(p2 = c(2)),
                                 settings, list())
  testthat::expect_equal(unique(ok$frontier$group_id), "f1")
})

# --- stage 4: parlay_allocate_portfolio --------------------------------------
# A state whose DECLARED budget really buys `units` tickets at the settings unit cost,
# so affordable_units stays consistent with available_cny. The shared test cutoff.
alloc_cutoff <- function(issue_id = "26097") {
  list(cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"), issue_id = issue_id)
}

# Hand-built frontier_result with the contract's exact marginals A(.30,.05),
# B(.20,.04). Stage 4 consumes `ranked`, so the allocation arithmetic is pinned to
# the contract numbers directly, independent of which mask can realise them. The
# REQUIRED `bound` metadata declares the cutoff/settings this artifact belongs to;
# every allocation validates it, since there is no bypass flag.
contract_frontier_result <- function(marginals = list(A = c(0.30, 0.05),
                                                      B = c(0.20, 0.04)),
                                     cutoff = alloc_cutoff(),
                                     unit_cny = 2, n_legs = 1L) {
  ranked_rows <- list()
  for (candidate_group in names(marginals)) {
    values <- marginals[[candidate_group]]
    for (i in seq_along(values)) {
      ranked_rows[[length(ranked_rows) + 1L]] <- tibble::tibble(
        candidate_id = paste0(candidate_group, "|p2"),
        ticket_id = paste0(candidate_group, ":", i),
        group_id = candidate_group, probability = values[i], ev_net_est = NA_real_,
        rank = as.integer(i), cumulative_mass = sum(values[seq_len(i)]))
    }
  }
  list(ranked = dplyr::bind_rows(ranked_rows),
       group_legs = alloc_group_legs(list(A = "fA", B = "fB")),
       tickets = match_typed_empty("tickets"),
       bound = tibble::tibble(
         issue_id = as.character(cutoff$issue_id), cutoff_utc = cutoff$cutoff_utc,
         n_legs = as.integer(n_legs), unit_cny = as.numeric(unit_cny),
         ranking = "probability_desc", max_depth = 10L))
}

# A valid one-row state declaring exactly `units` affordable tickets at unit 2, with
# available_cny = units * 2 so the affordability identity holds.
alloc_state <- function(units, cutoff = alloc_cutoff(), issue_id = cutoff$issue_id, spent = 0) {
  units <- as.numeric(units)
  tibble::tibble(
    issue_id = as.character(issue_id), issue_budget_cny = 1024,
    spent_before_cny = spent, remaining_cny = 1024 - spent,
    available_cny = units * 2, affordable_units = as.integer(units), unit_cny = 2)
}

testthat::test_that("budget 2/4/6 produces A1 / A1+B1 / A1+B1+A2 with derived group count", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  frontier_result <- contract_frontier_result()
  run_budget <- function(units) {
    state <- alloc_state(units, cutoff)
    parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state, NULL,
                              cutoff, list(max_reuse = 10L, max_overlap = 0L),
                              "probability")
  }
  # Budget 2 -> one unit -> A1 (one group).
  r2 <- run_budget(1L)
  testthat::expect_equal(r2$purchases$ticket_id, "A:1")
  testthat::expect_equal(r2$diagnostics$n_groups, 1L)
  # Budget 4 -> A1 + B1 (two groups).
  r4 <- run_budget(2L)
  testthat::expect_equal(r4$purchases$ticket_id, c("A:1", "B:1"))
  testthat::expect_equal(r4$diagnostics$n_groups, 2L)
  # Budget 6 -> A1 + B1 + A2: deepen A rather than start B2, because A2 (.05) beats
  # B2 (.04) -- opening and deepening compete in the same loop.
  r6 <- run_budget(3L)
  testthat::expect_equal(r6$purchases$ticket_id, c("A:1", "B:1", "A:2"))
  testthat::expect_equal(r6$diagnostics$n_groups, 2L)
  testthat::expect_equal(r6$diagnostics$units_bought, 3L)
  testthat::expect_equal(r6$diagnostics$cost_cny, 6)
  # The objective is expected ticket COUNT (sum of marginals), not union probability.
  testthat::expect_equal(r6$selected$objective_value[r6$selected$group_id == "A"], 0.35)
})

testthat::test_that("reuse counts distinct funded groups and deepening does not consume it", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  frontier_result <- contract_frontier_result()
  state <- alloc_state(3, cutoff)
  # A and B are DISJOINT groups, so max_reuse = 1 admits both (each fixture has one
  # use). A then deepens with A:2 -- that second ticket is NOT a second group use, so
  # the reuse ledger stays at one use per fixture and nothing is rejected.
  result <- parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state,
                                      NULL, cutoff,
                                      list(max_reuse = 1L, max_overlap = 0L),
                                      "probability")
  testthat::expect_equal(result$purchases$ticket_id, c("A:1", "B:1", "A:2"))
  testthat::expect_equal(result$diagnostics$n_groups, 2L)
  testthat::expect_equal(length(result$diagnostics$rejected), 0L)

  # A group that SHARES a fixture with an already-funded group consumes a second use
  # of that fixture and is refused at max_reuse = 1, even with overlap allowed.
  shared_legs <- alloc_group_legs(list("fA+fB" = c("fA", "fB"),
                                       "fA+fC" = c("fA", "fC")))
  shared_ranked <- tibble::tibble(
    candidate_id = c("fA+fB|p11", "fA+fC|p11"),
    ticket_id = c("fA:1|fB:1", "fA:1|fC:1"),
    group_id = c("fA+fB", "fA+fC"), probability = c(0.45, 0.44),
    ev_net_est = c(NA_real_, NA_real_), rank = c(1L, 1L),
    cumulative_mass = c(0.45, 0.44))
  shared_frontier <- list(ranked = shared_ranked, group_legs = shared_legs,
                          tickets = match_typed_empty("tickets"),
                          bound = contract_frontier_result(cutoff = cutoff,
                                                           n_legs = 2L)$bound)
  shared_state <- alloc_state(4, cutoff)
  shared_result <- parlay_allocate_portfolio(shared_frontier, shared_legs, shared_state,
                                             NULL, cutoff,
                                             list(max_reuse = 1L, max_overlap = 2L),
                                             "probability")
  testthat::expect_equal(shared_result$diagnostics$n_groups, 1L)
  testthat::expect_equal(shared_result$diagnostics$rejected[["fA+fC|p11"]],
                         "FIXTURE_REUSE_CAP_EXCEEDED")
})

testthat::test_that("overlap cap includes prior groups and blocks shared fixtures", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 2)
  # Groups AB and AC share fixture A. With max_overlap = 0 and AB already bought,
  # AC must be refused.
  group_legs <- alloc_group_legs(list("fA+fB" = c("fA", "fB"),
                                      "fA+fC" = c("fA", "fC")))
  ranked <- tibble::tibble(
    candidate_id = c("fA+fB|p11", "fA+fC|p11"),
    ticket_id = c("fA:1|fB:1", "fA:1|fC:1"),
    group_id = c("fA+fB", "fA+fC"), probability = c(0.45, 0.44),
    ev_net_est = c(NA_real_, NA_real_), rank = c(1L, 1L),
    cumulative_mass = c(0.45, 0.44))
  frontier_result <- list(ranked = ranked, group_legs = group_legs,
                          tickets = match_typed_empty("tickets"),
                          bound = contract_frontier_result(cutoff = cutoff,
                                                           n_legs = 2L)$bound)
  prior <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "fA:1|fB:2",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "fA+fB", candidate_id = "fA+fB|p11", stake_cny = 2),
    fixture_sets = list("fA+fB" = c("fA", "fB")))
  state <- alloc_state(5, cutoff, spent = 2)
  blocked <- parlay_allocate_portfolio(frontier_result, group_legs, state, prior, cutoff,
                                       list(max_reuse = 10L, max_overlap = 0L),
                                       "probability")
  # The prior group already uses fixture fA, so AC (overlap 1 > 0) is refused and
  # consumes no budget. The prior group is a deepening of fA+fB, which is allowed.
  testthat::expect_equal(blocked$diagnostics$rejected[["fA+fC|p11"]],
                         "GROUP_OVERLAP_CAP_EXCEEDED")
  testthat::expect_false("fA:1|fC:1" %in% blocked$purchases$ticket_id)

  allowed <- parlay_allocate_portfolio(frontier_result, group_legs, state, prior, cutoff,
                                       list(max_reuse = 10L, max_overlap = 1L),
                                       "probability")
  testthat::expect_true("fA:1|fC:1" %in% allowed$purchases$ticket_id)
})

testthat::test_that("a physical ticket is never purchased twice across structures and history", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  group_legs <- alloc_group_legs(list(fA = "fA"))
  # Two structures over the SAME group share tickets. One structure per group wins:
  # the other is refused, and the shared tickets are not bought twice.
  ranked <- tibble::tibble(
    candidate_id = c("fA|p2", "fA|p2", "fA|p3", "fA|p3", "fA|p3"),
    ticket_id = c("fA:1", "fA:2", "fA:1", "fA:2", "fA:3"),
    group_id = rep("fA", 5), probability = c(.60, .25, .60, .25, .15),
    ev_net_est = rep(NA_real_, 5), rank = c(1L, 2L, 1L, 2L, 3L),
    cumulative_mass = c(.60, .85, .60, .85, 1.00))
  frontier_result <- list(ranked = ranked, group_legs = group_legs,
                          tickets = match_typed_empty("tickets"),
                          bound = contract_frontier_result()$bound)
  state <- alloc_state(5, cutoff)
  result <- parlay_allocate_portfolio(frontier_result, group_legs, state, NULL, cutoff,
                                      list(max_reuse = 10L, max_overlap = 0L),
                                      "probability")
  testthat::expect_equal(sort(result$purchases$ticket_id), c("fA:1", "fA:2"))
  testthat::expect_equal(anyDuplicated(result$purchases$ticket_id), 0L)
  testthat::expect_equal(result$diagnostics$n_groups, 1L)
  testthat::expect_equal(result$diagnostics$rejected[["fA|p3"]],
                         "STRUCTURE_ALREADY_SELECTED")

  # A physical ticket already in the prior ledger is never bought again.
  prior <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "fA:1",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "fA", candidate_id = "fA|p2", stake_cny = 2),
    fixture_sets = list(fA = "fA"))
  state2 <- alloc_state(6, cutoff, spent = 2)
  result2 <- parlay_allocate_portfolio(frontier_result, group_legs, state2, prior, cutoff,
                                       list(max_reuse = 10L, max_overlap = 0L),
                                       "probability")
  testthat::expect_false("fA:1" %in% result2$purchases$ticket_id)
  testthat::expect_true(all(result2$purchases$ticket_id == "fA:2"))
})

testthat::test_that("EV objective fails on missing SP and leaves nonpositive marginals unspent", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  group_legs <- alloc_group_legs(list(A = "fA"))
  bound <- contract_frontier_result()$bound
  state <- alloc_state(3, cutoff)

  # Missing SP (NA EV) under the EV objective is a hard error, never a silent switch.
  missing_sp <- list(ranked = tibble::tibble(
    candidate_id = "A|p2", ticket_id = c("A:1", "A:2"), group_id = "A",
    probability = c(.30, .05), ev_net_est = c(NA_real_, 0.10),
    rank = c(1L, 2L), cumulative_mass = c(.30, .35)),
    group_legs = group_legs, tickets = match_typed_empty("tickets"), bound = bound)
  testthat::expect_error(
    parlay_allocate_portfolio(missing_sp, group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "ev"),
    "complete valid pre-cutoff SP valuation")

  # With valid EV, nonpositive marginals are left unspent: A:1 has +0.34, A:2 has
  # -0.375, so only A:1 is bought and the rest of the budget stays unspent.
  ev_ranked <- list(ranked = tibble::tibble(
    candidate_id = "A|p2", ticket_id = c("A:1", "A:2"), group_id = "A",
    probability = c(.30, .05), ev_net_est = c(0.34, -0.375),
    rank = c(1L, 2L), cumulative_mass = c(.30, .35)),
    group_legs = group_legs, tickets = match_typed_empty("tickets"), bound = bound)
  result <- parlay_allocate_portfolio(ev_ranked, group_legs, state, NULL, cutoff,
                                      list(max_reuse = 10L, max_overlap = 0L), "ev")
  testthat::expect_equal(result$purchases$ticket_id, "A:1")
  testthat::expect_equal(result$diagnostics$units_bought, 1L)
  testthat::expect_equal(result$diagnostics$unspent_cny, 4)
  testthat::expect_equal(result$selected$objective_value, 0.34)

  # An EV objective on a frontier whose rows are NOT in EV order is refused: skipping
  # the nonpositive A:2 while A:3 holds the best EV would silently buy the wrong set.
  out_of_order <- list(ranked = tibble::tibble(
    candidate_id = "A|p2", ticket_id = c("A:1", "A:2", "A:3"), group_id = "A",
    probability = c(.30, .05, .10), ev_net_est = c(0.34, -0.375, 0.90),
    rank = c(1L, 2L, 3L), cumulative_mass = c(.30, .35, .45)),
    group_legs = group_legs, tickets = match_typed_empty("tickets"), bound = bound)
  testthat::expect_error(
    parlay_allocate_portfolio(out_of_order, group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "ev"),
    "ranked by EV")

  testthat::expect_error(
    parlay_allocate_portfolio(ev_ranked, group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "profit"),
    "objective must be 'probability' or 'ev'")
})

testthat::test_that("zero affordable units and no feasible tickets yield typed empty outputs", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  frontier_result <- contract_frontier_result()
  state <- alloc_state(0, cutoff)
  result <- parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state,
                                      NULL, cutoff,
                                      list(max_reuse = 10L, max_overlap = 0L),
                                      "probability")
  testthat::expect_identical(result$purchases, match_typed_empty("purchases"))
  testthat::expect_equal(nrow(result$selected), 0L)
  testthat::expect_equal(result$diagnostics$n_groups, 0L)
  testthat::expect_equal(nrow(result$trace), 0L)
  # History still carries the prior ledger shape, not a detached zero.
  testthat::expect_equal(nrow(result$history$purchases), 0L)

  # No ranked tickets at all is likewise typed empty, not an error.
  none <- list(ranked = match_typed_empty("ranked"),
               group_legs = frontier_result$group_legs,
               tickets = match_typed_empty("tickets"),
               bound = frontier_result$bound)
  state2 <- alloc_state(4, cutoff)
  result2 <- parlay_allocate_portfolio(none, frontier_result$group_legs, state2, NULL,
                                       cutoff, list(max_reuse = 10L, max_overlap = 0L),
                                       "probability")
  testthat::expect_identical(result2$purchases, match_typed_empty("purchases"))
  testthat::expect_equal(result2$diagnostics$units_bought, 0L)
})

testthat::test_that("allocation history carries funded groups forward as binding evidence", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  frontier_result <- contract_frontier_result()
  state <- alloc_state(2, cutoff)
  result <- parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state,
                                      NULL, cutoff,
                                      list(max_reuse = 10L, max_overlap = 0L),
                                      "probability")
  # Budget 2 buys A:1 (.30) then B:1 (.20), opening two groups; the history carries
  # both fixture sets forward so the next decision cannot re-open them.
  testthat::expect_setequal(names(result$history$fixture_sets), c("A", "B"))
  testthat::expect_equal(result$history$fixture_sets$A, "fA")
  testthat::expect_equal(result$history$fixture_sets$B, "fB")
  testthat::expect_equal(nrow(result$history$purchases), 2L)
  # The returned history re-validates as prior state for the next decision.
  testthat::expect_silent(parlay_validate_prior_state(result$history))
  # budget_state and cutoff must agree on the issue.
  wrong_state <- state
  wrong_state$issue_id <- "26098"
  testthat::expect_error(
    parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, wrong_state,
                              NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "probability"),
    "bound to issue")
})

# --- review round 2: binding, budget arithmetic, trace ------------------------

testthat::test_that("allocator unspent_cny is available minus actual cost, fractional left", {
  cutoff <- alloc_cutoff()
  # An 11 CNY decision cap at unit 2 buys 5 tickets (10 CNY) and leaves 1 CNY truly
  # unspent: unspent is available - ACTUAL cost, not the units-left remainder.
  state <- tibble::tibble(
    issue_id = "26097", issue_budget_cny = 1024, spent_before_cny = 0,
    remaining_cny = 1024, available_cny = 11, affordable_units = 5L, unit_cny = 2)
  result <- parlay_allocate_portfolio(contract_frontier_result(),
                                      contract_frontier_result()$group_legs, state, NULL,
                                      cutoff, list(max_reuse = 10L, max_overlap = 0L),
                                      "probability")
  testthat::expect_equal(result$diagnostics$units_bought, 4L)
  testthat::expect_equal(result$diagnostics$cost_cny, 8)
  testthat::expect_equal(result$diagnostics$unspent_cny, 3)
  testthat::expect_equal(result$diagnostics$available_units, 5L)
  # Identity holds exactly: available == cost + unspent.
  testthat::expect_equal(result$diagnostics$cost_cny + result$diagnostics$unspent_cny,
                         state$available_cny)
})

testthat::test_that("allocator refuses a malformed or inconsistent budget_state", {
  cutoff <- alloc_cutoff()
  frontier_result <- contract_frontier_result()
  base <- alloc_state(3, cutoff)
  call_with <- function(state) {
    parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state, NULL,
                              cutoff, list(max_reuse = 10L, max_overlap = 0L),
                              "probability")
  }
  # as.integer() would silently turn 2.7 into 2 and a string into 1; both are refused.
  fractional <- base
  fractional$affordable_units <- 2.7
  testthat::expect_error(call_with(fractional), "must be a whole number")
  malformed <- base
  malformed$affordable_units <- "3"
  testthat::expect_error(call_with(malformed), "affordable_units")
  negative <- base
  negative$affordable_units <- -1
  testthat::expect_error(call_with(negative), "affordable_units")
  nonfinite <- base
  nonfinite$available_cny <- Inf
  testthat::expect_error(call_with(nonfinite), "available_cny")
  # 3 units at unit 2 cannot be afforded by 100 CNY? It can -- so use a stated
  # available that is too small for the declared units.
  inconsistent <- base
  inconsistent$available_cny <- 2
  testthat::expect_error(call_with(inconsistent), "inconsistent with available_cny")
})

testthat::test_that("allocation requires and consumes a frontier bound to the same cutoff", {
  cutoff <- alloc_cutoff()
  settings <- parlay_settings(n_legs = 1)
  frontier_result <- contract_frontier_result()
  state <- alloc_state(2, cutoff)
  # There is no settings/explicit bypass: the bound alone carries the binding and a
  # matching artifact is consumed straight through the exact contract signature.
  result <- parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state,
                                      NULL, cutoff,
                                      list(max_reuse = 10L, max_overlap = 0L),
                                      "probability")
  testthat::expect_equal(result$diagnostics$units_bought, 2L)

  # A frontier for ANOTHER cutoff instant is refused.
  other_cutoff <- list(
    cutoff_utc = as.POSIXct("2026-09-23 12:00:00", tz = "UTC"), issue_id = "26097")
  testthat::expect_error(
    parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state, NULL,
                              other_cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "probability"),
    "cutoff_utc")
  # A frontier for another issue is refused.
  other_issue <- contract_frontier_result(cutoff = alloc_cutoff("26098"))
  testthat::expect_error(
    parlay_allocate_portfolio(other_issue, other_issue$group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "probability"),
    "bound to issue")
  # A frontier priced at a different unit cost is refused.
  other_unit <- contract_frontier_result(unit_cny = 5)
  testthat::expect_error(
    parlay_allocate_portfolio(other_unit, other_unit$group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "probability"),
    "unit_cny")
  # A call without any bound metadata is refused UNCONDITIONALLY -- there is no
  # settings argument or flag that could relax this.
  unbound <- frontier_result
  unbound$bound <- NULL
  testthat::expect_error(
    parlay_allocate_portfolio(unbound, unbound$group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "probability"),
    "no `bound` metadata")
  # A partial bound is refused too, not treated as absent-but-optional.
  partial <- frontier_result
  partial$bound <- partial$bound[, c("issue_id", "n_legs", "unit_cny"), drop = FALSE]
  testthat::expect_error(
    parlay_allocate_portfolio(partial, partial$group_legs, state, NULL, cutoff,
                              list(max_reuse = 10L, max_overlap = 0L), "probability"),
    "bound is missing")
  # The allocator exposes exactly the contract signature: no settings or
  # explicit_frontier_result parameters exist to bypass the binding.
  testthat::expect_equal(
    names(formals(parlay_allocate_portfolio)),
    c("frontier_result", "group_legs", "budget_state", "prior_purchases", "cutoff",
      "constraints", "objective"))
})

testthat::test_that("allocation returns a typed selection trace with OPEN/DEEPEN actions", {
  cutoff <- alloc_cutoff()
  frontier_result <- contract_frontier_result()
  state <- alloc_state(3, cutoff)
  result <- parlay_allocate_portfolio(frontier_result, frontier_result$group_legs, state,
                                      NULL, cutoff,
                                      list(max_reuse = 10L, max_overlap = 0L),
                                      "probability")
  trace <- result$trace
  testthat::expect_equal(names(trace),
                         c("step", "candidate_id", "group_id", "ticket_id", "marginal",
                           "score_per_cny", "action"))
  # Three purchases, traced in order, matching the ledger exactly.
  testthat::expect_equal(nrow(trace), 3L)
  testthat::expect_equal(trace$step, 1:3)
  testthat::expect_equal(trace$ticket_id, result$purchases$ticket_id)
  testthat::expect_equal(trace$group_id, result$purchases$group_id)
  # A:1 opens A, B:1 opens B, A:2 deepens A.
  testthat::expect_equal(trace$action, c("OPEN", "OPEN", "DEEPEN"))
  testthat::expect_equal(trace$marginal, c(0.30, 0.20, 0.05))
  # score_per_cny is marginal / unit (unit 2).
  testthat::expect_equal(trace$score_per_cny, c(0.15, 0.10, 0.025))
  # The probability objective says explicitly it is an expected WIN COUNT, not a union.
  testthat::expect_match(result$diagnostics$objective_basis, "expected count of winning")

  empty <- parlay_allocate_portfolio(frontier_result, frontier_result$group_legs,
                                     alloc_state(0, cutoff), NULL, cutoff,
                                     list(max_reuse = 10L, max_overlap = 0L),
                                     "probability")
  testthat::expect_equal(names(empty$trace), names(trace))
  testthat::expect_equal(nrow(empty$trace), 0L)
})

testthat::test_that("empty group_legs takes its width from the required bound, no invented width", {
  cutoff <- alloc_cutoff()
  # A VALID 2-leg prior ledger: an invented 1-leg width would falsely reject it. The
  # width now comes from the REQUIRED frontier bound, through the one authoritative
  # .ValidatePriorBinding, so with no candidate universe the allocation is typed-empty.
  prior <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "t1",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = "f1+f2", candidate_id = "f1+f2|p11", stake_cny = 4),
    fixture_sets = list("f1+f2" = c("f1", "f2")))
  state <- alloc_state(2, cutoff, spent = 4)
  empty_frontier <- list(ranked = match_typed_empty("ranked"),
                         group_legs = match_typed_empty("group_legs"),
                         tickets = match_typed_empty("tickets"),
                         bound = contract_frontier_result(cutoff = cutoff,
                                                          n_legs = 2L)$bound)
  result <- parlay_allocate_portfolio(empty_frontier, match_typed_empty("group_legs"),
                                      state, prior, cutoff,
                                      list(max_reuse = 10L, max_overlap = 2L),
                                      "probability")
  testthat::expect_identical(result$purchases, match_typed_empty("purchases"))
  testthat::expect_equal(result$diagnostics$units_bought, 0L)
  # The prior ledger is still carried forward, never dropped.
  testthat::expect_equal(result$history$fixture_sets[["f1+f2"]], c("f1", "f2"))

  # A 7-leg prior is likewise accepted rather than width-rejected.
  prior7 <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = "t7",
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = paste0("f", 1:7, collapse = "+"), candidate_id = "g|p1111111",
      stake_cny = 4),
    fixture_sets = stats::setNames(list(sprintf("f%d", 1:7)),
                                   paste0("f", 1:7, collapse = "+")))
  empty7 <- list(ranked = match_typed_empty("ranked"),
                 group_legs = match_typed_empty("group_legs"),
                 tickets = match_typed_empty("tickets"),
                 bound = contract_frontier_result(cutoff = cutoff, n_legs = 7L)$bound)
  result7 <- parlay_allocate_portfolio(empty7, match_typed_empty("group_legs"), state,
                                       prior7, cutoff,
                                       list(max_reuse = 10L, max_overlap = 7L),
                                       "probability")
  testthat::expect_identical(result7$purchases, match_typed_empty("purchases"))
  # A foreign-issue prior is still refused even without an observable width.
  foreign <- prior
  foreign$purchases$issue_id <- "26098"
  testthat::expect_error(
    parlay_allocate_portfolio(empty_frontier, match_typed_empty("group_legs"), state,
                              foreign, cutoff,
                              list(max_reuse = 10L, max_overlap = 2L), "probability"),
    "belong to issue|bound to issue")
})

testthat::test_that("a prior group carrying multiple candidate IDs is refused", {
  cutoff <- alloc_cutoff()
  group_legs <- alloc_group_legs(list(fA = "fA"))
  ranked <- tibble::tibble(
    candidate_id = c("fA|p2", "fA|p2"), ticket_id = c("fA:1", "fA:2"),
    group_id = rep("fA", 2), probability = c(.60, .25), ev_net_est = c(NA_real_, NA_real_),
    rank = c(1L, 2L), cumulative_mass = c(.60, .85))
  frontier_result <- list(ranked = ranked, group_legs = group_legs,
                          tickets = match_typed_empty("tickets"),
                          bound = contract_frontier_result()$bound)
  # Two prior tickets on group fA, each attributed to a DIFFERENT structure. The
  # ledger cannot say which one opened the group, so the ambiguity is an error.
  prior <- list(
    purchases = tibble::tibble(
      issue_id = "26097", ticket_id = c("fA:1", "fA:2"),
      epoch_at = as.POSIXct("2026-09-22 08:00:00", tz = "UTC"),
      group_id = c("fA", "fA"), candidate_id = c("fA|p2", "fA|p3"),
      stake_cny = c(2, 2)),
    fixture_sets = list(fA = "fA"))
  testthat::expect_error(
    parlay_allocate_portfolio(frontier_result, group_legs, alloc_state(3, cutoff, spent = 4), prior,
                              cutoff, list(max_reuse = 10L, max_overlap = 0L),
                              "probability"),
    "more than one candidate_id")
})


testthat::test_that("allocator rejects detached prior spending and inflated balances", {
  f <- contract_frontier_result()
  state <- alloc_state(2)
  state$spent_before_cny <- 1000
  testthat::expect_error(parlay_allocate_portfolio(f, f$group_legs, state, NULL,
    alloc_cutoff(), list(max_reuse=1L,max_overlap=0L), "probability"), "disagrees with prior")
  state <- alloc_state(2)
  state$issue_budget_cny <- 2
  state$remaining_cny <- 2
  testthat::expect_error(parlay_allocate_portfolio(f, f$group_legs, state, NULL,
    alloc_cutoff(), list(max_reuse=1L,max_overlap=0L), "probability"), "exceeds remaining")
})

testthat::test_that("probability allocation refuses an inverted frontier ranking", {
  f <- contract_frontier_result(marginals=list(A=c(.05,.30)))
  testthat::expect_error(parlay_allocate_portfolio(f, f$group_legs, alloc_state(1), NULL,
    alloc_cutoff(), list(max_reuse=1L,max_overlap=0L), "probability"), "probability-ranked")
})


testthat::test_that("allocation cannot substitute fixture membership under unchanged IDs", {
  f <- contract_frontier_result()
  substituted <- f$group_legs
  substituted$fixture_id <- paste0("ghost", seq_len(nrow(substituted)))
  testthat::expect_error(parlay_allocate_portfolio(f, substituted, alloc_state(2), NULL,
    alloc_cutoff(), list(max_reuse=1L,max_overlap=0L), "probability"), "group membership differs")
})


testthat::test_that("zero probability tickets leave the remaining budget unspent", {
  f <- contract_frontier_result(marginals=list(A=c(.3,0)))
  result <- parlay_allocate_portfolio(f, f$group_legs, alloc_state(2), NULL,
    alloc_cutoff(), list(max_reuse=1L,max_overlap=0L), "probability")
  testthat::expect_equal(nrow(result$purchases), 1L)
  testthat::expect_equal(result$diagnostics$unspent_cny, 2)
})
