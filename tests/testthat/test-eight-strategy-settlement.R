source(testthat::test_path('..','..','r','eight_strategy_settlement.R'))
testthat::test_that('finality requires explicit completion or settlement publication',{
 f<-data.frame(issue='100101',slot=1,provider_id='358101')
 z<-data.frame(issue='100101',slot=1,native_match_id='358101',status='',
  source_url='https://cp.nowscore.com/beijingdanchang/rangqiushengpingfu/kaijiang_dc_5_100101.html')
 testthat::expect_equal(eight_strategy_completion_evidence(f,z)$completion_evidence,'OFFICIAL_KAIJIANG_PUBLICATION')
 z$status<-'下';testthat::expect_equal(eight_strategy_completion_evidence(f,z)$result_state,'未核实')
 z$status<-'';z$source_url<-'https://live.nowscore.com/'
 testthat::expect_equal(eight_strategy_completion_evidence(f,z)$result_state,'未核实')
 z$status<-'完场';testthat::expect_equal(eight_strategy_completion_evidence(f,z)$completion_evidence,'EXPLICIT_DB_COMPLETED')
 z$native_match_id<-'wrong';testthat::expect_equal(eight_strategy_completion_evidence(f,z)$result_state,'未核实')
 testthat::expect_equal(eight_strategy_completion_evidence(f,z[FALSE,])$result_state,'未核实')
 testthat::expect_error(eight_strategy_completion_evidence(rbind(f,f),z))
})
