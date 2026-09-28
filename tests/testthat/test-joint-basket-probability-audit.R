source(testthat::test_path("..", "..", "r", "joint_basket_construction.R"))
source(testthat::test_path("..", "..", "r", "joint_basket_settlement.R"))
source(testthat::test_path("..", "..", "r", "joint_basket_probability_audit.R"))

# --- helpers ---------------------------------------------------------------

# Two fixtures, three outcomes each, in jb_official_sp shape.
make_sp <- function() {
  tibble::tibble(
    issue = rep(c("100101", "100102"), each = 3),
    slot = rep(c(1L, 2L), each = 3),
    provider_id = rep(c("p1", "p2"), each = 3),
    option = rep(c("胜", "平", "负"), 2),
    sp = c(2, 4, 4, 5, 5, 2))
}

# One fixture x three outcomes cell frame.
make_cells <- function(fixture, p, q, realized, provider_id = "p1") {
  tibble::tibble(fixture = fixture, issue = sub("-.*", "", fixture),
                 slot = as.integer(sub(".*-", "", fixture)), provider_id = provider_id,
                 outcome = 1:3, p = p, q = q, realized = as.integer(1:3 == realized))
}

# --- jb_devig_triplet ------------------------------------------------------

test_that("jb_devig_triplet normalises inverse SP to a probability vector", {
  v <- jb_devig_triplet(c(2, 4), c(4, 4), c(4, 2))
  expect_equal(unname(v[1, ]), c(0.5, 0.25, 0.25))
  expect_equal(unname(v[2, ]), c(0.25, 0.25, 0.5))
  expect_equal(unname(rowSums(v)), c(1, 1))
  expect_equal(unname(jb_devig_triplet(2, 4, 4)[1, ]), c(0.5, 0.25, 0.25))
  expect_error(jb_devig_triplet(2, 4, "x"), "three numeric columns")
  expect_error(jb_devig_triplet(NA_real_, 4, 4), "missing SP")
  expect_error(jb_devig_triplet(Inf, 4, 4), "non-finite SP")
  expect_error(jb_devig_triplet(1, 4, 4), "must exceed 1")
  expect_error(jb_devig_triplet(0, 4, 4), "must exceed 1")
})

# --- jb_sp_signals ---------------------------------------------------------

test_that("jb_sp_signals pivots to one row per fixture and de-vigs", {
  out <- jb_sp_signals(make_sp())
  expect_equal(nrow(out), 2L)
  expect_equal(sort(out$s_1), sort(c(0.5, 0.2 / 0.9)))
  expect_equal(out$s_1 + out$s_2 + out$s_3, c(1, 1))
  expect_equal(attr(out, "dropped_fixtures"), 0L)
})

test_that("jb_sp_signals drops, never imputes, a partially priced fixture", {
  sp <- make_sp()
  sp$sp[sp$issue == "100102" & sp$option == "平"] <- NA_real_
  out <- jb_sp_signals(sp)
  expect_equal(nrow(out), 1L)
  expect_equal(out$issue, "100101")
  expect_equal(attr(out, "dropped_fixtures"), 1L)
  # An SP of exactly 1 is not a legal decimal price.
  sp2 <- make_sp(); sp2$sp[1] <- 1
  expect_equal(nrow(jb_sp_signals(sp2)), 1L)
  # A fixture set with nothing usable is an error, not an empty result.
  # With only two of three outcomes recorded the fixture cannot be de-vigged.
  sp3 <- make_sp(); sp3$sp[1] <- NA_real_
  expect_error(jb_sp_signals(sp3[sp3$issue == "100101", ]), "no fixture has three usable SP")
})

test_that("jb_sp_signals fails closed on malformed SP rows", {
  sp <- make_sp()
  expect_error(jb_sp_signals(sp[0, ]), "no SP rows")
  expect_error(jb_sp_signals(dplyr::select(sp, -sp)), "must include")
  expect_error(jb_sp_signals(rbind(sp, sp[1, ])), "duplicated issue/slot/option")
  bad <- sp; bad$option[1] <- "主胜"
  expect_error(jb_sp_signals(bad), "unknown option label")
  # A missing option is missing data: the row is dropped and counted.
  miss <- sp; miss$option[1] <- NA_character_
  kept <- jb_sp_signals(miss)
  expect_equal(nrow(kept), 1L)
  expect_equal(attr(kept, "dropped_rows"), 1L)
  allmiss <- sp; allmiss$option <- NA_character_
  expect_error(jb_sp_signals(allmiss), "no row carries both an option and an SP")
})

# --- jb_probability_signals ------------------------------------------------

test_that("jb_probability_signals joins p, q and s onto every cell", {
  frame <- dplyr::bind_rows(
    make_cells("100101-1", c(.5, .25, .25), c(.5, .3, .2), 1L),
    make_cells("100102-2", c(.2, .3, .5), c(.3, .3, .4), 3L, provider_id = "p2"))
  sig <- jb_probability_signals(frame, jb_sp_signals(make_sp()))
  expect_equal(nrow(sig), 6L)
  expect_true(all(c("p", "q", "s") %in% names(sig)))
  expect_equal(sig$s[sig$fixture == "100101-1"], c(.5, .25, .25))
})

test_that("jb_probability_signals fails closed on broken cell contracts", {
  good <- make_cells("100101-1", c(.5, .25, .25), c(.5, .3, .2), 1L)
  sps <- jb_sp_signals(make_sp())
  expect_error(jb_probability_signals(good[0, ], sps), "empty frame")
  expect_error(jb_probability_signals(dplyr::select(good, -p), sps), "must include")
  bad <- good; bad$outcome[1] <- 4L
  expect_error(jb_probability_signals(bad, sps), "outcome outside 1..3")
  bad2 <- good; bad2$p[1] <- 0
  expect_error(jb_probability_signals(bad2, sps), "non-positive probability")
  bad3 <- good; bad3$p <- c(.5, .25, .20)
  expect_error(jb_probability_signals(bad3, sps), "must each sum to one")
  bad4 <- good; bad4$realized <- c(1L, 1L, 0L)
  expect_error(jb_probability_signals(bad4, sps), "exactly one realized outcome")
  bad5 <- rbind(good, good[1, ])
  expect_error(jb_probability_signals(bad5, sps), "duplicated fixture/outcome")
  # A fixture with no SP row must not be silently dropped.
  other <- make_cells("100999-9", c(.5, .25, .25), c(.5, .3, .2), 1L)
  expect_error(jb_probability_signals(rbind(good, other), sps), "SP join dropped")
})

# --- jb_multiclass_scores --------------------------------------------------

test_that("jb_multiclass_scores computes log-loss, Brier and accuracy", {
  sig <- dplyr::bind_rows(
    make_cells("100101-1", c(.8, .1, .1), c(.6, .2, .2), 1L),
    make_cells("100102-2", c(.1, .7, .2), c(.2, .5, .3), 2L, provider_id = "p2"))
  sc <- jb_multiclass_scores(sig, c("p", "q"))
  expect_equal(sc$fixtures, c(2L, 2L))
  expect_equal(sc$log_loss[1], mean(-log(c(.8, .7))))
  expect_equal(sc$brier[1], 0.10)
  expect_equal(sc$accuracy[1], 1)
  expect_equal(sc$tied_argmax, c(0, 0))
  expect_equal(sc$log_loss[2], mean(-log(c(.6, .5))))
  expect_error(jb_multiclass_scores(sig[0, ], "p"), "no cells")
  expect_error(jb_multiclass_scores(sig, "nope"), "unknown prob column")
  # A tied argmax is scored as a miss and reported, not treated as an error.
  tied <- make_cells("100101-1", c(.4995, .4995, .001), c(.5, .3, .2), 1L)
  st <- jb_multiclass_scores(tied, "p")
  expect_equal(st$accuracy, 0)
  expect_equal(st$tied_argmax, 1)
  expect_equal(st$log_loss, -log(.4995))
})

# --- jb_calibration_table --------------------------------------------------

test_that("jb_calibration_table bins cells and reports the gap", {
  sig <- dplyr::bind_rows(
    make_cells("100101-1", c(.8, .1, .1), c(.6, .2, .2), 1L),
    make_cells("100102-2", c(.1, .7, .2), c(.2, .5, .3), 2L, provider_id = "p2"))
  cal <- jb_calibration_table(sig, "p", breaks = c(0, .2, .5, 1))
  expect_equal(sum(cal$cells), 6L)
  hi <- cal[cal$forecast > .5, ]
  expect_equal(hi$cells, 2L)             # .8 and .7; the .6 belongs to q, not p
  expect_equal(hi$forecast, mean(c(.8, .7)))
  expect_equal(hi$realised, 1)
  expect_equal(hi$gap, 1 - mean(c(.8, .7)))
  expect_error(jb_calibration_table(sig, "nope"), "must include")
  bad <- sig; bad$p[1] <- 0
  expect_error(jb_calibration_table(bad, "p"), "non-positive probability")
})

# --- jb_clr_divergence -----------------------------------------------------

test_that("jb_clr_divergence matches the centered log-ratio definition", {
  # log(0.5/0.25), log(0.25/0.5), log(0.25/0.25) = a, -a, 0  =>  clr = a
  a <- log(2)
  expect_equal(jb_clr_divergence(c(.5, .25, .25), c(.25, .5, .25), 1L), a)
  expect_equal(jb_clr_divergence(c(.5, .25, .25), c(.25, .5, .25), 2L), -a)
  expect_equal(jb_clr_divergence(c(.5, .25, .25), c(.25, .5, .25), 3L), 0)
  # Identical vectors have zero divergence on every component.
  v <- c(.2, .3, .5)
  expect_equal(vapply(1:3, function(o) jb_clr_divergence(v, v, o), numeric(1)), c(0, 0, 0))
  # Scale-free: the CLR removes any common rescaling of the source.
  expect_equal(jb_clr_divergence(c(.5, .25, .25) * 10, c(.25, .5, .25), 1L), a)
  # Degenerate components make the cell NA rather than being clipped.
  expect_true(is.na(jb_clr_divergence(c(0, .5, .5), c(.25, .5, .25), 1L)))
  expect_true(is.na(jb_clr_divergence(c(.5, .25, .25), c(0, .5, .5), 1L)))
})

test_that("jb_add_divergence adds divergences and 2nd/3rd gaps", {
  sig <- dplyr::bind_rows(
    make_cells("100101-1", c(.5, .3, .2), c(.4, .35, .25), 1L),
    make_cells("100102-2", c(.2, .3, .5), c(.3, .3, .4), 3L, provider_id = "p2"))
  sps <- jb_sp_signals(make_sp())
  full <- jb_probability_signals(sig, sps)
  out <- jb_add_divergence(full)
  expect_true(all(c("div_p_s", "div_q_s", "div_p_q", "gap23_p", "gap23_q", "gap23_s") %in%
                    names(out)))
  expect_equal(nrow(out), 6L)
  d1 <- out[out$fixture == "100101-1", ]
  expect_equal(unique(d1$gap23_p), .3 - .2)      # constant within a fixture
  expect_equal(unique(d1$gap23_q), .35 - .25)
  expect_equal(unique(d1$div_p_q), jb_clr_divergence(c(.5, .3, .2), c(.4, .35, .25), 1L))
  expect_error(jb_add_divergence(dplyr::select(full, -s)), "must include")
})

# --- jb_conditional_logit --------------------------------------------------

test_that("jb_conditional_logit attributes information to the true signal", {
  withr::local_seed(11)
  n <- 800L
  fx <- sprintf("f%04d", seq_len(n))
  q <- matrix(stats::runif(n * 3, 0.05, 0.9), nrow = n); q <- q / rowSums(q)
  p <- matrix(stats::runif(n * 3, 0.05, 0.9), nrow = n); p <- p / rowSums(p)
  oc <- vapply(seq_len(n), function(i) sample.int(3, 1, prob = q[i, ]), integer(1))
  d <- tibble::tibble(fixture = rep(fx, each = 3), outcome = rep(1:3, n),
                      p = as.vector(t(p)), q = as.vector(t(q)),
                      realized = as.integer(rep(1:3, n) == rep(oc, each = 3)))
  co <- jb_conditional_logit(d, c("p", "q"))
  expect_equal(nrow(co), 2L)
  expect_equal(co$n_fixtures, rep(n, 2))
  bq <- co[co$term == "logit_q", ]; bp <- co[co$term == "logit_p", ]
  expect_gt(bq$estimate, 0.6)            # q carries the truth
  expect_lt(bq$p, 1e-8)
  # At n = 800 even a small noise coefficient can clear p < 0.05, so the honest
  # assertion is that p's coefficient is negligible next to q's.
  expect_lt(abs(bp$estimate), 0.3 * bq$estimate)
  expect_error(jb_conditional_logit(d, "nope"), "unknown prob column")
  bad <- d; bad$p[1] <- 1
  expect_error(jb_conditional_logit(bad, "p"), "strictly inside")
})

test_that("jb_conditional_logit reports a null model honestly", {
  withr::local_seed(5)
  n <- 400L
  fx <- sprintf("f%04d", seq_len(n))
  p <- matrix(stats::runif(n * 3, 0.05, 0.9), nrow = n); p <- p / rowSums(p)
  oc <- vapply(seq_len(n), function(i) sample.int(3, 1), integer(1))
  d <- tibble::tibble(fixture = rep(fx, each = 3), outcome = rep(1:3, n),
                      p = as.vector(t(p)),
                      realized = as.integer(rep(1:3, n) == rep(oc, each = 3)))
  co <- jb_conditional_logit(d, "p")
  expect_gt(co$p, 0.05)                  # a pure-noise signal must not look real
})

test_that("jb_conditional_logit does not require the survival package attached", {
  # Regression: an unqualified strata() in the formula and the bare coxph()
  # that clogit() evaluates in its caller's frame both resolve only when
  # survival is attached. The implementation must supply those bindings itself.
  expect_false("package:survival" %in% search())
  withr::local_seed(21)
  n <- 600L
  q <- matrix(stats::runif(n * 3, 0.05, 0.9), nrow = n); q <- q / rowSums(q)
  p <- matrix(stats::runif(n * 3, 0.05, 0.9), nrow = n); p <- p / rowSums(p)
  oc <- vapply(seq_len(n), function(i) sample.int(3, 1, prob = q[i, ]), integer(1))
  d <- tibble::tibble(fixture = rep(seq_len(n), each = 3), outcome = rep(1:3, times = n),
                      p = as.vector(t(p)), q = as.vector(t(q)),
                      realized = as.integer(rep(1:3, times = n) == rep(oc, each = 3)))
  co <- jb_conditional_logit(d, c("p", "q"))
  expect_equal(nrow(co), 2L)
  expect_setequal(co$term, c("logit_p", "logit_q"))
  # The true signal must dominate the noise signal.
  bq <- co$estimate[co$term == "logit_q"]; bp <- co$estimate[co$term == "logit_p"]
  expect_gt(bq, 0.4)
  expect_lt(abs(bp), 0.3 * bq)
})
