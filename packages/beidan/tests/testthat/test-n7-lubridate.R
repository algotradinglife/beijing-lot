# Regression suite for the #510 lubridate date-management change.
#
# Scope is exactly the three touched call sites plus the public contract they must
# keep: match_parse_utc (ISO-8601 offset strings and POSIXct conversion), the fixture's
# fixed quote lead times, and the local-calendar decision window. Every assertion
# below observes behaviour through the public/package interface; none of them
# depends on lubridate's internals.

testthat::test_that("offset spellings resolve to the same instant and keep their representation", {
  z <- match_parse_utc("2026-09-23T10:00:00Z", "kickoff_at")
  colon <- match_parse_utc("2026-09-23T18:00:00+08:00", "kickoff_at")
  nocolon <- match_parse_utc("2026-09-23T18:00:00+0800", "kickoff_at")
  # The three representations of one instant are indistinguishable downstream.
  testthat::expect_identical(as.numeric(z), as.numeric(colon))
  testthat::expect_identical(as.numeric(z), as.numeric(nocolon))
  testthat::expect_identical(colon, z)
  testthat::expect_identical(nocolon, z)
  testthat::expect_identical(attr(z, "tzone"), "UTC")
  testthat::expect_identical(format(z, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "2026-09-23T10:00:00Z")

  # Negative offsets and a half-hour zone section, so the parser is not only
  # exercised on +08:00.
  west <- match_parse_utc("2026-09-23T06:00:00-04:00", "kickoff_at")
  testthat::expect_identical(as.numeric(west), as.numeric(z))
  kathmandu <- match_parse_utc("2026-09-23T15:45:00+05:45", "kickoff_at")
  testthat::expect_identical(as.numeric(kathmandu), as.numeric(z))
})

testthat::test_that("a non-UTC POSIXct keeps its exact fractional instant", {
  # A quarter second past the second is the case the old format() round-trip
  # truncated to a whole second.
  instant <- lubridate::ymd_hms("2026-09-22 20:00:00.25", tz = "Asia/Shanghai")
  parsed <- match_parse_utc(instant, "kickoff_at")
  testthat::expect_identical(attr(parsed, "tzone"), "UTC")
  testthat::expect_identical(as.numeric(parsed), as.numeric(instant))
  # The instant, not just the numeric: 0.25 s must survive the conversion.
  testthat::expect_equal(as.numeric(parsed) - floor(as.numeric(parsed)), 0.25)

  # A 123456-microsecond instant is not silently rounded to the second either.
  micro <- as.POSIXct(0.123456, origin = "1970-01-01", tz = "Asia/Shanghai")
  testthat::expect_identical(as.numeric(match_parse_utc(micro, "kickoff_at")), 0.123456)
})

testthat::test_that("a UTC POSIXct is returned unchanged, including whole vectors", {
  utc <- as.POSIXct(c("2026-09-23 10:00:00", "2026-09-23 10:00:00.5"), tz = "UTC")
  testthat::expect_identical(match_parse_utc(utc, "kickoff_at"), utc)
})

testthat::test_that("fractional-second ISO strings preserve the fraction", {
  whole <- match_parse_utc("2026-09-23T10:00:00Z", "kickoff_at")
  millis <- match_parse_utc("2026-09-23T10:00:00.250Z", "kickoff_at")
  micros <- match_parse_utc("2026-09-23T10:00:00.250000Z", "kickoff_at")
  testthat::expect_identical(as.numeric(millis), as.numeric(whole) + 0.25)
  testthat::expect_identical(as.numeric(micros), as.numeric(millis))
  # A fraction on an explicit non-UTC offset is converted, not truncated.
  offset_fraction <- match_parse_utc("2026-09-23T18:00:00.25+08:00", "kickoff_at")
  testthat::expect_identical(as.numeric(offset_fraction), as.numeric(millis))
})

testthat::test_that("a typed-empty POSIXct column stays a valid zero-length UTC vector", {
  # Regression: an empty schema column must not be routed through the string
  # parser, which would need a non-empty shape to accept it.
  parsed <- match_parse_utc(as.POSIXct(character(0), tz = "UTC"), "kickoff_at")
  testthat::expect_length(parsed, 0L)
  testthat::expect_s3_class(parsed, "POSIXct")
  testthat::expect_identical(attr(parsed, "tzone"), "UTC")
  testthat::expect_length(match_parse_utc(character(0), "kickoff_at"), 0L)

  # The typed-empty table itself keeps its POSIXct columns.
  empty <- match_typed_empty("fixtures")
  testthat::expect_identical(nrow(empty), 0L)
  testthat::expect_identical(attr(empty$kickoff_at, "tzone"), "UTC")
  testthat::expect_length(empty$kickoff_at, 0L)
})

testthat::test_that("NA, NaN and infinite instants are refused in both input forms", {
  testthat::expect_error(match_parse_utc(NA_character_, "kickoff_at"), "must not be NA")
  testthat::expect_error(match_parse_utc(c("2026-09-23T10:00:00Z", NA), "kickoff_at"),
                         "must not be NA")
  testthat::expect_error(match_parse_utc(NA_real_, "kickoff_at"), "must be character or POSIXct")

  # A POSIXct with an NA or non-finite instant must fail closed rather than be
  # stored as a silent missing timestamp.
  testthat::expect_error(
    match_parse_utc(as.POSIXct(NA_real_, origin = "1970-01-01", tz = "UTC"), "kickoff_at"),
    "must not be NA")
  testthat::expect_error(
    match_parse_utc(as.POSIXct(Inf, origin = "1970-01-01", tz = "UTC"), "kickoff_at"),
    "must not be NA")
  testthat::expect_error(
    match_parse_utc(as.POSIXct(-Inf, origin = "1970-01-01", tz = "UTC"), "kickoff_at"),
    "must not be NA")
})

testthat::test_that("invalid, naked and trailing-garbage timestamps fail instead of parsing", {
  # Naked wall-clock strings must not be assumed UTC: the offset is part of the
  # contract, and guessing it would silently shift a cutoff.
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00", "kickoff_at"),
                         "explicit UTC offset")
  testthat::expect_error(match_parse_utc("2026-09-23 10:00:00Z", "kickoff_at"),
                         "explicit UTC offset")
  testthat::expect_error(match_parse_utc("2026-09-23", "kickoff_at"),
                         "explicit UTC offset")
  testthat::expect_error(match_parse_utc("2026-09-23T10:00", "kickoff_at"),
                         "explicit UTC offset")
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00+08", "kickoff_at"),
                         "explicit UTC offset")

  # Trailing garbage: lubridate::ymd_hms() alone would silently read this as
  # 10:00:00Z. The strict shape gate must reject it.
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00Zxyz", "kickoff_at"),
                         "explicit UTC offset")
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00Z ", "kickoff_at"),
                         "explicit UTC offset")

  # Well-shaped but impossible values fail as parse errors, not silent NA.
  testthat::expect_error(match_parse_utc("2026-13-45T99:99:99Z", "kickoff_at"),
                         "not a parseable UTC instant")
  testthat::expect_error(match_parse_utc("2026-02-30T10:00:00Z", "kickoff_at"),
                         "not a parseable UTC instant")

  # Non-character, non-POSIXct input.
  testthat::expect_error(match_parse_utc(20260923, "kickoff_at"), "must be character or POSIXct")
  testthat::expect_error(match_parse_utc(list(1), "kickoff_at"), "must be character or POSIXct")
})

testthat::test_that("the what label is validated before any parsing happens", {
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00Z", NA), "single non-empty label")
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00Z", ""), "single non-empty label")
  testthat::expect_error(match_parse_utc("2026-09-23T10:00:00Z", c("a", "b")),
                         "single non-empty label")
})

testthat::test_that("fixture quotes sit exactly at the declared fixed offsets", {
  # Three companies spread the declared 0..120 s ladder; the lead is exactly 36 h.
  kickoff <- lubridate::with_tz(
    lubridate::ymd_hms(c("2026-09-23 12:00:00", "2026-09-24 12:00:00"),
                       tz = "Asia/Shanghai"), "UTC")
  fixture <- make_example_issue("00123", kickoff)
  offsets <- seq(0, 120, length.out = 3L)  # 0, 60, 120

  for (table in c("euro", "totals")) {
    quotes <- fixture[[table]]
    for (i in seq_along(kickoff)) {
      id <- fixture$fixtures$fixture_id[i]
      block <- quotes[quotes$fixture_id == id, , drop = FALSE]
      testthat::expect_equal(nrow(block), length(offsets) * if (table == "euro") 1L else 2L)
      for (company_index in seq_along(offsets)) {
        company <- sprintf("c%02d", company_index)
        rows <- block[block$company_id == company, , drop = FALSE]
        testthat::expect_true(nrow(rows) > 0L)
        testthat::expect_identical(unique(as.numeric(rows$quote_at)),
                                   as.numeric(kickoff[i]) - 36 * 3600 + offsets[company_index])
      }
    }
  }

  # Pre-match SP has no per-company offset: exactly the -36 h anchor.
  testthat::expect_identical(unique(as.numeric(fixture$prematch_sp$quote_at)),
                             as.numeric(kickoff) - 36 * 3600)
  # The synthetic status report shares the same anchor.
  testthat::expect_identical(as.numeric(fixture$match_status$status_at),
                             as.numeric(kickoff) - 36 * 3600)
  testthat::expect_identical(as.numeric(fixture$match_status$available_at),
                             as.numeric(kickoff) - 36 * 3600)
})

testthat::test_that("the decision window is the next half-open local calendar day", {
  # 2026-09-22 20:00 Asia/Shanghai == 12:00Z; the window is 09-23 local.
  window <- match_decision_window("2026-09-22T12:00:00Z", "Asia/Shanghai")
  testthat::expect_identical(window$start_utc, "2026-09-22T16:00:00Z")
  testthat::expect_identical(window$end_utc, "2026-09-23T16:00:00Z")

  start <- lubridate::ymd_hms(window$start_utc)
  end <- lubridate::ymd_hms(window$end_utc)
  fixture <- make_example_issue("00123", c(start - lubridate::dseconds(0.25),
    start, end - lubridate::dseconds(0.25), end))
  inputs <- read_match_inputs(example_match_source(fixture), "00123")
  epoch <- prepare_engine(inputs,
    list(issue_id = "00123", cutoff_utc = lubridate::ymd_hms("2026-09-22T12:00:00Z")),
    list(members = c("c01", "c02", "c03"), missing = "error"),
    list(companies = NULL, line = "nearest_main", watermark = "decimal"))
  testthat::expect_identical(epoch$fixtures$fixture_id, fixture$fixtures$fixture_id[c(2L, 3L)])

})

testthat::test_that("DST transitions give the correct 23-hour and 25-hour local days", {
  # America/New_York springs forward on 2026-03-08 and falls back on 2026-11-01.
  # A correct local-calendar boundary yields 23 h and 25 h; adding a fixed 24 h
  # would land an hour off local midnight on both dates.
  spring <- match_decision_window("2026-03-07T17:00:00Z", "America/New_York")
  spring_hours <- as.numeric(difftime(lubridate::ymd_hms(spring$end_utc),
                                      lubridate::ymd_hms(spring$start_utc),
                                      units = "hours"))
  testthat::expect_equal(spring_hours, 23)
  testthat::expect_identical(format(lubridate::with_tz(lubridate::ymd_hms(spring$start_utc),
                                                       "America/New_York"), "%H:%M:%S"),
                             "00:00:00")

  fall <- match_decision_window("2026-10-31T16:00:00Z", "America/New_York")
  fall_hours <- as.numeric(difftime(lubridate::ymd_hms(fall$end_utc),
                                    lubridate::ymd_hms(fall$start_utc),
                                    units = "hours"))
  testthat::expect_equal(fall_hours, 25)
  testthat::expect_identical(format(lubridate::with_tz(lubridate::ymd_hms(fall$end_utc),
                                                       "America/New_York"), "%H:%M:%S"),
                             "00:00:00")

  # An ordinary day is still exactly 24 h.
  plain <- match_decision_window("2026-09-22T12:00:00Z", "America/New_York")
  testthat::expect_equal(as.numeric(difftime(lubridate::ymd_hms(plain$end_utc),
                                             lubridate::ymd_hms(plain$start_utc),
                                             units = "hours")), 24)
})

testthat::test_that("report visibility at the cutoff keeps subsecond exclusion exact", {
  # The selector requires BOTH instants STRICTLY before the cutoff. A report at
  # exactly cutoff - 0.25 s is visible; one at the cutoff is not; one 0.25 s later
  # certainly is not. All three must be distinguished, which needs fractions.
  cutoff_seconds <- as.numeric(lubridate::ymd_hms("2026-09-22 12:00:00", tz = "UTC"))
  cutoff <- list(issue_id = "00123",
                 cutoff_utc = as.POSIXct(cutoff_seconds, origin = "1970-01-01", tz = "UTC"))
  kickoff <- as.POSIXct(cutoff_seconds + 16 * 3600, origin = "1970-01-01", tz = "UTC")
  fixture <- make_example_issue("00123", kickoff)

  visible_status <- fixture$match_status
  visible_status$status_at <- cutoff$cutoff_utc - 0.25
  visible_status$available_at <- cutoff$cutoff_utc - 0.25
  visible <- match_select_status(fixture$fixtures, visible_status, cutoff)
  testthat::expect_identical(nrow(visible$fixtures), 1L)

  at_cutoff <- visible_status
  at_cutoff$status_at <- cutoff$cutoff_utc
  at_cutoff$available_at <- cutoff$cutoff_utc
  testthat::expect_identical(nrow(match_select_status(fixture$fixtures, at_cutoff, cutoff)$fixtures), 0L)

  after_cutoff <- visible_status
  after_cutoff$status_at <- cutoff$cutoff_utc + 0.25
  after_cutoff$available_at <- cutoff$cutoff_utc + 0.25
  testthat::expect_identical(nrow(match_select_status(fixture$fixtures, after_cutoff, cutoff)$fixtures), 0L)
})

testthat::test_that("the public UTC POSIXct contract is unchanged for callers", {
  # Regression guard for the call sites that consume match_parse_utc: parsing must
  # still yield UTC POSIXct, whole-second offsets must be unchanged, and the
  # source-table coercion must still produce the declared schema.
  frame <- data.frame(
    issue_id = "26097", fixture_id = "f1", slot = "5", provider_id = "p",
    kickoff_at = "2026-09-23T18:00:00+08:00", handicap = "0",
    sale_state = "open", source_url = "u", stringsAsFactors = FALSE)
  coerced <- match_coerce_source_table(frame, "fixtures")
  testthat::expect_s3_class(coerced$kickoff_at, "POSIXct")
  testthat::expect_identical(attr(coerced$kickoff_at, "tzone"), "UTC")
  testthat::expect_identical(format(coerced$kickoff_at, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
                             "2026-09-23T10:00:00Z")

  # A fractional quote survives a full round trip through the boundary coercion.
  fractional <- frame
  fractional$kickoff_at <- "2026-09-23T18:00:00.25+08:00"
  fractional_coerced <- match_coerce_source_table(fractional, "fixtures")
  testthat::expect_equal(as.numeric(fractional_coerced$kickoff_at) -
                           floor(as.numeric(fractional_coerced$kickoff_at)), 0.25)
})


testthat::test_that("invalid numeric UTC offsets are rejected before permissive parsing", {
  for (offset in c("+9960", "+24:00", "-08:60", "+1299")) {
    testthat::expect_error(match_parse_utc(paste0("2026-09-23T10:00:00", offset), "quote"),
                           "explicit UTC offset")
  }
})


testthat::test_that("clock overflow and terminal newlines cannot normalize to valid instants", {
  for (clock in c("24:01:00", "23:59:61", "12:60:00", "25:00:00")) {
    testthat::expect_error(match_parse_utc(paste0("2026-01-01T", clock, "Z"), "clock"),
                           "not a parseable UTC instant")
  }
  testthat::expect_error(match_parse_utc("2026-01-01T12:00:00Z\n", "clock"),
                         "explicit UTC offset")
})
