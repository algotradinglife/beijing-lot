for(n in c('n7_probability_replay','n7_sleeve_tables','n7_joint_sleeves','third_outcome_tickets'))
 source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('frozen ticket preferences retain true mass, cost, identity and legality', {
 py<-Sys.getenv('RETICULATE_PYTHON');reticulate::use_python(py,required=TRUE)
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',
  expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),
  origin='QUALITY',enumeration=e,options=list())))
 f<-dplyr::bind_rows(e$fixtures) |> dplyr::mutate(new_W=.5,new_D=.3,new_L=.2)
 b<-n7_probability_bundle(b,f,b$cutoffs,'test')
 v<-n7_sleeve_tables(b,b$cutoffs,'test');fund<-tibble::tibble(sleeve_id='0',depth=64L)
 rules<-tibble::tibble(id=c('ORIGINAL','DISCOUNT50','CAP15','HARD'),kind=c('discount','discount','cap','hard'),value=c(1,.5,.15,0))
 p<-third_outcome_ticket_plan(b$expanded_pool$fixtures,v,fund,b$cutoffs,py,rules,2,.65,1024)
 testthat::expect_identical(p$options[[1]]$state_ids,as.integer(v$rank_idx[1,1:64]))
 testthat::expect_equal(p$options[[2]]$selection_weight[1094],.4^7)
 testthat::expect_equal(p$options[[3]]$selection_weight[1094],.35^7)
 testthat::expect_equal(p$options[[2]]$probability[1094],.3^7)
 testthat::expect_equal(vapply(p$options,`[[`,numeric(1),'stake'),rep(128,4))
 testthat::expect_equal(length(p$options[[4]]$purchase_order),128)
 testthat::expect_true(all(p$options[[4]]$third_count[p$options[[4]]$state_ids]==0))
 testthat::expect_lte(p$options[[4]]$coverage,.8^7+1e-12)
 testthat::expect_lte(p$options[[2]]$coverage,p$options[[1]]$coverage+1e-12)
 labs<-dplyr::bind_rows(b$expanded_pool$fixtures) |>
  dplyr::select(issue,slot,provider_id,handicap) |> dplyr::mutate(actual_direction='L',spf_sp=2)
 z<-third_outcome_ticket_settle(p,labs)
 testthat::expect_true(is.na(z$actual_rank[4]))
 testthat::expect_false(z$hit[4])
 testthat::expect_equal(z$actual_gross,rep(1.3*2^7,4))
 changed<-labs;changed$actual_direction<-'W'
 zz<-third_outcome_ticket_settle(p,changed)
 testthat::expect_true(all(zz$hit))
 testthat::expect_identical(p$seal,digest::digest(p[names(p)!='seal'],algo='sha256'))
 changed$provider_id[1]<-'bad'
 testthat::expect_error(third_outcome_ticket_settle(p,changed))
 extra<-labs[1,];extra$provider_id<-'other'
 testthat::expect_error(third_outcome_ticket_settle(p,dplyr::bind_rows(labs,extra)))
 testthat::expect_error(third_outcome_ticket_settle(p,dplyr::bind_rows(extra,labs)))
 bad<-p;bad$options[[1]]$stake<-2
 testthat::expect_error(third_outcome_ticket_settle(bad,labs))
 testthat::expect_error(third_outcome_ticket_plan(b$expanded_pool$fixtures,v,fund,list(),py,rules,2,.65,1024))
 bad<-b$expanded_pool$fixtures;bad[[1]]$actual_direction<-'W'
 testthat::expect_error(third_outcome_ticket_plan(bad,v,fund,b$cutoffs,py,rules,2,.65,1024))
 testthat::expect_error(third_outcome_ticket_plan(b$expanded_pool$fixtures,v,dplyr::bind_rows(fund,fund),b$cutoffs,py,rules,2,.65,1024))
 empty<-third_outcome_ticket_plan(b$expanded_pool$fixtures,v,fund[0,],b$cutoffs,py,rules,2,.65,1024)
 testthat::expect_length(empty$options,0)
 testthat::expect_equal(nrow(third_outcome_ticket_settle(empty,labs)),0)
 testthat::expect_identical(names(third_outcome_ticket_settle(empty,labs)),names(z))
 testthat::expect_identical(names(empty$members),names(p$members))
 bad_rules<-rules;bad_rules$value[1]<-1.1
 testthat::expect_error(third_outcome_ticket_plan(b$expanded_pool$fixtures,v,fund,b$cutoffs,py,bad_rules,2,.65,1024))
 testthat::expect_error(third_outcome_ticket_plan(b$expanded_pool$fixtures,v,fund,b$cutoffs,py,rules,2,.65,2))
 f2<-dplyr::bind_rows(b$expanded_pool$fixtures) |> dplyr::mutate(new_W=.45,new_D=.35,new_L=.2)
 b2<-n7_probability_bundle(b,f2,b$cutoffs,'second-becomes-largest')
 v2<-n7_sleeve_tables(b2,b2$cutoffs,'second-becomes-largest')
 zero<-third_outcome_ticket_plan(b2$expanded_pool$fixtures,v2,fund,b2$cutoffs,py,
  tibble::tibble(id='ZERO',kind='discount',value=0),2,.65,1024)
 testthat::expect_equal(zero$options[[1]]$selection_weight[1094],.55^7)
 testthat::expect_equal(zero$options[[1]]$state_ids[1],1094L)
 testthat::expect_true(all(zero$members$third=='L'))
})
