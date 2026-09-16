for(f in c('strategy_diagnostic_probabilities','n7_fixture_price_diagnostic','n7_return_attribution',
 'n7_recent_structure','joint_phase_diagnostic'))source(file.path('..','..','r',paste0(f,'.R')))
testthat::test_that('phase diagnosis reconciles outcomes, duplicates and explicit scope', {
  f<-tidyr::crossing(issue=c('01','02'),slot=1:7) |> dplyr::mutate(provider_id=as.character(slot),
    handicap=0,p_W=.4,p_D=.3,p_L=.3,q_W=.4,q_D=.3,q_L=.3)
  a<-f |> dplyr::select(issue,slot,provider_id,handicap) |> dplyr::mutate(actual_direction='W',
    spf_sp=2.5,spf_source_sha256='verified',status='READY')
  a$actual_direction[14]<-'D'
  k<-tibble::tibble(issue=c('01','02'),sleeve_id='0',fixture_slots='1,2,3,4,5,6,7',
    actual_rank=c(1,2),actual_gross_cny=1.3*2.5^7,coverage_25_cost_cny=2,
    actual_cumulative=.3,model_expected_hit_cost_cny=200)
  g<-tibble::tibble(issue=c('01','02'),policy='JOINT',sleeve_id='0',depth=1,stake=2,
    coverage=.25,expected_gross=1)
  r<-tibble::tibble(issue=c('01','02'),policy='JOINT',stake=2,gross=c(1.3*2.5^7,0),
    net=gross-stake,hits=c(1,0),model_hit=.25)
  m<-tibble::tibble(issue=c('01','02'),period=1:2,stage=c('BEFORE','AFTER'))
  z<-joint_phase_diagnostic(r,g,f,a,k,m,'JOINT',1.3,256,2,.65,7)
  testthat::expect_equal(sum(z$phases$net),sum(r$net))
  testthat::expect_equal(z$phases$avg_stake,c(2,2))
  testthat::expect_equal(z$phases$profit_issues,c(0L,1L))
  testthat::expect_equal(z$top2_groups$actual_all_top2,c(1,1))
  testthat::expect_equal(z$top2_groups$model_all_top2,rep(.7^7,2))
  testthat::expect_equal(sum(z$groups$hits),1)
  testthat::expect_equal(z$supply$mean_qualified,c(7,7))
  testthat::expect_equal(z$exposure$max_uses,c(1,1))
  testthat::expect_equal(z$exposure$herfindahl,rep(1/7,2))
  testthat::expect_true(all(z$scores$top2==1))
  # Multiple periods in a phase must not reuse already-summarised stake/net.
  both<-r;both$stake<-c(2,4);both$gross<-1.3*2.5^7;both$net<-both$gross-both$stake;both$hits<-1
  km<-k;km$actual_rank<-1;am<-a;am$actual_direction<-'W';mm<-m;mm$stage<-'ALL'
  gm<-g;gm$stake<-c(2,4);gm$depth<-c(1,2)
  zz<-joint_phase_diagnostic(both,gm,f,am,km,mm,'JOINT',1.3,256,2,.65,7)
  testthat::expect_equal(zz$phases$avg_stake,3)
  testthat::expect_equal(zz$phases$profit_issues,2L)
  cash<-r;cash[2,c('stake','gross','net','hits','model_hit')]<-0
  zz<-joint_phase_diagnostic(cash,g[1,],f,a,k,m,'JOINT',1.3,256,2,.65,7)
  testthat::expect_true(is.na(zz$phases$roi[zz$phases$stage=='AFTER']))
  testthat::expect_error(joint_phase_diagnostic(r[-1,],g,f,a,k,m,'JOINT',1.3,256,2,.65,7))
  testthat::expect_error(joint_phase_diagnostic(r,g,f[-1,],a,k,m,'JOINT',1.3,256,2,.65,7))
  bad<-r;bad$net[1]<-bad$net[1]+1
  testthat::expect_error(joint_phase_diagnostic(bad,g,f,a,k,m,'JOINT',1.3,256,2,.65,7))
  bad<-r;bad$stake[1]<-3
  testthat::expect_error(joint_phase_diagnostic(bad,g,f,a,k,m,'JOINT',1.3,256,2,.65,7))
  testthat::expect_error(joint_phase_diagnostic(r,g,f,a,k,dplyr::bind_rows(m,m),'JOINT',1.3,256,2,.65,7))
})
