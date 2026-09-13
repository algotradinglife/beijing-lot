source(file.path('..','..','r','n7_sleeve_tables.R'))
source(file.path('..','..','r','n7_joint_sleeves.R'))
source(file.path('..','..','r','n7_capital_portfolio.R'))

test_that('capital plans preserve permuted physical identity and monetary exposure',{
 cut<-list(x='epoch')
 # Canonical state 730 (one-based) is 1,0,0,0,0,0,0; place its first
 # coordinate at fixture 7, which moves to the final settlement column.
 o<-list(sleeve_id=0,rule='PROB_PREFIX',depth=2,fixtures=c(7,1:6),
   state_ids=c(730,1),stake=4,coverage=.4,expected_gross=5)
 pool<-list(issue='100101',model_id='test',fixtures=as.list(1:8),options=list(o),cutoffs=cut)
 sc<-list(hits=matrix(c(1,0),2,1),gross=matrix(c(12,0),2,1),cutoffs=cut)
 plan<-n7_capital_plan(pool,1,cut,'TEST',1,sc,sc,'CONTROL',list(),512,2,.65)
 expect_equal(plan$fixture_indices,matrix(rep(0:6,each=2),ncol=7))
 expect_equal(as.numeric(plan$outcomes[1,]),c(rep(0,6),1))
 expect_equal(as.numeric(plan$outcomes[2,]),rep(0,7))
 expect_equal(plan$sleeve_keys[[1]]$state_ids,as.list(c(729,0)))
 expect_equal(plan$groups,2);expect_equal(plan$funded_sleeves,1)
 expect_equal(plan$cash_cny,508)
 expect_equal(unlist(plan$fixture_exposure_cny),c(rep(4,7),0))
 expect_equal(plan$fixture_outcome_exposure_cny[7,],c(2,2,0))
 expect_equal(plan$max_reuse,1);expect_equal(plan$max_overlap,0)
 empty<-n7_capital_plan(pool,integer(),cut,'CASH',1,sc,sc,'Infeasible',list(),512,2,.65)
 expect_equal(empty$groups,0);expect_equal(empty$cash_cny,512)
 expect_equal(empty$max_outcome_exposure_cny,0)
 broken<-pool;broken$options[[1]]$state_ids<-c(1,1)
 expect_error(n7_capital_plan(broken,1,cut,'BAD',1,sc,sc,'CONTROL',list(),512,2,.65))
 duplicate<-pool;duplicate$options[[2]]<-o;duplicate$options[[2]]$sleeve_id<-1
 doubled<-list(hits=cbind(sc$hits,sc$hits),gross=cbind(sc$gross,sc$gross),cutoffs=cut)
 expect_error(n7_capital_plan(duplicate,1:2,cut,'BAD',1,doubled,doubled,'CONTROL',list(),512,2,.65))
})

test_that('prefix options reuse frozen canonical states and reject permuted duplicate sets',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 p<-unlist(e$probability);v<-unlist(e$expected_contribution)
 g<-list(id=0L,fixture_indices=as.list(0:6),origin='TEST',enumeration=e,
   options=list(PROB=list(status='COMPLETE',state_ids=as.list(order(-p,-v)[1:64]-1L))))
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='fixture',
   expanded_pool=list(fixtures=e$fixtures),sleeves=list(g))
 python<-Sys.getenv('FUNDAMENTALS_PYTHON');expect_true(nzchar(python))
 pool<-n7_capital_options(b,b$cutoffs,python,'fixed',c(1,2,64),2,.65)
 expect_equal(vapply(pool$options,`[[`,numeric(1),'depth'),c(1,2,64))
 expect_true(all(pool$options[[1]]$state_ids %in% pool$options[[3]]$state_ids))
 expect_equal(pool$options[[3]]$expected_gross,sum(v[pool$options[[3]]$state_ids]))
 expect_error(n7_capital_options(b,b$cutoffs,python,'fixed',c(1,1),2,.65))
 b$sleeves[[2]]<-g
 expect_error(n7_capital_options(b,b$cutoffs,python,'fixed',1,2,.65))
})

test_that('finite-space MILP agrees with exhaustive allocations including two hits',{
 cut<-list(x='epoch');hits<-cbind(c(1,0,0,0),c(1,1,0,0),c(0,0,1,0),c(0,0,1,1),c(1,0,0,0),c(1,0,0,1))
 opts<-lapply(1:6,function(j)list(sleeve_id=ceiling(j/2),stake=if(j%%2)2 else 4,
   expected_gross=if(j%%2)3 else 5,coverage=mean(hits[,j]),fixtures=(j+0:6)))
 pool<-list(options=opts,cutoffs=cut);sc<-list(hits=hits,gross=hits*12,cutoffs=cut)
 grid<-expand.grid(a=0:2,b=0:2,c=0:2)
 candidates<-lapply(seq_len(nrow(grid)),function(i){v<-unlist(grid[i,]);which(v>0)*2-2+v[v>0]})
 candidates<-Filter(function(ix)sum(vapply(opts[ix],`[[`,numeric(1),'stake'))==6,candidates)
 for(objective in c('any_hit','at_least_two','expected_net','row_coverage')) {
   oracle<-max(vapply(candidates,function(ix){nh<-rowSums(hits[,ix,drop=FALSE]);switch(objective,
     any_hit=mean(nh>=1),at_least_two=mean(nh>=2),expected_net=sum(vapply(opts[ix],function(o)o$expected_gross-o$stake,numeric(1))),
     row_coverage=sum(vapply(opts[ix],`[[`,numeric(1),'coverage')))},numeric(1)))
   fit<-n7_capital_solve(pool,sc,cut,6,objective,-1,0,TRUE,1000,0,0,60)
   expect_equal(fit$status,'OPTIMAL_WITHIN_TOLERANCE')
   val<-n7_capital_evaluate(pool,fit$selected,sc,cut,6)
   got<-switch(objective,any_hit=val$any_hit,at_least_two=val$at_least_two,expected_net=val$expected_net,
     row_coverage=sum(vapply(opts[fit$selected],`[[`,numeric(1),'coverage')))
   expect_equal(got,oracle)
 }
 empty<-n7_capital_evaluate(pool,integer(),sc,cut,6)
 expect_equal(empty$cash,6);expect_equal(empty$zero_net_probability,1);expect_true(is.na(empty$payoff_ratio))
 expect_true(is.na(empty$coverage_mean));expect_error(n7_capital_evaluate(pool,c(1,2),sc,cut,6))
 selected<-n7_capital_evaluate(pool,c(1,4),sc,cut,6)
 expect_equal(selected$coverage_mean,.375);expect_equal(selected$coverage_weighted_mean,(.25*2+.5*4)/6)
 expect_equal(selected$payoff_ratio,1)
 no<-n7_capital_solve(pool,sc,cut,2,'any_hit',100,0,TRUE,1000,0,0,60)
 expect_length(no$selected,0);expect_false(no$status %in% c('OPTIMAL_WITHIN_TOLERANCE','FEASIBLE_NOT_PROVEN'))
 expect_equal(no$status,'Infeasible')
 expect_error(n7_capital_solve(pool,sc,cut,3,'any_hit',-1,0,TRUE,1000,0,0,60))
})

test_that('explicit required options consume budget and cannot be silently dropped',{
 cut<-list(x='epoch')
 opts<-lapply(0:1,function(i)list(sleeve_id=i,stake=2,expected_gross=1,coverage=if(i==0)1 else .5))
 pool<-list(cutoffs=cut,options=opts)
 sc<-list(cutoffs=cut,hits=matrix(c(1,1,1,0),2,2),gross=matrix(0,2,2))
 fit<-n7_capital_solve(pool,sc,cut,2,'any_hit',-1,0,TRUE,100,.001,1,5,required_options=2L)
 expect_equal(fit$selected,2L)
 fit<-n7_capital_solve(pool,sc,cut,2,'any_hit',-1,0,TRUE,100,.001,1,5,required_options=1:2)
 expect_length(fit$selected,0)
 expect_error(n7_capital_solve(pool,sc,cut,2,'any_hit',-1,0,TRUE,100,.001,1,5,required_options=3L))
})
