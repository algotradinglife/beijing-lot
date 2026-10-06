test_that("Bernoulli dependence has independent, identical, exclusive and constant oracles", {
  expect_equal(.ParlayBernoulliCorrelation(.5, .5, .25), 0)
  expect_equal(.ParlayBernoulliCorrelation(.5, .5, .5), 1)
  expect_equal(.ParlayBernoulliCorrelation(.5, .5, 0), -1)
  expect_true(is.na(.ParlayBernoulliCorrelation(1, .5, .5)))
  expect_error(.ParlayBernoulliCorrelation(.3, .4, .5), "invalid joint")
  expect_error(.ParlayBernoulliCorrelation(NA_real_, .5, .2))
})

test_that("mask intersection counts restricted shared fixtures and complementary masks", {
  p <- tibble::tibble(fixture_id = rep(c("001", "002"), each = 3),
    outcome = rep(c("W", "D", "L"), 2), probability = c(.6, .3, .1, .5, .3, .2))
  legs <- tibble::tibble(group_id = c("a", "a", "b", "b", "c"),
    fixture_id = c("001", "002", "001", "002", "001"),
    allowed_outcomes = list("W", c("W", "D", "L"), "W", "W", "L"),
    retained_probability = c(.6, 1, .6, .5, .1))
  pairs <- .ParlayMaskPairs(legs, p)
  expect_s3_class(pairs, "tbl_df")
  expect_equal(nrow(pairs), 3L)
  ab <- pairs[pairs$group_a == "a" & pairs$group_b == "b", ]
  expect_equal(ab$shared_fixtures, 2L)
  expect_equal(ab$shared_restricted_fixtures, 1L)
  expect_equal(ab$joint_probability, .3)
  expect_equal(ab$mask_correlation, (.3 - .6 * .3) / sqrt(.6 * .4 * .3 * .7))
  expect_equal(pairs$joint_probability[pairs$group_a == "a" & pairs$group_b == "c"], 0)
  expect_identical(.ParlayMaskPairs(legs[1:2, ], p), .ParlayMaskPairs(legs[0, ], p))
})

test_that("frozen physical tickets have exact dependence and conditional stress", {
  e <- AllocationFixture()
  before <- rlang::hash(e)
  set.seed(919)
  rng <- .Random.seed
  x <- DiagnoseParlayDependence(e, n_draws = 1000L, seed = 17L)
  expect_identical(rlang::hash(e), before)
  expect_identical(.Random.seed, rng)
  expect_identical(x$cutoff, e$cutoff)
  expect_equal(nrow(x$candidate_pairs), 3L)
  expect_true(all(is.na(x$candidate_pairs$mask_correlation)))
  expect_equal(x$bought_pairs$owned_correlation, rep(0, 3), tolerance = 1e-12)
  expect_equal(x$bought_pairs$owned_joint_probability, c(.4 * .37, .4 * .34, .37 * .34))
  aw <- x$exposure[x$exposure$fixture_id == "A:001" & x$exposure$outcome == "W", ]
  ad <- x$exposure[x$exposure$fixture_id == "A:001" & x$exposure$outcome == "D", ]
  expect_equal(aw$knockout_fraction, 0)
  expect_equal(aw$conditional_hit_probability, 1)
  expect_equal(ad$knockout_fraction, 1/3)
  expect_equal(ad$conditional_hit_probability, 1 - (1 - .37) * (1 - .34))
  expect_equal(ad$conditional_expected_net_cny, 2 * .65 * 3 * (.37 + .34) - 6)
  for (id in unique(x$exposure$fixture_id)) {
    local <- x$exposure[x$exposure$fixture_id == id, ]
    expect_equal(sum(local$probability * local$conditional_hit_probability), 1 - .6 * .63 * .66)
    expect_equal(sum(local$probability * local$conditional_expected_net_cny), 3.9 * (.4 + .37 + .34) - 6)
  }
  expect_false(x$receipt$historical_learning)
  raw <- x; raw$receipt <- NULL
  expect_identical(x$receipt$output_hash, rlang::hash(raw))
  expect_identical(x, DiagnoseParlayDependence(e, n_draws = 1000L, seed = 17L))
  # Detached target labels cannot change the diagnostic: they are never an input.
  labels <- AllocationObservation(e); labels$settlements$settled_sp <- 1000
  expect_identical(x, DiagnoseParlayDependence(e, n_draws = 1000L, seed = 17L))
  bad <- e; bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc + 1
  expect_error(DiagnoseParlayDependence(bad), "cutoff|binding")
  bad <- e; bad$portfolio$prematch_sp$quote_at[1] <- e$cutoff$cutoff_utc
  expect_error(DiagnoseParlayDependence(bad), "cutoff|hash|binding")
  expect_error(DiagnoseParlayDependence(e, n_draws = 0L))
  expect_error(DiagnoseParlayDependence(e, seed = -1L))
})

test_that("no-purchase plans have typed empty exposures and bought pairs", {
  source <- AllocationFixture()
  empty <- parlay_select_groups(source$portfolio, budget_cny = 0, group_budget_cny = 2)$evaluation
  x <- DiagnoseParlayDependence(empty, n_draws = 10L)
  expect_s3_class(x$exposure, "tbl_df")
  expect_equal(nrow(x$exposure), 0L)
  expect_equal(nrow(x$bought_pairs), 0L)
  expect_equal(x$joint_risk$summary$hit_probability, 0)
  expect_equal(x$joint_risk$summary$expected_net_cny, 0)
  expect_true(is.na(x$joint_risk$summary$break_even_probability))
})

test_that("zero probability stress states and absent SP preserve unknown semantics", {
  cutoff <- list(issue_id="Z",cutoff_utc=as.POSIXct("2026-09-01",tz="UTC"))
  matches <- tibble::tibble(fixture_id=c("Z:001","Z:002"),win=c(.4,.4),draw=c(.6,.3),lose=c(0,.3))
  settings <- parlay_constant_defaults();settings$n_legs <- 1L;settings$issue_budget_cny <- 4
  sp <- tidyr::crossing(fixture_id=matches$fixture_id,outcome=c("W","D","L")) |>
    dplyr::mutate(quote_at=cutoff$cutoff_utc-60,sp_raw=NA_real_,source_url="fixture://missing")
  pool <- parlay_construct_role_groups(rank_outcome_selections(prepare_outcome_selections(matches,single_threshold=.7),cutoff),
    settings,2L,max_candidates=2L,prematch_sp=sp)
  e <- parlay_select_groups(pool,objective="coverage",budget_cny=4,group_budget_cny=2)$evaluation
  x <- DiagnoseParlayDependence(e,n_draws=100L)
  zero <- x$exposure[x$exposure$fixture_id=="Z:001" & x$exposure$outcome=="L",]
  expect_equal(nrow(zero),1L)
  expect_equal(zero$probability,0)
  expect_true(is.na(zero$conditional_hit_probability))
  expect_true(all(is.na(x$exposure$conditional_expected_net_cny)))
  expect_true(all(is.na(x$joint_risk$summary$expected_net_cny[x$joint_risk$summary$cost_cny>0])))
})
