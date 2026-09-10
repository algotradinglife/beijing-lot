source(file.path('..','..','r','fundamentals_integration_weight.R'))
source(file.path('..','..','r','fundamentals_decision_chain.R'))

test_that('decision-chain tables retain cash, period ROI, drawdown and abstentions', {
  x <- tibble::tibble(partition='TEST8',issue=rep(c('001','002'),2),
    policy=rep(c('CURRENT','CONFLICT_SKIP'),each=2),stake=c(256,256,256,0),
    gross=c(512,0,512,0),net=gross-stake,hits=c(1,0,1,0),groups=c(1,1,1,0),
    status=c('COMPLETE','COMPLETE','COMPLETE','NO_BET'),candidates=14,
    conflict_candidates=7,skipped_candidates=c(0,0,7,14),selected_matches=7*groups,
    removed_current_matches=c(0,0,0,7),added_matches=0,unspent_vs_current_cny=c(0,0,0,256))
  legs <- tibble::tibble(partition='TEST8',issue=c('001','002','001','002'),
    policy=x$policy,slot=1L,provider_id='0001',conflict=TRUE,selected=c(TRUE,TRUE,TRUE,FALSE),
    current_hit=c(TRUE,FALSE,TRUE,FALSE),routed_hit=c(TRUE,FALSE,TRUE,NA),
    selected_hit=c(TRUE,FALSE,TRUE,NA))
  z <- decision_chain_tables(list(rows=x,legs=legs))
  current <- dplyr::filter(z$summary,policy=='CURRENT')
  skip <- dplyr::filter(z$summary,policy=='CONFLICT_SKIP')
  expect_equal(current$roi,0)
  expect_equal(current$max_drawdown_cny,256)
  expect_equal(skip$roi,1)
  expect_equal(skip$return_on_current_budget,.5)
  expect_equal(skip$unspent_vs_current_cny,256)
  expect_true(is.na(dplyr::filter(z$periods,policy=='CONFLICT_SKIP',issue=='002')$ROI_percent))
  expect_equal(dplyr::filter(z$accuracy,policy=='CONFLICT_SKIP')$routed_fixtures,1L)
  expect_equal(dplyr::filter(z$accuracy,policy=='CONFLICT_SKIP')$selected_hit_rate,1)
  expect_equal(z,decision_chain_tables(list(rows=x[4:1,],legs=legs)))
  bad <- x;bad$net[1] <- 0
  expect_error(decision_chain_tables(list(rows=bad,legs=legs)))
  expect_error(decision_chain_tables(list(rows=x,legs=dplyr::bind_rows(legs,legs))))
})
