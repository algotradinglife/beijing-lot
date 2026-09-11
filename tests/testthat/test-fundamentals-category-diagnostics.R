source(file.path('..','..','r','fundamentals_missed_issues.R'))
source(file.path('..','..','r','fundamentals_category_diagnostics.R'))
testthat::test_that('diagnosis separates complete cohort, unique supports and repeated holdings',{
 f<-tibble::tibble(issue=rep(c('001','002'),each=7),slot=rep(1:7,2),provider_id=sprintf('%03d',1:14),
  handicap=0,p_W=.6,p_D=.25,p_L=.15,q_W=.2,q_D=.3,q_L=.5)
 features<-f |> dplyr::transmute(issue,slot,provider_id,status='READY',competition='LEAGUE',cup=0,
  expected_total=2.5,market_total=2.5,giving_venue_ppg=0,home_venue_n=10,away_venue_n=10)
 legs<-f |> dplyr::mutate(group=1L,support=ifelse(slot<=2,'3','31'))
 legs<-dplyr::bind_rows(legs,dplyr::mutate(legs[1:7,],group=2L))
 audit<-f |> dplyr::transmute(issue,slot,provider_id,handicap,status='READY',actual_direction=ifelse(issue=='001' & slot==1,'L','W'))
 issues<-tibble::tibble(issue=c('001','002'),hits=c(0,1))
 z<-category_diagnostics(f,features,legs,audit,issues)
 testthat::expect_equal(as.integer(table(z$observations$view)),c(28L,21L,14L))
 testthat::expect_equal(sum(z$observations$one_away_blocker),2L)
 s<-z$summary |> dplyr::filter(view=='SELECTED_UNIQUE',slice=='ALL',role=='SINGLE',dimension=='conflict')
 testthat::expect_equal(s$n,4L);testthat::expect_equal(s$actual_percent,75)
 testthat::expect_equal(s$predicted_percent,60);testthat::expect_equal(s$stratum,'STRONG_DIFF')
 features$competition[1]<-NA_character_
 testthat::expect_true(any(category_diagnostics(f,features,legs,audit,issues)$summary$stratum=='MISSING'))
 testthat::expect_error(category_diagnostics(f,features[-1,],legs,audit,issues))
 testthat::expect_error(category_diagnostics(f,features,legs,audit[-1,],issues))
 bad<-f;bad$p_W[1]<-.7
 testthat::expect_error(category_diagnostics(bad,features,legs,audit,issues))
 testthat::expect_error(category_diagnostics(f,features,legs,audit,dplyr::mutate(issues,hits=1)))
})
