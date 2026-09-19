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
