source('../../r/joint_diagnostic_grid.R')
testthat::test_that('grid distinguishes absent, sparse, hit and payout shortfalls',{
 x<-tibble::tibble(policy='A',stage='ALL',band=c('a','b','c','d'),payout_band='p',
  tickets=100,issues=c(40,40,40,2),expected_hits=c(10,10,10,1),
  actual_hits=c(8,12,12,1),stake=200,gross=c(250,150,250,400))
 z<-joint_diagnostic_grid(x,letters[1:5],'p',30,5)
 testthat::expect_equal(as.character(z$diagnosis),c('HIT_SHORTFALL','PAYOUT_SHORTFALL','HIT_AND_RETURN_OK','LOW_SUPPORT','NO_PURCHASE'))
 testthat::expect_equal(sum(z$stake_share),1)
 testthat::expect_equal(sum(z$stake),800)
 testthat::expect_true(is.na(z$roi[5]))
 testthat::expect_true(is.na(z$hit_ratio[5]))
 testthat::expect_error(joint_diagnostic_grid(dplyr::bind_rows(x,x[1,]),letters[1:5],'p',30,5))
 testthat::expect_error(joint_diagnostic_grid(x,letters[1:3],'p',30,5))
 testthat::expect_error(joint_diagnostic_grid(x,letters[1:5],'p',30,0))
})
