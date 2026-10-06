testthat::test_that("draw replacement preserves DC W:L and fixes the BD draw exactly", {
  dc <- tibble::tibble(fixture_id = rep(c("a", "b"), each = 3),
    outcome = rep(c("W", "D", "L"), 2), probability = c(.6,.2,.2,.1,.5,.4))
  bd <- dc; bd$probability <- c(.3,.6,.1,.2,.2,.6)
  x <- ReplaceDcDrawProbability(dc, bd[6:1, ])
  testthat::expect_equal(x$probability, c(.3,.6,.1,.16,.2,.64))
  testthat::expect_equal(x$probability[c(1,4)]/x$probability[c(3,6)], c(3,.25))
  testthat::expect_equal(sum(x$probability[1:3]), 1)
  testthat::expect_equal(sum(x$probability[4:6]), 1)
  testthat::expect_equal(ReplaceDcDrawProbability(dc, dc), dc, tolerance = 1e-14)
  zero <- bd; zero$probability[1:3] <- c(.75,0,.25)
  testthat::expect_equal(ReplaceDcDrawProbability(dc, zero)$probability[1:3], c(.75,0,.25))
  one <- bd; one$probability[1:3] <- c(0,1,0)
  testthat::expect_equal(ReplaceDcDrawProbability(dc, one)$probability[1:3], c(0,1,0))
  degenerate <- dc; degenerate$probability[1:3] <- c(0,1,0)
  testthat::expect_error(ReplaceDcDrawProbability(degenerate, bd), "Undefined")
  testthat::expect_equal(ReplaceDcDrawProbability(degenerate, one)$probability[1:3], c(0,1,0))
  testthat::expect_error(ReplaceDcDrawProbability(dc[0, ], bd))
  testthat::expect_error(ReplaceDcDrawProbability(dc[-1, ], bd))
  testthat::expect_error(ReplaceDcDrawProbability(dc, bd[-1, ]))
  testthat::expect_error(ReplaceDcDrawProbability(dc, dplyr::bind_rows(bd, bd[1, ])))
  bad <- bd; bad$fixture_id[1:3] <- "c"
  testthat::expect_error(ReplaceDcDrawProbability(dc, bad), "Mismatched")
  bad <- bd; bad$probability[1] <- Inf
  testthat::expect_error(ReplaceDcDrawProbability(dc, bad))
  bad$probability[1] <- NA_real_
  testthat::expect_error(ReplaceDcDrawProbability(dc, bad))
  bad$probability[1] <- -.1
  testthat::expect_error(ReplaceDcDrawProbability(dc, bad))
  bad <- bd; bad$outcome[1] <- "OTHER"
  testthat::expect_error(ReplaceDcDrawProbability(dc, bad))
  bad <- bd; bad$probability[1] <- .4
  testthat::expect_error(ReplaceDcDrawProbability(dc, bad))
})
