# Shared helpers for the N7 pipeline tests.
#
# match_kickoff_window() builds the explicit UTC kickoff vector the fixture generator
# now takes: `n` kickoffs spaced 15 minutes apart, starting at the 01:00 UTC slot of
# the calendar day after `decision_date`. Passing the schedule explicitly is the
# whole point of the refined interface -- generation no longer guesses a decision
# epoch, so tests state the timeline they mean.
match_kickoff_window <- function(decision_date, n, start_utc = "01:00:00", step_seconds = 900) {
  day <- as.Date(decision_date) + 1L
  start <- as.POSIXct(paste(format(day), start_utc), tz = "UTC")
  start + (seq_len(n) - 1L) * step_seconds
}

# A frames source carrying the required match_status table and nothing else, so
# tests that only care about the other tables stay legal now that a missing status
# ledger is an input-contract error rather than a silent typed-empty.
n7_empty_frames <- function() {
  list(kind = "frames", tables = list(match_status = match_typed_empty("match_status")))
}



# Shared fixture exercised by all epoch tests.
epoch_fixture <- function(n_fixtures = 10L, seed = 42L, local_date = '2026-09-22') {
  issue <- make_example_issue('26097', match_kickoff_window(local_date, n_fixtures), seed = seed)
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  inputs <- read_match_inputs(example_match_source(issue), '26097')
  list(issue = issue, cutoff = cutoff, inputs = inputs)
}

default_euro <- function() list(members = c('c01', 'c02', 'c03'), missing = 'error')
default_totals <- function() list(companies = NULL, line = 'nearest_main', watermark = 'decimal')

# Low-level behavioral tests exercise the explicit-table engines directly. The
# public entrypoints derive the issue from the fixtures and read model parameters
# from one model_config list; these wrappers state the same explicit tables/cutoff
# so a test can pin the engine boundary without going through the facade.
prepare_engine <- function(inputs, cutoff, euro_policy, totals_policy) {
  .PrepareMatchInputs(inputs, cutoff, euro_policy, totals_policy)
}

estimate_engine <- function(epoch_inputs, cutoff, rho = -0.14,
                            total_bounds = c(0.1, 16), tail_tolerance = 1e-10) {
  .EstimateMatchProbabilities(epoch_inputs, cutoff, rho, total_bounds, tail_tolerance)
}
