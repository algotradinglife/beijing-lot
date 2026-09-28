# Tests for r/n7_experiment_inputs.R.
#
# The reader is the boundary where an undeclared timezone, a coerced identifier or
# a missing SP would enter the experiment silently. These tests use a temporary
# SQLite store with the same shape as the live one, so they are deterministic and
# never touch data/beidan_live.db.

source(testthat::test_path("..", "..", "r", "n7_experiment_contract.R"))
source(testthat::test_path("..", "..", "r", "n7_experiment_inputs.R"))

n7_test_store <- function() {
  path <- tempfile(fileext = ".db")
  connection <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(connection, "CREATE TABLE matches (
    match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER, league TEXT,
    kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL)")
  DBI::dbExecute(connection, "CREATE TABLE snapshots (
    match_id TEXT, snapshot_ts TEXT, eu_h REAL, eu_d REAL, eu_a REAL,
    sp_3 REAL, sp_1 REAL, sp_0 REAL, source TEXT)")
  DBI::dbExecute(connection, "CREATE TABLE settlements (
    match_id TEXT PRIMARY KEY, issue TEXT, fthg INTEGER, ftag INTEGER,
    result_code TEXT, winning_sp REAL, source TEXT)")
  DBI::dbExecute(connection, "INSERT INTO matches VALUES
    ('m1','26051',1,'EPL','2026-05-02T20:00:00','A','B',-1.0),
    ('m2','26051',2,'EPL','2026-05-03T03:00:00','C','D',0.0),
    ('m3','26052',1,'EPL','2026-05-04T20:00:00','E','F',1.0)")
  DBI::dbExecute(connection, "INSERT INTO snapshots VALUES
    ('m1','2026-05-02T10:00:00Z',1.60,3.90,5.50,2.1,3.4,4.5,'merged'),
    ('m1','2026-05-02T11:00:00Z',NULL,NULL,NULL,NULL,NULL,NULL,'merged'),
    ('m2','2026-05-02T11:00:00Z',2.40,3.30,2.90,1.9,3.2,3.8,'merged'),
    ('m2','2026-05-03T01:00:00Z',2.45,3.25,2.95,1.8,3.1,3.9,'merged')")
  DBI::dbExecute(connection, "INSERT INTO settlements VALUES
    ('m1','26051',2,0,'3',2.10,'500.com'),
    ('m2','26051',1,1,'1',NULL,'500.com')")
  DBI::dbDisconnect(connection)
  path
}

n7_test_store_path <- local({
  cached <- NULL
  function() {
    if (is.null(cached)) cached <<- n7_test_store()
    cached
  }
})

testthat::test_that("n7_open_store opens the store read-only", {
  expect_error(n7_open_store(tempfile(fileext = ".db")), "existing SQLite file")
  expect_error(n7_open_store(NA_character_), "existing SQLite file")
  connection <- n7_open_store(n7_test_store_path())
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  expect_s4_class(connection, "SQLiteConnection")
  # A read-only handle cannot create or drop anything.
  expect_error(DBI::dbExecute(connection, "CREATE TABLE nope (a INTEGER)"))
  expect_equal(DBI::dbGetQuery(connection, "SELECT count(*) n FROM matches")$n, 3L)
})

testthat::test_that("n7_read_fixtures interprets the naive kickoff in the declared zone", {
  connection <- n7_open_store(n7_test_store_path())
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  fixtures <- n7_read_fixtures(connection, "26051", kickoff_tz = "Asia/Shanghai")
  expect_s3_class(fixtures, "tbl_df")
  expect_equal(nrow(fixtures), 2L)
  # 20:00 CST is 12:00 UTC; 03:00 CST is 19:00 UTC the previous day.
  expect_equal(fixtures$kickoff_utc,
               c("2026-05-02T12:00:00Z", "2026-05-02T19:00:00Z"))
  expect_type(fixtures$match_id, "character")
  expect_type(fixtures$issue, "character")
  expect_equal(fixtures$handicap_line, c(-1, 0))
  # The same naive string read as UTC is eight hours earlier: the declaration is
  # load-bearing, not cosmetic.
  as_utc <- n7_read_fixtures(connection, "26051", kickoff_tz = "UTC")
  expect_equal(as.numeric(as.POSIXct(as_utc$kickoff_utc, format = "%Y-%m-%dT%H:%M:%SZ",
                                     tz = "UTC")) -
                 as.numeric(as.POSIXct(fixtures$kickoff_utc, format = "%Y-%m-%dT%H:%M:%SZ",
                                       tz = "UTC")),
               rep(8 * 3600, 2L))
  expect_error(n7_read_fixtures(connection, "99999"), "no fixtures")
  expect_error(n7_read_fixtures(connection, "26051", kickoff_tz = "Not/AZone"),
               "not a known Olson timezone")
  expect_error(n7_read_fixtures(connection, "26051", kickoff_tz = ""), "non-empty timezone")
})

testthat::test_that("n7_read_snapshots keeps missing odds as a recorded absence", {
  connection <- n7_open_store(n7_test_store_path())
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  snapshots <- n7_read_snapshots(connection, "26051")
  expect_s3_class(snapshots, "tbl_df")
  expect_equal(nrow(snapshots), 4L)
  # Ordered by fixture then time.
  # Emitted canonically in the declared UTC form, so the selector can consume the
  # reader's output directly instead of the two disagreeing about the shape.
  expect_equal(snapshots$snapshot_ts,
               c("2026-05-02T10:00:00Z", "2026-05-02T11:00:00Z",
                 "2026-05-02T11:00:00Z", "2026-05-03T01:00:00Z"))
  # A poll with no European odds is NA, not zero and not dropped.
  expect_true(is.na(snapshots$eu_h[2L]))
  expect_equal(snapshots$sp_3[2L], NA_real_)
  expect_type(snapshots$source, "character")
  expect_error(n7_read_snapshots(connection, "26051", max_rows = 2L), "exceeds the declared")
  expect_error(n7_read_snapshots(connection, "99999"), "no snapshots")
})

testthat::test_that("n7_read_settlements refuses an unknown code and a bad SP", {
  connection <- n7_open_store(n7_test_store_path())
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  settlement <- n7_read_settlements(connection, "26051")
  expect_equal(settlement$result_code, c("3", "1"))
  # A missing winning_sp stays missing: it makes a group un-settleable rather
  # than a loss.
  expect_equal(settlement$winning_sp, c(2.1, NA_real_))
  expect_type(settlement$fthg, "integer")
  expect_error(n7_read_settlements(connection, "99999"), "no settlement")
})

testthat::test_that("n7_read_settlements stops on a code or SP the contract does not define", {
  path <- n7_test_store()
  connection <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(connection, "INSERT INTO settlements VALUES ('m3','26052',0,1,'9',1.5,'x')")
  DBI::dbDisconnect(connection)
  read <- n7_open_store(path)
  on.exit(DBI::dbDisconnect(read), add = TRUE)
  expect_error(n7_read_settlements(read, "26052"), "unknown result_code")
  # A recorded zero or negative SP is a parse failure, never a payout.
  path2 <- n7_test_store()
  write <- DBI::dbConnect(RSQLite::SQLite(), path2)
  DBI::dbExecute(write, "INSERT INTO settlements VALUES ('m3','26052',0,1,'0',0,'x')")
  DBI::dbDisconnect(write)
  read2 <- n7_open_store(path2)
  on.exit(DBI::dbDisconnect(read2), add = TRUE)
  expect_error(n7_read_settlements(read2, "26052"), "must be positive")
})

testthat::test_that("n7_read_fixtures and n7_read_snapshots fail closed on broken identity", {
  path <- n7_test_store()
  write <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(write, "INSERT INTO matches VALUES ('m4','26053',1,'EPL',NULL,'G','H',0)")
  DBI::dbExecute(write, "INSERT INTO snapshots VALUES ('m1','2026-05-02T10:00:00Z',1.6,3.9,5.5,2.1,3.4,4.5,'merged')")
  DBI::dbDisconnect(write)
  read <- n7_open_store(path)
  on.exit(DBI::dbDisconnect(read), add = TRUE)
  expect_error(n7_read_fixtures(read, "26053"), "missing its identity or kickoff")
  # The same fixture/time/source twice would double-count a poll.
  expect_error(n7_read_snapshots(read, "26051"), "duplicated match_id/snapshot_ts/source")
})

testthat::test_that("n7_check_issues treats issue codes as identifiers", {
  expect_equal(n7_check_issues(c("26051", "26052")), c("26051", "26052"))
  # A leading zero survives; a numeric vector is refused rather than coerced.
  expect_equal(n7_check_issues("09999"), "09999")
  expect_error(n7_check_issues(26051), "non-empty, unique, non-missing character")
  expect_error(n7_check_issues(character(0)), "non-empty, unique, non-missing character")
  expect_error(n7_check_issues(c("26051", "26051")), "non-empty, unique, non-missing character")
  expect_error(n7_check_issues(NA_character_), "non-empty, unique, non-missing character")
})

testthat::test_that("n7_file_hashes binds exact bytes and refuses a missing input", {
  path <- tempfile(fileext = ".txt")
  writeLines("n7", path)
  first <- n7_file_hashes(basename(path), project_root = dirname(path))
  expect_named(first, basename(path))
  expect_equal(nchar(first[[1L]]), 64L)
  expect_equal(n7_file_hashes(basename(path), project_root = dirname(path)), first)
  writeLines("n7!", path)
  expect_false(identical(n7_file_hashes(basename(path), project_root = dirname(path)), first))
  expect_error(n7_file_hashes("does_not_exist.txt"), "missing file")
  expect_error(n7_file_hashes(character(0)), "non-empty character vector")
})

testthat::test_that("the reader's output feeds the selector without reshaping", {
  source(testthat::test_path("..", "..", "r", "dixon_coles_grid.R"))
  source(testthat::test_path("..", "..", "r", "joint_basket_dc_fit.R"))
  source(testthat::test_path("..", "..", "r", "n7_fixture_portfolio.R"))
  source(testthat::test_path("..", "..", "r", "n7_experiment_replay.R"))
  connection <- n7_open_store(n7_test_store_path())
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  snapshots <- n7_read_snapshots(connection, "26051")
  fixtures <- n7_read_fixtures(connection, "26051", kickoff_tz = "Asia/Shanghai")
  # The 2026-05-02 decision epoch is 12:00Z and its window is the next Beijing
  # calendar day, [2026-05-02T16:00:00Z, 2026-05-03T16:00:00Z). m1 kicks off at
  # 12:00Z and is therefore NOT in it; m2 kicks off at 19:00Z and is.
  epoch <- "2026-05-02T12:00:00Z"
  eligible <- n7_eligible_fixtures(fixtures, epoch)$eligible
  expect_equal(eligible$match_id, "m2")
  expect_equal(eligible$hours_to_kickoff, 7)
  excluded <- n7_eligible_fixtures(fixtures, epoch)$excluded
  expect_equal(excluded$reason, "KICKOFF_BEFORE_WINDOW")
  # m2 has a poll at 11:00Z, before the epoch, and one after it; the strictly
  # backwards-looking rule must take the earlier one.
  selected <- n7_select_snapshots(snapshots, eligible, epoch)
  expect_equal(selected$priced$match_id, "m2")
  expect_equal(selected$priced$quote_utc, "2026-05-02T11:00:00Z")
  expect_equal(selected$priced$sp_3, 1.9)
  # The decision epoch itself is the 20:00 Asia/Shanghai instant of that date.
  expect_equal(n7_decision_epoch("2026-05-01"), "2026-05-01T12:00:00Z")
})

testthat::test_that("a stored value that is not a number stops instead of becoming NA", {
  path <- n7_test_store()
  write <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(write, "INSERT INTO snapshots VALUES
    ('m3','2026-05-04T10:00:00Z',1.6,3.9,5.5,2.1,3.4,4.5,'merged')")
  DBI::dbDisconnect(write)
  read <- n7_open_store(path)
  on.exit(DBI::dbDisconnect(read), add = TRUE)
  # A genuine SQL NULL is a recorded absence and stays NA.
  expect_true(is.na(n7_read_snapshots(read, "26051")$eu_h[2L]))
  # An empty string is NOT an absence: it is a record the store cannot represent,
  # and treating it as NA would silently change which poll the selector chooses.
  path2 <- n7_test_store()
  write2 <- DBI::dbConnect(RSQLite::SQLite(), path2)
  DBI::dbExecute(write2, "INSERT INTO snapshots VALUES
    ('m3','2026-05-04T10:00:00Z',1.6,3.9,5.5,2.1,3.4,4.5,'merged')")
  DBI::dbExecute(write2, "UPDATE snapshots SET eu_h = '' WHERE match_id = 'm3'")
  DBI::dbDisconnect(write2)
  read2 <- n7_open_store(path2)
  on.exit(DBI::dbDisconnect(read2), add = TRUE)
  expect_error(n7_read_snapshots(read2, "26052"), "not numbers")
})

testthat::test_that("non-finite and out-of-range stored numbers are refused", {
  # "Inf" parses as a number but is not a usable quote, and an out-of-range integer
  # becomes NA under as.integer() with only a warning: both must stop.
  expect_error(n7_stored_numeric(c("1.5", "Inf"), "probe"), "non-finite")
  # NaN is already NA after parsing, so it is refused as "not a number" instead.
  expect_error(n7_stored_numeric(c("1.5", "NaN"), "probe"), "not numbers|non-finite")
  expect_error(n7_stored_integer(c("1", "2147483648"), "probe"), "outside the integer range")
  expect_error(n7_stored_integer(c("1", "-2147483649"), "probe"), "outside the integer range")
  # R reserves -2147483648 for NA_integer_: it is representable but not admissible.
  expect_error(n7_stored_integer("-2147483648", "probe"), "outside the integer range")
  expect_error(n7_stored_integer(-2147483648, "probe"), "outside the integer range")
  expect_error(n7_stored_integer(c(1L, -2147483648), "probe"), "outside the integer range")
  # The largest admissible negative value still round-trips.
  expect_equal(n7_stored_integer("-2147483647", "probe"), -2147483647L)
  # An already-numeric column takes the same finiteness path as a text column.
  expect_error(n7_stored_numeric(c(1.5, Inf), "probe"), "non-finite")
  expect_error(n7_stored_numeric(c(1.5, -Inf), "probe"), "non-finite")
  expect_error(n7_stored_numeric(c(1.5, NaN), "probe"), "NaN")
  expect_error(n7_stored_integer(c(1L, Inf), "probe"), "non-finite")
  # A genuine NULL is still a recorded absence, not a failure.
  expect_equal(n7_stored_numeric(c(1.5, NA), "probe"), c(1.5, NA))
  expect_equal(n7_stored_integer(c(1L, NA), "probe"), c(1L, NA))
  expect_equal(n7_stored_integer(c("1", "2147483647"), "probe"), c(1L, 2147483647L))
})

testthat::test_that("a kickoff that is not exactly the declared local form stops", {
  for (bad in c("2026-05-02T20:00:00Z", "2026-05-02 20:00:00",
                "2026-05-02T20:00:00+08:00", "2026-05-02T20:00:00 ")) {
    path <- n7_test_store()
    write <- DBI::dbConnect(RSQLite::SQLite(), path)
    DBI::dbExecute(write, "UPDATE matches SET kickoff_ts = ? WHERE match_id = 'm1'",
                   params = list(bad))
    DBI::dbDisconnect(write)
    read <- n7_open_store(path)
    # Either it cannot be parsed at all, or it parses to something that is not the
    # declared form; both must stop rather than be silently reinterpreted.
    expect_error(n7_read_fixtures(read, "26051", kickoff_tz = "Asia/Shanghai"),
                 "could not be interpreted|declared naive-local form", info = bad)
    DBI::dbDisconnect(read)
  }
  # The declared form still round-trips.
  connection <- n7_open_store(n7_test_store_path())
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  expect_equal(nrow(n7_read_fixtures(connection, "26051")), 2L)
})

testthat::test_that("a snapshot time that is not declared UTC stops at the boundary", {
  path <- n7_test_store()
  write <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(write, "INSERT INTO snapshots VALUES
    ('m3','2026-05-04 10:00:00',1.6,3.9,5.5,2.1,3.4,4.5,'merged')")
  DBI::dbDisconnect(write)
  read <- n7_open_store(path)
  on.exit(DBI::dbDisconnect(read), add = TRUE)
  # A space-separated, zone-less timestamp must not be guessed at.
  expect_error(n7_read_snapshots(read, "26052"), "ISO-8601 UTC")
})

n7_cutoff_store <- function(rows) {
  path <- tempfile(fileext = ".db")
  connection <- DBI::dbConnect(RSQLite::SQLite(), path)
  DBI::dbExecute(connection, "CREATE TABLE nowscore_bjdc_matches (
    issue TEXT, match_idx INTEGER, raw_row TEXT)")
  for (i in seq_len(nrow(rows))) {
    DBI::dbExecute(connection, "INSERT INTO nowscore_bjdc_matches VALUES (?,?,?)",
                   params = list(rows$issue[i], rows$match_idx[i], rows$raw_row[i]))
  }
  DBI::dbDisconnect(connection)
  path
}

testthat::test_that("n7_read_sale_cutoffs parses the per-match 截止时间 label", {
  marker <- "截止时间："
  store <- n7_cutoff_store(tibble::tibble(
    issue = c("26051", "26051", "26052"),
    match_idx = c(1L, 2L, 1L),
    raw_row = c(paste0("<td>", marker, "2026-05-02 19:55</td><td>x</td>"),
                paste0("<td>", marker, "2026-05-03 02:55</td>"),
                "<td>no cutoff label here</td>")))
  connection <- n7_open_store(store)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  out <- n7_read_sale_cutoffs(connection, c("26051", "26052"))
  expect_equal(nrow(out), 3L)
  # The label is declared local time and converted, not taken as UTC.
  expect_equal(out$sale_cutoff_local[1], "2026-05-02 19:55")
  expect_equal(out$sale_cutoff_utc[1], "2026-05-02T11:55:00Z")
  expect_equal(out$sale_cutoff_utc[2], "2026-05-02T18:55:00Z")
  # A row with NO marker is a genuine absence: NA, and NOT a parse failure.
  expect_true(is.na(out$sale_cutoff_local[3]))
  expect_true(is.na(out$sale_cutoff_utc[3]))
  # The retired admission column is gone, not merely unused.
  expect_false("cutoff_source" %in% names(out))
})

testthat::test_that("n7_read_sale_cutoffs fails closed on a malformed label", {
  marker <- "截止时间："
  # The marker is present but its value is not a timestamp. This must STOP, not
  # silently become a missing value.
  store <- n7_cutoff_store(tibble::tibble(
    issue = "26051", match_idx = 1L,
    raw_row = paste0("<td>", marker, "nonsense</td>")))
  connection <- n7_open_store(store)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  expect_error(n7_read_sale_cutoffs(connection, "26051"), "no parsable value")
  # A well-formed PREFIX followed by junk must also stop: taking the first 16
  # characters would silently read this as 02:55.
  suffix <- n7_cutoff_store(tibble::tibble(
    issue = "26051", match_idx = 1L,
    raw_row = paste0("<td>", marker, "2026-05-03 02:5599nonsense</td>")))
  suffix_connection <- n7_open_store(suffix)
  on.exit(DBI::dbDisconnect(suffix_connection), add = TRUE)
  expect_error(n7_read_sale_cutoffs(suffix_connection, "26051"), "no parsable value")
  # The terminator must be the real source grammar: accepting any non-digit would
  # truncate these into a valid-looking time.
  for (bad_suffix in c("nonsense", ":99", "Z", "99x")) {
    bad_store <- n7_cutoff_store(tibble::tibble(
      issue = "26051", match_idx = 1L,
      raw_row = paste0(marker, "2026-05-03 02:55", bad_suffix)))
    bad_connection <- n7_open_store(bad_store)
    expect_error(n7_read_sale_cutoffs(bad_connection, "26051"), "no parsable value")
    DBI::dbDisconnect(bad_connection)
  }
  # A legitimate terminator (a tag, a quote, whitespace, or end of string) is accepted.
  for (suffix_text in c("</td>", "\"", "", " x")) {
    ok_store <- n7_cutoff_store(tibble::tibble(
      issue = "26051", match_idx = 1L,
      raw_row = paste0(marker, "2026-05-03 02:55", suffix_text)))
    ok_connection <- n7_open_store(ok_store)
    parsed <- n7_read_sale_cutoffs(ok_connection, "26051")
    expect_equal(parsed$sale_cutoff_local, "2026-05-03 02:55")
    DBI::dbDisconnect(ok_connection)
  }
  # A duplicated (issue, match_idx) is a broken join key, not a silent pick.
  dup <- n7_cutoff_store(tibble::tibble(
    issue = c("26051", "26051"), match_idx = c(1L, 1L),
    raw_row = rep(paste0(marker, "2026-05-02 19:55"), 2L)))
  dup_connection <- n7_open_store(dup)
  on.exit(DBI::dbDisconnect(dup_connection), add = TRUE)
  expect_error(n7_read_sale_cutoffs(dup_connection, "26051"), "duplicated")
  expect_error(n7_read_sale_cutoffs(connection, "26051", cutoff_tz = "Not/AZone"), "Olson")
})

