testthat::test_that("fixed mixture normalizes component masses separately and preserves identity", {
  dc <- tibble::tibble(fixture_id="001",outcome=c("W","D","L"),probability=c(.6,.3,.1))
  bd <- dplyr::mutate(dc,probability=c(.2,.4,.4))
  x <- BlendMatchProbabilities(dc,bd[3:1,],.75)
  testthat::expect_equal(x$probability,c(.3,.375,.325))
  testthat::expect_identical(x$fixture_id,dc$fixture_id)
  testthat::expect_identical(x$outcome,dc$outcome)
  testthat::expect_equal(sum(x$probability),1)
  testthat::expect_identical(BlendMatchProbabilities(dc,bd,0),dc)
  testthat::expect_identical(BlendMatchProbabilities(dc,bd,1),bd)
  testthat::expect_error(BlendMatchProbabilities(dc,bd,-.1))
  testthat::expect_error(BlendMatchProbabilities(dc,bd,1.1))
  testthat::expect_error(BlendMatchProbabilities(dc,bd,NA_real_))
  testthat::expect_error(BlendMatchProbabilities(dc,bd,Inf))
  testthat::expect_error(BlendMatchProbabilities(dc,bd,c(.5,.75)))
  testthat::expect_error(BlendMatchProbabilities(dc[0,],bd,.75))
  testthat::expect_error(BlendMatchProbabilities(dc[-1,],bd,.75))
  testthat::expect_error(BlendMatchProbabilities(dc,dplyr::bind_rows(bd,bd[1,]),.75))
  bad <- bd;bad$probability[1] <- NA_real_
  testthat::expect_error(BlendMatchProbabilities(dc,bad,.75))
  bad$probability[1] <- Inf
  testthat::expect_error(BlendMatchProbabilities(dc,bad,.75))
  bad <- bd;bad$probability[1] <- .3
  testthat::expect_error(BlendMatchProbabilities(dc,bad,.75))
  bad <- bd;bad$fixture_id <- "002"
  testthat::expect_error(BlendMatchProbabilities(dc,bad,.75),"Mismatched")
})
