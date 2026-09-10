source(file.path('..','..','r','fundamentals_integration_weight.R'))
source(file.path('..','..','r','fundamentals_compression_bridge.R'))
source(file.path('..','..','r','fundamentals_repeated_double.R'))

testthat::test_that('paired cases reuse risk summaries without mixing baselines', {
 x <- tidyr::expand_grid(case=c('A','B'),issue=c('100101','100102'),action=c('BASE','ADJUSTED')) |>
  dplyr::mutate(partition='TEST',policy=paste(case,action),depth=1L,kind=ifelse(action=='BASE','OLD','ADJUSTED'),status='COMPLETE',
   stake=128,cash_cny=128,budget_cny=256,groups=1L,hits=as.integer(issue=='100101'),gross=ifelse(issue=='100101',500,0),
   gross=gross+ifelse(action=='ADJUSTED' & issue=='100101',ifelse(case=='A',100,200),0),net=gross-stake,
   model_union=.5,fixture_hhi=1/7,repeat_units=0L,quality='TOP2',overlap='STRICT',
   changed_legs=as.integer(action=='ADJUSTED'),gained_groups=0L,lost_groups=0L,mean_group_probability=.1)
 s <- repeated_double_summary(x,100000)
 testthat::expect_equal(nrow(s),4L)
 testthat::expect_equal(sort(s$matched_lift[s$action=='ADJUSTED']),c(100,200))
 testthat::expect_true(all(s$ex_largest_lift==0))
 testthat::expect_true(all(s$budget_cny==512))
 testthat::expect_true(all(s$changed_legs[s$action=='ADJUSTED']==2))
 testthat::expect_error(repeated_double_summary(x[-1,],100000))
 testthat::expect_error(repeated_double_summary(dplyr::bind_rows(x,x),100000))
 bad <- x;bad$stake[1] <- 64
 testthat::expect_error(repeated_double_summary(bad,100000))
 bad <- x;bad$groups[1] <- 2L
 testthat::expect_error(repeated_double_summary(bad,100000))
 testthat::expect_error(repeated_double_summary(dplyr::mutate(x,action='UNKNOWN'),100000))
})
