# Package tests for filter_outcome_matches(): the pipeline's admission gate. A
# fixture is REMOVED when the latest quote for its model Top1 outcome strictly
# before the explicit cutoff carries a raw SP strictly below 2. A quote of 2 or
# more is retained, and a fixture with no usable Top1 quote is retained and
# flagged. Only the Top1 outcome's quote counts.

filter_test_cutoff <- function(issue_id = "26098") {
  list(issue_id = issue_id,
       cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
}

# 001 and 003 carry a Top1 SP below 2 and are removed; 002 is at 2.40 and stays.
filter_test_matches <- function() {
  tibble::tibble(
    fixture_id = c("001", "002", "003"),
    win = c(0.60, 0.40, 0.45),
    draw = c(0.25, 0.30, 0.28),
    lose = c(0.15, 0.30, 0.27),
    source = c("s1", "s2", "s3")
  )
}

filter_test_sp <- function() {
  tibble::tibble(
    fixture_id = c("001", "002", "003"),
    outcome = c("W", "W", "W"),
    quote_at = as.POSIXct(c("2026-09-26 10:00:00", "2026-09-26 10:05:00",
                            "2026-09-26 10:10:00"), tz = "Asia/Shanghai"),
    sp_raw = c(1.85, 2.40, 1.20),
    source_url = c("u1", "u2", "u3")
  )
}

test_that("signature exposes explicit minimum SP policy", {
  expect_identical(names(formals(filter_outcome_matches)),
                   c("matches", "prematch_sp", "cutoff", "sp_threshold"))
})

test_that("Top1 below 2 is excluded, Top1 at or above 2 is retained with audit", {
  result <- filter_outcome_matches(filter_test_matches(), filter_test_sp(),
                                   filter_test_cutoff())

  expect_identical(names(result),
                   c("matches", "excluded", "audit", "cutoff", "receipt"))
  expect_identical(result$matches$fixture_id, "002")
  expect_identical(names(result$matches),
                   c("fixture_id", "win", "draw", "lose", "source"))

  expect_identical(names(result$excluded),
                   c("fixture_id", "top1_outcome", "top1_probability", "top1_sp",
                     "quote_at", "retained", "reason"))
  expect_identical(result$excluded$fixture_id, c("001", "003"))
  expect_identical(result$excluded$top1_outcome, c("W", "W"))
  expect_equal(result$excluded$top1_probability, c(0.60, 0.45))
  expect_equal(result$excluded$top1_sp, c(1.85, 1.20))
  expect_identical(result$excluded$retained, c(FALSE, FALSE))
  expect_identical(result$excluded$reason, c("sp_below_threshold", "sp_below_threshold"))

  expect_identical(nrow(result$audit), 3L)
  expect_identical(result$audit$fixture_id, c("001", "002", "003"))
  expect_identical(result$audit$retained, c(FALSE, TRUE, FALSE))
  expect_identical(result$audit$missing_sp, c(FALSE, FALSE, FALSE))
  expect_identical(result$audit$reason,
                   c("sp_below_threshold", "retained", "sp_below_threshold"))
  expect_identical(result$audit$top1_outcome, c("W", "W", "W"))
  expect_type(result$audit$missing_sp, "logical")
})

test_that("the 2 boundary is strict: exactly 2 is kept, just below is removed", {
  matches <- tibble::tibble(
    fixture_id = c("a", "b"),
    win = c(0.60, 0.60), draw = c(0.25, 0.25), lose = c(0.15, 0.15)
  )
  # 2 and 1.99 are both below-or-equal to nothing: 2 is retained, 1.99 removed.
  sp <- tibble::tibble(
    fixture_id = c("a", "b"), outcome = c("W", "W"),
    quote_at = as.POSIXct(c("2026-09-26 10:00:00", "2026-09-26 10:00:00"),
                          tz = "Asia/Shanghai"),
    sp_raw = c(2.00, 1.99), source_url = c("u", "u")
  )
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(result$matches$fixture_id, "a")
  expect_identical(result$excluded$fixture_id, "b")
  expect_identical(result$excluded$reason, "sp_below_threshold")

  # Both are comfortably at or above 2 and are retained.
  sp$sp_raw <- c(2.5, 2.0)
  kept <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(kept$matches$fixture_id, c("a", "b"))
  expect_identical(nrow(kept$excluded), 0L)
})

test_that("only the Top1 outcome's quote can exclude a fixture", {
  # Top1 is W for every fixture; W has SP 5 while D and L are cheap.
  matches <- tibble::tibble(
    fixture_id = "only", win = 0.60, draw = 0.25, lose = 0.15
  )
  sp <- tibble::tibble(
    fixture_id = c("only", "only", "only"),
    outcome = c("W", "D", "L"),
    quote_at = as.POSIXct(rep("2026-09-26 10:00:00", 3), tz = "Asia/Shanghai"),
    sp_raw = c(5.00, 1.50, 1.50), source_url = c("u", "u", "u")
  )
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(result$matches$fixture_id, "only")
  expect_equal(result$audit$top1_sp, 5.00)

  # The same fixture with a cheap Top1 and expensive others is removed: the
  # D/L prices never rescue it.
  sp$sp_raw <- c(1.50, 5.00, 5.00)
  excluded <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(nrow(excluded$matches), 0L)
  expect_identical(excluded$excluded$reason, "sp_below_threshold")
})

test_that("the Top1 outcome follows the ranked probabilities, not the column order", {
  matches <- tibble::tibble(
    fixture_id = "d", win = 0.25, draw = 0.60, lose = 0.15
  )
  # Only W carries a quote; if the filter matched D it would be missing_sp.
  sp <- tibble::tibble(
    fixture_id = "d", outcome = "W",
    quote_at = as.POSIXct("2026-09-26 10:00:00", tz = "Asia/Shanghai"),
    sp_raw = 5.00, source_url = "u"
  )
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(result$audit$top1_outcome, "D")
  expect_equal(result$audit$top1_probability, 0.60)
  expect_identical(result$audit$missing_sp, TRUE)
  expect_identical(result$matches$fixture_id, "d")
})

test_that("only quotes strictly before the cutoff compete", {
  matches <- tibble::tibble(
    fixture_id = "t", win = 0.60, draw = 0.25, lose = 0.15
  )
  cutoff <- filter_test_cutoff()
  before <- as.POSIXct("2026-09-26 11:52:03", tz = "UTC")
  at <- cutoff$cutoff_utc
  after <- as.POSIXct("2026-09-26 11:52:05", tz = "UTC")

  # A cheap quote after the cutoff must not remove a retained pre-cutoff quote.
  sp <- tibble::tibble(
    fixture_id = "t", outcome = "W",
    quote_at = c(before, after), sp_raw = c(2.50, 1.10),
    source_url = c("u", "u")
  )
  result <- filter_outcome_matches(matches, sp, cutoff)
  expect_identical(result$matches$fixture_id, "t")
  expect_equal(result$audit$top1_sp, 2.50)
  expect_identical(result$audit$quote_at, before)
  expect_equal(as.numeric(result$audit$quote_at), as.numeric(before))

  # A retained quote after the cutoff must not rescue a pre-cutoff removal.
  sp$sp_raw <- c(1.10, 2.50)
  removed <- filter_outcome_matches(matches, sp, cutoff)
  expect_identical(nrow(removed$matches), 0L)
  expect_equal(removed$audit$top1_sp, 1.10)

  # The instant exactly AT the cutoff is not "before" it.
  sp <- tibble::tibble(
    fixture_id = "t", outcome = "W", quote_at = at, sp_raw = 2.10,
    source_url = "u"
  )
  expect_identical(filter_outcome_matches(matches, sp, cutoff)$audit$missing_sp,
                   TRUE)

  # With no pre-cutoff quote at all the fixture is kept and flagged.
  sp$quote_at <- after
  flagged <- filter_outcome_matches(matches, sp, cutoff)
  expect_identical(flagged$matches$fixture_id, "t")
  expect_identical(flagged$audit$missing_sp, TRUE)
  expect_identical(flagged$audit$reason, "missing_sp")
  expect_true(is.na(flagged$audit$top1_sp))
  expect_true(is.na(flagged$audit$quote_at))
})

test_that("post-cutoff mutation cannot change the selection or its receipt", {
  matches <- filter_test_matches()
  sp <- filter_test_sp()
  cutoff <- filter_test_cutoff()
  baseline <- filter_outcome_matches(matches, sp, cutoff)

  # Add, retime and reprice post-cutoff rows. None of them is admissible, so
  # neither the selection nor the frozen quote ledger may move.
  mutated <- rbind(
    sp,
    tibble::tibble(
      fixture_id = c("001", "002"), outcome = "W",
      quote_at = as.POSIXct(c("2026-09-26 12:30:00", "2026-09-26 12:30:00"),
                            tz = "UTC"),
      sp_raw = c(9.99, 0.10), source_url = c("x", "x")
    )
  )
  changed <- filter_outcome_matches(matches, mutated, cutoff)
  expect_identical(changed$matches, baseline$matches)
  expect_identical(changed$audit, baseline$audit)
  expect_identical(changed$excluded, baseline$excluded)
  expect_identical(changed$receipt$cutoff_hash, baseline$receipt$cutoff_hash)
  # The receipt still binds the exact ledger it was given, so the mutation is
  # visible as evidence even though it changed no decision.
  expect_false(identical(changed$receipt$prematch_sp_hash,
                         baseline$receipt$prematch_sp_hash))
  expect_identical(
    rlang::hash(changed$receipt$prematch_sp_snapshot),
    changed$receipt$prematch_sp_hash
  )
})

test_that("invalid pre-cutoff Top1 quotes fail rather than becoming missing", {
  matches <- tibble::tibble(fixture_id = "q", win = .60, draw = .25, lose = .15)
  cutoff <- filter_test_cutoff()
  base <- tibble::tibble(fixture_id = "q", outcome = "W",
    quote_at = cutoff$cutoff_utc - 60, sp_raw = 2.50, source_url = "u")
  for (value in c(NA_real_, NaN, Inf, -Inf, 0, -1.5)) {
    sp <- base
    sp$sp_raw <- value
    expect_error(filter_outcome_matches(matches, sp, cutoff), "invalid.*sp_raw")
  }
  sp <- dplyr::bind_rows(base, base)
  sp$sp_raw <- c(NA_real_, 1.50)
  sp$quote_at <- cutoff$cutoff_utc - c(60, 120)
  expect_error(filter_outcome_matches(matches, sp, cutoff), "invalid.*sp_raw")
})

test_that("conflicting quotes at the same latest instant fail closed", {
  matches <- tibble::tibble(
    fixture_id = "c", win = 0.60, draw = 0.25, lose = 0.15
  )
  when <- as.POSIXct("2026-09-26 10:00:00", tz = "Asia/Shanghai")
  sp <- tibble::tibble(
    fixture_id = "c", outcome = "W", quote_at = c(when, when),
    sp_raw = c(2.50, 2.80), source_url = c("u1", "u2")
  )
  expect_error(
    filter_outcome_matches(matches, sp, filter_test_cutoff()),
    "conflicting"
  )
  # An agreeing duplicate is not a conflict and is not multiplied.
  sp$sp_raw <- c(2.50, 2.50)
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(result$matches$fixture_id, "c")
  expect_equal(result$audit$top1_sp, 2.50)
  expect_identical(nrow(result$audit), 1L)
})

test_that("the latest pre-cutoff quote wins even when an earlier one is cheaper", {
  matches <- tibble::tibble(
    fixture_id = "l", win = 0.60, draw = 0.25, lose = 0.15
  )
  sp <- tibble::tibble(
    fixture_id = "l", outcome = "W",
    quote_at = as.POSIXct(c("2026-09-26 09:00:00", "2026-09-26 11:00:00"),
                          tz = "Asia/Shanghai"),
    sp_raw = c(2.80, 1.20), source_url = c("u1", "u2")
  )
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(nrow(result$matches), 0L)
  expect_equal(result$audit$top1_sp, 1.20)

  sp$sp_raw <- c(1.20, 2.80)
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(result$matches$fixture_id, "l")
  expect_equal(result$audit$top1_sp, 2.80)
})

test_that("an empty matches table returns typed-empty audits", {
  matches <- tibble::tibble(
    fixture_id = character(0), win = numeric(0),
    draw = numeric(0), lose = numeric(0), source = character(0)
  )
  result <- filter_outcome_matches(matches, filter_test_sp(), filter_test_cutoff())

  expect_identical(nrow(result$matches), 0L)
  expect_identical(names(result$matches),
                   c("fixture_id", "win", "draw", "lose", "source"))
  expect_identical(nrow(result$excluded), 0L)
  expect_identical(names(result$excluded),
                   c("fixture_id", "top1_outcome", "top1_probability", "top1_sp",
                     "quote_at", "retained", "reason"))
  expect_identical(nrow(result$audit), 0L)
  expect_identical(names(result$audit), c(names(result$excluded), "missing_sp"))
  expect_type(result$excluded$top1_probability, "double")
  expect_type(result$excluded$top1_sp, "double")
  expect_s3_class(result$excluded$quote_at, "POSIXct")
  expect_type(result$excluded$retained, "logical")
  expect_type(result$audit$missing_sp, "logical")
  # Typed-empty audits bind with non-empty ones.
  bound <- dplyr::bind_rows(
    result$audit,
    filter_outcome_matches(filter_test_matches(), filter_test_sp(),
                           filter_test_cutoff())$audit
  )
  expect_identical(nrow(bound), 3L)
})

test_that("an empty prematch_sp ledger keeps every fixture and flags missing", {
  matches <- filter_test_matches()
  empty_sp <- tibble::tibble(
    fixture_id = character(0), outcome = character(0),
    quote_at = as.POSIXct(character(0), tz = "UTC"),
    sp_raw = double(0), source_url = character(0)
  )
  result <- filter_outcome_matches(matches, empty_sp, filter_test_cutoff())
  expect_identical(result$matches$fixture_id, c("001", "002", "003"))
  expect_identical(result$audit$missing_sp, c(TRUE, TRUE, TRUE))
  expect_identical(result$audit$reason, rep("missing_sp", 3))
  expect_identical(nrow(result$excluded), 0L)
})

test_that("prematch_sp columns are accepted in any schema order", {
  # The authoritative schema fixes the names; a caller handing the same column
  # set in another order (as the control-side check does) is normalized rather
  # than rejected, and a genuinely different column set still fails closed.
  matches <- tibble::tibble(fixture_id = "001", win = 0.60, draw = 0.25,
                            lose = 0.15)
  reordered <- filter_test_sp()[c("fixture_id", "outcome", "sp_raw",
                                  "quote_at", "source_url")]
  result <- filter_outcome_matches(matches, reordered, filter_test_cutoff())
  expect_identical(result$excluded$fixture_id, "001")
  expect_equal(result$audit$top1_sp, 1.85)
  expect_error(
    filter_outcome_matches(matches,
                           reordered[, setdiff(names(reordered), "outcome")],
                           filter_test_cutoff()),
    "columns must be exactly"
  )
})

test_that("unknown outcomes and foreign fixtures are ignored, not matched", {
  matches <- tibble::tibble(
    fixture_id = "x", win = 0.60, draw = 0.25, lose = 0.15
  )
  sp <- tibble::tibble(
    fixture_id = c("x", "other"),
    outcome = c("W", "W"),
    quote_at = as.POSIXct(c("2026-09-26 10:00:00", "2026-09-26 10:00:00"),
                          tz = "Asia/Shanghai"),
    sp_raw = c(2.20, 1.00), source_url = c("u", "u")
  )
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())
  expect_identical(result$matches$fixture_id, "x")
  expect_equal(result$audit$top1_sp, 2.20)
  expect_equal(result$receipt$prematch_sp_hash,
               filter_outcome_matches(matches, sp, filter_test_cutoff())$receipt$prematch_sp_hash)
})

test_that("matches source columns, rows and attributes are preserved unmutated", {
  matches <- tibble::tibble(
    fixture_id = c("002", "001", "003"),
    win = c(0.40, 0.60, 0.45),
    draw = c(0.30, 0.25, 0.28),
    lose = c(0.30, 0.15, 0.27),
    match_date = as.Date(c("2026-01-01", "2026-01-02", "2026-01-03")),
    flagged = c(TRUE, FALSE, TRUE)
  )
  snapshot <- matches
  sp <- tibble::tibble(
    fixture_id = c("001", "002", "003"), outcome = c("W", "W", "W"),
    quote_at = as.POSIXct(rep("2026-09-26 10:00:00", 3), tz = "Asia/Shanghai"),
    sp_raw = c(1.85, 2.40, 1.20), source_url = c("u1", "u2", "u3")
  )
  sp_snapshot <- sp
  result <- filter_outcome_matches(matches, sp, filter_test_cutoff())

  expect_identical(matches, snapshot)
  expect_identical(sp, sp_snapshot)
  # Original row order of the input is kept: 002 came first and was retained.
  expect_identical(result$matches$fixture_id, "002")
  expect_identical(result$matches$match_date, as.Date("2026-01-01"))
  expect_identical(result$matches$flagged, TRUE)
  expect_false(any(c("top1_outcome", "missing_sp", "retained", "reason") %in%
                     names(result$matches)))
})

test_that("matches validation fails closed on identity and probabilities", {
  good <- filter_test_matches()
  cutoff <- filter_test_cutoff()
  sp <- filter_test_sp()

  expect_error(filter_outcome_matches(as.data.frame(good), sp, cutoff), "tibble")
  expect_error(
    filter_outcome_matches(good[, c("fixture_id", "win", "draw")], sp, cutoff),
    "missing required"
  )
  expect_error(
    filter_outcome_matches(
      tibble::tibble(fixture_id = c("x", "x"), win = c(0.6, 0.6),
                     draw = c(0.25, 0.25), lose = c(0.15, 0.15)), sp, cutoff),
    "unique"
  )
  expect_error(
    filter_outcome_matches(
      tibble::tibble(fixture_id = c("x", NA_character_), win = c(0.6, 0.6),
                     draw = c(0.25, 0.25), lose = c(0.15, 0.15)), sp, cutoff),
    "NA"
  )
  expect_error(
    filter_outcome_matches(
      tibble::tibble(fixture_id = c("x", ""), win = c(0.6, 0.6),
                     draw = c(0.25, 0.25), lose = c(0.15, 0.15)), sp, cutoff),
    "empty"
  )
  expect_error(
    filter_outcome_matches(tibble::tibble(fixture_id = 1, win = 0.6, draw = 0.25,
                                          lose = 0.15), sp, cutoff),
    "character"
  )
  expect_error(
    filter_outcome_matches(tibble::tibble(fixture_id = "x", win = "0.6",
                                          draw = 0.25, lose = 0.15), sp, cutoff),
    "numeric"
  )
  expect_error(
    filter_outcome_matches(tibble::tibble(fixture_id = "x", win = 0.6,
                                          draw = 0.25, lose = 0.10), sp, cutoff),
    "sum to one"
  )
  expect_error(
    filter_outcome_matches(tibble::tibble(fixture_id = "x", win = NA_real_,
                                          draw = 0.25, lose = 0.15), sp, cutoff),
    "NA|length 1|number"
  )
  expect_error(
    filter_outcome_matches(tibble::tibble(fixture_id = "x", win = 1.5,
                                          draw = -0.5, lose = 0), sp, cutoff),
    "<= 1|>= 0|number"
  )
  # Errors are not converted into excluded or missing rows.
  expect_error(
    filter_outcome_matches(tibble::tibble(fixture_id = "x", win = 0.6,
                                          draw = 0.25, lose = 0.10), sp, cutoff),
    "sum to one"
  )
})

test_that("a pre-existing reserved audit column is refused", {
  for (column in c("top1_outcome", "top1_probability", "top1_sp", "quote_at",
                   "retained", "reason", "missing_sp")) {
    matches <- filter_test_matches()
    matches[[column]] <- 1
    expect_error(
      filter_outcome_matches(matches, filter_test_sp(), filter_test_cutoff()),
      "refusing to overwrite"
    )
  }
})

test_that("prematch_sp schema violations and bad cutoffs fail closed", {
  matches <- filter_test_matches()
  cutoff <- filter_test_cutoff()
  good_sp <- filter_test_sp()

  # The shared validator accepts any data frame with the exact schema, so a
  # plain data frame carrying it is normalized like a tibble rather than
  # rejected; only a genuine schema breach stops the call.
  from_df <- filter_outcome_matches(matches, as.data.frame(good_sp), cutoff)
  expect_identical(from_df$matches$fixture_id, "002")
  expect_error(
    filter_outcome_matches(matches, good_sp[, setdiff(names(good_sp), "sp_raw")],
                           cutoff),
    "columns must be exactly"
  )
  bad_type <- good_sp
  bad_type$sp_raw <- as.character(bad_type$sp_raw)
  expect_error(filter_outcome_matches(matches, bad_type, cutoff), "double")

  expect_error(filter_outcome_matches(matches, good_sp, NULL), "cutoff")
  expect_error(filter_outcome_matches(matches, good_sp, "cutoff"), "cutoff")
  expect_error(
    filter_outcome_matches(matches, good_sp, list(issue_id = "26098")),
    "cutoff_utc"
  )
  expect_error(
    filter_outcome_matches(
      matches, good_sp,
      list(issue_id = "26098", cutoff_utc = "2026-09-26")),
    "POSIXct"
  )
  expect_error(
    filter_outcome_matches(
      matches, good_sp,
      list(issue_id = "26098",
           cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "America/New_York"))),
    "UTC"
  )
})

test_that("the receipt binds cutoff, both inputs and code without a clock", {
  matches <- filter_test_matches()
  sp <- filter_test_sp()
  cutoff <- filter_test_cutoff()
  result <- filter_outcome_matches(matches, sp, cutoff)

  expect_identical(sort(names(result$receipt)),
                   sort(c("cutoff", "cutoff_hash", "input_hash", "input_snapshot",
                          "prematch_sp_hash", "prematch_sp_snapshot",
                          "sp_threshold", "sp_strict_below",
                          "missing_sp_reason", "policy_hash", "code_hash")))
  expect_identical(result$cutoff, cutoff)
  expect_identical(result$receipt$cutoff, cutoff)
  expect_identical(result$receipt$cutoff_hash,
                   rlang::hash(list(as.character(cutoff$issue_id),
                                    as.numeric(cutoff$cutoff_utc))))
  expect_match(result$receipt$cutoff_hash, "^[0-9a-f]{32}$")
  expect_identical(result$receipt$input_snapshot, matches)
  expect_identical(rlang::hash(result$receipt$input_snapshot),
                   result$receipt$input_hash)
  expect_identical(result$receipt$prematch_sp_snapshot, sp)
  expect_identical(rlang::hash(result$receipt$prematch_sp_snapshot),
                   result$receipt$prematch_sp_hash)
  expect_identical(result$receipt$sp_threshold, 2)
  expect_identical(result$receipt$sp_strict_below, TRUE)
  expect_identical(result$receipt$missing_sp_reason, "missing_sp")
  expect_true(nzchar(result$receipt$code_hash))

  # Changing the cutoff changes the frozen cutoff receipt but not the input
  # hashes; repeated calls are byte-for-byte identical.
  retimed <- filter_outcome_matches(
    matches, sp, list(issue_id = "26098",
                      cutoff_utc = as.POSIXct("2026-09-27 11:52:04", tz = "UTC")))
  expect_false(identical(result$receipt$cutoff_hash,
                         retimed$receipt$cutoff_hash))
  expect_identical(result$receipt$input_hash, retimed$receipt$input_hash)
  expect_identical(result$receipt, filter_outcome_matches(matches, sp, cutoff)$receipt)

  # The hash follows evidence, not row order.
  reordered <- sp[c(3L, 1L, 2L), ]
  expect_identical(filter_outcome_matches(matches, reordered, cutoff)$receipt$prematch_sp_hash,
                   result$receipt$prematch_sp_hash)
  repriced <- sp
  repriced$sp_raw[1L] <- repriced$sp_raw[1L] + 0.01
  expect_false(identical(filter_outcome_matches(matches, repriced, cutoff)$receipt$prematch_sp_hash,
                         result$receipt$prematch_sp_hash))
})

test_that("classification is unaffected by quotes and cutoff", {
  # The classifier's signature and result prove it never reads SP or a cutoff:
  # the same probabilities give the same outcome regardless of any quote ledger.
  matches <- filter_test_matches()
  sp_cheap <- filter_test_sp()
  sp_expensive <- sp_cheap
  sp_expensive$sp_raw <- rep(9.99, nrow(sp_expensive))

  cheap <- filter_outcome_matches(matches, sp_cheap, filter_test_cutoff())
  expensive <- filter_outcome_matches(matches, sp_expensive, filter_test_cutoff())
  expect_identical(cheap$audit$top1_outcome, expensive$audit$top1_outcome)
  expect_identical(cheap$audit$top1_probability, expensive$audit$top1_probability)
  expect_false(identical(names(formals(classify_outcomes)),
                         c("matches", "prematch_sp", "cutoff", "sp_threshold")))
})

 test_that("filter receipt binds source identity independently of price", {
  matches <- tibble::tibble(fixture_id = "q", win = .60, draw = .25, lose = .15)
  cutoff <- filter_test_cutoff()
  sp <- tibble::tibble(fixture_id = "q", outcome = "W",
    quote_at = cutoff$cutoff_utc - 60, sp_raw = 3, source_url = "original")
  a <- filter_outcome_matches(matches, sp, cutoff)
  sp$source_url <- "changed"
  b <- filter_outcome_matches(matches, sp, cutoff)
  expect_false(identical(a$receipt$prematch_sp_hash, b$receipt$prematch_sp_hash))
  expect_identical(a$audit, b$audit)
})


test_that("quote source ties hash independently of row order and extra columns fail", {
  matches <- tibble::tibble(fixture_id = "q", win = .60, draw = .25, lose = .15)
  cutoff <- filter_test_cutoff()
  sp <- tibble::tibble(fixture_id = c("q", "q"), outcome = c("W", "W"),
    quote_at = rep(cutoff$cutoff_utc - 60, 2), sp_raw = c(3, 3),
    source_url = c("source-b", "source-a"))
  a <- filter_outcome_matches(matches, sp, cutoff)
  b <- filter_outcome_matches(matches, sp[2:1, ], cutoff)
  expect_identical(a$receipt$prematch_sp_hash, b$receipt$prematch_sp_hash)
  expect_identical(a$receipt$prematch_sp_snapshot, b$receipt$prematch_sp_snapshot)
  sp$undeclared <- "must not silently disappear"
  expect_error(filter_outcome_matches(matches, sp, cutoff), "columns must be exactly")
})

 test_that("minimum SP 1.9 admits equality and binds independently replayed policy", {
  m <- filter_test_matches(); q <- filter_test_sp(); q$sp_raw <- c(1.89,1.9,1.99)
  x <- filter_outcome_matches(m,q,filter_test_cutoff(),sp_threshold=1.9)
  expect_identical(x$matches$fixture_id,c("002","003"))
  expect_identical(x$receipt$sp_threshold,1.9)
  attr(x$matches,"filter_receipt") <- x$receipt
  ranked <- rank_outcome_selections(prepare_outcome_selections(x$matches),filter_test_cutoff())
  expect_s3_class(ranked,"tbl_df")
  for (bad in list(NA_real_,Inf,0,c(1.9,2),"1.9"))
    expect_error(filter_outcome_matches(m,q,filter_test_cutoff(),sp_threshold=bad))
  empty <- filter_outcome_matches(m[0,],q,filter_test_cutoff(),sp_threshold=1.9)
  expect_s3_class(empty$audit,"tbl_df")
  expect_equal(nrow(empty$audit),0)
  q$quote_at <- q$quote_at + 864000
  expect_true(all(filter_outcome_matches(m,q,filter_test_cutoff(),sp_threshold=1.9)$audit$missing_sp))
 })
