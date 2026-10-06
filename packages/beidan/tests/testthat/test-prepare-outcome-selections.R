# Tests for prepare_outcome_selections(): the second pipeline stage. It expands
# one admitted fixture into one row per classifier choice and carries the
# classifier's own base category. The thresholds are the classifier's business
# and are never restated here.

test_that("signature exposes matches and fixed threshold", {
  expect_identical(names(formals(prepare_outcome_selections)), c("matches", "single_threshold", "dc_protection", "role_allocation"))
})

test_that("fixture A expands to win/lose then win/draw with reference entropy", {
  matches <- tibble::tibble(
    fixture_id = "A",
    win = 0.45, draw = 0.22, lose = 0.33
  )
  res <- prepare_outcome_selections(matches)

  expect_s3_class(res, "tbl_df")
  expect_identical(nrow(res), 2L)
  expect_identical(res$fixture_id, c("A", "A"))
  expect_identical(res$selection_id, c(1L, 2L))
  expect_identical(res$outcomes, list(c("win", "lose"), c("win", "draw")))
  expect_identical(res$base_role, c(2L, 2L))
  expect_identical(res$n_outcomes, c(2L, 2L))
  expect_equal(res$coverage_probability, c(0.78, 0.67))
  expect_identical(res$p3, c(0.22, 0.22))

  reference_entropy <- c(
    -(45 / 78 * log(45 / 78) + 33 / 78 * log(33 / 78)) / log(2),
    -(45 / 67 * log(45 / 67) + 22 / 67 * log(22 / 67)) / log(2)
  )
  expect_equal(res$entropy, reference_entropy)
})

test_that("fixture B yields one triple with reference entropy", {
  matches <- tibble::tibble(
    fixture_id = "B",
    win = 0.4, draw = 0.3, lose = 0.3
  )
  res <- prepare_outcome_selections(matches)

  expect_identical(nrow(res), 1L)
  expect_identical(res$selection_id, 1L)
  expect_identical(res$outcomes, list(c("win", "draw", "lose")))
  expect_identical(res$base_role, 3L)
  expect_identical(res$n_outcomes, 3L)
  expect_equal(res$coverage_probability, 1)
  expect_equal(res$p3, 0.3)
  expect_equal(
    res$entropy,
    -(0.4 * log(0.4) + 2 * 0.3 * log(0.3)) / log(3)
  )
})

test_that("a single outcome choice carries base_role 1 and zero entropy", {
  matches <- tibble::tibble(fixture_id = "C", win = 1, draw = 0, lose = 0)
  res <- prepare_outcome_selections(matches)

  expect_identical(res$outcomes, list("win"))
  expect_identical(res$base_role, 1L)
  expect_identical(res$n_outcomes, 1L)
  expect_equal(res$coverage_probability, 1)
  expect_identical(res$p3, 0)
  expect_identical(res$entropy, 0)
})

test_that("base_role is the classifier attribute, not the row count", {
  # (0.55, 0.23, 0.22) is a base-role-1 fixture that emits THREE rows: the base
  # single plus both protected pairs. base_role must stay 1 while n_outcomes
  # tracks the row's own outcome count.
  matches <- tibble::tibble(
    fixture_id = "T1", win = 0.55, draw = 0.23, lose = 0.22
  )
  res <- prepare_outcome_selections(matches)

  expect_identical(res$base_role, c(1L, 1L, 1L))
  expect_identical(res$n_outcomes, c(1L, 2L, 2L))
  expect_identical(
    res$outcomes,
    list("win", c("win", "draw"), c("win", "lose"))
  )
  expect_equal(res$coverage_probability, c(0.55, 0.78, 0.77))
  expect_identical(res$entropy[1L], 0)
  expect_identical(attr(classify_outcomes(0.55, 0.23, 0.22), "base_role"), 1L)
})

test_that("base_role is read from the classifier for every base category", {
  cases <- list(
    c(0.60, 0.25, 0.15),
    c(0.45, 0.33, 0.22),
    c(0.40, 0.30, 0.30),
    c(0.55, 0.23, 0.22)
  )
  for (p in cases) {
    matches <- tibble::tibble(
      fixture_id = "z", win = p[1L], draw = p[2L], lose = p[3L]
    )
    res <- prepare_outcome_selections(matches)
    expected_role <- attr(classify_outcomes(p[1L], p[2L], p[3L]), "base_role")
    expect_identical(unique(res$base_role), as.integer(expected_role))
  }
})

test_that("input row order and classifier direction order are preserved", {
  matches <- tibble::tibble(
    fixture_id = c("f2", "f1"),
    win = c(0.45, 0.40),
    draw = c(0.22, 0.30),
    lose = c(0.33, 0.30)
  )
  res <- prepare_outcome_selections(matches)

  expect_identical(res$fixture_id, c("f2", "f2", "f1"))
  expect_identical(res$selection_id, c(1L, 2L, 1L))
  expect_identical(
    res$outcomes,
    c(classify_outcomes(0.45, 0.22, 0.33), classify_outcomes(0.40, 0.30, 0.30))
  )
})

test_that("extra columns keep type, Dates and leading zeros without mutation", {
  matches <- tibble::tibble(
    fixture_id = c("007", "010"),
    win = c(0.45, 0.40),
    draw = c(0.22, 0.30),
    lose = c(0.33, 0.30),
    match_date = as.Date(c("2026-01-01", "2026-02-02")),
    source = c("s1", "s2"),
    flagged = c(TRUE, FALSE)
  )
  snapshot <- matches
  res <- prepare_outcome_selections(matches)

  expect_identical(matches, snapshot)
  expect_identical(res$fixture_id, c("007", "007", "010"))
  expect_s3_class(res$match_date, "Date")
  expect_identical(
    res$match_date,
    as.Date(c("2026-01-01", "2026-01-01", "2026-02-02"))
  )
  expect_identical(res$source, c("s1", "s1", "s2"))
  expect_identical(res$flagged, c(TRUE, TRUE, FALSE))
})

test_that("empty typed schema returns a typed empty tibble", {
  matches <- tibble::tibble(
    fixture_id = character(0),
    win = numeric(0),
    draw = numeric(0),
    lose = numeric(0),
    source = integer(0)
  )
  res <- prepare_outcome_selections(matches)

  expect_identical(nrow(res), 0L)
  expect_identical(
    names(res),
    c(
      "fixture_id", "win", "draw", "lose", "source",
      "selection_id", "outcomes", "base_role", "n_outcomes",
      "coverage_probability", "entropy", "p3"
    )
  )
  expect_type(res$selection_id, "integer")
  expect_type(res$outcomes, "list")
  expect_type(res$base_role, "integer")
  expect_type(res$n_outcomes, "integer")
  expect_type(res$coverage_probability, "double")
  expect_type(res$entropy, "double")
  expect_type(res$p3, "double")
})

test_that("single fixture keeps named source columns in any order", {
  m1 <- tibble::tibble(
    fixture_id = "s", win = 0.45, draw = 0.22, lose = 0.33, source = "a"
  )
  m2 <- tibble::tibble(
    fixture_id = "s", source = "a", lose = 0.33, draw = 0.22, win = 0.45
  )
  r1 <- prepare_outcome_selections(m1)
  r2 <- prepare_outcome_selections(m2)

  expect_identical(r1$outcomes, r2$outcomes)
  expect_identical(r1$coverage_probability, r2$coverage_probability)
  expect_identical(r1$entropy, r2$entropy)
  expect_identical(r1$p3, r2$p3)
  expect_identical(r1$source, c("a", "a"))
})

test_that("schema, identity and probability failures raise errors", {
  valid <- tibble::tibble(fixture_id = "x", win = 0.4, draw = 0.3, lose = 0.3)

  expect_error(prepare_outcome_selections(as.data.frame(valid)), "tibble")
  expect_error(
    prepare_outcome_selections(valid[, c("fixture_id", "win", "draw")]),
    "missing required"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = c("x", "x"),
      win = c(0.4, 0.4), draw = c(0.3, 0.3), lose = c(0.3, 0.3)
    )),
    "unique"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = c("x", NA_character_),
      win = c(0.4, 0.4), draw = c(0.3, 0.3), lose = c(0.3, 0.3)
    )),
    "non-missing"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = c("x", ""),
      win = c(0.4, 0.4), draw = c(0.3, 0.3), lose = c(0.3, 0.3)
    )),
    "non-empty"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = 1, win = 0.4, draw = 0.3, lose = 0.3
    )),
    "character"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = "x", win = "0.4", draw = 0.3, lose = 0.3
    )),
    "numeric"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = "x", win = NA_real_, draw = 0.3, lose = 0.3
    )),
    "win"
  )
  expect_error(
    prepare_outcome_selections(tibble::tibble(
      fixture_id = "x", win = 0.4, draw = 0.3, lose = 0.2
    )),
    "sum to one"
  )
})

test_that("derived column collisions fail instead of overwriting", {
  for (column in c(
    "selection_id", "outcomes", "base_role", "n_outcomes",
    "coverage_probability", "entropy", "p3"
  )) {
    matches <- tibble::tibble(
      fixture_id = "x", win = 0.4, draw = 0.3, lose = 0.3
    )
    matches[[column]] <- 1
    expect_error(prepare_outcome_selections(matches), "derived")
  }
})

test_that("the retired role column is no longer derived or reserved", {
  res <- prepare_outcome_selections(tibble::tibble(
    fixture_id = "x", win = 0.55, draw = 0.23, lose = 0.22
  ))
  expect_false("role" %in% names(res))
  expect_identical(
    names(res),
    c("fixture_id", "win", "draw", "lose", "selection_id", "outcomes",
      "base_role", "n_outcomes", "coverage_probability", "entropy", "p3")
  )

  # `n_outcomes` is the per-row outcome count, never a second copy of base_role.
  fixture <- res[res$fixture_id == "x", ]
  expect_false(identical(fixture$n_outcomes, fixture$base_role))
})

test_that("outcomes integrate the authoritative classifier", {
  cases <- list(
    c(0.45, 0.22, 0.33),
    c(0.40, 0.30, 0.30),
    c(1, 0, 0),
    c(0.10, 0.45, 0.45),
    c(0.50, 0.25, 0.25),
    c(0.55, 0.23, 0.22)
  )
  for (p in cases) {
    matches <- tibble::tibble(
      fixture_id = "z", win = p[1L], draw = p[2L], lose = p[3L]
    )
    res <- prepare_outcome_selections(matches)
    expected <- classify_outcomes(p[1L], p[2L], p[3L])
    expected_role <- as.integer(attr(expected, "base_role"))
    attr(expected, "base_role") <- NULL
    expect_identical(res$outcomes, expected)
    expect_identical(unique(res$base_role), expected_role)
  }
})

test_that("p3 is the original minimum for every selection of a fixture", {
  matches <- tibble::tibble(
    fixture_id = c("T:001", "T:003", "T:004"),
    win = c(0.55, 0.40, 0.35),
    draw = c(0.23, 0.30, 0.33),
    lose = c(0.22, 0.30, 0.32)
  )
  res <- prepare_outcome_selections(matches)

  expect_equal(res$p3[res$fixture_id == "T:001"], rep(0.22, 3))
  expect_equal(res$p3[res$fixture_id == "T:003"], 0.30)
  expect_equal(res$p3[res$fixture_id == "T:004"], 0.32)
})

test_that("coverage is the raw selected sum and is never renormalized", {
  res <- prepare_outcome_selections(tibble::tibble(
    fixture_id = "T:001", win = 0.55, draw = 0.23, lose = 0.22
  ))
  expect_equal(res$coverage_probability, c(0.55, 0.78, 0.77))
  expect_false(any(res$coverage_probability == 1))
})

test_that("a carried receipt attribute survives the expansion", {
  matches <- tibble::tibble(
    fixture_id = c("T:001", "T:002"),
    win = c(0.55, 0.85), draw = c(0.23, 0.10), lose = c(0.22, 0.05)
  )
  receipt <- list(cutoff_hash = "abc", rows = nrow(matches))
  attr(matches, "filter_receipt") <- receipt

  res <- prepare_outcome_selections(matches)
  expect_identical(attr(res, "filter_receipt"), receipt)
  expect_identical(attr(res, "filter_receipt"), attr(matches, "filter_receipt"))

  # A pool with no carried receipt stays without one.
  bare <- prepare_outcome_selections(
    tibble::tibble(fixture_id = "x", win = 0.4, draw = 0.3, lose = 0.3)
  )
  expect_null(attr(bare, "filter_receipt"))
})

test_that("outcomes are matched by original direction, not input ranking", {
  # The same three probabilities in a different column order must produce the
  # same base category and the same named outcome sets.
  a <- prepare_outcome_selections(tibble::tibble(
    fixture_id = "x", win = 0.55, draw = 0.23, lose = 0.22
  ))
  b <- prepare_outcome_selections(tibble::tibble(
    fixture_id = "x", lose = 0.22, win = 0.55, draw = 0.23
  ))
  expect_identical(a$outcomes, b$outcomes)
  expect_identical(a$base_role, b$base_role)
  expect_equal(a$coverage_probability, b$coverage_probability)
})
