source('../../r/fundamentals_equity_curves.R')
source('../../r/fundamentals_complement.R')
testthat::test_that('descriptive complement accounting and downside correlations align by issue', {
  issue <- sprintf('%03d',1:12);main <- c(-10,20,-10,20,-10,20,-10,20,-10,20,-10,20)
  rows <- dplyr::bind_rows(
    tibble::tibble(issue=issue,policy='MAIN',alternative='A',main_budget_cny=1024,net=main),
    tibble::tibble(issue=issue,policy='ONLY_A',alternative='A',main_budget_cny=0,net=main),
    tibble::tibble(issue=issue,policy='ONLY_B',alternative='B',main_budget_cny=0,net=10-main),
    tibble::tibble(issue=issue,policy='MIX',alternative='B',main_budget_cny=512,net=rep(5,12))) |>
    dplyr::mutate(stake=100,gross=stake+net,budget_cny=1024,cash_cny=924,status='COMPLETE',groups=1,hits=as.integer(net>0),
      fixture_hhi=1/7,duplicate_ticket_units=0,max_fixture_uses=1,max_pair_overlap=0)
  z <- complement_summary(rows,'MAIN',issue,100000);s<-z$summary
  testthat::expect_equal(s$pearson[s$policy=='ONLY_B'],-1)
  testthat::expect_true(is.na(s$pearson[s$policy=='MIX']))
  testthat::expect_equal(s$source_pearson[s$policy=='MIX'],-1)
  testthat::expect_equal(s$net_cny,rep(60,4))
  testthat::expect_equal(s$max_drawdown_cny[s$policy=='MIX'],0)
  testthat::expect_equal(s$drawdown_reduction_cny[s$policy=='MIX'],10)
  testthat::expect_equal(s$profit_retained_percent,rep(100,4))
  testthat::expect_equal(s$spend_retained_percent,rep(100,4))
  testthat::expect_equal(s$net_when_main_loses[s$policy=='ONLY_B'],120)
  testthat::expect_equal(s$common_loss_percent[s$policy=='ONLY_B'],0)
  testthat::expect_equal(s$ex_best_net[s$policy=='MIX'],55)
  testthat::expect_equal(s$ex_best_lift[s$policy=='MIX'],-15)
  testthat::expect_equal(s$budget_ROI_percent,rep(100*60/(12*1024),4))
  testthat::expect_equal(complement_summary(rows[nrow(rows):1,],'MAIN',issue,100000)$summary,s)
  testthat::expect_error(complement_summary(rows,'missing',issue,100000))
  testthat::expect_error(complement_summary(dplyr::bind_rows(rows,rows[1,]),'MAIN',issue,100000))
  testthat::expect_error(complement_summary(rows,'MAIN',rev(issue)[-1],100000))
})
