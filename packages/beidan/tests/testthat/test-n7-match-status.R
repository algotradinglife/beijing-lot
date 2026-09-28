# #508 match-status tests: the real production selector, the schema/IO boundary, the
# epoch wiring, and the causal guarantees. These exercise production functions only;
# no local re-implementation of the selector is allowed to stand in for it.

status_issue <- function(issue_id = "00123", kickoffs = 2L, decision_date = "2026-09-22",
                         seed = 1L, match_status = "scheduled") {
  make_example_issue(issue_id, match_kickoff_window(decision_date, kickoffs),
                        seed = seed, match_status = match_status)
}

status_cutoff <- function(issue_id = "00123", cutoff_utc = "2026-09-22 12:00:00") {
  list(issue_id = issue_id, cutoff_utc = as.POSIXct(cutoff_utc, tz = "UTC"))
}

default_policies <- function() {
  list(
    euro = list(members = c("c01", "c02", "c03"), missing = "error"),
    totals = list(companies = NULL, line = "nearest_main", watermark = "decimal"))
}

# --- schema and raw IO boundary ---------------------------------------------

testthat::test_that("match_status is the sixteenth authoritative schema with a typed key", {
  schema <- match_table_schemas()$match_status
  testthat::expect_identical(
    schema$columns,
    c("issue_id", "fixture_id", "status", "status_at", "available_at", "source_url"))
  testthat::expect_identical(unname(schema$types), c(
    "character", "character", "character", "POSIXct", "POSIXct", "character"))
  # The declared key is the composite (issue_id, fixture_id, available_at) on TYPED
  # columns -- not a formatted timestamp string.
  testthat::expect_identical(schema$keys, c("issue_id", "fixture_id", "available_at"))
  empty <- match_typed_empty("match_status")
  testthat::expect_identical(names(empty), schema$columns)
  testthat::expect_s3_class(empty$status_at, "POSIXct")
  testthat::expect_identical(attr(empty$status_at, "tzone"), "UTC")
  testthat::expect_silent(match_validate_table(empty, "match_status"))
})

testthat::test_that("the seven status tokens are the authoritative set and unknown is valid", {
  testthat::expect_identical(
    match_status_levels(),
    c("scheduled", "live", "finished", "postponed", "cancelled", "abandoned", "unknown"))
})

testthat::test_that("malformed rows fail: NA, empty ids, unknown token, chronology, types", {
  good <- status_issue()$match_status
  base_time <- as.POSIXct("2026-09-22 08:00:00", tz = "UTC")

  na_id <- good
  na_id$issue_id[1] <- NA_character_
  testthat::expect_error(match_validate_status(na_id), "must not be NA")

  blank_id <- good
  blank_id$fixture_id[1] <- ""
  testthat::expect_error(match_validate_status(blank_id), "must not be empty")

  padded <- good
  padded$issue_id[1] <- " 00123"
  testthat::expect_error(match_validate_status(padded), "must not be padded")

  unknown_token <- good
  unknown_token$status[1] <- "postponed_ish"
  testthat::expect_error(match_validate_status(unknown_token), "unknown match status token")

  # NA status is missing, not a token: it must be refused before the membership test.
  na_status <- good
  na_status$status[1] <- NA_character_
  testthat::expect_error(match_validate_status(na_status), "must not be NA")

  empty_url <- good
  empty_url$source_url[1] <- ""
  testthat::expect_error(match_validate_status(empty_url), "must be non-empty")

  # The event cannot be observed before it happens.
  backwards <- good
  backwards$status_at[1] <- base_time + 10
  backwards$available_at[1] <- base_time
  testthat::expect_error(match_validate_status(backwards), "after its availability")

  na_instant <- good
  na_instant$available_at[1] <- as.POSIXct(NA, tz = "UTC")
  testthat::expect_error(match_validate_status(na_instant), "must not be NA")

  inf_instant <- good
  inf_instant$available_at[1] <- as.POSIXct(Inf, origin = "1970-01-01", tz = "UTC")
  testthat::expect_error(match_validate_status(inf_instant), "must be finite")

  # Type errors are refused, never coerced. A numeric id would be stringified by a
  # naive implementation and silently authorise the wrong match.
  numeric_id <- good
  numeric_id$fixture_id <- as.numeric(seq_len(nrow(numeric_id)))
  testthat::expect_error(match_validate_status(numeric_id), "must be character")

  factor_id <- good
  factor_id$issue_id <- factor(factor_id$issue_id)
  testthat::expect_error(match_validate_status(factor_id), "must be character")

  # Beijing display time preserves the instant and is an accepted boundary timezone.
  beijing <- good
  beijing$available_at <- lubridate::with_tz(good$available_at, "Asia/Shanghai")
  beijing$status_at <- lubridate::with_tz(good$status_at, "Asia/Shanghai")
  testthat::expect_silent(match_validate_status(beijing))
  testthat::expect_equal(as.numeric(beijing$available_at), as.numeric(good$available_at))
  wrong_zone <- good
  wrong_zone$available_at <- lubridate::with_tz(good$available_at, "America/New_York")
  wrong_zone$status_at <- lubridate::with_tz(good$status_at, "America/New_York")
  testthat::expect_error(match_validate_status(wrong_zone), "timezone|tz|UTC")

  # Extra and missing columns are both refused.
  extra <- good
  extra$note <- "x"
  testthat::expect_error(match_validate_status(extra), "columns must be exactly")
  dropped <- good[, setdiff(names(good), "source_url")]
  testthat::expect_error(match_validate_status(dropped), "columns must be exactly")
})

testthat::test_that("duplicate composite keys and conflicting statuses are refused", {
  good <- status_issue()$match_status
  duplicated_row <- dplyr::bind_rows(good, good[1, , drop = FALSE])
  testthat::expect_error(match_validate_status(duplicated_row), "duplicate key")

  # Two rows at one instant that disagree on status are the same duplicate key.
  conflicting <- good
  conflicting$status[1] <- "cancelled"
  conflicting <- dplyr::bind_rows(good, conflicting[1, , drop = FALSE])
  testthat::expect_error(match_validate_status(conflicting), "duplicate key")

  # A fractional-instant ledger keeps two distinct observations apart. Formatting the
  # instant to whole seconds would collapse these into one and wrongly report a
  # duplicate, so the typed key is what this pins.
  base_time <- as.POSIXct("2026-09-22 08:00:00", tz = "UTC")
  fractional <- tibble::tibble(
    issue_id = "00123", fixture_id = "00123_001", status = "scheduled",
    status_at = c(base_time + 0.25, base_time + 0.75),
    available_at = c(base_time + 0.25, base_time + 0.75),
    source_url = "synthetic://n7-pipeline/match_status/00123_001")
  testthat::expect_silent(match_validate_status(fractional))
})

testthat::test_that("the ledger relation is checked against a full frame with composite keys", {
  good <- status_issue()$match_status
  # A ledger row for a fixture that does not exist in the frame must fail.
  orphan <- good[1, , drop = FALSE]
  orphan$fixture_id <- "ghost"
  testthat::expect_error(
    match_validate_status(orphan, fixtures = status_issue()$fixtures),
    "not in fixtures")

  # A same-numbered fixture under another issue is a DIFFERENT match: it must not be
  # accepted as authorising this issue's fixture.
  other_issue <- good[1, , drop = FALSE]
  other_issue$issue_id <- "00999"
  testthat::expect_error(
    match_validate_status(other_issue, fixtures = status_issue()$fixtures),
    "not in fixtures")
})

testthat::test_that("frames and CSV sources both refuse a missing status table", {
  source <- example_match_source(status_issue())
  frames_missing <- source
  frames_missing$tables$match_status <- NULL
  testthat::expect_error(read_match_inputs(frames_missing, "00123"), "no match_status table")
  testthat::expect_error(match_read_fixture_source(frames_missing), "no match_status table")

  directory <- tempfile("n7-status-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)
  utils::write.csv(status_issue()$fixtures, file.path(directory, "fixtures.csv"),
                   row.names = FALSE)
  csv_missing <- list(kind = "csv_dir", path = directory)
  testthat::expect_error(match_read_fixture_source(csv_missing), "match_status.csv is missing")
  testthat::expect_error(read_match_inputs(csv_missing, "00123"), "match_status.csv is missing")
})

testthat::test_that("the CSV adapter round-trips the ledger without identifier damage", {
  issue <- status_issue(issue_id = "00123")
  # A leading-zero issue id would be destroyed by a numeric parse.
  issue$fixtures$issue_id <- "00123"
  issue$match_status$issue_id <- "00123"
  source <- example_match_source(issue)
  directory <- tempfile("n7-status-csv-")
  dir.create(directory)
  on.exit(unlink(directory, recursive = TRUE), add = TRUE)
  write_csv_utc <- function(data, path) {
    out <- data
    for (column in names(out)) {
      if (inherits(out[[column]], "POSIXct")) {
        out[[column]] <- format(out[[column]], "%Y-%m-%dT%H:%M:%S+0000", tz = "UTC")
      }
    }
    utils::write.csv(out, path, row.names = FALSE)
  }
  for (table in names(match_source_csv_columns())) {
    write_csv_utc(source$tables[[table]], file.path(directory, paste0(table, ".csv")))
  }
  frames <- read_match_inputs(source, "00123")
  csv <- read_match_inputs(list(kind = "csv_dir", path = directory), "00123")
  testthat::expect_identical(csv$fixtures$issue_id, rep("00123", nrow(csv$fixtures)))
  testthat::expect_identical(names(csv$match_status), names(frames$match_status))
  testthat::expect_identical(csv$match_status$status, frames$match_status$status)
  # Instants survive as typed UTC POSIXct, not as strings or shifted wall clock.
  testthat::expect_s3_class(csv$match_status$available_at, "POSIXct")
  testthat::expect_identical(as.numeric(csv$match_status$available_at),
                             as.numeric(frames$match_status$available_at))
  testthat::expect_identical(attr(csv$match_status$available_at, "tzone"), "UTC")
})

# --- the selector -----------------------------------------------------------

testthat::test_that("scheduled admits and every other token excludes with a stable reason", {
  cutoff <- status_cutoff()
  for (token in match_status_levels()) {
    issue <- status_issue(match_status = token)
    result <- match_select_status(issue$fixtures, issue$match_status, cutoff)
    if (identical(token, "scheduled")) {
      testthat::expect_equal(nrow(result$fixtures), nrow(issue$fixtures))
      testthat::expect_equal(nrow(result$exclusions), 0L)
      testthat::expect_true(all(result$selected_status$status == "scheduled"))
    } else {
      testthat::expect_equal(nrow(result$fixtures), 0L)
      testthat::expect_equal(nrow(result$exclusions), nrow(issue$fixtures))
      testthat::expect_true(all(result$exclusions$reason == paste0("match status: ", token)))
    }
  }
})

testthat::test_that("missing, empty and future-only histories exclude every fixture", {
  issue <- status_issue(kickoffs = 3L)
  cutoff <- status_cutoff()
  empty <- match_select_status(issue$fixtures, match_typed_empty("match_status"), cutoff)
  testthat::expect_equal(nrow(empty$fixtures), 0L)
  testthat::expect_true(all(empty$exclusions$reason == "no match status before cutoff"))
  # The empty slice keeps the full column set so it can be bound onto a populated frame.
  testthat::expect_identical(names(empty$fixtures), names(issue$fixtures))
  testthat::expect_identical(empty$fixtures, issue$fixtures[0, , drop = FALSE])

  future_only <- issue$match_status
  future_only$status_at <- cutoff$cutoff_utc + 3600
  future_only$available_at <- cutoff$cutoff_utc + 3600
  future <- match_select_status(issue$fixtures, future_only, cutoff)
  testthat::expect_equal(nrow(future$fixtures), 0L)
  testthat::expect_true(all(future$exclusions$reason == "no match status before cutoff"))

  # A missing ledger is a contract error, never read as "no visible status".
  testthat::expect_error(match_select_status(issue$fixtures, NULL, cutoff),
                         "match_status is required")
})

testthat::test_that("the strictly-before rule excludes an instant exactly at the cutoff", {
  issue <- status_issue()
  cutoff <- status_cutoff()
  at_cutoff <- issue$match_status
  at_cutoff$status_at <- cutoff$cutoff_utc
  at_cutoff$available_at <- cutoff$cutoff_utc
  result <- match_select_status(issue$fixtures, at_cutoff, cutoff)
  testthat::expect_equal(nrow(result$fixtures), 0L)

  # Arriving strictly before the cutoff is necessary but not sufficient for the event
  # time: a report whose observation instant is at the cutoff is still invisible.
  arrives_late <- issue$match_status
  arrives_late$status_at <- cutoff$cutoff_utc - 120
  arrives_late$available_at <- cutoff$cutoff_utc
  result <- match_select_status(issue$fixtures, arrives_late, cutoff)
  testthat::expect_equal(nrow(result$fixtures), 0L)
})

testthat::test_that("the latest visible report wins within a composite identity", {
  issue <- status_issue(kickoffs = 1L)
  cutoff <- status_cutoff()
  seed_row <- issue$match_status[1, , drop = FALSE]
  early_scheduled <- seed_row
  early_scheduled$status <- "scheduled"
  early_scheduled$status_at <- cutoff$cutoff_utc - 1800
  early_scheduled$available_at <- cutoff$cutoff_utc - 1800
  late_cancelled <- seed_row
  late_cancelled$status <- "cancelled"
  late_cancelled$status_at <- cutoff$cutoff_utc - 900
  late_cancelled$available_at <- cutoff$cutoff_utc - 900

  # Latest visible wins: cancelled excludes.
  by_latest <- match_select_status(
    issue$fixtures, dplyr::bind_rows(early_scheduled, late_cancelled), cutoff)
  testthat::expect_equal(nrow(by_latest$fixtures), 0L)
  testthat::expect_identical(by_latest$exclusions$reason, "match status: cancelled")

  # A scheduled report that arrives LATER than a cancelled one re-admits the fixture.
  late_scheduled <- early_scheduled
  late_scheduled$available_at <- cutoff$cutoff_utc - 600
  late_scheduled$status_at <- cutoff$cutoff_utc - 600
  by_recovery <- match_select_status(
    issue$fixtures, dplyr::bind_rows(late_cancelled, late_scheduled), cutoff)
  testthat::expect_equal(nrow(by_recovery$fixtures), 1L)
})

testthat::test_that("a future report cannot rewrite what was visible at the cutoff", {
  issue <- status_issue(kickoffs = 3L)
  cutoff <- status_cutoff()
  baseline <- match_select_status(issue$fixtures, issue$match_status, cutoff)

  future <- issue$match_status[1, , drop = FALSE]
  future$status <- "cancelled"
  future$status_at <- cutoff$cutoff_utc + 1
  future$available_at <- cutoff$cutoff_utc + 1
  mutated <- match_select_status(
    issue$fixtures, dplyr::bind_rows(issue$match_status, future), cutoff)
  testthat::expect_identical(baseline, mutated)

  # Even a whole future history that cancels every fixture changes nothing.
  all_future <- issue$match_status
  all_future$status <- "finished"
  all_future$status_at <- cutoff$cutoff_utc + 1
  all_future$available_at <- cutoff$cutoff_utc + 1
  mutated <- match_select_status(
    issue$fixtures, dplyr::bind_rows(issue$match_status, all_future), cutoff)
  testthat::expect_identical(baseline, mutated)
})

testthat::test_that("downstream sliced fixtures ignore unrelated ledger rows", {
  # The selector must NOT validate its ledger relation against the slice: a full
  # same-issue ledger handed to a sliced fixture frame is legitimate, and the rows for
  # the omitted fixtures are simply ignored.
  issue <- status_issue(kickoffs = 3L)
  cutoff <- status_cutoff()
  slice <- issue$fixtures[1, , drop = FALSE]
  result <- match_select_status(slice, issue$match_status, cutoff)
  testthat::expect_equal(nrow(result$fixtures), 1L)
  testthat::expect_identical(result$fixtures$fixture_id, slice$fixture_id)
  testthat::expect_equal(nrow(result$selected_status), 1L)

  # The selector does NOT relation-check the slice. A row for a match that never
  # existed is ignored here too: that failure was already raised at the raw input
  # boundary, and re-deriving the relation from a slice is exactly what would
  # manufacture a false "unknown match" for legitimately dropped fixtures.
  orphan <- issue$match_status[1, , drop = FALSE]
  orphan$fixture_id <- "ghost"
  ignored <- match_select_status(
    slice, dplyr::bind_rows(issue$match_status, orphan), cutoff)
  testthat::expect_equal(nrow(ignored$fixtures), 1L)
  testthat::expect_false("ghost" %in% ignored$fixtures$fixture_id)
  testthat::expect_false("ghost" %in% ignored$selected_status$fixture_id)
})

# --- epoch wiring and revalidation ------------------------------------------

testthat::test_that("prepare_epoch excludes fixtures the ledger has no visible scheduled report for", {
  issue <- status_issue(kickoffs = 3L)
  cutoff <- status_cutoff()
  policies <- default_policies()
  inputs <- read_match_inputs(example_match_source(issue), "00123")
  whole <- prepare_engine(inputs, cutoff, policies$euro, policies$totals)
  testthat::expect_equal(nrow(whole$fixtures), 3L)
  testthat::expect_equal(nrow(whole$status_selected), 3L)

  # Cancel one fixture before the cutoff: it leaves the epoch with a stable reason.
  cancelled <- issue$match_status
  cancelled$status[2] <- "cancelled"
  cancelled$status_at[2] <- cutoff$cutoff_utc - 60
  cancelled$available_at[2] <- cutoff$cutoff_utc - 60
  inputs$match_status <- cancelled
  filtered <- prepare_engine(inputs, cutoff, policies$euro, policies$totals)
  testthat::expect_equal(nrow(filtered$fixtures), 2L)
  testthat::expect_true(issue$fixtures$fixture_id[2] %in% filtered$exclusions$fixture_id)
  testthat::expect_true(any(filtered$exclusions$reason == "match status: cancelled"))
})

testthat::test_that("prepare_epoch rejects a ledger referencing a match that never existed", {
  issue <- status_issue(kickoffs = 2L)
  cutoff <- status_cutoff()
  policies <- default_policies()
  inputs <- read_match_inputs(example_match_source(issue), "00123")
  ghost <- issue$match_status[1, , drop = FALSE]
  ghost$fixture_id <- "ghost"
  inputs$match_status <- dplyr::bind_rows(issue$match_status, ghost)
  testthat::expect_error(
    prepare_engine(inputs, cutoff, policies$euro, policies$totals),
    "not in fixtures")
})

testthat::test_that("a sliced epoch keeps a full same-issue ledger without relation errors", {
  # Two fixtures, but only one falls inside the decision window. The epoch slices to
  # one and then hands the FULL ledger to the selector; the dropped fixture's ledger
  # row must be ignored, not reported as an unknown match.
  kickoffs <- as.POSIXct(c("2026-09-23 04:00:00", "2026-09-30 04:00:00"), tz = "UTC")
  issue <- make_example_issue("00123", kickoffs)
  cutoff <- status_cutoff()
  policies <- default_policies()
  inputs <- read_match_inputs(example_match_source(issue), "00123")
  epoch <- prepare_engine(inputs, cutoff, policies$euro, policies$totals)
  testthat::expect_equal(nrow(epoch$fixtures), 1L)
  testthat::expect_true("kickoff outside decision window" %in% epoch$exclusions$reason)
  testthat::expect_equal(nrow(epoch$match_status), 2L)
})

# --- causal invariance end to end -------------------------------------------

testthat::test_that("projection revalidates visibility and refuses a late cancellation", {
  issue <- status_issue(kickoffs = 4L)
  cutoff <- status_cutoff()
  policies <- default_policies()
  inputs <- read_match_inputs(example_match_source(issue), "00123")
  epoch <- prepare_engine(inputs, cutoff, policies$euro, policies$totals)
  projected <- estimate_engine(epoch, cutoff, -0.14, c(0.1, 16), 1e-10)
  testthat::expect_equal(nrow(projected$fit), 4L)

  # Cancelling a fixture BEFORE the cutoff and re-projecting the same epoch must fail:
  # the epoch's fixtures are no longer visible as scheduled.
  cancelled <- issue$match_status
  cancelled$status[1] <- "cancelled"
  cancelled$status_at[1] <- cutoff$cutoff_utc - 60
  cancelled$available_at[1] <- cutoff$cutoff_utc - 60
  epoch$match_status <- cancelled
  testthat::expect_error(
    estimate_engine(epoch, cutoff, -0.14, c(0.1, 16), 1e-10),
    "not visible as scheduled")
})

testthat::test_that("candidates, tickets and funding are invariant to a future cancellation", {
  issue <- status_issue(kickoffs = 14L)
  cutoff <- status_cutoff()
  probabilities <- tidyr::expand_grid(fixture_id = issue$fixtures$fixture_id,
                                      outcome = c("W", "D", "L")) |>
    dplyr::mutate(probability = rep(c(0.5, 0.3, 0.2), nrow(issue$fixtures)))
  constants <- parlay_settings(reset = TRUE)
  # Block 8 public path: the configuration declares explicit patterns and policy and
  # NO purchased group count; funded groups are derived from the budget.
  config <- parlay_strategy_config(
    constants, name = "status", construction_policy = list(max_candidates = 2L, seed = 1L),
    patterns = list(p3222221 = c(3L, 2L, 2L, 2L, 2L, 2L, 1L)),
    objective = "probability", max_reuse = 1L, max_overlap = 6L,
    spend_limit_cny = 160)
  # The public plan API consumes a bound projection; the mutated status ledgers are
  # the only thing that differs between the three calls below.
  project <- function(match_status) {
    list(cutoff = cutoff, fixtures = issue$fixtures, probabilities = probabilities,
         prematch_sp = issue$prematch_sp, match_status = match_status)
  }

  baseline <- parlay_build_plan(project(issue$match_status), config)

  future <- issue$match_status[1, , drop = FALSE]
  future$status <- "cancelled"
  future$status_at <- cutoff$cutoff_utc + 1
  future$available_at <- cutoff$cutoff_utc + 1
  mutated <- parlay_build_plan(
    project(dplyr::bind_rows(issue$match_status, future)), config)
  testthat::expect_identical(mutated, baseline)

  # A settlement-style mutation (finished) after the cutoff changes nothing either.
  finished <- future
  finished$status <- "finished"
  settled <- parlay_build_plan(
    project(dplyr::bind_rows(issue$match_status, finished)), config)
  testthat::expect_identical(settled, baseline)
})

testthat::test_that("direct candidate construction cannot bypass status filtering", {
  issue <- status_issue(kickoffs = 14L)
  cutoff <- status_cutoff()
  probabilities <- tidyr::expand_grid(fixture_id = issue$fixtures$fixture_id,
                                      outcome = c("W", "D", "L")) |>
    dplyr::mutate(probability = rep(c(0.5, 0.3, 0.2), nrow(issue$fixtures)))

  # A ledger that marks one fixture cancelled BEFORE the cutoff keeps it out of every
  # constructed group, even when the caller builds groups directly.
  blocked <- issue$fixtures$fixture_id[1]
  ledger <- issue$match_status
  ledger$status[1] <- "cancelled"
  ledger$status_at[1] <- cutoff$cutoff_utc - 60
  ledger$available_at[1] <- cutoff$cutoff_utc - 60
  built <- parlay_construct_groups(issue$fixtures, probabilities, cutoff, 7L,
                                   "fixture_round_robin", 2L, seed = 1L,
                                   match_status = ledger)
  testthat::expect_false(blocked %in% built$group_legs$fixture_id)

  # The same construction with the unmutated ledger does use the fixture.
  allowed <- parlay_construct_groups(issue$fixtures, probabilities, cutoff, 7L,
                                     "fixture_round_robin", 2L, seed = 1L,
                                     match_status = issue$match_status)
  testthat::expect_true(blocked %in% allowed$group_legs$fixture_id)

  # Direct construction refuses a wholly empty ledger rather than falling back.
  empty <- parlay_construct_groups(issue$fixtures, probabilities, cutoff, 7L,
                                   "fixture_round_robin", 2L, seed = 1L,
                                   match_status = match_typed_empty("match_status"))
  testthat::expect_equal(nrow(empty$group_legs), 0L)
})

# --- whole-issue reads and two-epoch selection -------------------------------

testthat::test_that("whole-issue reading keeps every match day and mutates no source", {
  two_days <- as.POSIXct(c("2026-09-23 04:00:00", "2026-09-24 04:00:00"), tz = "UTC")
  issue <- make_example_issue("00123", two_days)
  source <- example_match_source(issue)
  original <- source
  whole <- read_match_inputs(source, "00123")
  testthat::expect_equal(nrow(whole$fixtures), 2L)
  testthat::expect_identical(whole$fixtures$kickoff_at, two_days)
  testthat::expect_equal(nrow(whole$match_status), 2L)
  # The source is never mutated by reading it.
  testthat::expect_identical(source, original)
  # Reading is deterministic and repeatable.
  testthat::expect_identical(whole, read_match_inputs(source, "00123"))
})

testthat::test_that("two decision days independently select their next-day subset", {
  two_days <- as.POSIXct(c("2026-09-23 04:00:00", "2026-09-24 04:00:00"), tz = "UTC")
  issue <- make_example_issue("00123", two_days)
  source <- example_match_source(issue)
  original <- source
  whole <- read_match_inputs(source, "00123")
  policies <- default_policies()
  first <- status_cutoff(cutoff_utc = "2026-09-22 12:00:00")
  second <- status_cutoff(cutoff_utc = "2026-09-23 12:00:00")
  epoch_one <- prepare_engine(whole, first, policies$euro, policies$totals)
  epoch_two <- prepare_engine(whole, second, policies$euro, policies$totals)
  testthat::expect_identical(epoch_one$fixtures$fixture_id, whole$fixtures$fixture_id[1])
  testthat::expect_identical(epoch_two$fixtures$fixture_id, whole$fixtures$fixture_id[2])
  # Reading retained both days and never rewrote the source.
  testthat::expect_equal(nrow(whole$fixtures), 2L)
  testthat::expect_identical(source, original)
})

testthat::test_that("generated quotes and status reports are anchored to kickoff, not a cutoff", {
  # The generator no longer guesses a decision epoch: both quotes and the initial
  # status observation sit at kickoff - 36h for each fixture, plus a bounded company
  # offset that is already declared.
  kickoffs <- match_kickoff_window("2026-09-22", 3L)
  issue <- make_example_issue("00123", kickoffs)
  testthat::expect_identical(issue$match_status$available_at, kickoffs - 36 * 3600)
  testthat::expect_identical(issue$match_status$status_at, kickoffs - 36 * 3600)
  # A same-seed regeneration is byte-identical; a different seed changes the truth.
  again <- make_example_issue("00123", kickoffs)
  testthat::expect_identical(issue, again)
  other <- make_example_issue("00123", kickoffs, seed = 2L)
  testthat::expect_false(identical(issue$truth, other$truth))
})
