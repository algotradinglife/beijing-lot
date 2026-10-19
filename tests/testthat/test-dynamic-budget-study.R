test_that('budget grids preserve frozen cutoffs, physical stakes and selector receipts', {
 root<-Sys.getenv('BEIDAN_REPOSITORY_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 for(issue in c('26103','26104','26105')) {
  out<-file.path(root,'results/dynamic-budget-20261019',issue)
  manifest<-jsonlite::fromJSON(file.path(out,'selection-manifest.json'))
  expect_identical(manifest$sha256,digest::digest(file=file.path(out,'frozen-budget-selections.rds'),algo='sha256'))
  x<-readRDS(file.path(out,'frozen-budget-selections.rds'))
  source<-readRDS(file.path(root,'results/global-dynamic-walkforward-20261018',issue,'frozen-rounds.rds'))
  expect_false(x$target_labels_opened);expect_false(x$prospective_admission)
  expect_setequal(x$selections$tickets_per_group,c(50L,75L,100L,125L))
  expect_false(anyDuplicated(x$selections[c('index','model','tickets_per_group','group_id','ticket_id')])>0)
  for(key in names(x$receipts)) {
   pieces<-strsplit(key,'|',fixed=TRUE)[[1]];i<-as.integer(pieces[1]);mod<-pieces[2];n<-as.integer(pieces[3]);r<-x$receipts[[key]]
   expect_identical(r$cutoff,source$rounds[[as.character(i)]]$cutoff)
   expect_identical(r$input_hash,source$rounds[[as.character(i)]]$outputs[[mod]]$decision$input_hash)
   expect_equal(r$constants$tickets_per_group,n)
   p<-dplyr::filter(x$selections,index==i,model==mod,tickets_per_group==n)
   expect_equal(nrow(p),8*n);expect_equal(as.integer(table(p$group_id)),rep(n,8))
   expect_true(all(p$budget_cny==16*n))
   if(n==125)expect_equal(p[c('group_id','ticket_id')],dplyr::filter(source$rounds[[as.character(i)]]$outputs[[mod]]$selection$purchases,policy=='DYNAMIC_SET')[c('group_id','ticket_id')])
  }
 }
})

test_that('budget selector replays without target label metadata and fails on cutoff mutation', {
 root<-Sys.getenv('BEIDAN_REPOSITORY_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 original<-readRDS(file.path(root,'results/global-dynamic-walkforward-20261018/26104/frozen-rounds.rds'))
 frozen<-readRDS(file.path(root,'results/dynamic-budget-20261019/26104/frozen-budget-selections.rds'))
 d<-original$rounds[[1]]$outputs$GLOBAL$decision
 d$ignored_target_labels<-list('26104:1'='W')
 replay<-beidan:::SelectJointOutcomeTickets(d,50L,30L,2,3^12)
 actual<-dplyr::filter(replay$purchases,policy=='DYNAMIC_SET')
 expected<-dplyr::filter(frozen$selections,index==1,model=='GLOBAL',tickets_per_group==50)
 expect_equal(actual[c('group_id','ticket_id')],expected[c('group_id','ticket_id')])
 d$cutoff$cutoff_utc<-d$cutoff$cutoff_utc+1
 expect_error(beidan:::SelectJointOutcomeTickets(d,50L,30L,2,3^12))
})

test_that('budget evaluation keeps missing cash and reconciles physical copies', {
 root<-Sys.getenv('BEIDAN_REPOSITORY_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 for(issue in c('26103','26104','26105')) {
  out<-file.path(root,'results/dynamic-budget-20261019',issue)
  e<-jsonlite::fromJSON(file.path(out,'evaluation.json'))
  expect_true(e$baseline_2000_parity)
  expect_identical(e$rounds_sha256,digest::digest(file=file.path(out,'rounds.csv'),algo='sha256'))
  rows<-readr::read_csv(file.path(out,'rounds.csv'),show_col_types=FALSE)
  expect_true(all(rows$copies*2==rows$budget_cny))
  expect_true(all(is.na(rows$payout_cny[!rows$monetary_complete])))
  expect_equal(rows$net_cny[rows$monetary_complete],rows$payout_cny[rows$monetary_complete]-rows$budget_cny[rows$monetary_complete])
 }
})
