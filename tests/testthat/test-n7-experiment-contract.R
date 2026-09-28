# Tests for r/n7_experiment_contract.R.
#
# These pin the rules a replay can get silently wrong: the epoch conversion, the
# half-open forward window and the stop-sale boundary, the strictly
# backwards-looking snapshot choice, the fixed SP-estimate rule, the period
# budget ledger that is never reset per day, the group identity that makes
# "deepening the same group" different from "opening a new group", and the typed
# empty contract.

source(testthat::test_path("..", "..", "r", "n7_fixture_portfolio.R"))
source(testthat::test_path("..", "..", "r", "n7_experiment_contract.R"))

testthat::test_that("n7_decision_epoch converts the local decision hour to UTC", {
  expect_equal(n7_decision_epoch("2026-05-02"), "2026-05-02T12:00:00Z")
  expect_equal(n7_decision_epoch("2026-05-02", hour = 0L), "2026-05-01T16:00:00Z")
  expect_equal(n7_decision_epoch("2026-05-02", hour = 23L), "2026-05-02T15:00:00Z")
  # The same instant read back in the local zone is the requested hour.
  back <- as.POSIXct(n7_decision_epoch("2026-05-02"),
                     format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  expect_equal(format(back, "%H:%M", tz = "Asia/Shanghai"), "20:00")
  expect_equal(format(back, "%Y-%m-%d", tz = "Asia/Shanghai"), "2026-05-02")
})

testthat::test_that("n7_decision_epoch fails closed on malformed input", {
  expect_error(n7_decision_epoch("2026/05/02"), "YYYY-MM-DD")
  expect_error(n7_decision_epoch("20260502"), "YYYY-MM-DD")
  expect_error(n7_decision_epoch(c("2026-05-02", "2026-05-03")), "one YYYY-MM-DD")
  expect_error(n7_decision_epoch(NA_character_), "YYYY-MM-DD")
  expect_error(n7_decision_epoch("2026-05-02", hour = 24L), "0..23")
  expect_error(n7_decision_epoch("2026-05-02", hour = 20.5), "0..23")
  expect_error(n7_decision_epoch("2026-05-02", tz = ""), "timezone")
  expect_error(n7_decision_epoch("2026-05-02", tz = "Not/AZone"), "timezone")
})

testthat::test_that("n7_decision_epochs is one epoch per local date", {
  expect_equal(n7_decision_epochs(c("2026-05-02", "2026-05-03")),
               c("2026-05-02T12:00:00Z", "2026-05-03T12:00:00Z"))
  expect_error(n7_decision_epochs(character(0)), "non-empty")
})

testthat::test_that("n7_utc_seconds and n7_utc_iso round-trip and reject drift", {
  expect_equal(n7_utc_seconds("1970-01-01T00:00:00Z"), 0)
  expect_equal(n7_utc_seconds("2026-05-02T12:00:00Z"), 1777723200)
  expect_equal(n7_utc_iso(0), "1970-01-01T00:00:00Z")
  expect_equal(n7_utc_iso(n7_utc_seconds("2026-05-02T12:00:00Z")), "2026-05-02T12:00:00Z")
  expect_error(n7_utc_seconds("2026-05-02 12:00:00"), "ISO-8601")
  expect_error(n7_utc_seconds("2026-05-02T12:00:00+08:00"), "ISO-8601")
  expect_error(n7_utc_iso(NA_real_), "finite")
})

testthat::test_that("n7_epoch_date maps a kickoff to the preceding local date", {
  # A kickoff at 2026-05-02 19:00Z is 2026-05-03 03:00 Beijing, so its decision
  # epoch is the 2026-05-02 20:00 local window.
  expect_equal(n7_epoch_date("2026-05-02T19:00:00Z"), "2026-05-02")
  # A kickoff at exactly the next local midnight belongs to the same window.
  expect_equal(n7_epoch_date("2026-05-02T16:00:00Z"), "2026-05-02")
  # One second before that midnight is still the previous local day.
  expect_equal(n7_epoch_date("2026-05-02T15:59:59Z"), "2026-05-01")
  # Month and year transitions use the calendar, not a 24h subtraction.
  expect_equal(n7_epoch_date("2026-06-01T02:00:00Z"), "2026-05-31")
  expect_equal(n7_epoch_date("2027-01-01T02:00:00Z"), "2026-12-31")
  # It round-trips against the window it implies.
  kickoff <- "2026-05-02T19:00:00Z"
  epoch <- n7_decision_epoch(n7_epoch_date(kickoff))
  w <- n7_decision_window(epoch)
  expect_true(kickoff >= w$start_utc && kickoff < w$end_utc)
  # A bad zone must stop rather than silently fall back to UTC.
  expect_error(n7_epoch_date("2026-05-02T19:00:00Z", tz = "Not/AZone"), "Olson")
  expect_error(n7_epoch_date("2026-05-02T19:00:00"), "could not be parsed")
  expect_error(n7_epoch_date(NA_character_), "non-missing")
})

testthat::test_that("the eligible contract template matches the real output", {
  # The typed empty template must be usable as the schema of real output; a
  # leftover column from a deleted rule would break that silently.
  epoch <- "2026-05-02T12:00:00Z"
  out <- n7_eligible_fixtures(
    tibble::tibble(match_id = "a", issue = "26051",
                   kickoff_utc = "2026-05-02T19:00:00Z"), epoch)
  template <- n7_contract_templates()$eligible
  expect_identical(sort(names(out$eligible)), sort(names(template)))
  expect_identical(sort(names(out$excluded)), sort(names(template)))
  expect_equal(nrow(template), 0L)
  # The template must validate without error; that is the schema contract.
  expect_error(n7_validate_contract(n7_contract_templates()), NA)
  # ZERO-ROW input must keep the same schema: ifelse() on an empty vector returns
  # logical(0), which would silently change the type of `reason`.
  empty <- n7_eligible_fixtures(
    tibble::tibble(match_id = character(), issue = character(),
                   kickoff_utc = character()), epoch)
  expect_equal(nrow(empty$eligible), 0L)
  expect_equal(nrow(empty$excluded), 0L)
  expect_identical(sort(names(empty$eligible)), sort(names(template)))
  expect_identical(sort(names(empty$excluded)), sort(names(template)))
  expect_type(empty$eligible$reason, "character")
  expect_type(empty$excluded$reason, "character")
  # Real populated output validates against the same contract.
  full <- n7_contract_templates()
  full$eligible <- out$eligible
  expect_error(n7_validate_contract(full), NA)
})

testthat::test_that("n7_decision_window is the next local calendar day", {
  # 2026-05-02 20:00 Asia/Shanghai is 2026-05-02T12:00:00Z. The window is the next
  # natural day: 2026-05-03 00:00 CST to 2026-05-04 00:00 CST.
  w <- n7_decision_window("2026-05-02T12:00:00Z")
  expect_equal(w$start_utc, "2026-05-02T16:00:00Z")
  expect_equal(w$end_utc, "2026-05-03T16:00:00Z")
  # The two declared hour offsets are the same rule, not a second definition.
  start_h <- (n7_utc_seconds(w$start_utc) - n7_utc_seconds("2026-05-02T12:00:00Z")) / 3600
  end_h <- (n7_utc_seconds(w$end_utc) - n7_utc_seconds("2026-05-02T12:00:00Z")) / 3600
  expect_equal(start_h, N7_WINDOW_START_HOURS)
  expect_equal(end_h, N7_WINDOW_END_HOURS)
  # It is a natural day, i.e. exactly 24 hours wide.
  expect_equal(n7_utc_seconds(w$end_utc) - n7_utc_seconds(w$start_utc), 24 * 3600)
  expect_error(n7_decision_window("2026-05-02T12:00:00Z", tz = "Not/AZone"), "Olson")
})

testthat::test_that("n7_eligible_fixtures enforces the natural-day window half-open", {
  epoch <- "2026-05-02T12:00:00Z"
  at <- function(offset_seconds) n7_utc_iso(n7_utc_seconds(epoch) + offset_seconds)
  fixtures <- tibble::tibble(
    match_id = c("before", "start", "mid", "last", "end"),
    issue = "26051",
    kickoff_utc = c(at(4 * 3600 - 1), at(4 * 3600), at(16 * 3600),
                    at(28 * 3600 - 1), at(28 * 3600)))
  out <- n7_eligible_fixtures(fixtures, epoch)
  # Start is INCLUSIVE, end is EXCLUSIVE: a kickoff at the next local midnight is
  # decided at this epoch, one at the following midnight is not.
  expect_equal(out$eligible$match_id, c("start", "mid", "last"))
  expect_equal(out$excluded$reason,
               c("KICKOFF_BEFORE_WINDOW", "KICKOFF_AT_OR_AFTER_WINDOW"))
  expect_equal(out$eligible$hours_to_kickoff, c(4, 16, 28 - 1 / 3600))
  expect_true(all(out$eligible$hours_to_kickoff >= N7_WINDOW_START_HOURS))
  expect_true(all(out$eligible$hours_to_kickoff < N7_WINDOW_END_HOURS))
  # No fixture is admitted on a stop-sale minute rule any more: the contract
  # retired that presumption, so the admitted set is exactly the window set.
  expect_false("STOP_SALE_ALREADY_PASSED" %in% out$excluded$reason)
  expect_true(all(out$eligible$sale_state == "UNKNOWN"))
})

testthat::test_that("n7_eligible_fixtures validates its inputs and keeps identity", {
  fixtures <- tibble::tibble(match_id = "a", issue = "26051",
                             kickoff_utc = "2026-05-02T18:00:00Z")
  expect_error(n7_eligible_fixtures(fixtures, "2026-05-02T12:00:00"), "ISO-8601")
  expect_error(n7_eligible_fixtures(fixtures, "2026-05-02T12:00:00Z", tz = "Not/AZone"),
               "Olson")
  expect_error(n7_eligible_fixtures(
    tibble::tibble(match_id = c("a", "a"), issue = "26051",
                   kickoff_utc = c("2026-05-02T18:00:00Z", "2026-05-02T19:00:00Z")),
    "2026-05-02T12:00:00Z"), "unique")
  # Issue codes are identifiers and are not coerced.
  out <- n7_eligible_fixtures(
    tibble::tibble(match_id = "026051_001", issue = "026051",
                   kickoff_utc = "2026-05-02T18:00:00Z"), "2026-05-02T12:00:00Z")
  expect_identical(out$eligible$issue, "026051")
  expect_identical(out$eligible$match_id, "026051_001")
})

testthat::test_that("a recorded cutoff is an anomaly check, not an admission gate", {
  epoch <- "2026-05-02T12:00:00Z"
  at <- function(secs) n7_utc_iso(n7_utc_seconds(epoch) + secs)
  # All four kick off inside the window. Their recorded cutoffs differ widely,
  # including 5 / 20 / 25 minutes before kickoff, and one is absent entirely.
  # Under the retired minute-threshold rule these would have been treated
  # differently; now NONE of them is excluded on that basis.
  fixtures <- tibble::tibble(
    match_id = c("lead5", "lead20", "lead25", "no_cutoff"),
    issue = "26051",
    kickoff_utc = c(at(20 * 3600), at(20 * 3600), at(20 * 3600), at(20 * 3600)),
    sale_cutoff_utc = c(at(20 * 3600 - 5 * 60), at(20 * 3600 - 20 * 60),
                        at(20 * 3600 - 25 * 60), NA_character_))
  out <- n7_eligible_fixtures(fixtures, epoch)
  expect_equal(nrow(out$eligible), 4L)
  expect_equal(nrow(out$excluded), 0L)
  # Moving the epoch onto each cutoff does NOT close the fixture: the contract
  # retired the per-minute stop-sale presumption, so this must not gate.
  for (i in seq_len(3L)) {
    cut <- n7_utc_seconds(fixtures$sale_cutoff_utc[i])
    one <- n7_eligible_fixtures(fixtures[i, ], n7_utc_iso(cut))
    expect_equal(nrow(one$eligible), 0L)
    expect_equal(one$excluded$reason, "KICKOFF_BEFORE_WINDOW")
  }
  # A cutoff AFTER the kickoff still contradicts the stored kickoff, and that
  # schedule anomaly is excluded and counted.
  contradicted <- tibble::tibble(
    match_id = "bad", issue = "26051", kickoff_utc = at(20 * 3600),
    sale_cutoff_utc = at(20 * 3600 + 60))
  bad <- n7_eligible_fixtures(contradicted, epoch)
  expect_equal(nrow(bad$eligible), 0L)
  expect_equal(bad$excluded$reason, "KICKOFF_CONTRADICTED_BY_SALE_CUTOFF")
})

testthat::test_that("explicit sale-state evidence excludes and unknown state is recorded", {
  epoch <- "2026-05-02T12:00:00Z"
  at <- function(hours) n7_utc_iso(n7_utc_seconds(epoch) + hours * 3600)
  fixtures <- tibble::tibble(
    match_id = c("ok", "unknown", "stopped", "suspended", "cancelled", "moved"),
    issue = "26051",
    kickoff_utc = rep(at(20), 6),
    sale_state = c("ON_SALE", NA_character_, "NOT_FOR_SALE", "SUSPENDED",
                   "CANCELLED", "RESCHEDULED"))
  out <- n7_eligible_fixtures(fixtures, epoch)
  # A missing value means no evidence, which is UNKNOWN, not "sellable".
  expect_equal(out$eligible$match_id, c("ok", "unknown"))
  expect_equal(out$eligible$sale_state, c("ON_SALE", "UNKNOWN"))
  expect_equal(out$excluded$match_id, c("stopped", "suspended", "cancelled", "moved"))
  expect_equal(out$excluded$reason,
               c("SALE_STATE_NOT_FOR_SALE", "SALE_STATE_SUSPENDED",
                 "SALE_STATE_CANCELLED", "SALE_STATE_RESCHEDULED"))
  # No column at all means no evidence was supplied: everything is UNKNOWN and
  # nothing is silently claimed as verified sellable.
  bare <- n7_eligible_fixtures(fixtures[, c("match_id", "issue", "kickoff_utc")], epoch)
  expect_equal(nrow(bare$eligible), 6L)
  expect_true(all(bare$eligible$sale_state == "UNKNOWN"))
  # An unrecognised state is a contract failure, not a silent admission.
  expect_error(
    n7_eligible_fixtures(
      tibble::tibble(match_id = "x", issue = "26051", kickoff_utc = at(20),
                     sale_state = "MAYBE"), epoch),
    "unknown sale_state")
})

testthat::test_that("n7_local_to_utc_iso converts declared local time strictly", {
  # 20:00 Asia/Shanghai is 12:00Z; the zone has no DST so this is exact.
  expect_equal(n7_local_to_utc_iso("2026-05-02 20:00"), "2026-05-02T12:00:00Z")
  expect_equal(n7_local_to_utc_iso("2026-05-02 20:00", tz = "UTC"),
               "2026-05-02T20:00:00Z")
  expect_equal(n7_local_to_utc_iso(c("2026-05-02 20:00", "2026-05-03 00:00")),
               c("2026-05-02T12:00:00Z", "2026-05-02T16:00:00Z"))
  # A trailing Z would be read as local and shift the instant, so it stops.
  expect_error(n7_local_to_utc_iso("2026-05-02T20:00:00Z"), "local strings")
  expect_error(n7_local_to_utc_iso("2026-05-02"), "local strings")
  expect_error(n7_local_to_utc_iso(NA_character_), "local strings")
  expect_error(n7_local_to_utc_iso("2026-05-02 20:00", tz = "Not/AZone"), "Olson")
})

testthat::test_that("n7_select_snapshots is strictly backwards-looking", {
  epoch <- "2026-05-02T12:00:00Z"
  eligible <- tibble::tibble(match_id = c("a", "b"), issue = "26051",
                             kickoff_utc = c("2026-05-02T18:00:00Z", "2026-05-02T19:00:00Z"),
                             epoch_utc = epoch)
  snapshots <- tibble::tibble(
    match_id = c("a", "a", "a", "b", "b"),
    snapshot_ts = c("2026-05-02T10:00:00Z", "2026-05-02T11:59:59Z",
                    "2026-05-02T12:00:01Z", "2026-05-02T12:00:02Z",
                    "2026-05-02T11:00:00Z"),
    eu_h = c(1.5, 1.6, 1.7, 2.0, 2.1),
    eu_d = c(3.5, 3.6, 3.7, 3.2, 3.3),
    eu_a = c(6.0, 5.5, 5.0, 3.4, 3.5),
    source = "merged",
    sp_3 = c(2, 2.1, 2.2, 3, 3.1), sp_1 = c(4, 4.1, 4.2, 5, 5.1),
    sp_0 = c(6, 6.1, 6.2, 7, 7.1))
  out <- n7_select_snapshots(snapshots, eligible, epoch)
  expect_equal(nrow(out$priced), 2L)
  # a must take the 11:59:59 poll, never the 12:00:01 one that came after.
  a <- out$priced[out$priced$match_id == "a", ]
  expect_equal(a$quote_utc, "2026-05-02T11:59:59Z")
  expect_equal(a$lag_seconds, 1)
  expect_equal(a$previous_quote_utc, "2026-05-02T10:00:00Z")
  expect_equal(a$interval_seconds, 7199)
  expect_equal(a$eu_h, 1.6)
  expect_equal(a$source, "merged")
  # b's only pre-epoch poll is the chosen one, so the interval is an explicit NA.
  b <- out$priced[out$priced$match_id == "b", ]
  expect_equal(b$quote_utc, "2026-05-02T11:00:00Z")
  expect_true(is.na(b$previous_quote_utc))
  expect_true(is.na(b$interval_seconds))
  expect_equal(nrow(out$excluded), 0L)
})

testthat::test_that("n7_select_snapshots reports every availability failure separately", {
  epoch <- "2026-05-02T12:00:00Z"
  eligible <- tibble::tibble(match_id = c("none", "late", "bad", "ok"), issue = "26051",
                             kickoff_utc = "2026-05-02T18:00:00Z", epoch_utc = epoch)
  snapshots <- tibble::tibble(
    match_id = c("late", "bad", "ok"),
    snapshot_ts = c("2026-05-02T13:00:00Z", "2026-05-02T11:00:00Z", "2026-05-02T11:00:00Z"),
    eu_h = c(1.5, NA, 1.5), eu_d = c(3.5, 3.5, 3.5), eu_a = c(6, 6, 6),
    source = "merged", sp_3 = c(2, 2, 2), sp_1 = c(3, 3, 3), sp_0 = c(4, 4, 4))
  out <- n7_select_snapshots(snapshots, eligible, epoch)
  expect_equal(sort(out$excluded$reason),
               c("NO_PRE_EPOCH_SNAPSHOT", "NO_SNAPSHOT_AT_ALL", "NO_USABLE_ODDS_SNAPSHOT"))
  expect_equal(out$priced$match_id, "ok")
})

testthat::test_that("n7_select_snapshots fails closed on duplicate keys and bad times", {
  epoch <- "2026-05-02T12:00:00Z"
  eligible <- tibble::tibble(match_id = "a", issue = "26051",
                             kickoff_utc = "2026-05-02T18:00:00Z", epoch_utc = epoch)
  dup <- tibble::tibble(match_id = c("a", "a"), snapshot_ts = c("2026-05-02T11:00:00Z",
                                                                "2026-05-02T11:00:00Z"),
                        eu_h = 1.5, eu_d = 3.5, eu_a = 6, source = "merged",
                        sp_3 = 2, sp_1 = 3, sp_0 = 4)
  expect_error(n7_select_snapshots(dup, eligible, epoch), "unique")
  naive <- tibble::tibble(match_id = "a", snapshot_ts = "2026-05-02 11:00:00",
                          eu_h = 1.5, eu_d = 3.5, eu_a = 6, source = "merged",
                          sp_3 = 2, sp_1 = 3, sp_0 = 4)
  expect_error(n7_select_snapshots(naive, eligible, epoch), "ISO-8601")
})

testthat::test_that("n7_select_snapshots refuses conflicting quotes at one instant", {
  epoch <- "2026-05-02T12:00:00Z"
  eligible <- tibble::tibble(match_id = "a", issue = "T",
                             kickoff_utc = "2026-05-02T18:00:00Z")
  agree <- tibble::tibble(
    match_id = "a", snapshot_ts = "2026-05-02T11:00:00Z",
    eu_h = c(1.6, 1.6), eu_d = c(3.9, 3.9), eu_a = c(5.5, 5.5),
    source = c("s1", "s2"), sp_3 = 2, sp_1 = 3, sp_0 = 4)
  # Two sources quoting the SAME numbers are one observation, not a conflict.
  expect_equal(n7_select_snapshots(agree, eligible, epoch)$priced$eu_h, 1.6)
  # Two sources quoting DIFFERENT numbers have no declared policy, so the result
  # must not depend on which row happens to come first.
  conflict <- agree
  conflict$eu_h[2L] <- 1.7
  expect_error(n7_select_snapshots(conflict, eligible, epoch), "conflicting quotes")
  expect_error(n7_select_snapshots(conflict[2:1, ], eligible, epoch), "conflicting quotes")
  # Identical 1X2 with DIFFERENT SP is still a conflict: the estimated return
  # consumes the SP, so row order must not be able to change it.
  sp_conflict <- agree
  sp_conflict$sp_1[2L] <- 9
  expect_error(n7_select_snapshots(sp_conflict, eligible, epoch), "conflicting quotes")
  expect_error(n7_select_snapshots(sp_conflict[2:1, ], eligible, epoch), "conflicting quotes")
  # A missingness difference is a conflict too.
  na_conflict <- agree
  na_conflict$sp_0[2L] <- NA_real_
  expect_error(n7_select_snapshots(na_conflict, eligible, epoch), "conflicting quotes")
})

testthat::test_that("n7_sp_estimate is the fixed >10 rule, not a cap", {
  expect_equal(n7_sp_estimate(c(3.4, 10, 10.0001, 25, NA)), c(3.4, 10, 4.5, 4.5, NA))
  # The rule is applied per single fixture/outcome value.
  expect_equal(n7_sp_estimate(1.01), 1.01)
  expect_equal(n7_sp_estimate(1e6), 4.5)
  expect_true(is.na(n7_sp_estimate(NA_real_)))
  expect_error(n7_sp_estimate(0), "positive")
  expect_error(n7_sp_estimate(-1), "positive")
  expect_error(n7_sp_estimate(2, threshold = 0), "positive")
  expect_error(n7_sp_estimate(2, value = -1), "positive")
  expect_error(n7_sp_estimate("2"), "numeric")
})

testthat::test_that("n7_stake_cny and n7_affordable_tickets use the 2 CNY unit", {
  expect_equal(n7_stake_cny(c(0, 1, 512)), c(0, 2, 1024))
  expect_equal(n7_affordable_tickets(c(0, 1, 2, 1023, 1024)), c(0L, 0L, 1L, 511L, 512L))
  expect_error(n7_stake_cny(1.5), "whole")
  expect_error(n7_stake_cny(-1), "whole")
  expect_error(n7_affordable_tickets(-1), "non-negative")
})

testthat::test_that("n7_budget_ledger carries the balance across days and never resets", {
  ledger <- n7_budget_ledger(c(512, 256, 256))
  expect_equal(ledger$cumulative_stake_cny, c(512, 768, 1024))
  expect_equal(ledger$remaining_before_cny, c(1024, 512, 256))
  expect_equal(ledger$remaining_after_cny, c(512, 256, 0))
  expect_equal(ledger$affordable_tickets_after, c(256L, 128L, 0L))
  expect_equal(ledger$exhausted, c(FALSE, FALSE, TRUE))
  # The balance is a ceiling, not a per-day allowance: a second day sees what the
  # first day left, and an empty ledger is an empty typed table.
  expect_equal(nrow(n7_budget_ledger(numeric(0))), 0L)
  expect_error(n7_budget_ledger(c(512, 514)), "exceeds")
  expect_error(n7_budget_ledger(3), "whole multiple")
  expect_error(n7_budget_ledger(-2), "non-negative")
  expect_error(n7_budget_ledger(2, budget_cny = 0), "positive")
})

testthat::test_that("n7_group_key and n7_physical_ticket_key are order independent", {
  ids <- sprintf("m%d", 1:7)
  expect_equal(n7_group_key(ids), n7_group_key(rev(ids)))
  expect_equal(n7_group_key(ids), paste(sort(ids), collapse = "|"))
  expect_error(n7_group_key(ids[1:6]), "7 distinct")
  expect_error(n7_group_key(c(ids[1:6], ids[1])), "7 distinct")
  expect_error(n7_group_key(c(ids[1:6], NA_character_)), "7 distinct")
  # Two different outcome tuples over the same seven fixtures are different
  # physical tickets; the same tuples in another order are the same ticket.
  a <- n7_physical_ticket_key(ids, c(1, 1, 1, 1, 1, 1, 1))
  b <- n7_physical_ticket_key(rev(ids), rep(1, 7))
  d <- n7_physical_ticket_key(ids, c(1, 1, 1, 1, 1, 1, 2))
  expect_equal(a, b)
  expect_false(a == d)
  expect_error(n7_physical_ticket_key(ids, rep(4, 7)), "1..3")
  expect_error(n7_physical_ticket_key(ids, rep(1, 6)), "7 aligned")
})

testthat::test_that("n7_group_admission separates deepening from a new group", {
  base <- sprintf("m%d", 1:7)
  other <- sprintf("m%d", 8:14)
  # The same fixture set, in another order, is the same group: deepening.
  same <- n7_group_admission(list(base), rev(base), max_reuse = 1L, max_overlap = 0L)
  expect_true(same$admitted)
  expect_false(same$is_new_group)
  expect_equal(same$reason, "SAME_GROUP_DEEPENING")
  # A disjoint group is new and admissible under max_reuse = 1.
  fresh <- n7_group_admission(list(base), other, max_reuse = 1L, max_overlap = 0L)
  expect_true(fresh$admitted)
  expect_true(fresh$is_new_group)
  expect_equal(fresh$reason, "ADMITTED")
  expect_equal(fresh$max_uses_after, 1L)
  expect_equal(fresh$max_overlap_seen, 0L)
  # Reusing one fixture beyond the cap is refused.
  reuse <- n7_group_admission(list(base), c(base[1], other[1:6]),
                              max_reuse = 1L, max_overlap = 1L)
  expect_false(reuse$admitted)
  expect_equal(reuse$reason, "FIXTURE_REUSE_CAP_EXCEEDED")
  expect_equal(reuse$max_uses_after, 2L)
  # Overlap with an earlier group beyond the cap is refused even when the reuse
  # count of every fixture is still inside max_reuse.
  overlap <- n7_group_admission(list(base, other), c(base[1:3], other[1:4]),
                                max_reuse = 3L, max_overlap = 2L)
  expect_false(overlap$admitted)
  expect_equal(overlap$reason, "GROUP_OVERLAP_CAP_EXCEEDED")
  expect_equal(overlap$max_overlap_seen, 4L)
  # With no prior group there is nothing to overlap with.
  none <- n7_group_admission(list(), base, max_reuse = 1L, max_overlap = 0L)
  expect_true(none$admitted)
  expect_equal(none$max_overlap_seen, 0L)
  expect_error(n7_group_admission(list(base), base, max_reuse = 0L, max_overlap = 0L),
               "at least 1")
  expect_error(n7_group_admission(list(base), base, max_reuse = 1L, max_overlap = 8L),
               "0..7")
})

testthat::test_that("n7_ticket_admission refuses a repeated physical ticket", {
  a <- n7_physical_ticket_key(sprintf("m%d", 1:7), rep(1, 7))
  b <- n7_physical_ticket_key(sprintf("m%d", 1:7), rep(2, 7))
  out <- n7_ticket_admission(a, c(a, b))
  expect_equal(out$duplicate_of_period, c(TRUE, FALSE))
  expect_equal(nrow(n7_ticket_admission(character(0), b)), 1L)
  expect_false(n7_ticket_admission(character(0), b)$duplicate_of_period)
  expect_error(n7_ticket_admission(a, c(a, a)), "duplicate")
  expect_error(n7_ticket_admission(a, character(0)), "non-empty")
  expect_error(n7_ticket_admission(1, b), "character")
})

testthat::test_that("n7_structural_definitions are three same-budget structures plus tiers", {
  defs <- n7_structural_definitions()
  expect_equal(defs$structure,
               c("4x128", "8x64", "4x96_plus_4x32", "tier_96", "tier_32"))
  expect_equal(defs$total_tickets, c(512L, 512L, 512L, 96L, 32L))
  expect_equal(defs$total_cny, c(1024, 1024, 1024, 192, 64))
  # The three 1024-CNY structures are same-budget by construction.
  expect_true(all(defs$total_cny[1:3] == N7_PERIOD_BUDGET_CNY))
  # The tier names are the 96- and 32-ticket patterns, not a hard mask.
  expect_equal(n7_pattern_tickets(c(3, 2, 2, 2, 2, 2, 1)), 96L)
  expect_equal(n7_pattern_tickets(c(2, 2, 2, 2, 2, 1, 1)), 32L)
  expect_equal(defs$total_tickets[defs$structure == "tier_96"], 96L)
  expect_equal(defs$total_tickets[defs$structure == "tier_32"], 32L)
})

testthat::test_that("the contract templates are typed empty tables and validate", {
  templates <- n7_contract_templates()
  expect_equal(names(templates),
               c("decision_epochs", "eligible", "priced", "probabilities", "groups",
                 "tickets", "settlements", "ledger"))
  for (name in names(templates)) {
    expect_s3_class(templates[[name]], "tbl_df")
    expect_equal(nrow(templates[[name]]), 0L)
  }
  expect_identical(templates$settlements$hit, logical(0))
  expect_identical(templates$groups$group, integer(0))
  expect_identical(templates$eligible$hours_to_kickoff, double(0))
  expect_true(n7_validate_contract(templates))
  # A whole empty bundle validates: an empty result is still a valid contract.
  expect_true(n7_validate_contract(list(groups = templates$groups)))
  expect_error(n7_validate_contract(list(groups = templates$groups, nope = templates$groups)),
               "unknown contract table")
  expect_error(n7_validate_contract(list(groups = data.frame(group = "1"))), "group")
  broken <- templates$settlements
  broken$hit <- as.character(broken$hit)
  expect_error(n7_validate_contract(list(settlements = broken)), "must be logical")
  expect_error(n7_validate_contract(list(settlements = broken[, -1])), "missing column")
  expect_error(n7_validate_contract(list(groups = 1)), "data frame")
  expect_error(n7_validate_contract("nope"), "named list")
})

testthat::test_that("n7_select_snapshots parses only the fixtures it is selecting", {
  # A poll series is walked once per decision epoch. Parsing every timestamp on
  # every epoch would be quadratic on a real store, so an unparseable timestamp
  # belonging to a fixture outside the selection must not even be read.
  snapshots <- tibble::tibble(
    match_id = c("a", "a", "zzz"),
    snapshot_ts = c("2026-05-02T11:00:00Z", "2026-05-02T11:30:00Z", "not-a-timestamp"),
    eu_h = c(1.6, 1.5, 9), eu_d = c(3.9, 4.0, 9), eu_a = c(5.5, 6.0, 9),
    source = "merged", sp_3 = c(2, 2.1, 9), sp_1 = c(3, 3.1, 9), sp_0 = c(4, 4.1, 9))
  eligible <- tibble::tibble(match_id = "a", issue = "T",
                             kickoff_utc = "2026-05-02T18:00:00Z")
  out <- n7_select_snapshots(snapshots, eligible, "2026-05-02T12:00:00Z")
  expect_equal(nrow(out$priced), 1L)
  expect_equal(out$priced$quote_utc, "2026-05-02T11:30:00Z")
  # Selecting the broken fixture itself is still refused, not skipped.
  broken <- tibble::tibble(match_id = "zzz", issue = "T",
                           kickoff_utc = "2026-05-02T18:00:00Z")
  expect_error(n7_select_snapshots(snapshots, broken, "2026-05-02T12:00:00Z"), "snapshot_ts")
  # The uniqueness check is scoped the same way, because a duplicate poll on a
  # fixture outside the selection cannot change this epoch's answer. Whole-series
  # integrity is enforced once at the reader boundary (n7_read_snapshots).
  duplicated_outside <- rbind(snapshots, snapshots[3L, ])
  expect_equal(nrow(n7_select_snapshots(duplicated_outside, eligible,
                                        "2026-05-02T12:00:00Z")$priced), 1L)
  duplicated_inside <- rbind(snapshots, snapshots[2L, ])
  expect_error(n7_select_snapshots(duplicated_inside, eligible, "2026-05-02T12:00:00Z"),
               "must be unique")
})

