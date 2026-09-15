source('../../r/n7_quality_settlement.R')
testthat::test_that('an entirely unfunded factorial arm retains every issue and all cash', {
 rows<-tibble::tibble(issue=c('01','02'),arm='NEW_RULE',seed=42501,
  stake=0,budget_cny=1024,cash=1024,groups=0)
 funded<-tibble::tibble(issue=character(),arm=character(),seed=numeric(),sleeve_id=character(),
  depth=numeric(),stake=numeric(),copies=numeric())
 ranks<-tibble::tibble(issue=c('01','02'),sleeve_id='0',actual_rank=1,actual_gross_cny=100)
 z<-n7_quality_settlement(rows,funded,ranks)
 testthat::expect_equal(z$rows$gross,c(0,0))
 testthat::expect_equal(z$rows$net,c(0,0))
 testthat::expect_equal(z$rows$cash,c(1024,1024))
 testthat::expect_equal(nrow(z$groups),0)
})
