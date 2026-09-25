# Shared helpers for the N7 pipeline tests.
#
# n7_kickoff_window() builds the explicit UTC kickoff vector the fixture generator
# now takes: `n` kickoffs spaced 15 minutes apart, starting at the 01:00 UTC slot of
# the calendar day after `decision_date`. Passing the schedule explicitly is the
# whole point of the refined interface -- generation no longer guesses a decision
# epoch, so tests state the timeline they mean.
n7_kickoff_window <- function(decision_date, n, start_utc = "01:00:00", step_seconds = 900) {
  day <- as.Date(decision_date) + 1L
  start <- as.POSIXct(paste(format(day), start_utc), tz = "UTC")
  start + (seq_len(n) - 1L) * step_seconds
}

# A frames source carrying the required match_status table and nothing else, so
# tests that only care about the other tables stay legal now that a missing status
# ledger is an input-contract error rather than a silent typed-empty.
n7_empty_frames <- function() {
  list(kind = "frames", tables = list(match_status = n7_typed_empty("match_status")))
}



# Shared fixture exercised by all epoch tests.
epoch_fixture <- function(n_fixtures = 10L, seed = 42L, local_date = '2026-09-22') {
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window(local_date, n_fixtures), seed = seed)
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  inputs <- n7_read_inputs(n7_fixture_source(issue), '26097')
  list(issue = issue, cutoff = cutoff, inputs = inputs)
}

default_euro <- function() list(members = c('c01', 'c02', 'c03'), missing = 'error')
default_totals <- function() list(companies = NULL, line = 'nearest_main', watermark = 'decimal')
