# Package tests for the EV- and coverage-ordered group selector (#553 follow-up).
#
# The selector sits in front of the authoritative evaluator. These tests bind the
# OBSERVABLE contract:
#   * it orders constructed candidate groups by the declared objective and stops
#     on an explicit budget cap / EV floor;
#   * an unvaluable group (missing SP) is never treated as zero EV -- the EV
#     objective fails closed while the coverage objective, which is not an EV
#     statement, still selects;
#   * the emitted restricted pool still satisfies the evaluator's own pool
#     validation and buys exactly the selected groups' distinct physical tickets,
#     so the priced ledger reconciles with the selector's running ledger.
#
# Expectations are hand-derived from the group spaces, never from the selector's
# own output.

ps_cutoff <- function(issue_id = "26098") {
  list(issue_id = issue_id,
       cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
}

ps_settings <- function(n_legs) {
  settings <- parlay_settings()
  settings$n_legs <- as.integer(n_legs)
  settings
}

ps_matches <- function(ids, p) {
  p <- lapply(p, as.numeric)
  tibble::tibble(
    fixture_id = as.character(ids),
    win = vapply(p, `[[`, numeric(1), 1L),
    draw = vapply(p, `[[`, numeric(1), 2L),
    lose = vapply(p, `[[`, numeric(1), 3L))
}

# `triple` .40/.30/.30 -> base_role 3; `double` .50/.30/.20 -> base_role 2;
# `single` .55/.23/.22 -> base_role 1 with a protected top1+top3.
ps_triple <- c(0.40, 0.30, 0.30)
ps_double <- c(0.50, 0.30, 0.20)
ps_single <- c(0.55, 0.23, 0.22)

ps_fixtures <- function(kinds) {
  ids <- sprintf("F%02d", seq_along(kinds))
  p <- lapply(kinds, function(kind) switch(kind,
    triple = ps_triple, double = ps_double, single = ps_single,
    stop("unknown kind")))
  ps_matches(ids, p)
}

# A flat synthetic SP table: every outcome of every listed fixture quoted at
# `sp`, strictly before the cutoff.
ps_sp <- function(fixture_ids, sp = 6, cutoff = ps_cutoff()) {
  tidyr::expand_grid(fixture_id = as.character(fixture_ids),
                     outcome = c("W", "D", "L")) |>
    dplyr::mutate(quote_at = cutoff$cutoff_utc - 60,
                  sp_raw = as.numeric(sp),
                  source_url = "synthetic://select-groups")
}

ps_pool <- function(kinds, n_legs = 2L, pattern = c(3L, 2L), max_candidates = 3L,
                    prematch_sp = match_typed_empty("prematch_sp")) {
  matches <- ps_fixtures(kinds)
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches),
                                    ps_cutoff())
  parlay_construct_role_groups(ranked, ps_settings(n_legs), pattern = pattern,
                               max_candidates = max_candidates,
                               prematch_sp = prematch_sp)
}


# Independent 3^n outcome enumeration; does not call production union routines.
ps_exact_coverage <- function(evaluation) {
  p <- evaluation$portfolio$probabilities
  ids <- unique(p$fixture_id)
  states <- do.call(tidyr::expand_grid,
    stats::setNames(rep(list(c("W", "D", "L")), length(ids)), ids))
  mass <- rep(1, nrow(states))
  for (id in ids) {
    probabilities <- p$probability[p$fixture_id == id]
    names(probabilities) <- p$outcome[p$fixture_id == id]
    mass <- mass * probabilities[states[[id]]]
  }
  covered <- rep(FALSE, nrow(states))
  legs <- evaluation$plan$ticket_legs
  for (ticket in evaluation$purchases$ticket_id) {
    block <- legs[legs$ticket_id == ticket, ]
    hit <- rep(TRUE, nrow(states))
    for (i in seq_len(nrow(block))) {
      hit <- hit & states[[block$fixture_id[i]]] == block$outcome[i]
    }
    covered <- covered | hit
  }
  sum(mass[covered])
}

ps_check_ledger <- function(selected) {
  e <- selected$evaluation
  expect_equal(selected$summary$cost_cny, sum(e$purchases$cost_cny))
  expect_equal(selected$summary$cost_cny, sum(selected$selection$new_cost_cny))
  expect_identical(nrow(e$purchases), sum(selected$selection$new_ticket_count))
  expect_false(anyDuplicated(e$purchases$ticket_id) > 0)
  expect_equal(selected$summary$model_ev_cny, e$summary$ev_net_cny)
  expect_equal(selected$summary$coverage, ps_exact_coverage(e), tolerance = 1e-12)
  expect_equal(e$summary$actual_coverage, ps_exact_coverage(e), tolerance = 1e-12)
  expect_silent(.parlay_ranked_validate_evaluation(e))
  expect_equal(sum(e$plan$funded$stake_cny), sum(e$purchases$cost_cny))
}

ps_protected_pool <- function() {
  ps_pool(rep("single", 3), n_legs = 2L, pattern = c(1L, 1L),
    max_candidates = NULL, prematch_sp = ps_sp(sprintf("F%02d", 1:3)))
}

test_that("selector returns a frozen evaluation, not a second purchase input", {
  selected <- parlay_select_groups(ps_protected_pool(), "coverage", group_budget_cny = 4)
  expect_named(selected, c("evaluation", "selection", "summary", "excluded",
                           "receipt", "diagnostics"))
  expect_null(selected$pool)
  expect_s3_class(selected$summary, "tbl_df")
  expect_identical(selected$evaluation$receipt$producer, "parlay_select_groups")
  expect_identical(selected$evaluation$diagnostics$dynamic_resort, TRUE)
  ps_check_ledger(selected)
})

test_that("shared-ticket protected variants refill quotas before counting cost", {
  for (objective in c("ev", "coverage")) {
    selected <- parlay_select_groups(ps_protected_pool(), objective,
      group_budget_cny = 4)
    expect_gt(nrow(selected$selection), 1L)
    # Every admitted group has two NEW tickets unless its support is exhausted.
    e <- selected$evaluation
    for (i in seq_len(nrow(selected$selection))) {
      id <- selected$selection$group_id[i]
      prior <- selected$selection$group_id[seq_len(i - 1L)]
      previous <- e$purchases$ticket_id[e$purchases$group_id %in% prior]
      legs <- e$portfolio$role_legs[e$portfolio$role_legs$group_id == id, ]
      # Enumerate support directly from masks and canonical physical keys.
      states <- do.call(tidyr::expand_grid, stats::setNames(legs$allowed_outcomes,
                                                          legs$fixture_id))
      keys <- apply(states, 1, function(outcomes)
        parlay_physical_ticket_key(names(states), match(outcomes, match_outcomes())))
      expect_identical(selected$selection$new_ticket_count[i],
                       as.integer(min(2, length(setdiff(keys, previous)))))
    }
    ps_check_ledger(selected)
  }
})

test_that("remaining budget partially funds a group without changing its tickets later", {
  selected <- parlay_select_groups(ps_protected_pool(), "coverage",
    budget_cny = 5, group_budget_cny = 4)
  expect_equal(selected$summary$cost_cny, 4)
  expect_equal(selected$evaluation$summary$unspent_cny, 1)
  expect_equal(nrow(selected$evaluation$purchases), 2)
  expect_true(all(selected$excluded$reason == "budget_exhausted"))
  small <- parlay_select_groups(ps_protected_pool(), "coverage",
    budget_cny = 2, group_budget_cny = 4)
  expect_equal(small$summary$cost_cny, 2)
  expect_equal(nrow(small$evaluation$purchases), 1)
  ps_check_ledger(small)
})

test_that("coverage ranking uses only admitted groups, never rejected EV states", {
  p <- ps_pool(rep("single", 3), n_legs = 2L, pattern = c(1L, 1L),
    max_candidates = NULL, prematch_sp = ps_sp(sprintf("F%02d", 1:3), sp = 2))
  selected <- parlay_select_groups(p, "coverage", min_group_ev_cny = 0,
                                  group_budget_cny = 4)
  expect_gt(nrow(selected$excluded), 0L)
  expect_true(all(selected$selection$new_ev_cny > 0))
  ps_check_ledger(selected)
  # At each admitted step manually compare all remaining new-ticket gains.
  spaces <- .PrepareRankedFunding(.parlay_ranked_validate_pool(p), 4)$spaces
  prior <- character()
  previous_coverage <- 0
  for (i in seq_len(nrow(selected$selection))) {
    for (id in setdiff(names(spaces), selected$selection$group_id[seq_len(i - 1L)])) {
      fresh <- spaces[[id]]$ranked
      fresh <- fresh[!fresh$ticket_id %in% prior, ]
      fresh <- utils::head(fresh, 2)
      if (!nrow(fresh) || sum(fresh$ev_net_est) <= 0) next
      probe <- selected$evaluation
      probe$purchases <- tibble::tibble(ticket_id = c(prior, fresh$ticket_id))
      probe$plan$ticket_legs <- dplyr::bind_rows(
        selected$evaluation$plan$ticket_legs,
        spaces[[id]]$tickets$ticket_legs) |>
        dplyr::distinct(ticket_id, fixture_id, .keep_all = TRUE)
      gain <- ps_exact_coverage(probe) - previous_coverage
      expect_gte(selected$selection$marginal_coverage[i] + 1e-12, gain)
    }
    current <- selected$selection$group_id[i]
    prior <- c(prior, selected$evaluation$purchases$ticket_id[
      selected$evaluation$purchases$group_id == current])
    previous_coverage <- selected$selection$cumulative_coverage[i]
  }
})

test_that("EV is recomputed on actual new tickets including a single payout factor", {
  selected <- parlay_select_groups(ps_protected_pool(), "ev", group_budget_cny = 4)
  e <- selected$evaluation
  # Independently enumerate all 27 physical outcome states from source probabilities.
  p <- e$portfolio$probabilities
  ids <- unique(p$fixture_id)
  states <- do.call(tidyr::expand_grid,
    stats::setNames(rep(list(c("W", "D", "L")), length(ids)), ids))
  mass <- rep(1, nrow(states))
  for (id in ids) {
    block <- p[p$fixture_id == id, ]
    mass <- mass * block$probability[match(states[[id]], block$outcome)]
  }
  ev <- numeric(nrow(e$purchases))
  for (i in seq_len(nrow(e$purchases))) {
    legs <- e$plan$ticket_legs[e$plan$ticket_legs$ticket_id == e$purchases$ticket_id[i], ]
    hit <- rep(TRUE, nrow(states))
    for (j in seq_len(nrow(legs))) {
      hit <- hit & states[[legs$fixture_id[j]]] == legs$outcome[j]
    }
    # All frozen quotes are 6; CNY2 unit, exactly one 0.65 payout factor.
    ev[i] <- sum(mass[hit]) * (2 * 0.65 * 6^nrow(legs)) - 2
  }
  hand_ev <- sum(ev)
  expect_equal(selected$summary$model_ev_cny, hand_ev, tolerance = 1e-10)
  expect_equal(utils::tail(selected$selection$cumulative_ev_cny, 1), hand_ev)
  for (i in seq_len(nrow(selected$selection))) {
    id <- selected$selection$group_id[i]
    expect_equal(selected$selection$new_ev_cny[i],
      sum(ev[e$purchases$group_id == id]), tolerance = 1e-10)
  }
  expect_identical(e$receipt$selection_policy$min_group_ev_cny, 0)
  ps_check_ledger(selected)
})

test_that("actual finite reuse and overlap policies are applied during selection", {
  p <- ps_protected_pool()
  for (policies in list(list(reuse = 1L, overlap = NULL),
                        list(reuse = NULL, overlap = 0L))) {
    selected <- parlay_select_groups(p, "coverage", group_budget_cny = 4,
      reuse_policy = list(max_reuse = policies$reuse),
      overlap_policy = list(max_overlap = policies$overlap))
    expect_identical(selected$summary$selected_groups, 1L)
    expect_true(all(selected$excluded$reason %in%
      c("reuse_cap_exceeded", "overlap_cap_exceeded", "no_new_tickets")))
    ps_check_ledger(selected)
  }
})

test_that("zero group or total cap yields typed empty and no consumed admissions", {
  for (caps in list(list(group = 0, total = NULL),list(group = 4, total = 0))) {
    selected <- parlay_select_groups(ps_protected_pool(), "coverage",
      group_budget_cny = caps$group, budget_cny = caps$total)
    expect_equal(selected$summary$cost_cny, 0)
    expect_equal(selected$summary$coverage, 0)
    expect_identical(selected$summary$selected_groups, 0L)
    expect_s3_class(selected$selection, "tbl_df")
    ps_check_ledger(selected)
  }
})

test_that("NULL group cap means full support and duplicates are bought once", {
  selected <- parlay_select_groups(ps_protected_pool(), "coverage",
                                  group_budget_cny = NULL)
  expect_gt(selected$summary$cost_cny, 0)
  expect_equal(selected$summary$coverage, ps_exact_coverage(selected$evaluation))
  ps_check_ledger(selected)
})

test_that("EV missing SP rejects groups, coverage retains unknown EV", {
  p <- ps_pool(c("triple", "double", "triple", "double"))
  ev <- parlay_select_groups(p, "ev", group_budget_cny = 4)
  expect_identical(ev$summary$selected_groups, 0L)
  expect_true(all(ev$excluded$reason == "ev_unavailable"))
  expect_true(is.na(ev$summary$model_ev_cny))
  cov <- parlay_select_groups(p, "coverage", group_budget_cny = 4)
  expect_gt(cov$summary$selected_groups, 0L)
  expect_true(is.na(cov$summary$model_ev_cny))
  ps_check_ledger(cov)
})

test_that("a rejected high EV floor has no effect on the ledger", {
  selected <- parlay_select_groups(ps_protected_pool(), "ev",
    min_group_ev_cny = 1e6, group_budget_cny = 4)
  expect_identical(selected$summary$selected_groups, 0L)
  expect_true(all(selected$excluded$reason == "group_ev_floor"))
  expect_equal(selected$summary$cost_cny, 0)
  ps_check_ledger(selected)
})

test_that("all candidates belong exactly once to selected or excluded", {
  p <- ps_protected_pool()
  selected <- parlay_select_groups(p, "coverage", budget_cny = 10,
                                  group_budget_cny = 4)
  ids <- c(selected$selection$group_id, selected$excluded$group_id)
  expect_false(anyDuplicated(ids) > 0)
  expect_setequal(ids, p$groups$group_id)
  expect_identical(selected$selection$order, seq_len(nrow(selected$selection)))
  expect_identical(selected$summary$ended_by, "no_admissible_groups")
})

test_that("input identity and cutoff survive selection without mutating pool", {
  p <- ps_protected_pool()
  before <- rlang::hash(p)
  selected <- parlay_select_groups(p, "coverage", group_budget_cny = 4)
  expect_identical(rlang::hash(p), before)
  expect_identical(selected$evaluation$portfolio, p)
  expect_identical(selected$receipt$cutoff, p$cutoff)
  expect_identical(selected$evaluation$cutoff, p$cutoff)
  expect_identical(selected$receipt$evaluation_receipt_hash,
                   rlang::hash(selected$evaluation$receipt))
  changed <- p
  changed$cutoff$cutoff_utc <- p$cutoff$cutoff_utc + 1
  expect_error(parlay_select_groups(changed), "cutoff")
})

test_that("malformed parameters and altered frozen inputs fail closed", {
  p <- ps_protected_pool()
  expect_error(parlay_select_groups(list()))
  expect_error(parlay_select_groups(p, "sharpe"))
  for (floor in list(NA_real_, Inf, c(1,2), "0")) {
    expect_error(parlay_select_groups(p, min_group_ev_cny = floor))
  }
  expect_error(parlay_select_groups(p, budget_cny = -1))
  expect_error(parlay_select_groups(p, reuse_policy = list(max_reuse = 0)))
  expect_error(parlay_select_groups(p, overlap_policy = list(max_overlap = -1)))
  p$prematch_sp$sp_raw[1] <- 99
  expect_error(parlay_select_groups(p), "prematch_sp")
})

test_that("selector evaluation receipts reject changed physical ledgers and producers", {
  selected <- parlay_select_groups(ps_protected_pool(), "coverage", group_budget_cny = 4)
  e <- selected$evaluation
  e$purchases$cost_cny[1] <- 4
  expect_error(.parlay_ranked_validate_evaluation(e), "binding")
  e <- selected$evaluation
  e$receipt$producer <- "unknown"
  expect_error(.parlay_ranked_validate_evaluation(e), "producer")
})

test_that("default evaluator still uses nominal order through shared finalizer", {
  p <- ps_protected_pool()
  e <- parlay_evaluate_portfolio(p, group_budget_cny = 4,
    reuse_policy = list(max_reuse = NULL),overlap_policy = list(max_overlap = NULL),
    improve = FALSE)
  expect_identical(e$receipt$producer, "parlay_evaluate_portfolio")
  expect_false(e$diagnostics$dynamic_resort)
  expect_silent(.parlay_ranked_validate_evaluation(e))
  expect_equal(e$summary$actual_coverage, ps_exact_coverage(e))
})
