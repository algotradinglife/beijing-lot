# The N7 experiment contract: when the decision is taken, which fixtures are
# still bettable then, which quote was actually available at that instant, how
# much of the period budget is already spent, and whether a new seven-fixture
# group or a new physical ticket is admissible.
#
# Why this is separate from r/n7_fixture_portfolio.R: that module answers "given
# a seven-fixture group and a ticket budget, which tickets do I fund". This
# module answers the questions before it. Keeping them apart means the
# construction rule can be tested on synthetic groups while the calendar,
# availability and accounting rules are tested on their own.
#
# Time boundary: timestamps cross this boundary as ISO-8601 UTC strings of fixed
# width ("YYYY-MM-DDTHH:MM:SSZ"), which is the convention r/n7_market_projection.R
# already uses for its cutoff. Arithmetic converts to epoch seconds explicitly.
#
# Every function here is pure: explicit inputs, explicit outputs, no I/O, no
# hidden state, no default that silently changes a business constant. The
# business constants are the ones the confirmed contract fixes: 1024 CNY per
# period, 2 CNY per ticket, one decision per local day at 20:00 Asia/Shanghai,
# a 24-hour forward window, and a fixed SP-estimate rule.

# ---- Business constants (contract-fixed, never inferred from the data) -------

# Period stake ceiling in CNY. It is a ceiling: unspent budget stays cash and is
# never rolled into the next period's ceiling.
PARLAY_PERIOD_BUDGET_CNY <- 1024

# Stake of one physical ticket in CNY.
PARLAY_UNIT_CNY <- 2

# Local hour at which the one daily decision is taken.
MATCH_DECISION_HOUR <- 20L

# Local timezone of the decision hour.
MATCH_DECISION_TZ <- "Asia/Shanghai"

# Rolling elapsed-hour bounds: four-hour lead, followed by a 24-hour horizon.
# At 20:00 Beijing these bounds coincide with the next local calendar day.
MATCH_WINDOW_START_HOURS <- 4
MATCH_WINDOW_END_HOURS <- 28

# Sale-state values a fixture may carry. Only NOT_FOR_SALE / SUSPENDED /
# CANCELLED / RESCHEDULED are exclusion evidence; UNKNOWN is admitted as a
# regular candidate because the four-hour window lead (not a per-match minute
# threshold) is what provides the margin, and it is never reported as verified
# sellable.
#
# The contract explicitly retires the old uniform "kickoff - N minutes" stop-sale
# presumption and does not ask for a per-match minute threshold to be rebuilt.
# What remains is the explicit-evidence check below plus the schedule-anomaly
# check on a recorded cutoff.
MATCH_SALE_STATES <- c("ON_SALE", "UNKNOWN", "NOT_FOR_SALE", "SUSPENDED",
                    "CANCELLED", "RESCHEDULED")
MATCH_SALE_STATE_EXCLUSIONS <- c(
  NOT_FOR_SALE = "SALE_STATE_NOT_FOR_SALE",
  SUSPENDED = "SALE_STATE_SUSPENDED",
  CANCELLED = "SALE_STATE_CANCELLED",
  RESCHEDULED = "SALE_STATE_RESCHEDULED")

# The fixed estimated-payout rule: a single fixture/outcome with a pre-match 北单
# SP above 10 is estimated at 4.5, otherwise the recorded value is kept. This is
# a fixed rule, deliberately NOT a cap (min(sp, 4.5)) and NOT a re-derivation.
# The probability model declared for this round. Each fixture's 1X2 distribution is
# fitted with Dixon-Coles, but a seven-fixture ticket is priced as the PRODUCT of
# the seven marginal fixture distributions. Dixon-Coles models dependence between
# the two teams WITHIN one match; it does not establish independence BETWEEN
# fixtures. Declared rather than assumed silently, so the reported combination
# probabilities and ranks are not mistaken for a fitted seven-fixture joint model.
PARLAY_PROBABILITY_MODEL <- "INDEPENDENT_ACROSS_FIXTURES_PRODUCT_OF_MARGINALS"

MATCH_SP_ESTIMATE_THRESHOLD <- 10
MATCH_SP_ESTIMATE_VALUE <- 4.5

# ---- Time helpers ------------------------------------------------------------

# Parse a fixed-width ISO-8601 UTC instant into epoch seconds, failing closed on
# anything that is not exactly that shape.
match_utc_seconds <- function(instant, what = "instant") {
  if (!is.character(instant) || anyNA(instant) ||
      any(!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", instant))) {
    stop(sprintf("%s must be ISO-8601 UTC strings of the form YYYY-MM-DDTHH:MM:SSZ", what))
  }
  seconds <- as.numeric(as.POSIXct(instant, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  if (anyNA(seconds) || any(!is.finite(seconds))) {
    stop(sprintf("%s could not be parsed as UTC instants", what))
  }
  seconds
}

# One local wall-clock instant ("YYYY-MM-DD HH:MM", no zone in the string) in a
# declared zone, returned as the fixed-width UTC form. Used for source fields
# that are naive local time, e.g. the 北单 sale cutoff label. The zone is
# round-trip checked so a typo cannot shift the instant silently.
match_local_to_utc_iso <- function(local_instant, tz = MATCH_DECISION_TZ,
                                what = "local_instant") {
  if (!is.character(local_instant) || anyNA(local_instant) ||
      any(!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$", local_instant))) {
    stop(sprintf("%s must be 'YYYY-MM-DD HH:MM' local strings", what))
  }
  if (!is.character(tz) || length(tz) != 1L || is.na(tz) || !tz %in% OlsonNames()) {
    stop(sprintf("%s: tz is not a known Olson timezone name: %s", what, tz))
  }
  parsed <- as.POSIXct(local_instant, tz = tz, format = "%Y-%m-%d %H:%M")
  if (anyNA(parsed)) stop(sprintf("%s could not be interpreted in %s", what, tz))
  # A DST-less zone must round-trip exactly; anything else is a silent shift.
  if (any(format(parsed, "%Y-%m-%d %H:%M", tz = tz) != local_instant)) {
    stop(sprintf("%s did not round-trip through %s", what, tz))
  }
  match_utc_iso(as.numeric(parsed), what)
}

# Render epoch seconds back to the same fixed-width UTC form.
match_utc_iso <- function(seconds, what = "seconds") {
  if (!is.numeric(seconds) || anyNA(seconds) || any(!is.finite(seconds))) {
    stop(sprintf("%s must be finite numeric epoch seconds", what))
  }
  format(as.POSIXct(seconds, origin = "1970-01-01", tz = "UTC"),
         "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

# The single decision epoch of one local calendar day, returned as UTC.
# The local date is interpreted in `tz`, so 2026-05-02 20:00 Asia/Shanghai is
# 2026-05-02T12:00:00Z. There is no implicit "now": the caller passes the date.
match_decision_epoch <- function(local_date, hour = MATCH_DECISION_HOUR, tz = MATCH_DECISION_TZ) {
  if (!is.character(local_date) || length(local_date) != 1L || is.na(local_date) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", local_date)) {
    stop("match_decision_epoch: local_date must be one YYYY-MM-DD string")
  }
  if (length(hour) != 1L || !is.numeric(hour) || is.na(hour) || !is.finite(hour) ||
      hour != trunc(hour) || hour < 0 || hour > 23) {
    stop("match_decision_epoch: hour must be one whole number in 0..23")
  }
  if (!is.character(tz) || length(tz) != 1L || is.na(tz) || !nzchar(tz)) {
    stop("match_decision_epoch: tz must be one non-empty timezone name")
  }
  # An unknown zone silently falls back to UTC in R, which would move the epoch
  # by the offset without any error, so the name is checked against the zone
  # database instead of trusted.
  if (!tz %in% OlsonNames()) {
    stop("match_decision_epoch: tz is not a known Olson timezone name: ", tz)
  }
  local <- as.POSIXct(sprintf("%s %02d:00:00", local_date, as.integer(hour)),
                      tz = tz, format = "%Y-%m-%d %H:%M:%S")
  if (is.na(local)) stop("match_decision_epoch: local date/time could not be interpreted")
  # Guard the tz argument: a typo silently falls back to UTC in some builds.
  if (format(local, "%Y-%m-%d", tz = tz) != local_date ||
      format(local, "%H", tz = tz) != sprintf("%02d", as.integer(hour))) {
    stop("match_decision_epoch: timezone conversion did not round-trip; check tz")
  }
  match_utc_iso(as.numeric(local), "match_decision_epoch: epoch")
}

# Calendar label for the regular 20:00 Beijing schedule, not an inverse mapping
# for arbitrary daytime decision instants. A kickoff on local date L is assigned
# to the previous local date. This calendar labeling preserves local dates across
# DST; eligibility itself uses match_decision_window elapsed-hour bounds.
match_epoch_date <- function(kickoff_utc, tz = MATCH_DECISION_TZ) {
  if (!is.character(kickoff_utc) || anyNA(kickoff_utc)) {
    stop("match_epoch_date: kickoff_utc must be non-missing character")
  }
  # An unknown zone silently falls back to UTC in R, which would return the wrong
  # epoch date without any error, so the name is checked against the zone db.
  if (!is.character(tz) || length(tz) != 1L || is.na(tz) || !tz %in% OlsonNames()) {
    stop("match_epoch_date: tz is not a known Olson timezone name: ", tz)
  }
  local <- as.POSIXct(kickoff_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (anyNA(local)) stop("match_epoch_date: kickoff_utc could not be parsed as UTC")
  # The input must be the declared canonical form; as.POSIXct ignores trailing
  # content, so "2026-05-02T20:00:00" would be read as 20:00 UTC silently.
  if (any(format(local, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") != kickoff_utc)) {
    stop("match_epoch_date: kickoff_utc must be ISO-8601 UTC 'YYYY-MM-DDTHH:MM:SSZ'")
  }
  format(as.Date(format(local, "%Y-%m-%d", tz = tz)) - 1, "%Y-%m-%d")
}

# Vectorised decision epochs, one per local date.
match_decision_epochs <- function(local_dates, hour = MATCH_DECISION_HOUR, tz = MATCH_DECISION_TZ) {
  if (!is.character(local_dates) || !length(local_dates) || anyNA(local_dates)) {
    stop("match_decision_epochs: local_dates must be a non-empty character vector")
  }
  vapply(local_dates, match_decision_epoch, character(1L), hour = hour, tz = tz,
         USE.NAMES = FALSE)
}

# ---- Forward window and eligibility -----------------------------------------

#' Build a rolling decision window
#' @md
#'
#' @param epoch_utc One finite POSIXct decision instant or a whole-second
#'   ISO-8601 UTC string. POSIXct fractions are preserved.
#' @param tz One valid Olson timezone name. The window uses elapsed hours and
#'   therefore denotes the same instants in every timezone.
#' @return A list of UTC POSIXct instants, `start_utc` and `end_utc`, defining
#'   the half-open interval [decision + 4 hours, decision + 28 hours).
#' @details Invalid instants or timezones raise an error. There are no side
#'   effects. At 20:00 Beijing this is the following natural day; daytime
#'   decisions retain the same four-hour lead and 24 elapsed-hour horizon.
match_decision_window <- function(epoch_utc, tz = MATCH_DECISION_TZ) {
  epoch <- if (inherits(epoch_utc, "POSIXct")) as.numeric(epoch_utc) else
    match_utc_seconds(epoch_utc, "match_decision_window: epoch_utc")
  if (length(epoch) != 1L || !is.finite(epoch))
    stop("match_decision_window: epoch_utc must be one finite instant")
  if (!is.character(tz) || length(tz) != 1L || is.na(tz) || !tz %in% OlsonNames()) {
    stop("match_decision_window: tz is not a known Olson timezone name: ", tz)
  }
  instant <- as.POSIXct(epoch, origin = "1970-01-01", tz = "UTC")
  start <- instant + lubridate::dhours(MATCH_WINDOW_START_HOURS)
  end <- instant + lubridate::dhours(MATCH_WINDOW_END_HOURS)
  list(start_utc = start, end_utc = end)
}

# Fixtures eligible at one decision epoch: kickoff inside the rolling 24-hour
# window starting four elapsed hours after the decision AND not excluded by
# explicit sale-state or schedule-anomaly evidence.
#   eligible  <=>  window_start <= kickoff < window_end
#              AND sale_state is not an exclusion state
#              AND no recorded cutoff contradicts the kickoff
# The lower boundary is included and the upper boundary is excluded.
#
# Returns list(eligible = <tibble>, excluded = <tibble>) so that every
# non-investment reason is counted instead of being dropped.
match_eligible_fixtures <- function(fixtures, epoch_utc, tz = MATCH_DECISION_TZ) {
  required <- c("match_id", "issue", "kickoff_utc")
  if (!is.data.frame(fixtures) || !all(required %in% names(fixtures))) {
    stop("match_eligible_fixtures: fixtures needs match_id, issue, kickoff_utc")
  }
  if (!is.character(fixtures$match_id) || !is.character(fixtures$issue) ||
      !is.character(fixtures$kickoff_utc) || anyNA(fixtures[required])) {
    stop("match_eligible_fixtures: fixtures identities must be non-missing character")
  }
  if (anyDuplicated(fixtures$match_id)) {
    stop("match_eligible_fixtures: match_id must be unique")
  }
  epoch <- match_utc_seconds(epoch_utc, "match_eligible_fixtures: epoch_utc")
  if (length(epoch) != 1L) stop("match_eligible_fixtures: epoch_utc must be one instant")
  window <- match_decision_window(epoch_utc, tz = tz)
  window_start <- as.numeric(window$start_utc)
  window_end <- as.numeric(window$end_utc)
  kickoff <- match_utc_seconds(fixtures$kickoff_utc, "match_eligible_fixtures: kickoff_utc")

  # Explicit sale-state evidence. A missing column means no evidence was supplied
  # at all, which is recorded as UNKNOWN rather than silently treated as sellable.
  if ("sale_state" %in% names(fixtures)) {
    sale_state <- as.character(fixtures$sale_state)
    sale_state[is.na(sale_state)] <- "UNKNOWN"
    bad_state <- setdiff(unique(sale_state), MATCH_SALE_STATES)
    if (length(bad_state)) {
      stop("match_eligible_fixtures: unknown sale_state value(s): ",
           paste(bad_state, collapse = ", "))
    }
  } else {
    sale_state <- rep("UNKNOWN", nrow(fixtures))
  }

  # A recorded cutoff is NOT an admission gate; it is a schedule-anomaly check.
  # A cutoff AFTER the stored kickoff means the two records contradict each other,
  # and in this store it is always the kickoff that is wrong: 95/95 such rows sit
  # on a placeholder T00:00:00 kickoff while the cutoff carries a real clock time.
  # Neither value can place the fixture in a window, so it is excluded and counted
  # rather than silently resolved in favour of one of them.
  contradicted <- rep(FALSE, nrow(fixtures))
  if ("sale_cutoff_utc" %in% names(fixtures)) {
    raw_cutoff <- fixtures$sale_cutoff_utc
    if (!is.character(raw_cutoff)) {
      stop("match_eligible_fixtures: sale_cutoff_utc must be a character column")
    }
    cutoff_known <- !is.na(raw_cutoff)
    if (any(cutoff_known)) {
      observed <- match_utc_seconds(raw_cutoff[cutoff_known],
                                 "match_eligible_fixtures: sale_cutoff_utc")
      contradicted[cutoff_known] <- observed > kickoff[cutoff_known]
    }
  }
  in_window <- kickoff >= window_start & kickoff < window_end
  state_excluded <- sale_state %in% names(MATCH_SALE_STATE_EXCLUSIONS)
  # as.character() is not cosmetic: with zero fixtures ifelse() returns
  # logical(0), which would give an empty result a different schema from the typed
  # empty template and break the contract for the empty case.
  reason <- as.character(ifelse(
    contradicted, "KICKOFF_CONTRADICTED_BY_SALE_CUTOFF",
    ifelse(!in_window,
           ifelse(kickoff < window_start,
                  "KICKOFF_BEFORE_WINDOW", "KICKOFF_AT_OR_AFTER_WINDOW"),
           ifelse(state_excluded,
                  MATCH_SALE_STATE_EXCLUSIONS[sale_state], "ELIGIBLE"))))
  out <- tibble::tibble(
    match_id = fixtures$match_id, issue = fixtures$issue,
    kickoff_utc = fixtures$kickoff_utc,
    window_start_utc = match_utc_iso(window_start, "window start"),
    window_end_utc = match_utc_iso(window_end, "window end"),
    epoch_utc = match_utc_iso(rep(epoch, length(kickoff)), "match_eligible_fixtures: epoch"),
    hours_to_kickoff = (kickoff - epoch) / 3600,
    sale_state = sale_state,
    reason = reason)
  list(eligible = out[out$reason == "ELIGIBLE", , drop = FALSE],
       excluded = out[out$reason != "ELIGIBLE", , drop = FALSE])
}

# ---- Availability: the quote that actually existed at the epoch -------------

# For every eligible fixture, pick the most recent snapshot at or before the
# epoch. This is the availability rule the contract fixes: a decision-time input
# may only be a quote that already existed then, so the selection is strictly
# backwards-looking and never repaired with a later or closing value.
#
# Returns list(priced = <tibble>, excluded = <tibble>). Each priced row carries
# the quote time, its lag behind the epoch, the interval to the previous snapshot
# of the same fixture, and the source identity, so the availability evidence
# travels with the value instead of being asserted in prose.
# `rows_by_fixture` is an optional precomputed index of `snapshots` rows by
# match_id, as returned by match_index_snapshots(). A replay walks many epochs over
# the same series, so building the index once per series keeps the selection
# linear overall instead of quadratic in the number of epochs.
match_select_snapshots <- function(snapshots, eligible, epoch_utc, rows_by_fixture = NULL) {
  snap_required <- c("match_id", "snapshot_ts", "eu_h", "eu_d", "eu_a", "source",
                     "sp_3", "sp_1", "sp_0")
  if (!is.data.frame(snapshots) || !all(snap_required %in% names(snapshots))) {
    stop("match_select_snapshots: snapshots needs ", paste(snap_required, collapse = ", "))
  }
  if (!is.data.frame(eligible) || !all(c("match_id", "issue", "kickoff_utc") %in% names(eligible))) {
    stop("match_select_snapshots: eligible needs match_id, issue, kickoff_utc")
  }
  if (!is.character(snapshots$match_id) || !is.character(snapshots$snapshot_ts) ||
      !is.character(snapshots$source) ||
      anyNA(snapshots[c("match_id", "snapshot_ts", "source")])) {
    stop("match_select_snapshots: snapshot identity, time and source must be non-missing character")
  }
  # Odds may legitimately be absent on a poll. That is a usability question
  # answered per fixture below, not a schema violation, so it is checked here
  # only for type.
  if (!is.numeric(snapshots$eu_h) || !is.numeric(snapshots$eu_d) ||
      !is.numeric(snapshots$eu_a)) {
    stop("match_select_snapshots: eu_h, eu_d and eu_a must be numeric")
  }
  epoch <- match_utc_seconds(epoch_utc, "match_select_snapshots: epoch_utc")
  if (length(epoch) != 1L) stop("match_select_snapshots: epoch_utc must be one instant")
  # Index the poll series once by fixture. A per-fixture scan of the whole series
  # would be quadratic on a real store (millions of polls), so the rows of each
  # fixture are resolved a single time here.
  if (is.null(rows_by_fixture)) {
    rows_by_fixture <- match_index_snapshots(snapshots)
  } else {
    if (!is.list(rows_by_fixture) ||
        length(rows_by_fixture) != length(unique(snapshots$match_id))) {
      stop("match_select_snapshots: rows_by_fixture must index this snapshots table")
    }
  }
  # Only the polls of the fixtures actually being selected are parsed. Parsing the
  # whole series on every call would make a replay quadratic in the number of
  # decision epochs, which is the same mistake as rescanning it per fixture.
  candidate_rows <- sort(unique(unlist(rows_by_fixture[as.character(eligible$match_id)],
                                              use.names = FALSE)))
  if (is.null(candidate_rows)) candidate_rows <- integer(0L)
  snapshot_seconds <- rep(NA_real_, nrow(snapshots))
  usable <- rep(FALSE, nrow(snapshots))
  if (length(candidate_rows)) {
    # The uniqueness check is scoped to the rows actually being selected. Running
    # it over the whole series would be correct but quadratic across the epochs of
    # a replay, and a duplicate outside the selection cannot affect this result.
    selected <- snapshots[candidate_rows, c("match_id", "snapshot_ts", "source")]
    if (anyDuplicated(selected)) {
      stop("match_select_snapshots: snapshots must be unique on match_id/snapshot_ts/source")
    }
    snapshot_seconds[candidate_rows] <-
      match_utc_seconds(snapshots$snapshot_ts[candidate_rows],
                     "match_select_snapshots: snapshot_ts")
    usable[candidate_rows] <- is.finite(snapshots$eu_h[candidate_rows]) &
      is.finite(snapshots$eu_d[candidate_rows]) & is.finite(snapshots$eu_a[candidate_rows])
  }
  priced <- excluded <- list()
  for (i in seq_len(nrow(eligible))) {
    fixture <- eligible$match_id[i]
    rows <- rows_by_fixture[[fixture]]
    if (is.null(rows)) rows <- integer(0L)
    if (!length(rows)) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = fixture, issue = eligible$issue[i], reason = "NO_SNAPSHOT_AT_ALL")
      next
    }
    if (!any(usable[rows])) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = fixture, issue = eligible$issue[i], reason = "NO_USABLE_ODDS_SNAPSHOT")
      next
    }
    rows <- rows[usable[rows]]
    before <- rows[snapshot_seconds[rows] <= epoch]
    if (!length(before)) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = fixture, issue = eligible$issue[i], reason = "NO_PRE_EPOCH_SNAPSHOT")
      next
    }
    latest <- max(snapshot_seconds[before])
    tied <- before[snapshot_seconds[before] == latest]
    # Two sources can quote the same fixture at the same instant. Picking whichever
    # row comes first would make the probabilities depend on row order, so a
    # disagreement is refused instead of silently resolved.
    if (length(tied) > 1L) {
      # Every field this selection consumes is compared, not just the European
      # odds: two rows with the same 1X2 but different SP would otherwise make the
      # estimated return depend on row order.
      odds <- unique(snapshots[tied, c("eu_h", "eu_d", "eu_a",
                                       "sp_3", "sp_1", "sp_0")])
      if (nrow(odds) > 1L) {
        stop("match_select_snapshots: conflicting quotes for ", fixture, " at ",
             match_utc_iso(latest), " with no declared source-selection policy")
      }
    }
    chosen <- tied[1L]
    previous <- before[snapshot_seconds[before] < latest]
    previous_ts <- if (length(previous)) {
      match_utc_iso(max(snapshot_seconds[previous]), "match_select_snapshots: previous")
    } else {
      NA_character_
    }
    priced[[length(priced) + 1L]] <- tibble::tibble(
      match_id = fixture, issue = eligible$issue[i],
      kickoff_utc = eligible$kickoff_utc[i], epoch_utc = match_utc_iso(epoch),
      quote_utc = snapshots$snapshot_ts[chosen],
      lag_seconds = epoch - snapshot_seconds[chosen],
      previous_quote_utc = previous_ts,
      interval_seconds = if (is.na(previous_ts)) NA_real_
        else snapshot_seconds[chosen] - max(snapshot_seconds[previous]),
      source = snapshots$source[chosen],
      eu_h = snapshots$eu_h[chosen], eu_d = snapshots$eu_d[chosen],
      eu_a = snapshots$eu_a[chosen],
      # The pre-match 北单 SP of the three outcomes AT THE CHOSEN POLL. Carried so
      # the estimated-return view can use the decision-time value under the fixed
      # SP rule; it is never an input to a probability and never to settlement.
      sp_3 = snapshots$sp_3[chosen], sp_1 = snapshots$sp_1[chosen],
      sp_0 = snapshots$sp_0[chosen])
  }
  priced_template <- tibble::tibble(
    match_id = character(), issue = character(), kickoff_utc = character(),
    epoch_utc = character(), quote_utc = character(), lag_seconds = double(),
    previous_quote_utc = character(), interval_seconds = double(), source = character(),
    eu_h = double(), eu_d = double(), eu_a = double(),
    sp_3 = double(), sp_1 = double(), sp_0 = double())
  excluded_template <- tibble::tibble(
    match_id = character(), issue = character(), reason = character())
  list(priced = dplyr::bind_rows(priced_template, priced),
       excluded = dplyr::bind_rows(excluded_template, excluded))
}

# Index a poll series by fixture once, for callers that select snapshots at many
# epochs over the same series.
match_index_snapshots <- function(snapshots) {
  if (!is.data.frame(snapshots) || !is.character(snapshots$match_id) ||
      anyNA(snapshots$match_id)) {
    stop("match_index_snapshots: snapshots needs a non-missing character match_id")
  }
  split(seq_len(nrow(snapshots)), snapshots$match_id)
}

# ---- The fixed SP-estimate rule ---------------------------------------------

# Estimated pre-match 北单 SP for a single fixture/outcome. The recorded value is
# kept for SP <= 10; an SP strictly above 10 is estimated at 4.5. A missing SP
# stays missing: it is a recorded absence, and filling it with 0 or with the
# reciprocal of a probability would invent a price.
#
# This value is used ONLY for the estimated-return view. It never enters a
# probability and never enters actual settlement.
match_sp_estimate <- function(sp, threshold = MATCH_SP_ESTIMATE_THRESHOLD,
                           value = MATCH_SP_ESTIMATE_VALUE) {
  if (!is.numeric(sp)) stop("match_sp_estimate: sp must be numeric")
  if (length(threshold) != 1L || is.na(threshold) || !is.finite(threshold) || threshold <= 0) {
    stop("match_sp_estimate: threshold must be one positive finite number")
  }
  if (length(value) != 1L || is.na(value) || !is.finite(value) || value <= 0) {
    stop("match_sp_estimate: value must be one positive finite number")
  }
  if (any(is.finite(sp) & sp <= 0)) stop("match_sp_estimate: a recorded SP must be positive")
  out <- sp
  out[is.finite(sp) & sp > threshold] <- value
  out
}

# ---- Period budget ledger ----------------------------------------------------

# Actual stake of a whole number of tickets, in CNY.
parlay_stake_cny <- function(tickets, unit_cny = PARLAY_UNIT_CNY) {
  if (length(unit_cny) != 1L || !is.numeric(unit_cny) || is.na(unit_cny) ||
      !is.finite(unit_cny) || unit_cny <= 0) {
    stop("parlay_stake_cny: unit_cny must be one positive number")
  }
  if (!is.numeric(tickets) || anyNA(tickets) || any(!is.finite(tickets)) ||
      any(tickets != trunc(tickets)) || any(tickets < 0)) {
    stop("parlay_stake_cny: tickets must be whole non-negative counts")
  }
  tickets * unit_cny
}

# How many more tickets the remaining budget can buy.
parlay_affordable_tickets <- function(remaining_cny, unit_cny = PARLAY_UNIT_CNY) {
  if (!is.numeric(remaining_cny) || anyNA(remaining_cny) ||
      any(!is.finite(remaining_cny)) || any(remaining_cny < 0)) {
    stop("parlay_affordable_tickets: remaining_cny must be finite and non-negative")
  }
  if (length(unit_cny) != 1L || !is.numeric(unit_cny) || is.na(unit_cny) ||
      !is.finite(unit_cny) || unit_cny <= 0) {
    stop("parlay_affordable_tickets: unit_cny must be one positive number")
  }
  as.integer(floor(remaining_cny / unit_cny + 1e-9))
}

# Walk the decision epochs of ONE period and account for the stake actually
# committed at each. The period ceiling is a ceiling: the remaining balance is
# carried across epochs inside the period, is never reset per day, and is never
# increased by a payout. A committed plan cannot be withdrawn and re-allocated,
# so the ledger is cumulative and monotone.
#
# Returns one row per epoch with the remaining balance before and after, plus an
# `exhausted` flag meaning "this epoch could no longer buy a single ticket".
parlay_budget_ledger <- function(stakes_cny, budget_cny = PARLAY_PERIOD_BUDGET_CNY,
                             unit_cny = PARLAY_UNIT_CNY) {
  if (!is.numeric(stakes_cny) || anyNA(stakes_cny) || any(!is.finite(stakes_cny)) ||
      any(stakes_cny < 0)) {
    stop("parlay_budget_ledger: stakes_cny must be finite and non-negative")
  }
  if (length(budget_cny) != 1L || !is.numeric(budget_cny) || is.na(budget_cny) ||
      !is.finite(budget_cny) || budget_cny <= 0) {
    stop("parlay_budget_ledger: budget_cny must be one positive number")
  }
  if (length(unit_cny) != 1L || !is.numeric(unit_cny) || is.na(unit_cny) ||
      !is.finite(unit_cny) || unit_cny <= 0) {
    stop("parlay_budget_ledger: unit_cny must be one positive number")
  }
  # Every stake must be a whole number of tickets, otherwise the ledger would
  # carry a fractional ticket that cannot exist.
  units <- stakes_cny / unit_cny
  if (any(abs(units - round(units)) > 1e-9)) {
    stop("parlay_budget_ledger: every stake must be a whole multiple of unit_cny")
  }
  remaining_before <- budget_cny - c(0, cumsum(stakes_cny))[seq_along(stakes_cny)]
  remaining_after <- budget_cny - cumsum(stakes_cny)
  if (any(remaining_after < -1e-9)) {
    stop("parlay_budget_ledger: cumulative stake exceeds the period budget")
  }
  tibble::tibble(
    epoch_index = seq_along(stakes_cny),
    stake_cny = stakes_cny,
    cumulative_stake_cny = cumsum(stakes_cny),
    remaining_before_cny = remaining_before,
    remaining_after_cny = remaining_after,
    affordable_tickets_after = parlay_affordable_tickets(remaining_after, unit_cny),
    exhausted = parlay_affordable_tickets(remaining_after, unit_cny) == 0L)
}

# ---- Group and physical-ticket admission ------------------------------------

# Identity of a group is the actual SET of its fixtures, so two groups built in a
# different order are the same group. This is what makes "deepening the same
# group" distinguishable from "opening a new group".
#
# `legs` is REQUIRED. There is no ambient default width: a caller that does not say
# how many legs its group has would silently inherit the session's current 7 and
# reshape a 6- or 8-leg plan, so the width is either supplied explicitly or inferred
# from `match_ids` when `legs` is NULL. Every value is validated here rather than
# trusted, so a bad width fails at the identity boundary.
parlay_group_key <- function(match_ids, legs = NULL) {
  if (!is.character(match_ids) || !length(match_ids) || anyNA(match_ids) ||
      anyDuplicated(match_ids)) {
    stop("parlay_group_key: match_ids must be distinct non-missing character ids")
  }
  if (is.null(legs)) {
    legs <- length(match_ids)
  }
  if (length(legs) != 1L || !is.numeric(legs) || is.na(legs) ||
      legs != trunc(legs) || legs < 1L) {
    stop("parlay_group_key: legs must be one whole number of at least 1")
  }
  legs <- as.integer(legs)
  if (length(match_ids) != legs) {
    stop(sprintf("parlay_group_key: match_ids must be %d distinct non-missing ids", legs))
  }
  paste(sort(match_ids), collapse = "|")
}

# Identity of one physical ticket: the (fixture, outcome) pairs, order independent.
# Two tickets with the same pairs are the same physical ticket even if they were
# reached from different groups. The width is the actual number of aligned pairs,
# so ticket identity works for 6, 7 or 8 legs without a fixed constant.
parlay_physical_ticket_key <- function(match_ids, outcomes) {
  width <- length(match_ids)
  if (!is.character(match_ids) || !is.numeric(outcomes) || width < 1L ||
      length(outcomes) != width ||
      anyNA(match_ids) || anyNA(outcomes) || anyDuplicated(match_ids)) {
    stop("parlay_physical_ticket_key: match_ids and outcomes must be ",
         "aligned, distinct and non-missing, with at least one leg")
  }
  if (any(outcomes != trunc(outcomes)) || any(outcomes < 1L) || any(outcomes > 3L)) {
    stop("parlay_physical_ticket_key: outcomes must be whole numbers in 1..3")
  }
  paste(sort(paste(match_ids, as.integer(outcomes), sep = ":")), collapse = "|")
}

# Admit or refuse one candidate fixture group for a period, given the groups
# already bought in that same period. The group width is taken from the candidate
# itself, so admission is not tied to a fixed seven.
#
#   * A candidate whose fixture SET equals an already-bought group is a
#     DEEPENING, not a new group: it is admitted and does not consume reuse.
#   * A new group is admitted only when every one of its fixtures stays within
#     `max_reuse` cumulative group uses, AND it shares at most `max_overlap`
#     fixtures with EVERY group already bought in this period.
#
# The numeric caps are parameters on purpose: the contract leaves their values to
# #496, so this module validates the constraint without claiming a chosen
# threshold.
parlay_group_admission <- function(prior_groups, candidate, max_reuse, max_overlap) {
  if (!is.list(prior_groups)) stop("parlay_group_admission: prior_groups must be a list")
  if (!is.character(candidate) || !length(candidate) ||
      anyNA(candidate) || anyDuplicated(candidate)) {
    stop("parlay_group_admission: candidate must be distinct non-missing ids")
  }
  width <- length(candidate)
  prior_groups <- lapply(prior_groups, function(g) {
    if (!is.character(g) || length(g) != width || anyNA(g) || anyDuplicated(g)) {
      stop("parlay_group_admission: every prior group must be ", width,
           " distinct non-missing ids, matching the candidate width")
    }
    g
  })
  if (length(max_reuse) != 1L || !is.numeric(max_reuse) || is.na(max_reuse) ||
      max_reuse != trunc(max_reuse) || max_reuse < 1) {
    stop("parlay_group_admission: max_reuse must be one whole number of at least 1")
  }
  if (length(max_overlap) != 1L || !is.numeric(max_overlap) || is.na(max_overlap) ||
      max_overlap != trunc(max_overlap) || max_overlap < 0 || max_overlap > width) {
    stop("parlay_group_admission: max_overlap must be one whole number in 0..",
         width)
  }
  candidate_key <- parlay_group_key(candidate, width)
  prior_keys <- vapply(prior_groups, parlay_group_key, character(1L), legs = width)
  if (candidate_key %in% prior_keys) {
    return(list(admitted = TRUE, is_new_group = FALSE,
                reason = "SAME_GROUP_DEEPENING",
                max_uses_after = NA_integer_, max_overlap_seen = NA_integer_))
  }
  # Reuse and overlap are counted over DISTINCT prior groups. The same seven
  # fixtures bought twice is one group deepened, not two groups that reuse each
  # other, so a caller that passes the same set twice must not burn two uses.
  prior_groups <- prior_groups[!duplicated(prior_keys)]
  uses <- vapply(candidate, function(id) {
    sum(vapply(prior_groups, function(g) id %in% g, logical(1L)))
  }, integer(1L))
  max_uses_after <- max(uses) + 1L
  overlaps <- vapply(prior_groups, function(g) length(intersect(g, candidate)), integer(1L))
  max_overlap_seen <- if (length(overlaps)) max(overlaps) else 0L
  if (max_uses_after > max_reuse) {
    return(list(admitted = FALSE, is_new_group = TRUE,
                reason = "FIXTURE_REUSE_CAP_EXCEEDED",
                max_uses_after = max_uses_after, max_overlap_seen = max_overlap_seen))
  }
  if (max_overlap_seen > max_overlap) {
    return(list(admitted = FALSE, is_new_group = TRUE,
                reason = "GROUP_OVERLAP_CAP_EXCEEDED",
                max_uses_after = max_uses_after, max_overlap_seen = max_overlap_seen))
  }
  list(admitted = TRUE, is_new_group = TRUE, reason = "ADMITTED",
       max_uses_after = max_uses_after, max_overlap_seen = max_overlap_seen)
}

# Which of a candidate group's physical tickets have already been bought in this
# period. The same physical ticket may not be bought twice, and this check spans
# the whole period, not one group.
parlay_ticket_admission <- function(prior_ticket_keys, candidate_keys) {
  if (!is.character(prior_ticket_keys)) {
    stop("parlay_ticket_admission: prior_ticket_keys must be character")
  }
  if (!is.character(candidate_keys) || !length(candidate_keys) || anyNA(candidate_keys)) {
    stop("parlay_ticket_admission: candidate_keys must be a non-empty character vector")
  }
  if (anyDuplicated(candidate_keys)) {
    stop("parlay_ticket_admission: candidate_keys contains a duplicate within the candidate")
  }
  tibble::tibble(
    ticket_key = candidate_keys,
    duplicate_of_period = candidate_keys %in% prior_ticket_keys)
}

# ---- The three structural comparison definitions ----------------------------

# The contract fixes three same-budget structural definitions to compare, plus
# the two budget-tier names. "3222221" and "2222211" are names for the 96-ticket
# and 32-ticket tiers; they do not imply a hard mask.
parlay_structural_definitions <- function() {
  tibble::tibble(
    structure = c("4x128", "8x64", "4x96_plus_4x32", "tier_96", "tier_32"),
    groups = c(4L, 8L, 8L, 1L, 1L),
    pattern = c("2^7", "2^6", "3*2^5 then 2^5", "3*2^5", "2^5"),
    tickets_per_group = c("128 x4", "64 x8", "96 x4 + 32 x4", "96", "32"),
    total_tickets = c(512L, 512L, 512L, 96L, 32L),
    total_cny = c(1024, 1024, 1024, 192, 64),
    # The ticket count of each group the period plan intends to open, in order.
    # Keeping it beside the totals lets the plan loop and the totals be checked
    # against each other instead of drifting.
    group_tickets = list(rep(128L, 4L), rep(64L, 8L), c(rep(96L, 4L), rep(32L, 4L)),
                         rep(96L, 1L), rep(32L, 1L)),
    note = c("every leg covered twice", "every leg covered twice, more groups",
             "four deep groups plus four shallow groups",
             "3222221 tier", "2222211 tier"))
}

# ---- Typed contract templates and validation --------------------------------

# One typed empty table per contract entity, so an empty result is still a table
# with the right schema rather than NULL or an untyped zero-row frame.
parlay_contract_templates <- function() {
  list(
    decision_epochs = tibble::tibble(
      issue = character(), local_date = character(), epoch_utc = character()),
    eligible = tibble::tibble(
      match_id = character(), issue = character(), kickoff_utc = character(),
      window_start_utc = character(), window_end_utc = character(),
      epoch_utc = character(), hours_to_kickoff = double(),
      sale_state = character(), reason = character()),
    priced = tibble::tibble(
      match_id = character(), issue = character(), kickoff_utc = character(),
      epoch_utc = character(), quote_utc = character(), lag_seconds = double(),
      previous_quote_utc = character(), interval_seconds = double(),
      source = character(), eu_h = double(), eu_d = double(), eu_a = double(),
      sp_3 = double(), sp_1 = double(), sp_0 = double()),
    probabilities = tibble::tibble(
      match_id = character(), issue = character(), epoch_utc = character(),
      p_W = double(), p_D = double(), p_L = double(),
      lambda_home = double(), lambda_away = double(),
      expected_total = double(), fit_residual = double(), rho = double(),
      sp_3 = double(), sp_1 = double(), sp_0 = double()),
    groups = tibble::tibble(
      structure = character(), issue = character(), epoch_utc = character(),
      group = integer(), group_key = character(), tickets = integer(),
      stake_cny = double(), max_uses_after = integer(), max_overlap_seen = integer()),
    tickets = tibble::tibble(
      structure = character(), issue = character(), epoch_utc = character(),
      group = integer(), group_key = character(), ticket_key = character(),
      combo_row = integer(), probability = double()),
    settlements = tibble::tibble(
      structure = character(), issue = character(), epoch_utc = character(),
      group = integer(), group_key = character(), tickets = integer(),
      cost_cny = double(), settleable = logical(), outcome_known = logical(),
      hit = logical(), payout_cny = double(),
      estimated_expected_return_cny = double(), true_rank = integer(),
      covered = logical(), mask_excluded = logical(), reason = character()),
    ledger = tibble::tibble(
      structure = character(), issue = character(), epoch_utc = character(),
      n_priced = integer(), groups_opened = integer(), tickets = integer(),
      stake_cny = double(), remaining_after_cny = double(), reason = character())
  )
}

# Fail closed when a contract table is missing or carries the wrong column type.
# Only the columns listed in the template are checked, so callers may carry extra
# diagnostic columns.
parlay_validate_contract <- function(bundle) {
  if (!is.list(bundle) || is.null(names(bundle))) {
    stop("parlay_validate_contract: bundle must be a named list")
  }
  templates <- parlay_contract_templates()
  unknown <- setdiff(names(bundle), names(templates))
  if (length(unknown)) {
    stop("parlay_validate_contract: unknown contract table(s): ", paste(unknown, collapse = ", "))
  }
  for (name in names(bundle)) {
    value <- bundle[[name]]
    if (!is.data.frame(value)) {
      stop("parlay_validate_contract: ", name, " must be a data frame")
    }
    template <- templates[[name]]
    missing <- setdiff(names(template), names(value))
    if (length(missing)) {
      stop("parlay_validate_contract: ", name, " is missing column(s): ",
           paste(missing, collapse = ", "))
    }
    for (column in names(template)) {
      if (typeof(value[[column]]) != typeof(template[[column]])) {
        stop("parlay_validate_contract: ", name, "$", column, " must be ",
             typeof(template[[column]]), ", not ", typeof(value[[column]]))
      }
    }
  }
  invisible(TRUE)
}
