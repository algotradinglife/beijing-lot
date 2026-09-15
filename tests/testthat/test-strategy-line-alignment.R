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

test_that('numeric residuals, bin boundaries, Brier and tails match hand calculations', {
  x<-tibble::tibble(issue='01',slot=1:5,provider_id=as.character(1:5),model='raw',stage='test',
    handicap=c(-1,-1,1,0,0),home_goals=c(4,0,0,1,0),away_goals=c(0,3,1,0,1),
    p_W=c(.6,.2,.1,.3,.45),p_D=c(.2,.3,.2,.4,.1),p_L=c(.2,.5,.7,.3,.45))
  y<-strategy_line_alignment(x,c(0,.5,1))
  expect_equal(y$fixtures$direction_residual,c(.6,-.7,.6,1,-1))
  expect_equal(y$fixtures$line_distance,c(3,-4,0,1,-1))
  expect_equal(as.character(y$fixtures$conditional_bin),c('[0.5,1]','[0,0.5)','[0,0.5)','[0.5,1]','[0.5,1]'))
  c0<-y$classes |> dplyr::filter(handicap==0) |> dplyr::arrange(outcome)
  expect_equal(c0$outcome,c('D','L','W'))
  expect_equal(c0$predicted,c(.25,.375,.375))
  expect_equal(c0$observed,c(0,.5,.5))
  expect_equal(c0$gap,c(-.25,.125,.125))
  lo<-y$conditional |> dplyr::filter(handicap==-1,predicted<.5)
  hi<-y$conditional |> dplyr::filter(handicap==-1,predicted>.5)
  expect_equal(lo$gap,-2/7);expect_equal(lo$brier,4/49)
  expect_equal(hi$gap,.25);expect_equal(hi$brier,1/16)
  mid<-y$conditional |> dplyr::filter(handicap==0)
  expect_equal(mid$gap,0);expect_equal(mid$brier,.25)
  tails<-y$distances |> dplyr::filter(handicap==-1) |> dplyr::arrange(distance_band)
  expect_setequal(tails$distance_band,c('<=-3','>=3'))
  expect_equal(tails$observed,c(.5,.5));expect_equal(tails$fixtures,c(1L,1L))
})
