source(file.path('..','..','r','fundamentals_integration_weight.R'))
source(file.path('..','..','r','fundamentals_compression_bridge.R'))

testthat::test_that('budget and stake denominators and paired tails remain distinct', {
 x <- tibble::tibble(partition='TEST',issue=c('100101','100102','100103'),policy='D1_OLD',depth=1,kind='OLD',status='COMPLETE',
  stake=128,cash_cny=128,budget_cny=256,gross=c(0,512,0),net=c(-128,384,-128),hits=c(0L,1L,0L),groups=1L,
  model_union=.5,fixture_hhi=1/7,repeat_units=0L)
 z <- dplyr::mutate(x,policy='C',kind='FACTORIAL',net=net+c(0,1000,100),gross=net+stake)
 s <- compression_bridge_summary(dplyr::bind_rows(x,z),100000)
 c <- s[s$policy=='C',]
 testthat::expect_equal(c$matched_lift,1100)
 testthat::expect_equal(c$ex_largest_lift,100)
 testthat::expect_equal(c$ex_largest_net,-156)
 testthat::expect_equal(c$budget_return,1228/768)
 testthat::expect_equal(c$roi,1228/384)
 testthat::expect_equal(c$cash_cny,384)
 testthat::expect_equal(c$ending_capital,101228)
 testthat::expect_true(is.na(c$worst_5_loss))
 testthat::expect_error(compression_bridge_summary(z,100000))
 testthat::expect_error(compression_bridge_summary(dplyr::bind_rows(x,x),100000))
 testthat::expect_error(compression_bridge_summary(dplyr::mutate(x,cash_cny=0),100000))
})

testthat::test_that('factor contrasts pair every issue and hold other factors fixed', {
 x <- tidyr::expand_grid(issue=c('100101','100102'),depth=1L,preserve_prefix=c(TRUE,FALSE),quality=c('TOP2','COMPRESSED'),overlap=c('STRICT','FREE'),cash_policy=c('HOLD','REPEAT_BEST')) |>
  dplyr::mutate(partition='ALL',kind='FACTORIAL',policy=paste(preserve_prefix,quality,overlap,cash_policy),
   net=ifelse(quality=='COMPRESSED',ifelse(issue=='100101',1000,10),0),stake=128,budget_cny=256,model_union=.5)
 z <- compression_bridge_contrasts(x)
 testthat::expect_equal(nrow(z$rows),64L)
 testthat::expect_equal(nrow(z$summary),32L)
 testthat::expect_true(all(z$summary$net_delta[z$summary$factor=='quality']==1010))
 testthat::expect_true(all(z$summary$ex_largest_delta[z$summary$factor=='quality']==10))
 testthat::expect_true(all(z$summary$net_delta[z$summary$factor!='quality']==0))
 testthat::expect_error(compression_bridge_contrasts(x[-1,]))
 testthat::expect_error(compression_bridge_contrasts(dplyr::bind_rows(x,x)))
 testthat::expect_error(compression_bridge_contrasts(dplyr::mutate(x,quality='BAD')))
})
