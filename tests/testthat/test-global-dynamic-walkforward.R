test_that('walk-forward commands reject invalid modes before opening inputs', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 for(command in c('global_dynamic_walkforward_20261018.R','global_dynamic_select_20261018.R','global_dynamic_evaluate_20261018.R')) {
  log<-tempfile()
  status<-suppressWarnings(system2(file.path(R.home('bin'),'Rscript'),shQuote(c(file.path(root,'r',command),root,'invalid')),stdout=log,stderr=log))
  expect_equal(status,1L)
  expect_match(paste(readLines(log),collapse='\n'),'not TRUE')
 }
})


test_that('actual common-epoch pool and cyclic-group expressions keep seven unique legs', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 nodes<-as.list(parse(file=file.path(root,'r/global_dynamic_select_20261018.R')))
 scope<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('<-'))&&identical(n[[2]],as.name('scope')),nodes)[[1]]
 partitions<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('<-'))&&identical(n[[2]],as.name('partitions')),nodes)[[1]]
 outer<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('for'))&&identical(n[[2]],as.name('i')),nodes)[[1]]
 loop<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('for'))&&identical(n[[2]],as.name('g')),as.list(outer[[4]])[-1])[[1]]
 e<-new.env(parent=asNamespace('dplyr'));e$p<-list(maximum_pool=14L,minimum_pool=8L,groups=8L,legs=7L,rotation_step=1L)
 e$x<-list(audit=tibble::tibble(fixture_id=paste0('26103:',1:30),slot=1:30,state='ESTIMATED_FULL100',
  cutoff_utc=as.POSIXct('2026-10-08 00:00:00',tz='UTC')+c(rep(0,23),rep(3600,7))))
 e$fixtures<-e$x$audit |> dplyr::transmute(fixture_id,kickoff_at=cutoff_utc+86400)
 eval(scope,e);eval(partitions,e)
 expect_identical(e$partitions$n,c(14L,9L,7L));expect_identical(e$partitions$eligible,c(TRUE,TRUE,FALSE))
 for(size in 8:14) {
  e$ids<-paste0('26103:',seq_len(size));e$gl<-list();eval(loop,e)
  groups<-dplyr::bind_rows(e$gl)
  expect_equal(nrow(groups),56L)
  expect_equal(as.integer(table(groups$group_id)),rep(7L,8))
  expect_false(anyDuplicated(groups[c('group_id','fixture_id')])>0L)
  signatures<-vapply(e$gl,function(x)paste(x$fixture_id,collapse='|'),character(1))
  expect_equal(length(unique(signatures)),8L)
  expect_setequal(groups$fixture_id,e$ids)
 }
})

test_that('actual evaluator preserves pending hits and settlement column order', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 nodes<-as.list(parse(file=file.path(root,'r/global_dynamic_evaluate_20261018.R')))
 zloop<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('for'))&&identical(n[[2]],as.name('z')),nodes)[[1]]
 model_body<-as.list(zloop[[4]][[4]])[-1]
 policy_loop<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('for'))&&identical(n[[2]],as.name('policy')),model_body)[[1]]
 body<-as.list(policy_loop[[4]])[-1]
 cash<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('<-'))&&identical(n[[2]],as.name('cash')),body)[[1]]
 # cash <- parlay_settle_plan(...)$ticket_returns
 call<-cash[[3]][[2]]
 e<-new.env(parent=asNamespace('dplyr'))
 e$settlement<-list(settlements=tibble::tibble(source_url='fixture',status='settled',label_available_at=as.POSIXct('2026-10-20',tz='UTC'),settled_sp=2,outcome='W',fixture_id='009:1',issue_id='009'))
 table<-eval(call[[3]],e)
 expect_identical(names(table),c('issue_id','fixture_id','outcome','settled_sp','label_available_at','status','source_url'))
 expect_silent(beidan:::match_validate_table(table,'settlements'))
 row<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('<-'))&&is.call(n[[2]])&&identical(n[[2]][[2]],as.name('rows')),body)[[1]][[3]]
 e$gs<-tibble::tibble(hit=FALSE,pending=TRUE);expect_true(is.na(eval(row[['any_hit']],e)))
 e$gs<-tibble::tibble(hit=FALSE,pending=FALSE);expect_false(eval(row[['any_hit']],e))
 e$gs<-tibble::tibble(hit=TRUE,pending=TRUE);expect_true(eval(row[['any_hit']],e))
})

test_that('rejected actual evaluation publication leaves accepted artifact bytes intact', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 nodes<-as.list(parse(file=file.path(root,'r/global_dynamic_evaluate_20261018.R')))
 guard<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('tryCatch')),nodes)[[1]]
 branches<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('if')),as.list(guard[[2]])[-1])
 publish<-tail(branches,1)[[1]]
 out<-tempfile();dir.create(out);withr::defer(unlink(out,recursive=TRUE))
 destination<-file.path(out,'evaluation');stage<-file.path(out,'stage');dir.create(destination);dir.create(stage)
 writeLines('accepted',file.path(destination,'metrics.csv'));writeLines('rejected',file.path(stage,'metrics.csv'))
 before<-readBin(file.path(destination,'metrics.csv'),'raw',100)
 e<-new.env(parent=baseenv());e$out<-out;e$stage<-stage;e$destination<-destination;e$receipt_path<-file.path(destination,'evaluation.json')
 expect_error(eval(publish,e),'not TRUE')
 expect_identical(readBin(file.path(destination,'metrics.csv'),'raw',100),before)
 expect_false(file.exists(file.path(out,'evaluation-replay.json')))
 writeBin(before,file.path(stage,'metrics.csv'));writeLines('{}',e$receipt_path);file.copy(e$receipt_path,file.path(stage,'evaluation.json'))
 expect_silent(eval(publish,e))
 expect_identical(readBin(file.path(destination,'metrics.csv'),'raw',100),before)
 expect_true(file.exists(file.path(out,'evaluation-replay.json')))
})

test_that('actual upstream snapshot receipt excludes descriptive model labels', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 nodes<-as.list(parse(file=file.path(root,'r/global_dynamic_select_20261018.R')))
 outer<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('for'))&&identical(n[[2]],as.name('i')),nodes)[[1]]
 model<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('for'))&&identical(n[[2]],as.name('model')),as.list(outer[[4]])[-1])[[1]]
 assignment<-Filter(function(n)is.call(n)&&identical(n[[1]],as.name('<-'))&&identical(n[[2]],quote(d$source_receipt)),as.list(model[[4]])[-1])[[1]]
 e<-new.env(parent=baseenv());sha<-paste(rep('a',64),collapse='')
 e$d<-list(source_bindings=list(forecasts=sha,client=sha,policy=sha,model='RAW'))
 e$cutoff<-list(issue_id='26103',cutoff_utc=as.POSIXct('2026-10-08',tz='UTC'))
 e$q<-tibble::tibble(fixture_id='26103:1',outcome='W',probability=1)
 e$candidates<-tibble::tibble(group_id='g01',ticket_id='26103:1:1',probability=1,rank=1L)
 e$source_at<-e$cutoff$cutoff_utc-1
 receipt<-eval(assignment[[3]],e)
 expect_setequal(names(receipt$source_snapshots),c('forecasts','client','policy'))
 expect_true(all(grepl('^[a-f0-9]{64}$',unlist(receipt$source_snapshots))))
 expect_identical(receipt$probability_hash,rlang::hash(e$q))
})

test_that('actual report refuses internally valid but mismatched evaluation inputs', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 lines<-readLines(file.path(root,'quarto/global_dynamic_walkforward_20261018.qmd'))
 line<-lines[grepl('stopifnot(identical(ev$forecast_sha256',lines,fixed=TRUE)]
 expect_length(line,1L)
 guard<-parse(text=line)
 e<-new.env(parent=baseenv());e$issue<-'26103'
 e$fr<-list(sha256='forecast-A');e$sr<-list(sha256='round-A')
 e$ev<-list(forecast_sha256='forecast-A',rounds_sha256='round-A')
 e$decisions<-list('26103'=list(forecast_sha256='forecast-A'))
 expect_silent(eval(guard,e))
 e$ev$forecast_sha256<-'forecast-B';expect_error(eval(guard,e),'not TRUE')
 e$ev$forecast_sha256<-'forecast-A';e$ev$rounds_sha256<-'round-B';expect_error(eval(guard,e),'not TRUE')
 e$ev$rounds_sha256<-'round-A';e$decisions[['26103']]$forecast_sha256<-'forecast-B';expect_error(eval(guard,e),'not TRUE')
})
