source(file.path("..", "..", "r", "n7_sleeve_tables.R"))
source(file.path("..", "..", "r", "n7_joint_sleeves.R"))

testthat::test_that("shared worlds, canonical state returns and native cutoffs preserve contracts", {
  e <- jsonlite::fromJSON(gzfile("../fixtures/n7_sleeve_numerical.json.gz"), simplifyVector = FALSE)$enumeration
  python <- Sys.getenv("FUNDAMENTALS_PYTHON")
  testthat::expect_true(nzchar(python))
  testthat::expect_identical(n7_joint_validate(e$fixtures, e$cutoffs, python), e$cutoffs)
  bad <- e$fixtures; bad[[1]]$actual_home <- 2L
  testthat::expect_error(n7_joint_validate(bad, e$cutoffs, python), "Prediction-only")
  testthat::expect_error(n7_joint_validate(e$fixtures, e$cutoffs[-1], python), "cutoff")
  p <- as.numeric(unlist(e$probability)); v <- as.numeric(unlist(e$expected_contribution))
  b <- list(issue = e$issue, cutoffs = e$cutoffs, historical_admission = FALSE, seal = "fixture",
    expanded_pool = list(fixtures = e$fixtures), sleeves = list(list(id = 0L,
      fixture_indices = as.list(0:6), origin = "TEST", enumeration = e,
      options = list(PROB = list(status = "COMPLETE", state_ids = as.list(order(-p, -v)[1:64] - 1L))))))
  pool <- n7_joint_options(b, b$cutoffs, python, "fixed", 2, .65, .8, -.35, 200, .01, 1e-9)
  testthat::expect_identical(pool$options[[1]]$state_ids, order(-p, -v, seq_along(p))[1:64])
  testthat::expect_equal(pool$options[[1]]$coverage, sum(p[pool$options[[1]]$state_ids]))
  testthat::expect_true(all(vapply(pool$options, function(o) length(o$state_ids) == 64 && !anyDuplicated(o$state_ids), logical(1))))
  set.seed(99); before <- .Random.seed
  worlds <- n7_joint_worlds(pool, e$cutoffs, 42, 200)
  testthat::expect_identical(.Random.seed, before)
  testthat::expect_identical(worlds, n7_joint_worlds(pool, e$cutoffs, 42, 200))
  testthat::expect_error(n7_joint_worlds(pool, list(), 42, 200))
  # The same fixture set/option must hit in exactly the same worlds, not
  # independently resampled copies. All canonical states also replay exactly.
  pool$options[[length(pool$options) + 1L]] <- pool$options[[1]]
  canonical <- as.matrix(expand.grid(rep(list(0:2), 7)))[, 7:1]
  r <- n7_joint_returns(pool, canonical, e$cutoffs)
  testthat::expect_identical(r$hits[, 1], r$hits[, ncol(r$hits)])
  ix <- pool$options[[1]]$state_ids
  testthat::expect_equal(which(r$hits[, 1] == 1), sort(ix))
  testthat::expect_equal(r$gross[ix, 1], as.numeric(unlist(e$estimated_payout))[ix])
  testthat::expect_error(n7_joint_returns(pool, canonical + 3, e$cutoffs))
  testthat::expect_error(n7_joint_returns(pool, canonical, list()))
})

testthat::test_that("five-round drawdown uses every interval, not terminal loss", {
  testthat::expect_equal(n7_joint_path_drawdowns(c(0, 0, 400, 0, 0), 5, 100), 200)
  testthat::expect_equal(n7_joint_path_drawdowns(c(0, 0, 0, 0, 0, rep(100, 5)), 5, 100), c(500, 0))
  testthat::expect_error(n7_joint_path_drawdowns(c(1, 2), 5, 100))
  testthat::expect_error(n7_joint_path_drawdowns(c(NA_real_), 1, 100))
})

testthat::test_that("joint optimum agrees with brute force and constraints change decisions", {
  cutoffs <- list(`1` = "2010-01-01T00:00:00+00:00")
  pool <- list(cutoffs = cutoffs, fixtures = as.list(1:22), options = list(
    list(sleeve_id = 1, fixtures = 1:7, expected_gross = 200),
    list(sleeve_id = 2, fixtures = 8:14, expected_gross = 200),
    list(sleeve_id = 3, fixtures = c(1:6, 15), expected_gross = 300),
    list(sleeve_id = 4, fixtures = 16:22, expected_gross = 400)))
  hit <- cbind(c(1, 1, 0, 0, 0), c(0, 0, 1, 1, 0), c(1, 0, 1, 0, 0), c(0, 0, 0, 0, 1))
  s <- list(hits = hit, gross = hit * 400, cutoffs = cutoffs)
  args <- list(pool = pool, scenarios = s, cutoffs = cutoffs, choose = 2,
    budget_cny = 256, unit_cny = 2, reuse_cap = 2, overlap_cap = 7,
    minimum_roi = -1, path_steps = 5, mean_drawdown_cap = Inf, solver_nodes = 200, solver_gap = 0, solver_feasibility_tolerance = 1e-9)
  z <- do.call(n7_joint_solve, args)
  all <- combn(4, 2)
  coverage <- apply(all, 2, function(ix) mean(rowSums(hit[, ix, drop = FALSE]) > 0))
  testthat::expect_equal(mean(rowSums(hit[, z$selected, drop = FALSE]) > 0), max(coverage))
  testthat::expect_equal(sort(z$selected), c(1L, 2L))
  higher <- do.call(n7_joint_solve, modifyList(args, list(minimum_roi = 1.5)))
  testthat::expect_equal(sort(higher$selected), c(3L, 4L))
  impossible <- do.call(n7_joint_solve, modifyList(args, list(minimum_roi = 10)))
  testthat::expect_length(impossible$selected, 0)
  testthat::expect_match(impossible$status, "Infeasible", ignore.case = TRUE)
  # Consecutive losses can distinguish equally priced/covered portfolios.
  s$gross <- cbind(c(200, 200, 0, 0, 0), c(0, 0, 200, 200, 0),
                   c(1000, 0, 1000, 0, 0), c(0, 0, 0, 0, 1000))
  args$scenarios <- s
  risk <- do.call(n7_joint_solve, modifyList(args, list(mean_drawdown_cap = 300)))
  testthat::expect_true(length(risk$selected) == 2)
  testthat::expect_equal(sort(risk$selected), c(3L, 4L))
  testthat::expect_lte(n7_joint_path_drawdowns(rowSums(s$gross[, risk$selected]), 5, 256), 300 + 1e-5)
  no_risk_fit <- do.call(n7_joint_solve, modifyList(args, list(mean_drawdown_cap = 0)))
  testthat::expect_length(no_risk_fit$selected, 0)
  capped <- do.call(n7_joint_solve, modifyList(args, list(overlap_cap = 0, reuse_cap = 1)))
  testthat::expect_length(intersect(pool$options[[capped$selected[1]]]$fixtures,
                                  pool$options[[capped$selected[2]]]$fixtures), 0)
  # Make the uniquely best pair overlap by one fixture. Test U and P separately:
  # deleting either constraint family must now fail its corresponding oracle.
  args$pool$options[[2]]$fixtures <- c(1L, 8:13)
  by_u <- do.call(n7_joint_solve, modifyList(args, list(reuse_cap = 1, overlap_cap = 7)))
  by_p <- do.call(n7_joint_solve, modifyList(args, list(reuse_cap = 8, overlap_cap = 0)))
  testthat::expect_lt(mean(rowSums(hit[, by_u$selected, drop = FALSE]) > 0), max(coverage))
  testthat::expect_lt(mean(rowSums(hit[, by_p$selected, drop = FALSE]) > 0), max(coverage))
  args$cutoffs <- list()
  testthat::expect_error(do.call(n7_joint_solve, args))
})

testthat::test_that("whole R issue exports exact 8x64 plans and empty plans hold cash", {
  e <- jsonlite::fromJSON(gzfile("../fixtures/n7_sleeve_numerical.json.gz"), simplifyVector = FALSE)$enumeration
  b <- list(issue = e$issue, historical_admission = FALSE, seal = "synthetic",
            expanded_pool = list(fixtures = list()), cutoffs = list(), sleeves = list())
  for (j in 1:8) {
    z <- e; z$cutoffs <- list()
    for (k in 1:7) {
      slot <- (j - 1L) * 7L + k
      z$fixtures[[k]]$slot <- slot
      z$fixtures[[k]]$provider_id <- sprintf("%06d", slot)
      z$cutoffs[[as.character(slot)]] <- e$cutoffs[[1]]
    }
    b$cutoffs <- c(b$cutoffs, z$cutoffs)
    b$expanded_pool$fixtures <- c(b$expanded_pool$fixtures, z$fixtures)
    b$sleeves[[j]] <- list(id = j, fixture_indices = as.list((j - 1L) * 7L + 0:6),
      origin = "SYNTHETIC", enumeration = z, options = list())
  }
  cfg <- jsonlite::fromJSON("../../config/n7_joint_424.json", simplifyVector = FALSE)
  cfg$training_worlds <- 10; cfg$evaluation_worlds <- 20; cfg$seeds <- list(42)
  out <- n7_joint_issue(b, b$cutoffs, cfg, Sys.getenv("FUNDAMENTALS_PYTHON"))
  testthat::expect_length(out$plans, 8)
  plan <- out$plans[[1]]
  testthat::expect_equal(dim(plan$fixture_indices), c(512, 7))
  testthat::expect_equal(plan$groups, 512)
  testthat::expect_equal(plan$stake, 1024)
  testthat::expect_equal(plan$max_reuse, 1)
  testthat::expect_equal(plan$max_overlap, 0)
  testthat::expect_length(plan$sleeve_keys, 8)
  testthat::expect_false(plan$historical_admission)
  # Selection is unchanged by any labels outside the accepted prediction input;
  # result-bearing input itself is rejected at the boundary.
  b$expanded_pool$fixtures[[1]]$result <- "W"
  testthat::expect_error(n7_joint_issue(b, b$cutoffs, cfg, Sys.getenv("FUNDAMENTALS_PYTHON")), "Prediction-only")
  b$expanded_pool$fixtures[[1]]$result <- NULL
  pool <- n7_joint_options(b, b$cutoffs, Sys.getenv("FUNDAMENTALS_PYTHON"), cfg$model_id,
    2, .65, .8, -.35, 200, .01, 1e-9)
  world <- n7_joint_returns(pool, n7_joint_worlds(pool, b$cutoffs, 42, 10), b$cutoffs)
  empty <- n7_joint_plan(pool, integer(), b$cutoffs, "EMPTY", 42, world, world, "Infeasible", NULL, cfg)
  testthat::expect_equal(empty$stake, 0)
  testthat::expect_equal(empty$cash_cny, 1024)
  testthat::expect_equal(empty$eval_path_drawdown, 0)
  testthat::expect_equal(empty$eval_coverage, 0)
  path <- tempfile(fileext = ".json")
  jsonlite::write_json(plan, path, auto_unbox = TRUE, digits = NA, null = "null", matrix = "rowmajor")
  restored <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  testthat::expect_length(restored$fixture_indices, 512)
  testthat::expect_identical(restored$fixtures[[1]]$provider_id, "000001")
})

testthat::test_that("100913 numerical boundary is solved tightly and invalid incumbents are rejected", {
  b <- jsonlite::fromJSON(gzfile("../fixtures/n7_joint_numerical_boundary.json.gz"), simplifyVector = FALSE)
  python <- Sys.getenv("FUNDAMENTALS_PYTHON")
  p <- as.numeric(unlist(b$sleeves[[1]]$enumeration$probability))
  v <- as.numeric(unlist(b$sleeves[[1]]$enumeration$expected_contribution))
  floor <- .8 * sum(p[order(-p, -v, seq_along(p))[1:64]])
  bad_ids <- as.integer(unlist(b$observed_bad_state_ids))
  # Observed default-HiGHS result: Optimal, but coverage deficit 9.0147e-7.
  testthat::expect_lt(sum(p[bad_ids]) - floor, -1e-7)
  tight <- n7_joint_options(b, b$cutoffs, python, "fixed", 2, .65, .8, -.35, 200, .01, 1e-9)
  frontier <- Filter(function(o) o$rule == "FRONTIER", tight$options)
  testthat::expect_length(frontier, 1)
  testthat::expect_gte(frontier[[1]]$coverage + 1e-7, floor)
  testthat::local_mocked_bindings(highs_solve = function(...) list(status_message = "Optimal",
    primal_solution = replace(rep(0, 2187), bad_ids, 1), info = list(mip_gap = 0)), .package = "highs")
  rejected <- n7_joint_options(b, b$cutoffs, python, "fixed", 2, .65, .8, -.35, 200, .01, 1e-9)
  testthat::expect_equal(rejected$statuses$frontier_status, "NUMERICAL_REJECTION")
  testthat::expect_false(any(vapply(rejected$options, function(o) o$rule == "FRONTIER", logical(1))))
  # The joint solver also refuses an invalid rounded binary assignment without
  # aborting unrelated issues or funding that incumbent.
  pool <- list(cutoffs = b$cutoffs, fixtures = as.list(1:7), options = list(
    list(sleeve_id = 1, fixtures = 1:7, expected_gross = 128)))
  s <- list(hits = matrix(1, 5, 1), gross = matrix(256, 5, 1), cutoffs = b$cutoffs)
  z <- n7_joint_solve(pool, s, b$cutoffs, 1, 128, 2, 1, 7, -1, 5, Inf, 200, .01, 1e-9)
  testthat::expect_equal(z$status, "NUMERICAL_REJECTION")
  testthat::expect_length(z$selected, 0)
})
