test_that("divergence features classify fixtures from label-free evidence", {
  pool <- list(fixtures = list(
    list(issue = "x", slot = 1L, provider_id = "p", p_W = .7, p_D = .2, p_L = .1)),
    cutoffs = list(x = "2020-01-01T00:00:00Z"))
  f <- divergence_reuse_features(pool, data.frame(issue = "x", slot = 1L,
    provider_id = "p", degree = 1, stringsAsFactors = FALSE))
  expect_equal(f$fixture_index, 1L)
  expect_equal(f$category, "HIGH")
})

test_that("allocator respects a per-fixture reuse cap", {
  expect_true(is.function(divergence_reuse_allocate))
})
