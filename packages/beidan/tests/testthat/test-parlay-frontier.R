#' Assemble deterministic frontier test inputs.
#' @param scenario_id Character identifiers.
#' @param prefix_groups Whole prefix depths.
#' @param cost_cny CNY costs.
#' @param hit_probability Model hit probabilities.
#' @param expected_net_cny Expected CNY net, optionally NA.
#' @param max_reuse Whole reuse limit.
#' @param max_overlap Whole overlap limit.
#' @param pattern Character structure identifier.
#' @return Scenario tibble; no side effects.
frontier_summary <- function(scenario_id, prefix_groups, cost_cny, hit_probability,
                             expected_net_cny, max_reuse = 1L, max_overlap = 0L,
                             pattern = "p") {
  return(tibble::tibble(
    scenario_id = scenario_id,
    pattern = pattern,
    prefix_groups = prefix_groups,
    cost_cny = cost_cny,
    hit_probability = hit_probability,
    expected_net_cny = expected_net_cny,
    max_reuse = max_reuse,
    max_overlap = max_overlap
  ))
}

test_that("frontier flags follow hand-calculated dominance and preserve input", {
  summary <- frontier_summary(
    scenario_id = c("A", "B", "C", "D"),
    prefix_groups = c(1, 1, 1, 1),
    cost_cny = c(4, 2, 4, 2),
    hit_probability = c(0.5, 0.5, 0.8, 0.5),
    expected_net_cny = c(NA_real_, NA_real_, 5, NA_real_)
  )
  actual <- parlay_frontier(summary)
  expect_identical(names(actual), c(names(summary), "coverage_frontier", "return_frontier"))
  expect_identical(actual[names(summary)], summary)
  expect_identical(actual$coverage_frontier, c(FALSE, TRUE, TRUE, TRUE))
  expect_identical(actual$return_frontier, c(FALSE, FALSE, TRUE, FALSE))
  expect_type(actual$coverage_frontier, "logical")
  expect_type(actual$return_frontier, "logical")
})

test_that("exact ties retain both scenarios on both frontiers", {
  summary <- frontier_summary(
    scenario_id = c("t1", "t2"),
    prefix_groups = c(2, 2),
    cost_cny = c(3, 3),
    hit_probability = c(0.6, 0.6),
    expected_net_cny = c(4, 4)
  )
  actual <- parlay_frontier(summary)
  expect_identical(actual$coverage_frontier, c(TRUE, TRUE))
  expect_identical(actual$return_frontier, c(TRUE, TRUE))
})

test_that("dominance is confined to the same reuse/overlap profile across patterns", {
  summary <- frontier_summary(
    scenario_id = c("X", "Y", "Z"),
    pattern = c("p1", "p1", "p2"),
    prefix_groups = c(1, 1, 1),
    cost_cny = c(1, 5, 5),
    hit_probability = c(0.9, 0.1, 0.1),
    expected_net_cny = c(2, 2, 2),
    max_reuse = c(1L, 2L, 1L),
    max_overlap = c(0L, 0L, 0L)
  )
  actual <- parlay_frontier(summary)
  # X dominates Z in the shared (1,0) profile even though patterns differ.
  expect_identical(actual$coverage_frontier, c(TRUE, TRUE, FALSE))
  # Y survives because profile (2,0) is never compared with (1,0).
  expect_identical(actual$return_frontier, c(TRUE, TRUE, FALSE))
})

test_that("missing expected net returns FALSE and never dominates", {
  summary <- frontier_summary(
    scenario_id = c("M", "N", "O"),
    prefix_groups = c(2, 2, 2),
    cost_cny = c(1, 2, 1),
    hit_probability = c(0.5, 0.5, 0.5),
    expected_net_cny = c(NA_real_, 3, NA_real_)
  )
  actual <- parlay_frontier(summary)
  expect_identical(actual$return_frontier, c(FALSE, TRUE, FALSE))
  # Coverage is independent: M dominates N, and M/O tie.
  expect_identical(actual$coverage_frontier, c(TRUE, FALSE, TRUE))
})

test_that("zero cost and zero prefix rows are excluded from flags and dominance", {
  summary <- frontier_summary(
    scenario_id = c("Z", "P", "Q"),
    prefix_groups = c(2, 0, 1),
    cost_cny = c(0, 3, 3),
    hit_probability = c(0.5, 0.9, 0.4),
    expected_net_cny = c(5, 1, 2)
  )
  actual <- parlay_frontier(summary)
  expect_identical(actual$coverage_frontier, c(FALSE, FALSE, TRUE))
  expect_identical(actual$return_frontier, c(FALSE, FALSE, TRUE))
})

test_that("invalid schemas are rejected", {
  valid <- frontier_summary(
    scenario_id = c("a", "b"),
    prefix_groups = c(1, 2),
    cost_cny = c(1, 2),
    hit_probability = c(0.2, 0.4),
    expected_net_cny = c(1, NA_real_)
  )
  expect_error(parlay_frontier(as.data.frame(valid)), "parlay_frontier")
  expect_error(parlay_frontier(valid["scenario_id"]), "parlay_frontier")
  expect_error(parlay_frontier(valid[c(1, 2, 2), ]), "parlay_frontier")

  bad <- valid; bad$scenario_id <- c("a", NA_character_)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$scenario_id <- c("a", "")
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$scenario_id <- c(1, 2)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$prefix_groups <- c(1, -1)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$prefix_groups <- c(1, 1.5)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$prefix_groups <- c(1, NA_real_)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$cost_cny <- c(1, -1)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$cost_cny <- c(1, NA_real_)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$cost_cny <- c(1, Inf)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$hit_probability <- c(0.2, 1.2)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$hit_probability <- c(0.2, -0.1)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$expected_net_cny <- c(1, Inf)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$expected_net_cny <- c(1, NaN)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$max_reuse <- c(1L, 0L)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$max_reuse <- c(1L, 1.5)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$max_overlap <- c(0L, -1L)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$cost_cny <- as.difftime(c(1, 2), units = "secs")
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$cost_cny <- matrix(c(1, 2), ncol = 1L)
  expect_error(parlay_frontier(bad), "parlay_frontier")

  bad <- valid; bad$coverage_frontier <- c(TRUE, TRUE)
  expect_error(parlay_frontier(bad), "parlay_frontier")
  bad <- valid; bad$return_frontier <- c(TRUE, TRUE)
  expect_error(parlay_frontier(bad), "parlay_frontier")
})

test_that("a zero-row summary returns a typed empty result", {
  valid <- frontier_summary(
    scenario_id = c("a", "b"),
    prefix_groups = c(1, 2),
    cost_cny = c(1, 2),
    hit_probability = c(0.2, 0.4),
    expected_net_cny = c(1, NA_real_)
  )
  empty <- valid[0, ]
  actual <- parlay_frontier(empty)
  expect_s3_class(actual, "tbl_df")
  expect_equal(nrow(actual), 0L)
  expect_identical(names(actual), c(names(valid), "coverage_frontier", "return_frontier"))
  expect_identical(actual$coverage_frontier, logical(0))
  expect_identical(actual$return_frontier, logical(0))
  full <- parlay_frontier(valid)
  expect_identical(vapply(actual, typeof, character(1)),
                   vapply(full, typeof, character(1)))
})


test_that("constraint identity uses exact numbers and schema names are unique", {
  x <- frontier_summary(c("a", "b"), c(1, 1), c(1, 2), c(.8, .2), c(2, 1),
                        max_reuse = c(1e16, 1e16 + 2))
  expect_identical(parlay_frontier(x)$coverage_frontier, c(TRUE, TRUE))
  expect_identical(parlay_frontier(x)$return_frontier, c(TRUE, TRUE))
  names(x)[2] <- "scenario_id"
  expect_error(parlay_frontier(x))
})
