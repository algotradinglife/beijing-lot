test_that("role generator returns only 6:1 and 5:2 structures", {
  f <- data.frame(fixture_id = as.character(1:9), role = c(rep("主力", 7), rep("机会", 2)))
  z <- generate_role_combinations(f, max_candidates = 100)
  expect_true(all(z$main_count == 6 & z$opportunity_count == 1 |
    z$main_count == 5 & z$opportunity_count == 2))
  expect_true(all(vapply(strsplit(z$fixtures, ",", fixed = TRUE), length, integer(1)) == 7))
})
