source(testthat::test_path("..", "..", "r", "joint_basket_construction.R"))
source(testthat::test_path("..", "..", "r", "joint_basket_inputs.R"))

# --- helpers ---------------------------------------------------------------

three <- function(...) matrix(c(...), ncol = 3L, byrow = TRUE)

# Exhaustive reference allocation: minimise sum log(1 - c_i) over all splits.
brute_allocation <- function(prob_vectors, n_tickets) {
  k <- length(prob_vectors)
  best <- list(value = Inf, n = NULL)
  rec <- function(i, left, acc) {
    if (i == k) {
      n <- c(acc, left)
      c_i <- vapply(seq_len(k), function(j) if (n[j] == 0) 0 else sum(prob_vectors[[j]][seq_len(n[j])]), numeric(1))
      value <- sum(log1p(-c_i))
      if (value < best$value) best <<- list(value = value, n = n)
      return(invisible(NULL))
    }
    for (x in 0:left) rec(i + 1L, left - x, c(acc, x))
  }
  rec(1L, n_tickets, numeric(0))
  best$n
}

write_test_source <- function(dir, issues) {
  dir.create(file.path(dir, "b"), showWarnings = FALSE)
  fx <- data.frame(
    slot = 1:8,
    provider_id = as.character(1000 + 1:8),
    handicap = c(0, 1, -1, 0, 1, 0, -1, 0),
    p_W = c(0.5, 0.6, 0.4, 0.55, 0.45, 0.5, 0.35, 0.6),
    p_D = c(0.3, 0.25, 0.3, 0.25, 0.3, 0.3, 0.3, 0.25),
    p_L = c(0.2, 0.15, 0.3, 0.20, 0.25, 0.2, 0.35, 0.15),
    stringsAsFactors = FALSE)
  labels <- list()
  rows <- list()
  for (iss in issues) {
    f <- fx
    f$issue <- iss
    f <- f[, c("handicap", "issue", "p_D", "p_L", "p_W", "provider_id", "slot")]
    bundle <- list(issue = iss, historical_admission = FALSE, seal = "seal",
                   cutoffs = as.list(stats::setNames(rep("2010-01-01T00:00:00+00:00", nrow(f)), f$slot)),
                   expanded_pool = list(mode = "EXPOSED_FIXTURE_RELATIVE_REVIEW_NOT_SIMULTANEOUS_TICKET",
                                        fixtures = f))
    con <- gzfile(file.path(dir, "b", paste0(iss, ".json.gz")), "w")
    writeLines(jsonlite::toJSON(bundle, auto_unbox = TRUE, digits = NA), con)
    close(con)
    labels[[length(labels) + 1L]] <- data.frame(
      issue = iss, slot = f$slot, provider_id = f$provider_id, handicap = f$handicap,
      actual_home = c(2, 1, 0, 1, 3, 2, 0, 1), actual_away = c(0, 1, 2, 0, 1, 1, 1, 2),
      result_state = "完场", cohort = "ORIGINAL", stringsAsFactors = FALSE)
    rows[[length(rows) + 1L]] <- data.frame(
      issue = iss, cohort = "ORIGINAL",
      path = file.path(dir, "b", paste0(iss, ".json.gz")), stringsAsFactors = FALSE)
  }
  cat_row <- do.call(rbind, rows)
  cat_row$sha256 <- vapply(cat_row$path, jb_sha256_file, character(1))
  writeLines(jsonlite::toJSON(list(issues = cat_row, historical_admission = FALSE),
                              auto_unbox = TRUE, digits = NA),
             file.path(dir, "catalog.json"))
  writeLines(jsonlite::toJSON(do.call(rbind, labels), auto_unbox = TRUE, digits = NA),
             file.path(dir, "labels.json"))
  writeLines(jsonlite::toJSON(list(historical_admission = FALSE), auto_unbox = TRUE),
             file.path(dir, "receipt.json"))
  dir
}

# --- jb_outcome_index ------------------------------------------------------

test_that("jb_outcome_index maps the settled net to W/D/L", {
  expect_equal(jb_outcome_index(2, 0, 0), 1L)   # clear home win
  expect_equal(jb_outcome_index(1, 1, 0), 2L)   # draw
  expect_equal(jb_outcome_index(0, 1, 0), 3L)   # away win
  expect_equal(jb_outcome_index(2, 2, 1), 1L)   # draw + home handicap wins
  expect_equal(jb_outcome_index(2, 2, -1), 3L)  # draw + away handicap wins
  expect_equal(jb_outcome_index(1, 2, 1), 2L)   # handicap exactly levels it
  expect_equal(jb_outcome_index(c(2, 0), c(0, 1), c(0, 0)), c(1L, 3L))
})

test_that("jb_outcome_index fails closed on missing or ragged input", {
  expect_error(jb_outcome_index(NA_integer_, 0, 0), "missing settled score")
  expect_error(jb_outcome_index(1, 1, NA_real_), "missing settled score")
  expect_error(jb_outcome_index(c(1, 2), 1, c(0, 0)), "must have equal length")
})

# --- jb_basket_joint_probs -------------------------------------------------

test_that("jb_basket_joint_probs returns the full 3^n mass, sorted", {
  pv <- three(0.5, 0.3, 0.2, 0.6, 0.25, 0.15)
  v <- jb_basket_joint_probs(pv)
  expect_length(v, 9L)
  expect_equal(sum(v), 1)
  expect_true(all(diff(v) <= 1e-15))
  expect_equal(v[1], 0.5 * 0.6)
})

test_that("jb_basket_joint_probs rejects invalid distributions", {
  expect_error(jb_basket_joint_probs(three(0.5, 0.3, 0.1)), "rows must sum to 1")
  expect_error(jb_basket_joint_probs(matrix(c(0.5, 0.5), ncol = 2)), "expected n x 3 matrix")
  expect_error(jb_basket_joint_probs(three(-0.1, 0.6, 0.5)), "non-negative")
})

# --- jb_tuple_index --------------------------------------------------------

test_that("jb_tuple_index is the mixed-radix position used by the enumeration", {
  expect_equal(jb_tuple_index(c(1, 1)), 1L)
  expect_equal(jb_tuple_index(c(2, 1)), 2L)
  expect_equal(jb_tuple_index(c(1, 2)), 4L)
  expect_equal(jb_tuple_index(rep(3L, 7)), 3L^7)
})

test_that("jb_tuple_index agrees with the unnamed enumeration", {
  pv <- three(0.5, 0.3, 0.2, 0.6, 0.25, 0.15)
  grid <- jb_basket_joint_grid(pv)
  expect_length(grid, 9L)
  for (a in 1:3) for (b in 1:3) {
    expect_equal(grid[jb_tuple_index(c(a, b))], pv[1, a] * pv[2, b])
  }
  expect_equal(sort(grid, decreasing = TRUE), jb_basket_joint_probs(pv))
})

test_that("jb_basket_hit tests membership by rank, not by tuple index", {
  # A leg whose third outcome outranks the other leg's second outcome: the
  # ranks and the mixed-radix indices disagree, so an identity permutation
  # would silently pass the wrong tuples.
  pv <- three(0.80, 0.10, 0.10, 0.35, 0.35, 0.30)
  grid <- jb_basket_joint_grid(pv)
  ord <- order(grid, decreasing = TRUE)
  expect_true(jb_basket_hit(pv, c(1L, 1L), 1L))
  expect_identical(jb_basket_hit(pv, c(3L, 1L), 1L), jb_tuple_index(c(3L, 1L)) == ord[1])
  expect_true(jb_basket_hit(pv, c(1L, 1L), 9L))
  expect_false(jb_basket_hit(pv, c(3L, 3L), 1L))
  # every tuple that is bought is reported as a hit, and only those
  for (n in 1:9) {
    kept <- ord[seq_len(n)]
    for (a in 1:3) for (b in 1:3) {
      expect_identical(jb_basket_hit(pv, c(a, b), n), jb_tuple_index(c(a, b)) %in% kept)
    }
  }
})

test_that("jb_tuple_index fails closed on out-of-range outcomes", {
  expect_error(jb_tuple_index(c(1, 4)), "outcomes must be 1..3")
  expect_error(jb_tuple_index(c(0, 1)), "outcomes must be 1..3")
  expect_error(jb_tuple_index(c(1, NA)), "outcomes must not be missing")
  expect_error(jb_tuple_index(integer(0)), "must not be empty")
})

# Truncation regression: as.integer() would turn 1.9 into outcome 1 and silently
# index a tuple that the enumeration never produced.
test_that("jb_tuple_index rejects non-integer outcomes instead of truncating", {
  expect_error(jb_tuple_index(c(1.9, 1)), "whole numbers")
  expect_error(jb_tuple_index(c(1, 2.5, 3)), "whole numbers")
  expect_error(jb_tuple_index(c(1, -0.5)), "whole numbers")
  # Integer-valued doubles are still a legitimate input.
  expect_identical(jb_tuple_index(c(1, 2)), jb_tuple_index(c(1L, 2L)))
  expect_equal(jb_tuple_index(c(3, 3)), 9)   # 1 + 2*3^0 + 2*3^1
})

# A shorter outcomes vector used to index a longer grid without complaint, so a
# 1-leg tuple could be reported as a hit inside a 7-leg basket.
test_that("jb_basket_hit requires one outcome per leg", {
  pv <- matrix(rep(c(.5, .3, .2), 7), nrow = 7, byrow = TRUE)
  expect_error(jb_basket_hit(pv, 1L, 1L), "must equal basket legs")
  expect_error(jb_basket_hit(pv, rep(1L, 6), 1L), "must equal basket legs")
  expect_error(jb_basket_hit(pv, rep(1L, 8), 1L), "must equal basket legs")
  expect_silent(jb_basket_hit(pv, rep(1L, 7), 1L))
})

# --- jb_top_mass -----------------------------------------------------------

test_that("jb_top_mass equals the sum of the n largest elements", {
  v <- c(0.05, 0.4, 0.2, 0.3, 0.05)
  for (n in 1:5) expect_equal(jb_top_mass(v, n), sum(sort(v, decreasing = TRUE)[seq_len(n)]))
  expect_equal(jb_top_mass(v, 0), 0)
  expect_equal(jb_top_mass(v, 99), sum(v))
})

# --- jb_greedy_select_group ------------------------------------------------

test_that("jb_greedy_select_group returns 7 distinct available fixtures", {
  pv <- three(0.6, 0.25, 0.15, 0.5, 0.3, 0.2, 0.4, 0.35, 0.25, 0.7, 0.2, 0.1,
              0.45, 0.3, 0.25, 0.55, 0.25, 0.2, 0.35, 0.4, 0.25, 0.5, 0.3, 0.2)
  sel <- jb_greedy_select_group(pv, seq_len(8), 4)
  expect_length(sel, 7L)
  expect_equal(length(unique(sel)), 7L)
  expect_true(all(sel %in% seq_len(8)))
  expect_identical(sel, jb_greedy_select_group(pv, seq_len(8), 4))  # deterministic
})

test_that("jb_greedy_select_group fails closed on a short or duplicated pool", {
  pv <- three(0.6, 0.25, 0.15, 0.5, 0.3, 0.2, 0.4, 0.35, 0.25)
  expect_error(jb_greedy_select_group(pv, 1:3, 4), "fewer than 7 available")
  expect_error(jb_greedy_select_group(pv, c(1, 1, 2, 3, 1, 2, 3), 4), "must be unique")
})

# --- jb_allocate_tickets ---------------------------------------------------

test_that("jb_allocate_tickets matches exhaustive search", {
  set.seed(3)
  for (trial in 1:15) {
    k <- sample(2:3, 1)
    vs <- lapply(seq_len(k), function(i) sort(runif(40, 0, 0.05), decreasing = TRUE))
    n <- jb_allocate_tickets(vs, 8)
    expect_equal(sum(n), 8L)
    expect_true(all(n >= 0))
    expect_equal(n, brute_allocation(vs, 8))
  }
})

test_that("jb_allocate_tickets handles a single basket and a zero ticket count", {
  v <- list(sort(runif(20, 0, 0.1), decreasing = TRUE))
  expect_equal(jb_allocate_tickets(v, 5), 5L)
  expect_equal(jb_allocate_tickets(list(c(0.5, 0.3), c(0.4, 0.2)), 0), c(0L, 0L))
})

test_that("jb_allocate_tickets fails closed on bad input", {
  expect_error(jb_allocate_tickets(list(), 3), "no baskets")
  expect_error(jb_allocate_tickets(list(c(0.5)), -1), "non-negative")
})

# --- masses, coverage, hits ------------------------------------------------

test_that("jb_expected_coverage equals the basket mass for one basket", {
  v <- list(sort(runif(50, 0, 0.1), decreasing = TRUE))
  expect_equal(jb_expected_coverage(v, 7L), sum(v[[1]][1:7]))
})

test_that("jb_expected_coverage reduces to the independence identity", {
  a <- 0.17; b <- 0.23
  v <- list(c(a, rep(0, 10)), c(b, rep(0, 10)))
  expect_equal(jb_expected_coverage(v, c(1L, 1L)), 1 - (1 - a) * (1 - b))
})

test_that("jb_basket_masses zeroes baskets that buy nothing", {
  v <- list(c(0.5, 0.25), c(0.3, 0.2))
  expect_equal(jb_basket_masses(v, c(2L, 0L)), c(0.75, 0))
  expect_error(jb_basket_masses(v, 2L), "length mismatch")
})

test_that("jb_basket_hit detects membership of the settled tuple", {
  # leg 1 favours W, leg 2 favours D, so the most likely tuple is (W, D).
  pv <- three(0.9, 0.06, 0.04, 0.06, 0.9, 0.04)
  expect_true(jb_basket_hit(pv, c(1L, 2L), 1L))     # the single most likely tuple
  expect_false(jb_basket_hit(pv, c(1L, 1L), 1L))    # not the most likely tuple
  expect_false(jb_basket_hit(pv, c(3L, 3L), 1L))    # least likely tuple not bought
  expect_true(jb_basket_hit(pv, c(3L, 3L), 9L))     # buying all 9 always hits
  expect_false(jb_basket_hit(pv, c(1L, 2L), 0L))    # buying nothing never hits
})

# --- jb_construct_portfolio ------------------------------------------------

test_that("jb_construct_portfolio builds disjoint groups and buys the budget", {
  set.seed(5)
  pv <- matrix(runif(21 * 3), ncol = 3)
  pv <- pv / rowSums(pv)
  pf <- jb_construct_portfolio(pv, 256, 2)
  expect_equal(pf$n_groups, 3L)
  all_idx <- unlist(pf$groups)
  expect_length(all_idx, 21L)
  expect_equal(length(unique(all_idx)), 21L)
  expect_equal(sum(pf$allocation), 128L)
  expect_true(pf$expected_coverage > 0 && pf$expected_coverage < 1)
  expect_identical(pf$allocation, jb_construct_portfolio(pv, 256, 2)$allocation)
})

test_that("jb_construct_portfolio fails closed on a short pool or tiny budget", {
  pv <- matrix(rep(c(0.5, 0.3, 0.2), 6), ncol = 3, byrow = TRUE)
  expect_error(jb_construct_portfolio(pv, 256, 2), "fewer than 7 fixtures")
  pv7 <- matrix(rep(c(0.5, 0.3, 0.2), 7), ncol = 3, byrow = TRUE)
  expect_error(jb_construct_portfolio(pv7, 1, 2), "budget buys no ticket")
})

test_that("jb_realised_hits marks unbought baskets as NA", {
  set.seed(9)
  pv <- matrix(runif(14 * 3), ncol = 3); pv <- pv / rowSums(pv)
  pf <- jb_construct_portfolio(pv, 20, 2)   # 10 tickets over 2 groups
  outcomes <- rep(1L, 14)
  hits <- jb_realised_hits(pf, pv, outcomes)
  expect_length(hits, pf$n_groups)
  expect_true(all(is.na(hits) == (pf$allocation == 0L)))
})

test_that("buying the whole 3^7 space covers the issue for certain", {
  pv <- matrix(rep(c(0.5, 0.3, 0.2), 7), ncol = 3, byrow = TRUE)
  pf <- jb_construct_portfolio(pv, 2 * 3^7, 2)   # 2187 tickets == the full space
  expect_equal(pf$allocation[1], 3^7)
  expect_equal(pf$masses[1], 1)
  expect_equal(pf$expected_coverage, 1)
  outcomes <- rep(2L, 7)
  expect_true(jb_basket_hit(pv[pf$groups[[1]], , drop = FALSE], outcomes, 3^7))
  expect_true(any(jb_realised_hits(pf, pv, outcomes), na.rm = TRUE))
})

# --- input readers ---------------------------------------------------------

test_that("the input readers verify hashes and join labels to fixtures", {
  dir <- withr::local_tempdir()
  src <- write_test_source(dir, c("100101", "100102"))
  cat0 <- jb_read_catalog(src)
  expect_equal(nrow(cat0), 2L)
  expect_identical(cat0$issue, c("100101", "100102"))
  expect_equal(jb_verify_bundle_hashes(cat0), 2L)
  lab <- jb_read_labels(src)
  expect_equal(nrow(lab), 16L)
  expect_true(all(lab$outcome %in% 1:3))
  b <- jb_read_bundle(cat0$path[1], cat0$sha256[1])
  expect_false(b$historical_admission)
  expect_equal(nrow(b$fixtures), 8L)
  d <- jb_issue_design(b, lab)
  expect_equal(nrow(d$pv), 8L)
  expect_length(d$outcomes, 8L)
})

test_that("jb_read_catalog fails closed on a tampered bundle", {
  dir <- withr::local_tempdir()
  src <- write_test_source(dir, c("100101"))
  cat0 <- jb_read_catalog(src)
  con <- gzfile(cat0$path[1], "w"); writeLines('{"issue":"100101"}', con); close(con)
  expect_error(jb_verify_bundle_hashes(cat0), "hash mismatch")
  expect_error(jb_read_bundle(cat0$path[1], cat0$sha256[1]), "bundle hash mismatch")
})

test_that("jb_read_labels fails closed on non-final settlement", {
  dir <- withr::local_tempdir()
  src <- write_test_source(dir, c("100101"))
  lab <- jsonlite::fromJSON(file.path(src, "labels.json"))
  lab$result_state[1] <- "未开赛"
  writeLines(jsonlite::toJSON(lab, auto_unbox = TRUE, digits = NA), file.path(src, "labels.json"))
  expect_error(jb_read_labels(src), "non-final settlement")
})

test_that("jb_issue_design fails closed on an unsettled fixture", {
  dir <- withr::local_tempdir()
  src <- write_test_source(dir, c("100101"))
  cat0 <- jb_read_catalog(src)
  b <- jb_read_bundle(cat0$path[1], cat0$sha256[1])
  lab <- jb_read_labels(src)
  expect_error(jb_issue_design(b, lab[lab$slot != 3, ]), "unsettled fixture")
  expect_error(jb_issue_design(b, lab[0, ]), "no settlement rows")
})

test_that("jb_issue_design fails closed on handicap disagreement", {
  dir <- withr::local_tempdir()
  src <- write_test_source(dir, c("100101"))
  cat0 <- jb_read_catalog(src)
  b <- jb_read_bundle(cat0$path[1], cat0$sha256[1])
  lab <- jb_read_labels(src)
  lab$handicap[1] <- lab$handicap[1] + 1
  expect_error(jb_issue_design(b, lab), "handicap disagreement")
})

test_that("jb_read_catalog fails closed on duplicate or missing identities", {
  dir <- withr::local_tempdir()
  src <- write_test_source(dir, c("100101", "100102"))
  cat0 <- jsonlite::fromJSON(file.path(src, "catalog.json"))
  dup <- rbind(cat0$issues, cat0$issues[1, ])
  writeLines(jsonlite::toJSON(list(issues = dup, historical_admission = FALSE),
                              auto_unbox = TRUE, digits = NA), file.path(src, "catalog.json"))
  expect_error(jb_read_catalog(src), "duplicate issue identity")
  expect_error(jb_read_catalog(file.path(dir, "nope")), "missing")
})

test_that("jb_restricted_rank matches brute force on every in-space tuple", {
  pvg <- matrix(c(.6, .3, .1, .5, .3, .2, .4, .35, .25, .45, .3, .25,
                  .5, .25, .25, .55, .3, .15, .6, .25, .15), 7, 3, byrow = TRUE)
  top2 <- t(vapply(seq_len(7), function(j) order(-pvg[j, ])[1:2], integer(2)))
  sub <- as.matrix(expand.grid(lapply(seq_len(7), function(j) top2[j, ])))
  pr <- apply(sub, 1L, function(o) prod(pvg[cbind(seq_len(7), o)]))
  ord <- order(pr, decreasing = TRUE)
  for (k in seq_len(nrow(sub))) {
    expect_equal(jb_restricted_rank(pvg, top2, sub[k, ]), match(k, ord))
  }
})

test_that("jb_restricted_rank returns NA only for tuples outside the space", {
  pvg <- matrix(c(.6, .3, .1, .5, .3, .2, .4, .35, .25, .45, .3, .25,
                  .5, .25, .25, .55, .3, .15, .6, .25, .15), 7, 3, byrow = TRUE)
  top2 <- t(vapply(seq_len(7), function(j) order(-pvg[j, ])[1:2], integer(2)))
  outside <- top2[, 1]; outside[1] <- which(!(1:3 %in% top2[1, ]))
  expect_true(is.na(jb_restricted_rank(pvg, top2, outside)))
  # A tuple can carry a full-space index far above 128 and still rank correctly:
  # this is the base-mismatch case that silently produced NA.
  deep <- top2[, 2]
  expect_gt(jb_tuple_index(deep), 128L)
  expect_false(is.na(jb_restricted_rank(pvg, top2, deep)))
})

test_that("jb_restricted_rank fails closed on malformed input", {
  pvg <- matrix(1 / 3, 7, 3)
  top2 <- t(vapply(seq_len(7), function(j) order(-pvg[j, ])[1:2], integer(2)))
  expect_error(jb_restricted_rank(pvg[1:6, ], top2, rep(1L, 7)), "pvg must be 7 x 3")
  expect_error(jb_restricted_rank(pvg, top2[, 1, drop = FALSE], rep(1L, 7)), "top2 must be 7 x 2")
  expect_error(jb_restricted_rank(pvg, top2, rep(1L, 6)), "outcomes must be 7 values")
  expect_error(jb_restricted_rank(pvg, top2, c(rep(1L, 6), 4L)), "outcomes must be 7 values")
  bad <- pvg; bad[1, ] <- 0
  expect_error(jb_restricted_rank(bad, top2, rep(1L, 7)), "every leg must carry probability mass")
  dup <- top2; dup[1, ] <- c(1L, 1L)
  expect_error(jb_restricted_rank(pvg, dup, rep(1L, 7)), "two distinct outcomes")
})

test_that("jb_sha256_file hashes file CONTENT, not the path string", {
  dir <- withr::local_tempdir()
  a <- file.path(dir, "a.txt"); b <- file.path(dir, "b.txt")
  writeLines("same content", a); writeLines("same content", b)
  # Same bytes under different paths must hash identically.
  expect_identical(jb_sha256_file(a), jb_sha256_file(b))
  # And it must equal the digest of the bytes, not of the path.
  expect_identical(jb_sha256_file(a),
                   digest::digest(readBin(a, "raw", file.size(a)), algo = "sha256", serialize = FALSE))
  # digest(path) is the vacuous form this guards against: prove they differ, so
  # the test fails loudly if the implementation ever regresses to it.
  expect_false(identical(jb_sha256_file(a), digest::digest(a, algo = "sha256")))
  # Changing content must change the hash.
  writeLines("other content", b)
  expect_false(identical(jb_sha256_file(a), jb_sha256_file(b)))
  expect_error(jb_sha256_file(file.path(dir, "missing.txt")), "missing file")
})
