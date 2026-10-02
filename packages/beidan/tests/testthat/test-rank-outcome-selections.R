# Tests for rank_outcome_selections(): ranking of outcome-selection VARIANTS.
# Every row is a (fixture, selection) choice and each choice competes inside its
# own base_role board, so two directions of one fixture never share a rank.

.make_cutoff <- function(issue_id = "26098") {
  list(
    issue_id = issue_id,
    cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC")
  )
}

.selections <- function(...) {
  prepare_outcome_selections(tibble::tibble(...))
}

# The control-side acceptance pool: T:001 is a base-role-1 fixture that expands to
# three variants, T:002 is a strong base-role-1 single, T:003 and T:004 are
# base-role-3 triples with different least-likely outcomes.
.acceptance_pool <- function() {
  .selections(
    fixture_id = c("T:001", "T:002", "T:003", "T:004"),
    win = c(0.55, 0.85, 0.40, 0.35),
    draw = c(0.23, 0.10, 0.30, 0.33),
    lose = c(0.22, 0.05, 0.30, 0.32)
  )
}

# A filtered pool: the admitted matches table carrying the filter's receipt, which
# prepare_outcome_selections() must carry into the expansion.
.filtered_pool <- function(cutoff = .make_cutoff()) {
  matches <- tibble::tibble(
    fixture_id = c("001", "002", "003"),
    win = c(0.55, 0.85, 0.40),
    draw = c(0.23, 0.10, 0.30),
    lose = c(0.22, 0.05, 0.30)
  )
  prematch_sp <- tibble::tibble(
    fixture_id = c("001", "002"),
    outcome = c("W", "W"),
    quote_at = as.POSIXct(c("2026-09-26 10:00:00", "2026-09-26 10:05:00"),
                          tz = "Asia/Shanghai"),
    sp_raw = c(1.85, 2.40),
    source_url = c("https://example.test/a", "https://example.test/b")
  )
  filtered <- filter_outcome_matches(matches, prematch_sp, cutoff)
  admitted <- filtered$matches
  attr(admitted, "filter_receipt") <- filtered$receipt
  prepare_outcome_selections(admitted)
}

test_that("signature exposes selections, cutoff and a coverage-first priority", {
  expect_identical(
    names(formals(rank_outcome_selections)),
    c("selections", "cutoff", "priority")
  )
  expect_identical(
    eval(formals(rank_outcome_selections)$priority),
    c("coverage", "balance")
  )
})

test_that("coverage ranks every base-role-1 variant separately", {
  result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff())

  board <- result[result$base_role == 1L, ]
  expect_identical(board$fixture_id, c("T:002", "T:001", "T:001", "T:001"))
  expect_identical(board$selection_id, c(1L, 2L, 3L, 1L))
  expect_identical(board$rank, 1:4)
  expect_equal(board$coverage_probability, c(0.85, 0.78, 0.77, 0.55))
})

test_that("no two variants of one fixture share a rank under coverage", {
  result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff())
  t1 <- result[result$fixture_id == "T:001", ]

  expect_identical(t1$rank, c(2L, 3L, 4L))
  expect_identical(anyDuplicated(t1$rank), 0L)
  # The base single is last on coverage, not first: the protected pairs cover more.
  expect_identical(t1$selection_id[t1$rank == 4L], 1L)
})

test_that("base-role-3 coverage ranks the larger p3 first", {
  result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff())

  board <- result[result$base_role == 3L, ]
  expect_identical(board$fixture_id, c("T:004", "T:003"))
  expect_identical(board$rank, 1:2)
  expect_equal(board$coverage_probability, c(1, 1))
  expect_equal(board$p3, c(0.32, 0.30))
})

test_that("balance decides between near-equal coverage variants by entropy", {
  result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff(), "balance")

  # T:001/2 (coverage 0.78) and T:001/3 (0.77) are near-equal on coverage; the
  # more balanced pairing wins on entropy. T:002 is a single and has entropy 0.
  board1 <- result[result$base_role == 1L, ]
  expect_identical(board1$fixture_id, c("T:001", "T:001", "T:002", "T:001"))
  expect_identical(board1$selection_id, c(2L, 3L, 1L, 1L))
  expect_identical(board1$rank, 1:4)
  expect_equal(board1$entropy[1:2], c(0.8749315877, 0.8631205686), tolerance = 1e-9)
  expect_identical(board1$entropy[3:4], c(0, 0))
  expect_false(is.unsorted(rev(board1$entropy)))

  board3 <- result[result$base_role == 3L, ]
  expect_identical(board3$fixture_id, c("T:004", "T:003"))
  expect_identical(board3$rank, 1:2)
})

test_that("every board has unique consecutive integer ranks", {
  for (policy in c("coverage", "balance")) {
    result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff(), policy)
    for (role in c(1L, 2L, 3L)) {
      board <- result[result$base_role == role, ]
      if (!nrow(board)) next
      expect_type(board$rank, "integer")
      expect_identical(sort(board$rank), seq_len(nrow(board)))
    }
  }
})

test_that("the overall order is base_role 3/2/1 then rank, not role grouping", {
  result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff())

  expect_identical(result$base_role, c(3L, 3L, 1L, 1L, 1L, 1L))
  expect_identical(result$rank, c(1L, 2L, 1L, 2L, 3L, 4L))
  expect_identical(result$fixture_id,
                   c("T:004", "T:003", "T:002", "T:001", "T:001", "T:001"))
})

test_that("rank 1 of a weaker board is never forced behind another board", {
  # T:002's rank-1 variant sits between role-3 rank 2 and the remaining role-1
  # ranks; the overall order is a pure (base_role desc, rank asc) sort.
  result <- rank_outcome_selections(.acceptance_pool(), .make_cutoff())
  expect_identical(which(result$rank == 1L), c(1L, 3L))
  expect_identical(result$base_role[3L], 1L)
})

test_that("a base-role-2 pool ranks by coverage and by entropy", {
  pool <- .selections(
    fixture_id = c("A", "D"),
    win = c(0.45, 0.50),
    draw = c(0.22, 0.35),
    lose = c(0.33, 0.15)
  )
  coverage <- rank_outcome_selections(pool, .make_cutoff(), "coverage")
  expect_identical(coverage$base_role, c(2L, 2L, 2L))
  expect_identical(coverage$fixture_id, c("D", "A", "A"))
  expect_identical(coverage$rank, c(1L, 2L, 3L))

  balance <- rank_outcome_selections(pool, .make_cutoff(), "balance")
  # A/1 (coverage 0.78, entropy 0.983) beats D/1 (0.85, 0.977) on balance, and
  # A/2 (0.67, 0.913) stays last inside the same board.
  expect_identical(balance$fixture_id, c("A", "D", "A"))
  expect_identical(balance$rank, c(1L, 2L, 3L))
})

test_that("tied variants break deterministically on fixture_id then selection_id", {
  tied <- .selections(
    fixture_id = c("Z", "A"),
    win = c(0.40, 0.40),
    draw = c(0.30, 0.30),
    lose = c(0.30, 0.30)
  )
  for (policy in c("coverage", "balance")) {
    result <- rank_outcome_selections(tied, .make_cutoff(), policy)
    expect_identical(result$fixture_id, c("A", "Z"))
    expect_identical(result$rank, c(1L, 2L))
  }
})

test_that("a permuted input table yields the same canonical ranking", {
  selections <- .acceptance_pool()
  permuted <- selections[c(5L, 1L, 4L, 2L, 6L, 3L), ]
  reference <- rank_outcome_selections(selections, .make_cutoff(), "balance")
  result <- rank_outcome_selections(permuted, .make_cutoff(), "balance")

  expect_identical(names(reference), names(result))
  for (column in names(reference)) {
    expect_identical(reference[[column]], result[[column]])
  }
})

test_that("extra source columns are preserved in type and value", {
  selections <- .selections(
    fixture_id = c("A", "D"),
    win = c(0.45, 0.50),
    draw = c(0.22, 0.35),
    lose = c(0.33, 0.15),
    match_date = as.Date(c("2026-01-01", "2026-02-02")),
    source = c("s1", "s2")
  )
  result <- rank_outcome_selections(selections, .make_cutoff())

  expect_s3_class(result$match_date, "Date")
  expect_identical(result$source[result$fixture_id == "D"], "s2")
  expect_identical(result$source[result$fixture_id == "A"], c("s1", "s1"))
})

test_that("the input table is never mutated", {
  selections <- .acceptance_pool()
  snapshot <- selections
  invisible(rank_outcome_selections(selections, .make_cutoff(), "balance"))
  expect_identical(selections, snapshot)
})

test_that("an empty table returns the typed-empty shape with integer rank", {
  empty <- prepare_outcome_selections(tibble::tibble(
    fixture_id = character(0),
    win = numeric(0),
    draw = numeric(0),
    lose = numeric(0),
    source = character(0)
  ))
  result <- rank_outcome_selections(empty, .make_cutoff())

  expect_identical(nrow(result), 0L)
  expect_identical(names(result), c(
    "fixture_id", "win", "draw", "lose", "source", "selection_id", "outcomes",
    "base_role", "n_outcomes", "coverage_probability", "entropy", "p3", "rank"
  ))
  expect_type(result$rank, "integer")
  expect_identical(attr(result, "priority"), "coverage")
  expect_identical(attr(result, "cutoff"), .make_cutoff())
  expect_true(nzchar(attr(result, "input_hash")))
  expect_true(nzchar(attr(result, "code_hash")))
  expect_null(attr(result, "filter_receipt"))
})

test_that("empty strict schema still rejects a missing column", {
  empty <- prepare_outcome_selections(tibble::tibble(
    fixture_id = character(0), win = numeric(0),
    draw = numeric(0), lose = numeric(0)
  ))
  broken <- empty[, setdiff(names(empty), "p3")]
  expect_error(
    rank_outcome_selections(broken, .make_cutoff()),
    "missing required"
  )
})

test_that("wrong column types fail closed", {
  selections <- .acceptance_pool()

  bad <- selections
  bad$selection_id <- as.character(bad$selection_id)
  expect_error(rank_outcome_selections(bad, .make_cutoff()), "integer")

  bad <- selections
  bad$base_role <- as.numeric(bad$base_role)
  expect_error(rank_outcome_selections(bad, .make_cutoff()), "integer")

  bad <- selections
  bad$n_outcomes <- as.numeric(bad$n_outcomes)
  expect_error(rank_outcome_selections(bad, .make_cutoff()), "integer")

  bad <- selections
  bad$outcomes <- as.character(bad$outcomes)
  expect_error(rank_outcome_selections(bad, .make_cutoff()), "list")

  bad <- selections
  bad$coverage_probability <- as.character(bad$coverage_probability)
  expect_error(rank_outcome_selections(bad, .make_cutoff()), "double")

  bad <- selections
  bad$win <- as.character(bad$win)
  expect_error(rank_outcome_selections(bad, .make_cutoff()), "numeric")
})

test_that("missing columns, duplicates, incomplete pairs and bad roles fail", {
  selections <- .acceptance_pool()

  missing_column <- selections[, setdiff(names(selections), "entropy")]
  expect_error(
    rank_outcome_selections(missing_column, .make_cutoff()),
    "missing required"
  )

  duplicated_keys <- selections[c(1L, 1L, seq_len(nrow(selections))), ]
  expect_error(
    rank_outcome_selections(duplicated_keys, .make_cutoff()),
    "duplicate"
  )

  incomplete <- selections[
    !(selections$fixture_id == "T:001" & selections$selection_id == 2L), ]
  expect_error(
    rank_outcome_selections(incomplete, .make_cutoff()),
    "keys"
  )

  bad_role <- selections
  bad_role$base_role[1L] <- 4L
  expect_error(
    rank_outcome_selections(bad_role, .make_cutoff()),
    "base_role"
  )

  # n_outcomes is verified against the mask, never trusted as a label.
  mismatched <- selections
  mismatched$n_outcomes[1L] <- mismatched$n_outcomes[1L] + 1L
  expect_error(
    rank_outcome_selections(mismatched, .make_cutoff()),
    "n_outcomes"
  )
})

test_that("tampered metrics and outcomes fail closed", {
  selections <- .acceptance_pool()

  tampered <- selections
  tampered$coverage_probability[1L] <- tampered$coverage_probability[1L] + 1e-6
  expect_error(
    rank_outcome_selections(tampered, .make_cutoff()),
    "recomputed metric"
  )

  altered <- selections
  altered$outcomes[[1L]] <- "draw"
  expect_error(
    rank_outcome_selections(altered, .make_cutoff()),
    "outcomes"
  )

  # A perturbation inside the documented 1e-12 tolerance is accepted.
  within <- selections
  within$coverage_probability[1L] <- within$coverage_probability[1L] + 1e-13
  expect_silent(rank_outcome_selections(within, .make_cutoff()))
})

test_that("invalid probabilities and conflicting source rows fail closed", {
  single <- .selections(fixture_id = "x", win = 0.40, draw = 0.30, lose = 0.30)
  invalid <- single
  invalid$win <- 0.50
  expect_error(
    rank_outcome_selections(invalid, .make_cutoff()),
    "sum to one"
  )

  selections <- .selections(
    fixture_id = c("A", "D"),
    win = c(0.45, 0.50),
    draw = c(0.22, 0.35),
    lose = c(0.33, 0.15),
    source = c("s1", "s2")
  )
  conflicting <- selections
  conflicting$source[2L] <- "sX"
  expect_error(
    rank_outcome_selections(conflicting, .make_cutoff()),
    "inconsistent"
  )

  # A fixture-level derived column is checked too: base_role is one value per
  # fixture by contract.
  torn <- selections
  torn$base_role[2L] <- 3L
  expect_error(
    rank_outcome_selections(torn, .make_cutoff()),
    "inconsistent"
  )
})

test_that("a pre-existing rank is rejected instead of overwritten", {
  selections <- .acceptance_pool()
  selections$rank <- seq_len(nrow(selections))
  expect_error(
    rank_outcome_selections(selections, .make_cutoff()),
    "refusing to overwrite"
  )
})

test_that("bad priority and missing or malformed cutoff fail closed", {
  selections <- .acceptance_pool()

  expect_error(
    rank_outcome_selections(selections, .make_cutoff(), "Balance"),
    "priority"
  )
  expect_error(
    rank_outcome_selections(selections, .make_cutoff(), c("balance", "coverage")),
    "priority"
  )
  expect_error(
    rank_outcome_selections(selections, .make_cutoff(), "cov"),
    "priority"
  )

  expect_error(rank_outcome_selections(selections, NULL), "cutoff")
  expect_error(rank_outcome_selections(selections, "cutoff"), "cutoff")
  expect_error(
    rank_outcome_selections(selections, list(issue_id = "26098")),
    "cutoff"
  )
  expect_error(
    rank_outcome_selections(
      selections,
      list(issue_id = "26098", cutoff_utc = "2026-09-26")
    ),
    "POSIXct"
  )
  expect_error(
    rank_outcome_selections(
      selections,
      list(
        issue_id = "26098",
        cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "America/New_York")
      )
    ),
    "UTC"
  )
})

test_that("the receipt binds cutoff, input, priority and code without a clock", {
  selections <- .acceptance_pool()
  coverage <- rank_outcome_selections(selections, .make_cutoff())
  balance <- rank_outcome_selections(selections, .make_cutoff(), "balance")

  expect_true(all(c("names", "row.names", "class", "cutoff", "cutoff_hash",
                    "input_hash", "input_snapshot", "priority",
                    "code_hash") %in% names(attributes(coverage))))
  expect_identical(attr(coverage, "priority"), "coverage")
  expect_identical(attr(balance, "priority"), "balance")
  expect_identical(attr(coverage, "cutoff"), .make_cutoff())
  expect_true(nzchar(attr(coverage, "code_hash")))
  # The frozen cutoff receipt uses the pool's authoritative scheme: the exact
  # issue identity and UTC instant, nothing else.
  expect_identical(attr(coverage, "cutoff_hash"),
                   rlang::hash(list(as.character(.make_cutoff()$issue_id),
                                    as.numeric(.make_cutoff()$cutoff_utc))))
  expect_match(attr(coverage, "cutoff_hash"), "^[0-9a-f]{32}$")
  # The original pre-rank selection table is carried as explicit, verifiable
  # snapshot state: it is the exact supplied table and its hash is the receipt.
  expect_identical(attr(coverage, "input_snapshot"), selections)
  expect_identical(rlang::hash(attr(coverage, "input_snapshot")),
                   attr(coverage, "input_hash"))

  # Changing the supplied table changes the bound input hash.
  other <- .selections(
    fixture_id = "Q", win = 0.60, draw = 0.25, lose = 0.15
  )
  other_result <- rank_outcome_selections(other, .make_cutoff())
  expect_false(identical(
    attr(coverage, "input_hash"),
    attr(other_result, "input_hash")
  ))

  # Changing ONLY the cutoff instant leaves the input hash untouched but must
  # change the frozen cutoff receipt.
  later <- list(issue_id = "26098",
                cutoff_utc = as.POSIXct("2026-09-26 13:00:00", tz = "UTC"))
  retimed <- rank_outcome_selections(selections, later)
  expect_identical(attr(coverage, "input_hash"), attr(retimed, "input_hash"))
  expect_false(identical(attr(coverage, "cutoff_hash"),
                         attr(retimed, "cutoff_hash")))

  # Changing ONLY the cutoff issue changes the bound cutoff and its receipt, not
  # the input hash.
  shifted <- rank_outcome_selections(selections, .make_cutoff("26099"))
  expect_false(identical(attr(coverage, "cutoff"), attr(shifted, "cutoff")))
  expect_false(identical(attr(coverage, "cutoff_hash"),
                         attr(shifted, "cutoff_hash")))
  expect_identical(attr(coverage, "input_hash"), attr(shifted, "input_hash"))

  # Repeated calls are byte-for-byte identical: no hidden clock in the receipt.
  expect_identical(attributes(coverage),
                   attributes(rank_outcome_selections(selections,
                                                      .make_cutoff())))
})

test_that("an empty ranking still freezes a verifiable cutoff receipt", {
  empty <- prepare_outcome_selections(tibble::tibble(
    fixture_id = character(0), win = numeric(0),
    draw = numeric(0), lose = numeric(0)
  ))
  result <- rank_outcome_selections(empty, .make_cutoff())
  expect_identical(nrow(result), 0L)
  expect_identical(attr(result, "cutoff_hash"),
                   rlang::hash(list(as.character(.make_cutoff()$issue_id),
                                    as.numeric(.make_cutoff()$cutoff_utc))))
  # An empty table is not a blank cheque: a retimed cutoff is a different receipt.
  retimed <- rank_outcome_selections(empty, .make_cutoff("26099"))
  expect_false(identical(attr(result, "cutoff_hash"),
                         attr(retimed, "cutoff_hash")))
})

test_that("the input snapshot is explicit table state that verifies its hash", {
  selections <- .acceptance_pool()
  result <- rank_outcome_selections(selections, .make_cutoff())

  snapshot <- attr(result, "input_snapshot")
  # Explicit table state, not a hidden global: it IS the supplied table, in the
  # caller's original row order, and it never carries the appended rank.
  expect_s3_class(snapshot, "tbl_df")
  expect_identical(snapshot, selections)
  expect_false("rank" %in% names(snapshot))
  expect_identical(rlang::hash(snapshot), attr(result, "input_hash"))

  # Source attributes of the original table ride along in the snapshot so the bound
  # hash stays the exact hash of the original object.
  annotated <- selections
  attr(annotated, "source_receipt") <- list(issue_id = "26098",
                                            rows = nrow(selections))
  annotated_result <- rank_outcome_selections(annotated, .make_cutoff())
  expect_identical(rlang::hash(attr(annotated_result, "input_snapshot")),
                   attr(annotated_result, "input_hash"))
  expect_identical(attr(attr(annotated_result, "input_snapshot"),
                        "source_receipt"),
                   attr(annotated, "source_receipt"))

  # A permuted source order is a different input and therefore a different bound
  # hash, even though the canonical ranking columns are unchanged.
  permuted <- selections[c(5L, 1L, 4L, 2L, 6L, 3L), ]
  permuted_result <- rank_outcome_selections(permuted, .make_cutoff())
  expect_false(identical(attr(result, "input_hash"),
                         attr(permuted_result, "input_hash")))
  expect_identical(rlang::hash(attr(permuted_result, "input_snapshot")),
                   attr(permuted_result, "input_hash"))
  for (column in setdiff(names(result), "rank")) {
    expect_identical(result[[column]], permuted_result[[column]])
  }

  # The snapshot is poly by construction but never silently repaired: a snapshot
  # whose hash disagrees with the receipt cannot be produced by this function.
  expect_false(identical(rlang::hash(selections[, c(1L, 2L)]),
                         attr(result, "input_hash")))
})

# --- filter receipt integration ---------------------------------------------

test_that("a filtered pool carries its filter receipt through expansion", {
  pool <- .filtered_pool()
  receipt <- attr(pool, "filter_receipt")

  expect_true(is.list(receipt))
  expect_identical(receipt$cutoff, .make_cutoff())
  # The admitted pool is the filter's admitted rows, not the full input table.
  expect_identical(sort(unique(pool$fixture_id)), c("002", "003"))
  expect_false("001" %in% pool$fixture_id)
})

test_that("ranking a filtered pool verifies and re-exposes the receipt", {
  pool <- .filtered_pool()
  result <- rank_outcome_selections(pool, .make_cutoff())

  # The ranking carries the SAME verified receipt object, not a re-derived copy.
  expect_identical(attr(result, "filter_receipt"), attr(pool, "filter_receipt"))
  expect_identical(
    attr(result, "cutoff_hash"),
    attr(pool, "filter_receipt")[["cutoff_hash"]]
  )
  expect_identical(result$fixture_id, c("003", "002"))
  expect_identical(result$rank, c(1L, 1L))
})

test_that("a retimed ranking cutoff is refused against the filter receipt", {
  pool <- .filtered_pool()
  later <- list(issue_id = "26098",
                cutoff_utc = as.POSIXct("2026-09-26 13:00:00", tz = "UTC"))
  expect_error(
    rank_outcome_selections(pool, later),
    "retimed"
  )
  expect_error(
    rank_outcome_selections(pool, .make_cutoff("26099")),
    "retimed"
  )
})

test_that("a re-sourced or re-priced quote ledger is refused", {
  pool <- .filtered_pool()
  receipt <- attr(pool, "filter_receipt")

  # Source identity is part of the bound evidence: the same prices from another
  # source URL must not verify.
  resourced <- receipt
  resourced$prematch_sp_snapshot$source_url[1L] <- "https://example.test/other"
  tampered <- pool
  attr(tampered, "filter_receipt") <- resourced
  expect_error(rank_outcome_selections(tampered, .make_cutoff()), "source")

  repriced <- receipt
  repriced$prematch_sp_snapshot$sp_raw[2L] <- 2.55
  tampered <- pool
  attr(tampered, "filter_receipt") <- repriced
  expect_error(rank_outcome_selections(tampered, .make_cutoff()), "quote evidence")
})

test_that("a substituted filter input or admitted pool is refused", {
  pool <- .filtered_pool()
  receipt <- attr(pool, "filter_receipt")

  # A swapped filter input that is itself valid but is no longer the table the
  # receipt was taken from.
  swapped <- receipt
  swapped$input_snapshot$win[2L] <- 0.60
  swapped$input_snapshot$draw[2L] <- 0.25
  swapped$input_snapshot$lose[2L] <- 0.15
  tampered <- pool
  attr(tampered, "filter_receipt") <- swapped
  expect_error(rank_outcome_selections(tampered, .make_cutoff()), "input_hash")

  # A filter input that no longer classifies is refused by the replay itself.
  broken <- receipt
  broken$input_snapshot$win[3L] <- 0.99
  tampered <- pool
  attr(tampered, "filter_receipt") <- broken
  expect_error(rank_outcome_selections(tampered, .make_cutoff()), "replay")

  # A pool whose rows are NOT a subset of what the receipt admits must fail even
  # though every column of the pool is internally consistent: "004" was never in
  # the filter input at all.
  extra <- rbind(
    pool[, setdiff(names(pool), "rank")],
    prepare_outcome_selections(tibble::tibble(
      fixture_id = "004", win = 0.45, draw = 0.33, lose = 0.22
    ))
  )
  attr(extra, "filter_receipt") <- receipt
  expect_error(
    rank_outcome_selections(extra, .make_cutoff()),
    "admitted"
  )
})

test_that("a stale implementation binding is refused", {
  pool <- .filtered_pool()
  receipt <- attr(pool, "filter_receipt")
  stale <- receipt
  stale$code_hash <- "00000000000000000000000000000000"
  tampered <- pool
  attr(tampered, "filter_receipt") <- stale

  expect_error(rank_outcome_selections(tampered, .make_cutoff()), "stale")
})

test_that("a malformed filter receipt fails closed", {
  pool <- .filtered_pool()
  truncated <- pool
  attr(truncated, "filter_receipt") <- list(cutoff = .make_cutoff())
  expect_error(rank_outcome_selections(truncated, .make_cutoff()), "missing field")

  not_a_list <- pool
  attr(not_a_list, "filter_receipt") <- "receipt"
  expect_error(rank_outcome_selections(not_a_list, .make_cutoff()), "malformed")
})

test_that("an unfiltered pool keeps its no-SP semantics without a receipt", {
  # Pure probability classification stays valid: no filter receipt is invented and
  # a plain pool ranks without any quote or source URL.
  pool <- .acceptance_pool()
  expect_null(attr(pool, "filter_receipt"))
  result <- rank_outcome_selections(pool, .make_cutoff())
  expect_null(attr(result, "filter_receipt"))
  expect_identical(result$rank, c(1L, 2L, 1L, 2L, 3L, 4L))
})

test_that("ranking identity conservatively binds filter implementation", {
  plain <- rank_outcome_selections(.acceptance_pool(), .make_cutoff())
  filtered_input <- .filtered_pool()
  filtered <- rank_outcome_selections(filtered_input, .make_cutoff())
  # One loaded implementation has one transitive identity. Receipt and input
  # hashes distinguish the SP-filtered decision context.
  expect_identical(attr(plain, "code_hash"), attr(filtered, "code_hash"))
  expect_null(attr(plain, "filter_receipt"))
  expect_true(is.list(attr(filtered, "filter_receipt")))
  testthat::local_mocked_bindings(
    filter_outcome_matches = function(matches, prematch_sp, cutoff) {
      stop("changed filtering implementation")
    }, .package = "beidan")
  expect_false(identical(beidan:::.rank_outcome_code_hash(), attr(plain, "code_hash")))
  expect_error(rank_outcome_selections(filtered_input, .make_cutoff()),
    "independent filter replay")
})


test_that("filter replay handles admitted variants and binds full sources and policy", {
  cutoff <- .make_cutoff()
  matches <- tibble::tibble(fixture_id = "X", win = .55, draw = .23,
    lose = .22, home_team = "Original")
  sp <- tibble::tibble(fixture_id = "X", outcome = "W",
    quote_at = cutoff$cutoff_utc - 60, sp_raw = 3, source_url = "source")
  filtered <- filter_outcome_matches(matches, sp, cutoff)
  attr(filtered$matches, "filter_receipt") <- filtered$receipt
  pool <- prepare_outcome_selections(filtered$matches)
  result <- rank_outcome_selections(pool, cutoff)
  expect_identical(result$selection_id, c(2L, 3L, 1L))
  expect_identical(result$rank, 1:3)
  changed <- pool
  changed$home_team <- "Changed"
  expect_error(rank_outcome_selections(changed, cutoff), "does not match.*admitted")
  for (field in c("sp_threshold", "sp_strict_below", "missing_sp_reason")) {
    changed <- pool
    receipt <- attr(changed, "filter_receipt")
    receipt[[field]] <- switch(field, sp_threshold = 1.5,
      sp_strict_below = FALSE, missing_sp_reason = "changed")
    attr(changed, "filter_receipt") <- receipt
    expect_error(rank_outcome_selections(changed, cutoff), "policy")
  }
  expect_error(beidan:::.rank_outcome_code_hash("nonexistent_implementation_root"),
    "Missing implementation root")
})
