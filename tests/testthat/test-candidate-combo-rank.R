test_that("candidate ranking uses fixed budget and Pareto frontier", {
  x <- data.frame(combo_id = c("a", "b", "c"), hit_probability = c(.4, .3, .2),
    expected_gross = c(200, 500, 100), stake_cny = c(100, 100, 100),
    legal_mass = c(.9, .9, .9))
  z <- rank_candidate_combinations(x, budget_cny = 200)
  expect_equal(z$copies, rep(2, 3))
  expect_equal(z$budget_hit_probability[match(c("a", "b", "c"), z$combo_id)], c(.4, .3, .2))
  expect_true(z$pareto_frontier[z$combo_id == "a"])
  expect_false(z$pareto_frontier[z$combo_id == "c"])
})

test_that("role combinations feed the same fixed-budget ranker", {
  combos <- data.frame(combo_id = c("M6O1-a", "M5O2-b"),
    main_count = c(6L, 5L), opportunity_count = c(1L, 2L), fixtures = c("1,2", "2,3"))
  metrics <- data.frame(combo_id = combos$combo_id, hit_probability = c(.4, .3),
    expected_gross = c(200, 500), stake_cny = c(100, 100), legal_mass = c(.9, .9))
  z <- rank_role_combinations(combos, metrics, 200)
  expect_equal(nrow(z), 2)
  expect_true(all(z$main_count %in% c(5L, 6L)))
})
