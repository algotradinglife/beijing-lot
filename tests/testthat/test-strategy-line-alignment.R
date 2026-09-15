source(file.path('..','..','r','strategy_line_alignment.R'))

test_that('line signs, conditional denominator and model-invariant outcomes are explicit', {
  x <- tibble::tibble(issue='001',slot=1:4,provider_id=as.character(1:4),
    model='raw',stage='test',handicap=c(-2,-2,1,0),
    home_goals=c(2,3,0,0),away_goals=c(0,0,2,0),
    p_W=.48,p_D=.2,p_L=.32)
  y <- strategy_line_alignment(x,c(0,.5,1))
  expect_equal(y$fixtures$actual,c('D','W','L','D'))
  expect_equal(y$fixtures$conditional_W,rep(.6,4))
  expect_equal(sum(y$conditional$fixtures),2)
  expect_equal(sum(y$conditional$directional_hits),1)
  expect_equal(sum(y$classes$hits),4)
  expect_equal(sum(y$distances$fixtures),4)
  paired <- dplyr::bind_rows(x,dplyr::mutate(x,model='refresh',p_W=.36,p_D=.4,p_L=.24))
  yy <- strategy_line_alignment(paired,c(0,.5,1))
  expect_equal(yy$fixtures$conditional_W,rep(.6,8))
  expect_equal(sum(yy$distances$fixtures),4)
  paired$home_goals[5] <- 7
  expect_error(strategy_line_alignment(paired,c(0,1)))
  expect_error(strategy_line_alignment(dplyr::bind_rows(x,x),c(0,1)))
  expect_error(strategy_line_alignment(x[0,],c(0,1)))
  expect_error(strategy_line_alignment(x,c(0,.5,.5,1)))
  x$p_W[1]<-NA_real_;expect_error(strategy_line_alignment(x,c(0,1)))
})

test_that('all draws yield empty conditional diagnostics and ties abstain', {
  x <- tibble::tibble(issue='01',slot=1L,provider_id='1',model='raw',stage='test',
    handicap=0,home_goals=0,away_goals=0,p_W=.4,p_D=.2,p_L=.4)
  expect_equal(nrow(strategy_line_alignment(x,c(0,1))$conditional),0)
  x$home_goals<-1
  expect_equal(strategy_line_alignment(x,c(0,1))$conditional$directional_n,0)
  x$p_D<-.3;expect_error(strategy_line_alignment(x,c(0,1)))
})
