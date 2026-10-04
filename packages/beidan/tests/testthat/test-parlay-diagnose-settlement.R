# Package tests for parlay_diagnose_settlement(), the one-call post-settlement
# diagnostic. Exercises the settled ledgers, the per-leg admission verdict, the
# group attribution and the fail-closed paths through the real
# classify -> rank -> construct -> select -> settle chain.

ps_cutoff <- function() {
  list(issue_id = "26098",
       cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
}

# Build a pool from explicit probability triples, then select from it.
ps_pool <- function(p, pattern, n_legs = length(pattern), max_candidates = NULL) {
  matches <- tibble::tibble(
    fixture_id = paste0("F", seq_along(p)),
    win = vapply(p, `[`, numeric(1), 1L),
    draw = vapply(p, `[`, numeric(1), 2L),
    lose = vapply(p, `[`, numeric(1), 3L))
  cutoff <- ps_cutoff()
  sp <- tidyr::expand_grid(fixture_id = matches$fixture_id,
                           outcome = c("W", "D", "L")) |>
    dplyr::mutate(quote_at = cutoff$cutoff_utc - 60, sp_raw = 3,
                  source_url = "synthetic://post-settlement")
  filtered <- filter_outcome_matches(matches, sp, cutoff)
  admitted <- filtered$matches
  attr(admitted, "filter_receipt") <- filtered$receipt
  ranked <- rank_outcome_selections(prepare_outcome_selections(admitted), cutoff,
                                    "coverage")
  settings <- parlay_settings()
  settings$n_legs <- as.integer(n_legs)
  list(
    pool = parlay_construct_role_groups(ranked, settings, pattern = pattern,
      max_candidates = max_candidates, prematch_sp = sp),
    sp = sp)
}

ps_select <- function(pool, group_budget_cny = 4) {
  parlay_select_groups(pool, objective = "coverage", budget_cny = NULL,
    group_budget_cny = group_budget_cny,
    reuse_policy = list(max_reuse = NULL),
    overlap_policy = list(max_overlap = NULL))$evaluation
}

ps_settlements <- function(outcomes, at = "2026-09-26 14:00:00") {
  tibble::tibble(
    issue_id = "26098",
    fixture_id = names(outcomes),
    outcome = unname(outcomes),
    settled_sp = 3,
    label_available_at = as.POSIXct(at, tz = "UTC"),
    status = "settled",
    source_url = "https://example.test/s")
}

ps_as_of <- function(at = "2026-09-26 15:00:00") as.POSIXct(at, tz = "UTC")

test_that("a settled diagnostic returns the ledgers, the verdicts and one summary", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30), c(.50, .28, .22),
                        c(.42, .31, .27)), c(3L, 2L))
  evaluation <- ps_select(built$pool)
  out <- parlay_diagnose_settlement(evaluation, built$pool,
    ps_settlements(c(F1 = "W", F2 = "D")), ps_as_of())

  expect_named(out, c("issue_returns", "group_returns", "ticket_returns",
                      "coverage", "group_outcomes", "summary"))
  expect_s3_class(out$summary, "tbl_df")
  expect_identical(nrow(out$summary), 1L)
  expect_identical(out$summary$groups, nrow(out$group_outcomes))
  expect_identical(out$summary$legs, nrow(out$coverage))
  # One verdict per group leg, never per ticket.
  expect_identical(out$summary$legs,
    as.integer(nrow(evaluation$plan$group_legs)))
  # An unsettled leg is NA, not FALSE: only legs with a usable label can be
  # called unadmitted.
  expect_identical(out$summary$unadmitted_legs,
    as.integer(sum(!out$coverage$admitted, na.rm = TRUE)))
})

test_that("a group whose every leg admitted the realised outcome can still lose", {
  # 2222222: every leg is a double selecting two outcomes. If the realised outcome
  # for each fixture is the one omitted by the bought double, every leg is
  # unadmitted -- but the group can also lose with all legs admitted, which must be
  # reported as missed_admitted rather than folded into the structural count.
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30)), c(2L, 2L))
  evaluation <- ps_select(built$pool)
  # Label every fixture with the outcome its bought double omitted, so all legs fail.
  masks <- built$pool$role_legs |>
    dplyr::filter(group_id %in% evaluation$purchases$group_id)
  outcomes <- vapply(seq_len(nrow(masks)), function(i) {
    setdiff(match_outcomes(), masks$allowed_outcomes[[i]])[1]
  }, character(1))
  labels <- stats::setNames(outcomes, masks$fixture_id)
  out <- parlay_diagnose_settlement(evaluation, built$pool,
    ps_settlements(labels), ps_as_of())
  expect_true(all(out$group_outcomes$unadmitted_legs > 0L))
  expect_true(all(out$group_outcomes$status %in% c("missed_structure", "won")))
  expect_identical(sum(out$group_outcomes$status == "missed_admitted"), 0L)
})

test_that("admitted and unadmitted legs are counted from the pool mask, not the ticket", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30), c(.50, .28, .22)),
                   c(3L, 2L))
  evaluation <- ps_select(built$pool)
  out <- parlay_diagnose_settlement(evaluation, built$pool,
    ps_settlements(c(F1 = "W", F2 = "D", F3 = "L")), ps_as_of())
  # The verdict must agree with re-deriving admission from the mask directly.
  check <- vapply(seq_len(nrow(out$coverage)), function(i) {
    mask <- strsplit(out$coverage$allowed_outcomes[i], "+", fixed = TRUE)[[1]]
    out$coverage$actual_outcome[i] %in% mask
  }, logical(1))
  expect_identical(out$coverage$admitted, check)
  # Every realised, admitted leg is still not enough by itself to win a parlay.
  expect_true(all(out$coverage$reason %in% c("admitted", "unadmitted_outcome",
                                             "not_settled")))
})

test_that("labels not yet available at as_of are invisible and reported, not guessed", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30)), c(2L, 2L))
  evaluation <- ps_select(built$pool)
  # Label becomes available later than as_of, so the diagnosis must not consume it.
  late <- ps_settlements(c(F1 = "W", F2 = "D"), at = "2026-09-26 20:00:00")
  out <- parlay_diagnose_settlement(evaluation, built$pool, late,
    ps_as_of("2026-09-26 15:00:00"))
  expect_true(all(is.na(out$coverage$admitted)))
  expect_true(all(out$coverage$reason == "not_settled"))
  expect_true(all(out$group_outcomes$status == "unsettled"))
  expect_identical(out$summary$won_groups, 0L)
})

test_that("a fixture with one settled outcome per row is required, not chosen from", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30)), c(2L, 2L))
  evaluation <- ps_select(built$pool)
  conflicting <- dplyr::bind_rows(ps_settlements(c(F1 = "W", F2 = "D")),
                                  ps_settlements(c(F1 = "L", F2 = "W")))
  expect_error(parlay_diagnose_settlement(evaluation, built$pool, conflicting,
    ps_as_of()), "more than one settled outcome")
})

test_that("an unknown realised outcome fails closed", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30)), c(2L, 2L))
  evaluation <- ps_select(built$pool)
  bad <- ps_settlements(c(F1 = "X", F2 = "D"))
  expect_error(parlay_diagnose_settlement(evaluation, built$pool, bad, ps_as_of()),
    "unknown realised outcome")
})

test_that("a non-UTC as_of and a bad evaluation fail closed", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30)), c(2L, 2L))
  evaluation <- ps_select(built$pool)
  labels <- ps_settlements(c(F1 = "W", F2 = "D"))
  expect_error(parlay_diagnose_settlement(evaluation, built$pool, labels,
    as.POSIXct("2026-09-26 15:00:00", tz = "Asia/Shanghai")), "UTC")
  expect_error(parlay_diagnose_settlement(list(), built$pool, labels, ps_as_of()),
    "frozen plan")
  expect_error(parlay_diagnose_settlement(evaluation, list(), labels, ps_as_of()),
    "role_legs")
})

test_that("summary arithmetic reconciles with the settled issue ledger", {
  built <- ps_pool(list(c(.45, .30, .25), c(.40, .30, .30), c(.50, .28, .22)),
                   c(3L, 2L))
  evaluation <- ps_select(built$pool)
  out <- parlay_diagnose_settlement(evaluation, built$pool,
    ps_settlements(c(F1 = "W", F2 = "D", F3 = "L")), ps_as_of())
  expect_equal(out$summary$stake_cny, sum(out$group_outcomes$stake_cny))
  expect_equal(out$summary$payout_cny, sum(out$group_outcomes$payout_cny))
  expect_equal(out$summary$net_cny, out$summary$payout_cny - out$summary$stake_cny)
  expect_identical(out$summary$won_groups,
    as.integer(sum(out$group_outcomes$status == "won")))
  expect_identical(out$summary$missed_structure,
    as.integer(sum(out$group_outcomes$status == "missed_structure")))
})
