testthat::test_that("paired ranks, scores, precision and recall have independent numeric expectations", {
  p <- tibble::tibble(fixture_id = rep(c("a", "b"), each = 3), model = "m",
    outcome = rep(c("W", "D", "L"), 2), probability = c(.5, .3, .2, .2, .3, .5))
  y <- tibble::tibble(fixture_id = c("a", "b"), actual_outcome = c("W", "D"))
  x <- DcAccuracyDiagnostic(p, y)
  testthat::expect_equal(x$scores$actual_rank, c(1L, 2L))
  testthat::expect_equal(x$summary$top1, .5)
  testthat::expect_equal(x$summary$top2, 1)
  testthat::expect_equal(x$summary$top3, 1)
  testthat::expect_equal(x$summary$brier, (.38 + .78) / 2)
  testthat::expect_equal(x$summary$logloss, -mean(log(c(.5, .3))))
  testthat::expect_equal(x$precision$precision, c(0, 1))
  testthat::expect_equal(x$recall$top1, c(0, 1))
  testthat::expect_equal(x$calibration$predicted_mass, c(.3, .35, .35))
  testthat::expect_equal(x$calibration$observed_mass, c(.5, 0, .5))
  testthat::expect_equal(sum(x$confusion$n), 2L)
  tied <- p; tied$probability <- 1/3
  testthat::expect_equal(DcAccuracyDiagnostic(tied, y)$scores$actual_rank, c(1L, 2L))
  zero <- p; zero$probability[1:3] <- c(0, .6, .4)
  testthat::expect_equal(DcAccuracyDiagnostic(zero, y)$summary$logloss, Inf)
  paired <- dplyr::bind_rows(p, dplyr::mutate(p, model = "second"))
  testthat::expect_equal(nrow(DcAccuracyDiagnostic(paired, y)$scores), 4L)
  testthat::expect_error(DcAccuracyDiagnostic(paired[-1, ], y), "Incomplete")
  testthat::expect_error(DcAccuracyDiagnostic(p[0, ], y))
  testthat::expect_error(DcAccuracyDiagnostic(dplyr::bind_rows(p, p[1, ]), y), "Invalid")
  testthat::expect_error(DcAccuracyDiagnostic(p, dplyr::bind_rows(y, y[1, ])), "Invalid")
  bad <- p; bad$probability[1] <- Inf
  testthat::expect_error(DcAccuracyDiagnostic(bad, y), "Invalid")
  bad$probability[1] <- NA_real_
  testthat::expect_error(DcAccuracyDiagnostic(bad, y), "Invalid")
  bad$probability[1] <- .6
  testthat::expect_error(DcAccuracyDiagnostic(bad, y), "Incomplete")
  bad_y <- y; bad_y$fixture_id[1] <- "unknown"
  testthat::expect_error(DcAccuracyDiagnostic(p, bad_y), "Incomplete")
})

testthat::test_that("rho scenarios refit the authoritative production model and reject chronology errors", {
  fx <- epoch_fixture(n_fixtures = 2L)
  epoch <- prepare_match_inputs(fx$inputs, fx$cutoff$cutoff_utc,
    list(euro = default_euro(), totals = default_totals()))
  config <- list(rho = -.14, total_bounds = c(.1, 16), tail_tolerance = 1e-10)
  x <- DcRhoScenarios(epoch, config, c(-.14, 0))
  expected <- estimate_match_probabilities(epoch, config)
  actual <- x$probabilities |> dplyr::filter(rho == -.14) |>
    dplyr::select(fixture_id, outcome, probability)
  testthat::expect_identical(actual, expected$probabilities)
  testthat::expect_equal(nrow(x$fit), 4L)
  testthat::expect_identical(x$cutoff, epoch$cutoff)
  testthat::expect_identical(x, DcRhoScenarios(epoch, config, c(-.14, 0)))
  testthat::expect_false(identical(x$fit$lambda_home[1:2], x$fit$lambda_home[3:4]))
  testthat::expect_error(DcRhoScenarios(epoch, config, numeric()))
  testthat::expect_error(DcRhoScenarios(epoch, config, c(0, 0)))
  testthat::expect_error(DcRhoScenarios(epoch, config, Inf))
  testthat::expect_error(DcRhoScenarios(epoch, config, 2), "rho")
  late <- epoch; late$totals_selected$quote_at <- late$cutoff$cutoff_utc
  testthat::expect_error(DcRhoScenarios(late, config, 0), "cutoff")
  missing <- epoch; missing$cutoff <- NULL
  testthat::expect_error(DcRhoScenarios(missing, config, 0), "cutoff")
  empty <- epoch; empty$fixtures <- empty$fixtures[0, ]
  testthat::expect_error(DcRhoScenarios(empty, config, 0), "No fitted")
})
