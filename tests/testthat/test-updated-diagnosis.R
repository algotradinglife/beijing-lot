source('../../r/fundamentals_updated_diagnosis.R')

testthat::test_that('diagnosis reconciles roles, unique supports and payout', {
  f<-tibble::tibble(cohort='new100',issue='001',slot=1:5,provider_id=as.character(1:5),
    handicap=0,home='H',away='A',competition='League',actual='W',spf_sp=2,
    p_W=.6,p_D=.25,p_L=.15,q_W=.65,q_D=.2,q_L=.15)
  l<-tibble::tibble(cohort='new100',issue='001',policy='N5',group=1,slot=1:5,
    provider_id=as.character(1:5),role=c('A','A','D','D','C'),support=c('3','3','31','31','30'),hit=1)
  i<-tibble::tibble(cohort='new100',issue='001',policy='N5',stake=16,gross=41.6,net=25.6,groups=1,hits=1,status='COMPLETE')
  v<-updated_scope_diagnosis(f,l,i)
  testthat::expect_equal(v$payout$ROI_percent,160)
  testthat::expect_equal(v$payout$group_hit_percent,100)
  testthat::expect_equal(v$groups$n,5L)
  testthat::expect_equal(v$available$market_top1_hit,100)
  testthat::expect_equal(v$pools$anchors,5L)
  testthat::expect_error(updated_scope_diagnosis(dplyr::bind_rows(f,f),l,i))
  testthat::expect_error(updated_scope_diagnosis(f,dplyr::bind_rows(l,l),i))
  testthat::expect_error(updated_scope_diagnosis(f,l,dplyr::mutate(i,hits=0)))
  testthat::expect_error(updated_scope_diagnosis(dplyr::mutate(f,p_W=.9),l,i))
  f$actual[1]<-'L';l$hit[1]<-0;i$gross<-0;i$net<- -16;i$hits<-0
  f$spf_sp[1]<-NA_real_
  v<-updated_scope_diagnosis(f,l,i)
  testthat::expect_equal(v$failures$cause,'SINGLES_ONLY')
  testthat::expect_equal(v$failures$one_away,1L)
  f$actual[1]<-'W';l$hit[1]<-1
  testthat::expect_error(updated_scope_diagnosis(f,l,i))
})
