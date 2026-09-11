source(testthat::test_path('..','..','r','fundamentals_double_failure.R'))
testthat::test_that('miss attribution separates oracle repair and no-bet',{
 legs<-tibble::tibble(issue=rep(sprintf('%02d',1:5),each=7),policy='P',group=1L,
  slot=rep(1:7,5),role=rep(c('A','A','D','D','D','D','C'),5),hit=TRUE)
 legs$hit[c(1,10,15,17)]<-FALSE
 rows<-tibble::tibble(issue=sprintf('%02d',1:6),policy='P',groups=c(rep(1L,5),0L),
  hits=c(0L,0L,0L,1L,1L,0L),status=c(rep('COMPLETE',5),'NO_BET'))
 z<-double_failure_summary(rows,legs)
 testthat::expect_equal(z$summary$missed_active,3)
 testthat::expect_equal(z$summary$no_bet,1)
 testthat::expect_equal(z$summary$repair_singles,1)
 testthat::expect_equal(z$summary$repair_doubles,1)
 testthat::expect_equal(z$summary$both_required_issues,1)
 testthat::expect_equal(z$summary$one_single_away,1)
 testthat::expect_equal(z$summary$one_double_away,1)
 # Different groups in one issue can support either oracle repair, not double-counted categories.
 legs2<-legs[legs$issue %in% c('01','02'),];legs2$group<-as.integer(legs2$issue);legs2$issue<-'01'
 rows2<-rows[1,];rows2$groups<-2L
 z2<-double_failure_summary(rows2,legs2)
 testthat::expect_equal(z2$summary$either_issues,1)
 testthat::expect_equal(z2$summary$repair_singles,1)
 testthat::expect_equal(z2$summary$repair_doubles,1)
 testthat::expect_error(double_failure_summary(rows,rbind(legs,legs[1,])))
 bad<-rows;bad$hits[1]<-1L
 testthat::expect_error(double_failure_summary(bad,legs))
 testthat::expect_error(double_failure_summary(rows,legs[-1,]))
 legs$hit<-TRUE;rows$hits<-rows$groups
 z<-double_failure_summary(rows,legs)
 testthat::expect_equal(z$summary$missed_active,0)
 testthat::expect_equal(z$summary$repair_singles,0)
 testthat::expect_equal(nrow(z$per_issue),0)
})
