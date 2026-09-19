for(n in c('fundamentals_equity_curves','n7_purchase_accounting','legacy_strategy_comparison',
 'eight_strategy_validation','eight_strategy_detail_audit','n7_purchase_cohort_audit'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('independent detail replay covers funding stops and numerical corruption',{
 ids<-c('100101','100102','100103','100104')
 x<-data.frame(issue=rep(ids,2),policy=rep(c('JOINT','OTHER'),each=4),
  stake=600,gross=c(0,0,1800,0,1200,0,0,1800),model='test',budget_cny=1024,
  status='COMPLETE',stage=rep(c('A','A','B','B'),2))
 x$net<-x$gross-x$stake;x$hits<-as.numeric(x$gross>0);x$cash_cny<-1024-x$stake
 result<-legacy_strategy_comparison(x,ids,c('A','B'),'JOINT',1000)
 tails<-eight_strategy_tail_diagnostics(result$curves,c(1,3,5))
 result$trimmed<-tails$trimmed;result$streaks<-tails$streaks
 scopes<-list(ALL=ids,A=ids[1:2],B=ids[3:4])
 testthat::expect_true(eight_strategy_detail_audit(x,scopes,result,1000,'JOINT'))
 summary<-result$summary[result$summary$evaluation=='ALL',]
 other<-summary;other$evaluation<-'ADDITIONAL';summary<-rbind(summary,other)
 path<-tempfile(fileext='.csv');readr::write_csv(summary,path)
 inferred<-readr::read_csv(path,show_col_types=FALSE)
 typed<-readr::read_csv(path,col_types=readr::cols(funding_stop_issue='c'),show_col_types=FALSE)
 testthat::expect_error(n7_purchase_cohort_audit(x,inferred,ids,character(),c('JOINT','OTHER'),1024,1000))
 testthat::expect_s3_class(n7_purchase_cohort_audit(x,typed,ids,character(),c('JOINT','OTHER'),1024,1000),'data.frame')
 unlink(path)
 for(field in c('issue','stopped','stop_started','funding_stop_issue')) {
  broken<-result
  if(field %in% c('issue','funding_stop_issue'))broken$curves[[field]][2]<-'999999' else
   broken$curves[[field]][2]<-!broken$curves[[field]][2]
  testthat::expect_error(eight_strategy_detail_audit(x,scopes,broken,1000,'JOINT'))
 }
 for(n in c('curves','trimmed','streaks','complementarity','paired')) {
  broken<-result
  field<-switch(n,curves='equity_cny',trimmed='net_cny',streaks='longest_no_hit_bet_run',
   complementarity='unique_hit',paired='net_change_cny')
  broken[[n]][[field]][1]<-broken[[n]][[field]][1]+1
  testthat::expect_error(eight_strategy_detail_audit(x,scopes,broken,1000,'JOINT'))
  broken<-result;broken[[n]]<-broken[[n]][broken[[n]]$evaluation!='ALL',]
  testthat::expect_error(eight_strategy_detail_audit(x,scopes,broken,1000,'JOINT'))
 }
})
