source('../../r/fundamentals_integration_weight.R')
source('../../r/fundamentals_compression_bridge.R')
source('../../r/fundamentals_repeated_double.R')
source('../../r/fundamentals_expanded_comparison.R')

testthat::test_that('expanded-data comparisons preserve matched budgets and cash periods', {
 x <- expand.grid(issue=c('100402','100403'),rule=c('BASE','TV20'),stringsAsFactors=FALSE) |>
  dplyr::mutate(case='D2_TOP2_STRICT',policy=paste(case,rule,sep='_'),depth=2L,quality='TOP2',overlap='STRICT',
   status='COMPLETE',stake=64,cash_cny=960,budget_cny=1024,gross=c(100,0,120,0),net=gross-stake,roi=net/stake,
   hits=as.integer(gross>0),groups=1L,model_union=.2,fixture_hhi=1/7,repeat_units=0L,changed_legs=as.integer(rule!='BASE'),
   gained_groups=0L,lost_groups=0L,mean_group_probability=.2)
 y <- x;y$gross <- y$gross+10;y$net <- y$gross-y$stake;y$roi <- y$net/y$stake
 z <- expanded_variant_comparison(x,y,100000)
 testthat::expect_equal(nrow(z$summary),2)
 testthat::expect_equal(z$summary$net_change,c(20,20))
 testthat::expect_equal(z$summary$budget_cny,c(2048,2048))
 testthat::expect_equal(nrow(z$periods),4)
 testthat::expect_equal(length(z$common_issues),2)
 cash <- x;take <- cash$issue=='100403'
 cash$status[take] <- 'NO_BET';cash$stake[take] <- cash$gross[take] <- cash$net[take] <- cash$groups[take] <- cash$hits[take] <- 0
 cash$cash_cny[take] <- 1024;cash$roi[take] <- NA_real_
 a <- expanded_variant_comparison(cash,y,100000)
 testthat::expect_equal(a$summary$before_stake_cny,c(64,64))
 testthat::expect_equal(a$summary$stake_cny,c(128,128))
 testthat::expect_equal(sum(a$scope$no_bet),2)
 bad <- y;bad$net[1] <- NA_real_
 testthat::expect_error(expanded_variant_comparison(x,bad,100000))
 bad$status[1] <- 'PENDING_AUDIT_OR_WINNING_SP'
 p <- expanded_variant_comparison(x,bad,100000)
 testthat::expect_equal(p$common_issues,'100403')
 testthat::expect_equal(nrow(p$periods),4)
 testthat::expect_true(anyNA(p$periods$net_change))
 testthat::expect_error(expanded_variant_comparison(x,y[-1,],100000))
 testthat::expect_error(expanded_variant_comparison(x,dplyr::bind_rows(y,y[1,]),100000))
 bad <- y;bad$budget_cny <- 2048;bad$cash_cny <- 1984
 testthat::expect_error(expanded_variant_comparison(x,bad,100000))
 bad <- y;bad$status <- 'PENDING'
 testthat::expect_error(expanded_variant_comparison(x,bad,100000),'No jointly complete')
})
