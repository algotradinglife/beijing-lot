test_that('FM17 frozen batch retains parent sources and complete probability contracts', {
 root<-Sys.getenv('FM17_BACKTEST_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-three-issues-20261013')
 x<-readRDS(file.path(out,'forecasts.rds'));m<-jsonlite::fromJSON(file.path(out,'manifest.json'))
 parent<-readRDS(file.path(root,'results/fm16-three-issues-20261012/forecasts.rds'))
 expect_length(x$entries,346L);expect_equal(nrow(x$probabilities),346L*2L*3L)
 expect_identical(digest::digest(file=file.path(out,'forecasts.rds'),algo='sha256'),m$forecast_sha256)
 expect_identical(x$model_id,'FM-1.7.0');expect_setequal(names(x$entries),names(parent$entries))
 expect_false(anyDuplicated(x$audit$fixture_id)>0L)
 for(id in names(x$entries)) {
  e<-x$entries[[id]];p<-parent$entries[[id]]
  expect_identical(e$parent_selection,p$selection$receipt)
  expect_identical(e$parent_review,p$review)
  for(r in e$results) {
   expect_identical(r$base,p$selection$base)
   expect_s3_class(r$final$grid,'tbl_df');expect_s3_class(r$core$ranked_margins,'tbl_df')
   expect_equal(sum(r$final$grid$probability),1,tolerance=1e-12)
   expect_true(all(r$final$grid$probability>=0))
   expect_identical(r$core$judgement$model_id,'FM-1.7.0')
   expect_identical(r$final$cutoff,e$cutoff)
   expect_identical(r$final$receipt$source_context$source_hashes$tail_binding,r$core$binding_hash)
   expect_identical(r$final$receipt$cache_reuse,'NONE')
   expect_gt(r$core$core_mass,.9)
   boundary<-r$core$boundary_rank
   expect_gt(r$core$ranked_margins$cumulative[boundary],.9+1e-12)
   if(boundary>1)expect_lte(r$core$ranked_margins$cumulative[boundary-1],.9+1e-12)
  }
  raw<-e$results[['FM17-source-before-tail']]
  expect_equal(raw$final$grid$probability,raw$base$grid$probability,tolerance=1e-12)
  expect_identical(e$results[['FM-1.7.0']]$review$decision,p$results[['FM-1.6.0']]$review$decision)
 }
 normalized<-x$probabilities |> dplyr::group_by(fixture_id,model) |>
  dplyr::summarise(n=dplyr::n(),mass=sum(probability),.groups='drop')
 expect_true(all(normalized$n==3L));expect_equal(normalized$mass,rep(1,nrow(normalized)),tolerance=1e-12)
})

test_that('FM17 same-fixture scoring totals agree independently', {
 root<-Sys.getenv('FM17_BACKTEST_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-three-issues-20261013')
 metrics<-readr::read_csv(file.path(out,'metrics.csv'),show_col_types=FALSE)
 scores<-readr::read_csv(file.path(out,'scores.csv'),show_col_types=FALSE)
 labels<-readr::read_csv(file.path(out,'labels.csv'),show_col_types=FALSE)
 ev<-jsonlite::fromJSON(file.path(out,'evaluation.json'))
 for(n in c('scores','changes','labels')) {
  field<-if(n=='labels')'labels_csv_sha256'else paste0(n,'_sha256')
  expect_identical(digest::digest(file=file.path(out,paste0(n,'.csv')),algo='sha256'),ev[[field]])
 }
 expect_equal(nrow(labels),345L)
 expect_false(anyDuplicated(labels$fixture_id)>0L)
 for(i in seq_len(nrow(metrics))) {
  r<-metrics[i,];z<-dplyr::filter(scores,issue_id==r$issue_id,comparison==r$comparison,cohort==r$cohort,model==r$model)
  expect_equal(nrow(z),r$n);expect_equal(sum(z$top1),r$hits1);expect_equal(sum(z$top2),r$hits2)
  expect_equal(mean(z$brier),r$brier);expect_equal(mean(z$logloss),r$logloss)
 }
 ns<-metrics |> dplyr::group_by(issue_id,comparison,cohort) |>
  dplyr::summarise(n=dplyr::n_distinct(n),.groups='drop')
 expect_true(all(ns$n==1L))
 p<-tibble::tibble(fixture_id=c('a','a','a','b','b','b'),model='manual',outcome=rep(c('W','D','L'),2),probability=c(.5,.3,.2,.2,.3,.5))
 y<-tibble::tibble(fixture_id=c('a','b'),actual_outcome=c('W','D'))
 d<-beidan:::DcAccuracyDiagnostic(p,y)
 expect_equal(d$summary$top1,.5);expect_equal(d$summary$top2,1)
 expect_equal(d$summary$brier,(.38+.78)/2)
 expect_equal(d$summary$logloss,-mean(log(c(.5,.3))))
})

test_that('post-cutoff/target mutation cannot change sealed core score or projection', {
 root<-Sys.getenv('FM17_BACKTEST_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-three-issues-20261013')
 e<-readRDS(file.path(out,'forecasts.rds'))$entries[['26102:10']]
 r<-e$results[['FM-1.7.0']]
 impl<-file.path(root,'results/fm15-26102-20261012/implementation')
 reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
 reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
 backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
 shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
 ct<-format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 for(kind in c('future','target')) {
  row<-e$evidence_rows[[1]];row$evidence_id<-paste0('excluded-',kind);row$row_key<-row$evidence_id;row$source_hash<-'changed-excluded-source'
  if(kind=='future'){row$data_available_ts<-ct;row$label_available_ts<-ct}else row$issue_code<-e$fixture$issue_id
  ctx<-backend$build_adjustment_evidence_context(c(e$evidence_rows,list(row)),as.list(e$fixture),shared$Cutoff$decision_epoch(e$fixture$issue_id,ct),r$bindings,shared$AvailabilityPolicy$historical_proxy('FM17_POSTHOC_RULE_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',impl)
  adjusted<-adjust_score_margin_distribution(r$base,r$core$judgement,ctx,e$fixture,e$cutoff,impl)
  expect_identical(adjusted$grid,r$final$grid)
  expect_identical(adjusted$margins,r$final$margins)
  expect_identical(project_score_outcomes(adjusted,-1L,impl),project_score_outcomes(r$final,-1L,impl))
  expect_false(row$evidence_id %in% adjusted$evidence$evidence_id)
 }
 bad<-r$final;bad$cutoff$cutoff_utc<-bad$cutoff$cutoff_utc+1
 expect_error(project_score_outcomes(bad,-1L,impl),'Frozen distribution integrity differs')
})

test_that('report rejects an evaluation bound to another frozen batch', {
 root<-Sys.getenv('FM17_BACKTEST_ROOT');stopifnot(nzchar(root))
 td<-tempfile('fm17-report-');dir.create(td)
 on.exit(unlink(td,recursive=TRUE),add=TRUE)
 out<-file.path(root,'results/fm17-three-issues-20261013')
 expect_true(all(file.copy(file.path(out,c('manifest.json','evaluation.json','replay.json','forecasts.rds','metrics.csv')),td)))
 ev<-jsonlite::fromJSON(file.path(td,'evaluation.json'));ev$forecast_sha256<-paste(rep('0',64),collapse='')
 jsonlite::write_json(ev,file.path(td,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
 qmd<-readLines(file.path(root,'quarto/fm17_three_issues_20261013.qmd'))
 qmd<-gsub("root<-normalizePath('..');out<-file.path(root,'results/fm17-three-issues-20261013')",paste0('root<-',encodeString(root,quote='"'),';out<-',encodeString(td,quote='"')),qmd,fixed=TRUE)
 qp<-file.path(td,'mismatch.qmd');writeLines(qmd,qp)
 status<-suppressWarnings(system2('quarto',c('render',shQuote(qp),'--no-cache'),stdout=file.path(td,'render.log'),stderr=file.path(td,'render.log'),env=paste0('R_LIBS_USER=',shQuote(file.path(root,'r_lib')))))
 expect_false(status==0L)
 expect_match(paste(readLines(file.path(td,'render.log')),collapse='\n'),'forecast_sha256.*not TRUE')
})

test_that('evaluation rejects a changed parent forecast before opening labels', {
 root<-Sys.getenv('FM17_BACKTEST_ROOT');stopifnot(nzchar(root))
 td<-tempfile('fm17-parent-');dir.create(td)
 on.exit(unlink(td,recursive=TRUE),add=TRUE)
 rd<-file.path(td,'results');dir.create(rd)
 out<-file.path(rd,'fm17-three-issues-20261013');dir.create(out)
 expect_true(all(file.copy(file.path(root,'results/fm17-three-issues-20261013',c('manifest.json','forecasts.rds')),out)))
 expect_true(file.symlink(file.path(root,'results/fm17-release-20261013'),file.path(rd,'fm17-release-20261013')))
 expect_true(file.symlink(file.path(root,'results/fm16-three-issues-20261012'),file.path(rd,'fm16-three-issues-20261012')))
 m<-jsonlite::fromJSON(file.path(out,'manifest.json'));m$source_hashes$parent_forecast<-paste(rep('0',64),collapse='')
 jsonlite::write_json(m,file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
 log<-file.path(td,'evaluate.log')
 status<-suppressWarnings(system2('/opt/R/4.6.1/bin/Rscript',c(shQuote(file.path(root,'r/fm17_three_issue_evaluate.R')),shQuote(td)),stdout=log,stderr=log,env=paste0('R_LIBS_USER=',shQuote(file.path(root,'r_lib')))))
 expect_false(status==0L)
 expect_match(paste(readLines(log),collapse='\n'),'Parent forecast hash differs; labels remain unopened')
 expect_false(file.exists(file.path(out,'evaluation.json')))
})

test_that('report rejects changed derived changes CSV before displaying cases', {
 root<-Sys.getenv('FM17_BACKTEST_ROOT');stopifnot(nzchar(root))
 td<-tempfile('fm17-changes-');dir.create(td)
 on.exit(unlink(td,recursive=TRUE),add=TRUE)
 out<-file.path(root,'results/fm17-three-issues-20261013')
 files<-c('manifest.json','evaluation.json','replay.json','forecasts.rds','metrics.csv','scores.csv','changes.csv','labels.csv','scope.csv')
 expect_true(all(file.copy(file.path(out,files),td)))
 con<-file(file.path(td,'changes.csv'),'ab');writeBin(charToRaw('\n'),con);close(con)
 qmd<-readLines(file.path(root,'quarto/fm17_three_issues_20261013.qmd'))
 qmd<-gsub("root<-normalizePath('..');out<-file.path(root,'results/fm17-three-issues-20261013')",paste0('root<-',encodeString(root,quote='"'),';out<-',encodeString(td,quote='"')),qmd,fixed=TRUE)
 qp<-file.path(td,'mismatch.qmd');writeLines(qmd,qp)
 status<-suppressWarnings(system2('quarto',c('render',shQuote(qp),'--no-cache'),stdout=file.path(td,'render.log'),stderr=file.path(td,'render.log'),env=paste0('R_LIBS_USER=',shQuote(file.path(root,'r_lib')))))
 expect_false(status==0L)
 expect_match(paste(readLines(file.path(td,'render.log')),collapse='\n'),'Report changes hash differs')
})
