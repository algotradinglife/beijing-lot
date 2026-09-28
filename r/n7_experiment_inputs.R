# Read-only extraction of the N7 experiment inputs from the live collector store.
#
# Why this file exists: the decision-epoch contract needs fixtures, the odds/SP
# poll series and the settlement, each with an explicit identity and an explicit
# timezone. The live store does not declare its timezones, so this module makes
# the interpretation explicit, records the evidence for it, and fails closed when
# a value cannot be interpreted instead of guessing.
#
# Timezone evidence (measured, not assumed). `matches.kickoff_ts` is naive local
# Asia/Shanghai; `snapshots.snapshot_ts` and `matches.created_ts` are UTC.
# Measured on issues 26083 and 26085: the last European-odds change of a fixture
# sits at a median of -7.91 h from `kickoff_ts` read as naive, with 444 of 627
# fixtures in the -8 h bin, i.e. the market stops moving exactly at kickoff once
# the 8-hour CST/UTC offset is accounted for. The declared `kickoff_tz` argument
# carries that interpretation and is a parameter, not a hidden constant.
#
# No function here writes to the database, fetches from the network, or reads a
# label before the caller has frozen a ticket set. The connection is opened
# read-only.

# ---- Connection --------------------------------------------------------------

# Open the live store read-only. The caller owns the connection and must close
# it; nothing here keeps hidden state between calls.
n7_open_store <- function(db_path) {
  if (!is.character(db_path) || length(db_path) != 1L || is.na(db_path) ||
      !file.exists(db_path)) {
    stop("n7_open_store: db_path must be an existing SQLite file")
  }
  RSQLite::dbConnect(RSQLite::SQLite(), db_path, flags = RSQLite::SQLITE_RO)
}

# ---- Fixtures ----------------------------------------------------------------

# Fixtures of the requested issues, with kickoff normalised to UTC.
#
# `kickoff_tz` is the timezone the stored naive kickoff string is in. It is a
# required declaration: passing the wrong one shifts every window boundary, so
# the caller must state it rather than inherit a default.
n7_read_fixtures <- function(connection, issues, kickoff_tz = N7_DECISION_TZ) {
  if (!inherits(connection, "SQLiteConnection")) {
    stop("n7_read_fixtures: connection must be an open SQLite connection")
  }
  issues <- n7_check_issues(issues)
  if (!is.character(kickoff_tz) || length(kickoff_tz) != 1L || is.na(kickoff_tz) ||
      !nzchar(kickoff_tz)) {
    stop("n7_read_fixtures: kickoff_tz must be one non-empty timezone name")
  }
  # An unknown zone silently falls back to UTC in R, which would shift every
  # window boundary by the offset without an error, so the name is checked
  # against the zone database rather than trusted.
  if (!kickoff_tz %in% OlsonNames()) {
    stop("n7_read_fixtures: kickoff_tz is not a known Olson timezone name: ", kickoff_tz)
  }
  rows <- DBI::dbGetQuery(connection,
    "SELECT match_id, issue, match_idx, league, kickoff_ts, home, away, handicap_line
       FROM matches WHERE issue IN (SELECT value FROM json_each(?))",
    params = list(jsonlite::toJSON(as.list(issues), auto_unbox = TRUE)))
  if (!nrow(rows)) stop("n7_read_fixtures: no fixtures for the requested issues")
  if (anyNA(rows$match_id) || anyNA(rows$kickoff_ts)) {
    stop("n7_read_fixtures: a fixture is missing its identity or kickoff")
  }
  if (anyDuplicated(rows$match_id)) stop("n7_read_fixtures: duplicated match_id")
  # The stored form is declared as a naive local wall-clock time. as.POSIXct()
  # ignores trailing content, so "2026-05-02T20:00:00Z" would be silently read as
  # 20:00 LOCAL and shifted by the zone offset; the round trip is therefore
  # checked explicitly and anything that is not exactly the declared form stops.
  kickoff_text <- as.character(rows$kickoff_ts)
  kickoff <- as.POSIXct(kickoff_text, tz = kickoff_tz, format = "%Y-%m-%dT%H:%M:%S")
  if (anyNA(kickoff)) {
    stop("n7_read_fixtures: a kickoff could not be interpreted in ", kickoff_tz)
  }
  round_trip <- format(kickoff, "%Y-%m-%dT%H:%M:%S", tz = kickoff_tz)
  if (any(round_trip != kickoff_text)) {
    bad <- unique(kickoff_text[round_trip != kickoff_text])
    stop("n7_read_fixtures: a kickoff is not the declared naive-local form ",
         "YYYY-MM-DDTHH:MM:SS: ", paste(utils::head(bad, 3L), collapse = ", "))
  }
  tibble::tibble(
    match_id = as.character(rows$match_id),
    issue = as.character(rows$issue),
    match_idx = n7_stored_integer(rows$match_idx, "n7_read_fixtures: match_idx"),
    league = as.character(rows$league),
    kickoff_utc = n7_utc_iso(as.numeric(kickoff), "n7_read_fixtures: kickoff"),
    home = as.character(rows$home),
    away = as.character(rows$away),
    handicap_line = n7_stored_numeric(rows$handicap_line, "n7_read_fixtures: handicap_line"))
}

# ---- Poll series -------------------------------------------------------------

# The append-only odds/SP poll series of the requested issues, in UTC.
#
# The series is returned whole rather than pre-filtered to one epoch: which poll
# was available at a decision instant is the contract's question, answered by
# n7_select_snapshots, not by this reader.
n7_read_snapshots <- function(connection, issues, max_rows = Inf) {
  if (!inherits(connection, "SQLiteConnection")) {
    stop("n7_read_snapshots: connection must be an open SQLite connection")
  }
  issues <- n7_check_issues(issues)
  rows <- DBI::dbGetQuery(connection,
    "SELECT s.match_id, m.issue, s.snapshot_ts, s.eu_h, s.eu_d, s.eu_a,
            s.sp_3, s.sp_1, s.sp_0, s.source
       FROM snapshots s JOIN matches m ON m.match_id = s.match_id
      WHERE m.issue IN (SELECT value FROM json_each(?))
      ORDER BY s.match_id, s.snapshot_ts",
    params = list(jsonlite::toJSON(as.list(issues), auto_unbox = TRUE)))
  if (!nrow(rows)) stop("n7_read_snapshots: no snapshots for the requested issues")
  if (nrow(rows) > max_rows) {
    stop("n7_read_snapshots: ", nrow(rows), " rows exceeds the declared max_rows of ",
         max_rows)
  }
  if (anyNA(rows$match_id) || anyNA(rows$snapshot_ts) || anyNA(rows$source)) {
    stop("n7_read_snapshots: a snapshot is missing its identity, time or source")
  }
  if (anyDuplicated(rows[c("match_id", "snapshot_ts", "source")])) {
    stop("n7_read_snapshots: duplicated match_id/snapshot_ts/source")
  }
  # The stored representation is declared UTC with an explicit Z. It is parsed
  # strictly and re-emitted canonically here, so every downstream consumer sees the
  # same shape the selector requires instead of whatever the store happened to hold.
  snapshot_seconds <- n7_utc_seconds(rows$snapshot_ts, "n7_read_snapshots: snapshot_ts")
  tibble::tibble(
    match_id = as.character(rows$match_id),
    issue = as.character(rows$issue),
    snapshot_ts = n7_utc_iso(snapshot_seconds, "n7_read_snapshots: snapshot_ts"),
    eu_h = n7_stored_numeric(rows$eu_h, "n7_read_snapshots: eu_h"),
    eu_d = n7_stored_numeric(rows$eu_d, "n7_read_snapshots: eu_d"),
    eu_a = n7_stored_numeric(rows$eu_a, "n7_read_snapshots: eu_a"),
    sp_3 = n7_stored_numeric(rows$sp_3, "n7_read_snapshots: sp_3"),
    sp_1 = n7_stored_numeric(rows$sp_1, "n7_read_snapshots: sp_1"),
    sp_0 = n7_stored_numeric(rows$sp_0, "n7_read_snapshots: sp_0"),
    source = as.character(rows$source))
}

# ---- Settlement --------------------------------------------------------------

# The authoritative settlement of the requested issues. `result_code` is the
# settled 让球胜平负 code and `winning_sp` the settled SP of that outcome.
# A missing winning_sp is kept as NA: it is a recorded absence that makes a
# group un-settleable, and it must not be turned into a zero or a loss.
n7_read_settlements <- function(connection, issues) {
  if (!inherits(connection, "SQLiteConnection")) {
    stop("n7_read_settlements: connection must be an open SQLite connection")
  }
  issues <- n7_check_issues(issues)
  rows <- DBI::dbGetQuery(connection,
    "SELECT match_id, issue, fthg, ftag, result_code, winning_sp, source
       FROM settlements WHERE issue IN (SELECT value FROM json_each(?))",
    params = list(jsonlite::toJSON(as.list(issues), auto_unbox = TRUE)))
  if (!nrow(rows)) stop("n7_read_settlements: no settlement for the requested issues")
  if (anyDuplicated(rows$match_id)) stop("n7_read_settlements: duplicated match_id")
  if (anyNA(rows$result_code)) {
    stop("n7_read_settlements: a settlement is missing its result code")
  }
  # result_code must be one of the three declared codes; anything else would be
  # silently mapped by n7_outcome_code and is refused here instead.
  if (any(!rows$result_code %in% c("3", "1", "0"))) {
    stop("n7_read_settlements: unknown result_code value(s): ",
         paste(unique(rows$result_code[!rows$result_code %in% c("3", "1", "0")]),
               collapse = ", "))
  }
  winning_sp <- n7_stored_numeric(rows$winning_sp, "n7_read_settlements: winning_sp")
  if (any(is.finite(winning_sp) & winning_sp <= 0)) {
    stop("n7_read_settlements: a recorded winning_sp must be positive")
  }
  tibble::tibble(
    match_id = as.character(rows$match_id),
    issue = as.character(rows$issue),
    fthg = n7_stored_integer(rows$fthg, "n7_read_settlements: fthg"),
    ftag = n7_stored_integer(rows$ftag, "n7_read_settlements: ftag"),
    result_code = as.character(rows$result_code),
    winning_sp = n7_stored_numeric(rows$winning_sp, "n7_read_settlements: winning_sp"),
    source = as.character(rows$source))
}

# ---- Stored-value conversion -------------------------------------------------

# Convert one stored column, keeping a genuine SQL NULL distinct from a value the
# store cannot represent as a number. as.numeric("") is NA with only a warning,
# and that NA would enter the pipeline as a "recorded absence" and silently change
# which quote is chosen, so a conversion failure stops instead.
# ---- Per-match sale cutoff ---------------------------------------------------

# The 北单 sale cutoff recorded NEXT TO each match on the source listing
# ("截止时间：YYYY-MM-DD HH:MM"). It feeds the SCHEDULE-ANOMALY check only: a
# recorded cutoff later than the stored kickoff means the two records contradict
# each other. It is NOT an admission gate -- the contract retired the per-match
# minute stop-sale rule and asks for it to be deleted, not rebuilt.
#
# The label is naive local wall-clock time in `cutoff_tz`, so the caller declares
# the zone instead of inheriting one. A row that CARRIES the marker but whose
# value cannot be parsed stops the read: a conversion failure must never be
# downgraded to a missing value. A row with no marker is a genuine absence and
# comes back NA; the caller treats an absent cutoff as "no anomaly evidence",
# which is not the same as "verified sellable".
#
# Returns tibble(issue, match_idx, sale_cutoff_local, sale_cutoff_utc). The
# cutoff is used ONLY for the schedule-anomaly check; it is not an admission gate.
n7_read_sale_cutoffs <- function(connection, issues, cutoff_tz = N7_DECISION_TZ) {
  if (!inherits(connection, "SQLiteConnection")) {
    stop("n7_read_sale_cutoffs: connection must be an open SQLite connection")
  }
  issues <- n7_check_issues(issues)
  if (!is.character(cutoff_tz) || length(cutoff_tz) != 1L || is.na(cutoff_tz) ||
      !cutoff_tz %in% OlsonNames()) {
    stop("n7_read_sale_cutoffs: cutoff_tz is not a known Olson timezone name: ", cutoff_tz)
  }
  rows <- DBI::dbGetQuery(connection,
    "SELECT issue, match_idx, raw_row FROM nowscore_bjdc_matches
      WHERE issue IN (SELECT value FROM json_each(?))",
    params = list(jsonlite::toJSON(as.list(issues), auto_unbox = TRUE)))
  if (!nrow(rows)) {
    stop("n7_read_sale_cutoffs: no nowscore matches for the requested issues")
  }
  raw <- as.character(rows$raw_row)
  if (anyNA(raw)) stop("n7_read_sale_cutoffs: a stored row has no raw_row")
  marker <- "截止时间："
  # The MARKER is located on its own, separately from the timestamp shape. A
  # single combined regex would simply fail to match "截止时间：nonsense" and the
  # row would look like a genuine absence, silently turning a parse failure into a
  # missing value. Locating the marker first makes that case detectable.
  marker_at <- regexpr(marker, raw, fixed = TRUE)
  has_marker <- marker_at > 0
  local <- rep(NA_character_, length(raw))
  if (any(has_marker)) {
    rest <- substring(raw[has_marker], marker_at[has_marker] + nchar(marker))
    # The WHOLE field must be a timestamp followed by an explicit terminator (a
    # tag, quote, whitespace or end of string). Taking only the first 16
    # characters would accept "2026-05-03 02:5599nonsense" as 02:55.
    # The terminator must be what the source actually uses after the label: the
    # start of a closing tag, a quote, whitespace, or end of string. Accepting any
    # non-digit would silently truncate "02:55nonsense", "02:55:99" and "02:55Z".
    terminator <- '("|[[:space:]]|</|$)'
    well_formed <- grepl(
      paste0("^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}", terminator), rest)
    candidate <- substr(rest, 1L, 16L)
    if (any(!well_formed)) {
      stop("n7_read_sale_cutoffs: ", sum(!well_formed),
           " row(s) carry the cutoff marker but no parsable value, e.g. '",
           substr(rest[!well_formed][1L], 1L, 40L), "'")
    }
    local[has_marker] <- candidate
  }
  found <- has_marker
  utc <- rep(NA_character_, length(raw))
  if (any(found)) {
    utc[found] <- n7_local_to_utc_iso(local[found], tz = cutoff_tz,
                                      what = "n7_read_sale_cutoffs: cutoff")
  }
  out <- tibble::tibble(
    issue = as.character(rows$issue),
    match_idx = n7_stored_integer(rows$match_idx, "n7_read_sale_cutoffs: match_idx"),
    sale_cutoff_local = local,
    sale_cutoff_utc = utc)
  if (anyDuplicated(out[c("issue", "match_idx")])) {
    stop("n7_read_sale_cutoffs: duplicated (issue, match_idx)")
  }
  out[order(out$issue, out$match_idx), , drop = FALSE]
}

n7_stored_numeric <- function(values, what) {
  if (is.logical(values) && all(is.na(values))) return(rep(NA_real_, length(values)))
  if (is.numeric(values)) {
    converted <- as.numeric(values)
  } else if (is.character(values)) {
    converted <- suppressWarnings(as.numeric(values))
    # An empty string is a record the store cannot represent as a number, NOT a
    # recorded absence: only a genuine NULL may become NA.
    failed <- is.na(converted) & !is.na(values)
    if (any(failed)) {
      stop(what, " has ", sum(failed), " value(s) that are not numbers: ",
           paste(utils::head(unique(values[failed]), 3L), collapse = ", "))
    }
  } else {
    stop(what, " must be numeric or text in the store")
  }
  # Every path reaches the same finiteness check, including an already-numeric
  # column: an infinite quote must be refused, not silently carried or dropped.
  # NaN is NA to R but is not a recorded absence, so it is named separately.
  nan <- is.nan(converted)
  if (any(nan)) {
    stop(what, " has ", sum(nan), " NaN value(s)")
  }
  non_finite <- !is.na(converted) & !is.finite(converted)
  if (any(non_finite)) {
    stop(what, " has ", sum(non_finite), " non-finite value(s): ",
         paste(utils::head(unique(converted[non_finite]), 3L), collapse = ", "))
  }
  converted
}

# The same contract for whole-number columns. The range is checked before the
# coercion, because as.integer() turns an out-of-range value into NA with only a
# warning, which would smuggle a missing value past the boundary.
n7_stored_integer <- function(values, what) {
  converted <- n7_stored_numeric(values, what)
  if (any(converted != trunc(converted), na.rm = TRUE)) {
    stop(what, " must be whole numbers")
  }
  # R reserves -2147483648 for NA_integer_, so it is NOT an admissible value even
  # though it is representable: as.integer() would turn it into a missing value.
  out_of_range <- !is.na(converted) &
    (converted > .Machine$integer.max | converted < -.Machine$integer.max)
  if (any(out_of_range)) {
    stop(what, " has ", sum(out_of_range), " value(s) outside the integer range: ",
         paste(utils::head(unique(converted[out_of_range]), 3L), collapse = ", "))
  }
  as.integer(converted)
}

# ---- Shared validation and provenance ---------------------------------------

# Issue codes are identifiers: they stay character, are never coerced to numbers,
# and are unique.
n7_check_issues <- function(issues) {
  if (!is.character(issues) || !length(issues) || anyNA(issues) ||
      any(!nzchar(issues)) || anyDuplicated(issues)) {
    stop("issues must be a non-empty, unique, non-missing character vector")
  }
  issues
}

# sha256 of every bound input file, so a receipt can name the exact bytes the
# result was produced from.
n7_file_hashes <- function(paths, project_root = ".") {
  if (!is.character(paths) || !length(paths) || anyNA(paths)) {
    stop("n7_file_hashes: paths must be a non-empty character vector")
  }
  resolved <- file.path(project_root, paths)
  missing <- paths[!file.exists(resolved)]
  if (length(missing)) {
    stop("n7_file_hashes: missing file(s): ", paste(missing, collapse = ", "))
  }
  stats::setNames(
    vapply(resolved, function(path) digest::digest(file = path, algo = "sha256"),
           character(1L)),
    paths)
}
