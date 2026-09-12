source('../../r/n7_capital_depth.R')
source('../../r/n7_capital_compare.R')

test_that('same-cost ranks cross without removing locally dominated sleeves',{
  p<-rbind(A=c(.6,.1,rep(.3/2185,2185)),B=c(.4,.35,rep(.25/2185,2185)))
  rank<-rbind(1:2187,1:2187);rownames(rank)<-rownames(p)
  surface<-list(prob_mat=p,value_mat=2.5*p,rank_idx=rank)
  cuts<-list('1'='2010-01-01T00:00:00Z')
  curves<-n7_capital_curves(surface,cuts,cuts,2)
  result<-n7_capital_compare(curves,c(1,2),c(.5,.7),1024,1e-12,cuts,cuts)
  x<-result$comparisons
  one<-x[x$mode=='top_n' & x$target==1,];two<-x[x$mode=='top_n' & x$target==2,]
  expect_equal(one$coverage_rank,c(1L,2L));expect_equal(two$coverage_rank,c(2L,1L))
  expect_equal(one$locally_dominated,c(FALSE,TRUE));expect_equal(two$locally_dominated,c(TRUE,FALSE))
  expect_equal(result$candidates_before,2);expect_equal(result$candidates_after,2)
  expect_equal(result$crossings$reversed_pairs,1);expect_equal(result$crossings$spearman,-1)
  expect_equal(one$full_probability_hhi[1],.6^2+.1^2+2185*(.3/2185)^2)
  tau<-x[x$mode=='coverage' & x$target==.5,]
  expect_equal(tau$n_tickets,c(1L,2L));expect_equal(tau$stake,c(2,4))
  limited<-n7_capital_compare(curves,1,.5,2,1e-12,cuts,cuts)
  expect_true(all(limited$comparisons$all_sleeves_status=='OVER_BUDGET'))
  expect_equal(limited$candidates_after,2)
  expect_error(n7_capital_compare(curves,1,NA,1024,1e-12,cuts,cuts))
})

test_that('registered model frontier and near ranges are descriptive and explicit',{
  a<-tibble::tibble(arm=c('A','B','C'),budget_cny=512,any_hit_percent=c(60,55,40),
    modeled_net_cny=c(-20,-30,10),sleeves_median=c(8,10,4),funded_trials=10L)
  x<-n7_capital_frontier(a,2,5)
  expect_equal(x$points$registered_frontier,c(TRUE,FALSE,TRUE))
  expect_equal(x$regions$near_hit_sleeves_min,8);expect_equal(x$regions$near_hit_sleeves_max,8)
  expect_equal(x$regions$near_net_sleeves_min,4)
  expect_error(n7_capital_frontier(a,-1,5))
  expect_error(n7_capital_frontier(dplyr::bind_rows(a,a),2,5))
})

test_that('unfunded diagnostic zeros cannot become the allocation optimum',{
  a<-tibble::tibble(arm=c('funded','infeasible'),budget_cny=512,
    any_hit_percent=c(40,0),modeled_net_cny=c(-100,0),
    sleeves_median=c(8,0),funded_trials=c(10L,0L))
  x<-n7_capital_frontier(a,2,5)
  expect_equal(x$points$registered_frontier,c(TRUE,FALSE))
  expect_equal(x$points$near_registered_net_max,c(TRUE,FALSE))
  expect_equal(x$regions$near_net_sleeves_min,8)
  expect_equal(x$regions$unfunded_policies,1)
  empty<-n7_capital_frontier(a[2,],2,5)
  expect_false(empty$points$frontier_eligible)
  expect_false(empty$points$registered_frontier)
  expect_equal(empty$regions$eligible_policies,0)
  expect_equal(empty$regions$near_net_policies,0)
  expect_true(is.na(empty$regions$near_net_sleeves_min))
  a$funded_trials[1]<-NA_integer_
  expect_error(n7_capital_frontier(a,2,5))
})
