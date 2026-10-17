# Offline test of the complete frozen issue; no scraping or PA calls.
suppressPackageStartupMessages(library(tidyverse));library(jsonlite);library(reticulate)
root<-rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
out<-file.path(root,'results/fm14-26101-20261011')
library(beidan,lib.loc=normalizePath(file.path(out,'library')))
manifest<-fromJSON(file.path(out,'manifest.json'),simplifyVector=FALSE)
batch<-readRDS(file.path(out,manifest$batch_file))

test_that('FM14 issue keeps roster and complete immutable grid contracts', {
 expect_identical(beidan:::.score_margin_hash(batch),manifest$batch_hash)
 expect_identical(digest::digest(file=file.path(out,manifest$batch_file),algo='sha256'),manifest$batch_sha256)
 expect_equal(nrow(batch$ledger),115);expect_equal(n_distinct(batch$ledger$fixture_id),115);expect_true(all(batch$ledger$handicap==round(batch$ledger$handicap)))
 expect_equal(length(batch$entries),sum(batch$ledger$stage!='UNAVAILABLE'));expect_equal(sum(batch$ledger$fm14_status=='UNAVAILABLE_UPSTREAM'),sum(batch$ledger$stage=='UNAVAILABLE'))
 stage<-fromJSON(file.path(out,'stage-manifest.json'));expect_identical(digest::digest(file=file.path(out,stage$stage_file),algo='sha256'),stage$sha256)
 for(e in batch$entries) {
  g<-e$final$grid;old<-e$base$grid
  expect_s3_class(g,'tbl_df');expect_equal(sum(g$probability),1,tolerance=1e-12);expect_true(all(g$probability>=0 & is.finite(g$probability)))
  expect_identical(readRDS(file.path(out,e$score_path)),e$final)
  expect_identical(e$final$receipt$model_id,'FM-1.4.0')
  expect_identical(e$final$receipt$source_context$source_hashes$fm14_policy_binding,e$policy$binding_hash)
  expect_true(all(map_dbl(e$evidence_rows,~as.numeric(ymd_hms(.x$data_available_ts,tz='UTC')))<as.numeric(e$cutoff$cutoff_utc)))
  expect_identical(e$review$base_hash,beidan:::.score_margin_hash(old))
  expect_equal(ymd_hms(e$review$cutoff_utc,tz='UTC'),e$cutoff$cutoff_utc)
  if(e$policy$branch=='balanced_top3_tail03') {
    m<-old |> mutate(margin=home_goals-away_goals) |> group_by(margin) |> summarise(p=sum(probability),.groups='drop') |> arrange(desc(p),margin)
    expect_setequal(e$policy$core_margins,m$margin[1:3])
    w<-ifelse(g$margin %in% e$policy$core_margins,1,.3)
    expect_equal(g$probability,old$probability*w/sum(old$probability*w),tolerance=1e-12)
    expect_true(is.na(e$policy$ratio))
  } else if(e$policy$branch=='strong_tailr02') {
    d<-g$margin*if(e$review$strong_side=='home') 1 else -1
    expect_equal(sum(g$probability[d<=0])/sum(g$probability[d==1]),e$policy$ratio,tolerance=1e-12)
    expect_true(is.na(e$policy$coefficient))
    for(mask in list(d>0,d<=0)) expect_equal(g$probability[mask]/sum(g$probability[mask]),old$probability[mask]/sum(old$probability[mask]),tolerance=1e-12)
  } else expect_equal(g$probability,old$probability,tolerance=1e-12)
  for(h in c(-2L,0L,2L,as.integer(e$projection$handicap[1]))) {
    before<-e$final$seal;p<-project_score_outcomes(e$final,h,root);dm<-g$margin+h
    expected<-c(W=sum(g$probability[dm>0]),D=sum(g$probability[dm==0]),L=sum(g$probability[dm<0]))
    expect_equal(p$probability,unname(expected[p$outcome]),tolerance=1e-12)
    expect_identical(e$final$seal,before)
  }
 }
})

test_that('FM14 intake and final projection resist future and target label mutation', {
 use_python(file.path(root,'.venv/bin/python'),required=TRUE)
 sys<-import('sys',convert=FALSE);sys$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
 backend<-import('beidan_backend.fundamental_probability',convert=FALSE);shared<-import('beidan_backend.temporal_learning',convert=FALSE)
 # Exercise each executed policy branch and both strong directions.
 ids<-batch$ledger |> filter(!is.na(branch)) |> distinct(branch,strong_side,.keep_all=TRUE) |> pull(fixture_id)
 for(id in ids) {
  e<-batch$entries[[id]]
  future<-modifyList(e$evidence_rows[[1]],list(evidence_id='future-attack',row_key='future-attack',source_hash='future-not-admitted',label_available_ts=format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),data_available_ts=format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')))
  target<-modifyList(e$evidence_rows[[1]],list(evidence_id='target-attack',row_key='target-attack',source_hash='target-not-admitted',issue_code='26101'))
  ctx<-backend$build_adjustment_evidence_context(c(e$evidence_rows,list(future,target)),as.list(e$fixture),shared$Cutoff$decision_epoch('26101',format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')),e$bindings,shared$AvailabilityPolicy$historical_proxy('HISTORY_ARTICLE_QUOTE_PROXY_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',root)
  replay<-adjust_score_margin_distribution(e$base,e$judgement,ctx,e$fixture,e$cutoff,root)
  expect_identical(replay$grid,e$final$grid);expect_identical(replay$margins,e$final$margins)
  expect_false(any(c('future-attack','target-attack') %in% replay$evidence$evidence_id))
  expect_equal(project_score_outcomes(replay,as.integer(e$projection$handicap[1]),root),e$projection)
 }
})

test_that('same cutoff scoring and full report reconcile without sample loss', {
 full<-as_tibble(map(read_csv(file.path(out,'whole-issue-report.csv'),show_col_types=FALSE),identity))
 sp<-as_tibble(map(read_csv(file.path(out,'selected-sp.csv'),show_col_types=FALSE),identity))
 scores<-as_tibble(map(read_csv(file.path(out,'scores-same-cutoff.csv'),show_col_types=FALSE),identity))
 metrics<-as_tibble(map(read_csv(file.path(out,'metrics-same-cutoff.csv'),show_col_types=FALSE),identity))
 expect_equal(nrow(full),115);expect_equal(n_distinct(full$fixture_id),115)
 expect_true(all(is.na(full$FM14_W[full$fm14_status=='UNAVAILABLE_UPSTREAM'])))
 expect_true(all(sp$quote_at<sp$selection_cutoff));expect_true(all(is.na(sp$model_cutoff_utc)==is.na(sp$cutoff_utc)))
 expect_true(all(sp$model_cutoff_utc[!is.na(sp$cutoff_utc)]==sp$cutoff_utc[!is.na(sp$cutoff_utc)]))
 expect_true(all(sp$mode[is.na(sp$model_cutoff_utc)]=='near_sale'))
 expect_true(all(sp$fixture_id[is.na(sp$model_cutoff_utc)] %in% full$fixture_id[full$fm14_status=='UNAVAILABLE_UPSTREAM']))
 expect_true(all(sp$selection_cutoff[sp$mode=='same_cutoff']==sp$cutoff_utc[sp$mode=='same_cutoff']))
 for(model in metrics$model) {
   z<-scores |> filter(.data$model==.env$model)
   expect_equal(nrow(z),sum(full$in_primary_comparison));expect_equal(metrics$n[metrics$model==model],nrow(z))
   expect_equal(metrics$brier[metrics$model==model],mean(z$brier));expect_equal(metrics$logloss[metrics$model==model],mean(z$logloss))
   expect_equal(metrics$hits1[metrics$model==model],sum(z$top1));expect_equal(metrics$hits2[metrics$model==model],sum(z$top2))
 }
 # Historical timestamp normalization is explicit and bound to typed source UTC.
 accepted<-fromJSON(file.path(out,'pa-acceptance.json'),simplifyVector=TRUE)
 expect_equal(nrow(accepted),ceiling(length(batch$entries)/6));expect_true(all(accepted$status=='ACCEPTED'))
 for(i in seq_len(nrow(accepted))) {
   expect_identical(digest::digest(file=file.path(root,accepted$input_path[i]),algo='sha256'),accepted$input_sha256[i])
   expect_identical(digest::digest(file=file.path(root,accepted$review_path[i]),algo='sha256'),accepted$review_sha256[i])
 }
})

test_that('forecast intake rejects edits after PA acceptance before reading reviews', {
 sandbox<-tempfile();dir.create(sandbox);on.exit(unlink(sandbox,recursive=TRUE))
 dir.create(file.path(sandbox,'reviews'))
 a<-fromJSON(file.path(out,'pa-acceptance.json'),simplifyVector=TRUE);nb<-nrow(a)
 for(kind in c('input','review','raw_review')) {
  a[[paste0(kind,'_path')]]<-paste0('reviews/',kind,'-',seq_len(nb),'.json')
  for(i in seq_len(nb)) writeLines('{}',file.path(sandbox,a[[paste0(kind,'_path')]][i]))
  a[[paste0(kind,'_sha256')]]<-map_chr(file.path(sandbox,a[[paste0(kind,'_path')]]),~digest::digest(file=.x,algo='sha256'))
 }
 write_json(a,file.path(sandbox,'pa-acceptance.json'))
 code<-readLines(file.path(root,'r/fm14_26101_run.R'))
 first<-tail(which(startsWith(code,'acceptance<-')),1L)
 last<-which(startsWith(code,'reviews<-'))-1L
 env<-new.env();env$root<-sandbox;env$out<-sandbox;env$nb<-nb;env$review_files<-file.path(sandbox,a$review_path)
 expect_error(eval(parse(text=code[first:last]),env),NA)
 for(kind in c('input','review','raw_review')) {
  path<-file.path(sandbox,a[[paste0(kind,'_path')]][1]);original<-readBin(path,'raw',n=file.info(path)$size)
  writeLines('{"scene":"balanced"}',path)
  expect_error(eval(parse(text=code[first:last]),env),'not TRUE')
  writeBin(original,path)
 }
})

test_that('immutable consumer rejects changed transitive implementation receipts', {
 use_python(file.path(root,'.venv/bin/python'),required=TRUE)
 sys<-import('sys',convert=FALSE);sys$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
 provenance<-import('beidan_backend.temporal_learning.provenance',convert=FALSE)
 py_root<-import('pathlib',convert=FALSE)$Path(root)
 original<-batch$entries[[1]]$final$receipt$source_context$implementation
 original$root_modules<-as.list(original$root_modules)
 # Historical snapshots stay immutable; only a closure rebuilt from the loaded
 # current implementation may be positively admitted against the current root.
 current<-reticulate::py_to_r(provenance$implementation_closure(py_root,original$root_modules,
  distributions=as.list(names(original$distributions))))
 current$root_modules<-as.list(current$root_modules)
 expect_error(provenance$verify_implementation_closure(py_root,current),NA)
 if(!identical(original,current)) {
  expect_error(provenance$verify_implementation_closure(py_root,original),'transitive implementation closure differs')
 } else expect_error(provenance$verify_implementation_closure(py_root,original),NA)
 for(module in c('fundamental_probability.py','temporal_learning/core.py')) {
  poisoned<-current
  key<-names(poisoned$files)[endsWith(names(poisoned$files),module)]
  expect_length(key,1)
  poisoned$files[[key]]<-paste(rep('0',64),collapse='')
  expect_error(provenance$verify_implementation_closure(py_root,poisoned),'transitive implementation closure differs')
 }
})

test_that('PA schema-only correction preserves every original qualitative value', {
 old<-fromJSON(file.path(out,'brief-work-12/reviews-wrapped-original.json'),simplifyVector=FALSE)$reviews
 fixed<-fromJSON(file.path(out,'brief-work-12/reviews-schema-fixed-unaccepted.json'),simplifyVector=FALSE)
 expect_identical(fixed,old)
 accept<-fromJSON(file.path(out,'pa-acceptance.json'))
 for(i in seq_len(nrow(accept))) {
  r<-fromJSON(file.path(root,accept$receipt_path[i]))
  expect_identical(r$exit_code,0L);expect_false(r$timed_out);expect_identical(r$model,'opencode/deepseek-v4.1-flash')
 }
})
