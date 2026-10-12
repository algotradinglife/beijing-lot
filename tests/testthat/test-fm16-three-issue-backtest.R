test_that('FM16 historical inputs and canonical quote contracts are preserved', {
 root<-Sys.getenv('FM16_BACKTEST_ROOT');skip_if(!nzchar(root),'Explicit diagnostic input root required')
 out<-file.path(root,'results/fm16-three-issues-20261012');s<-readRDS(file.path(out,'stage.rds'));m<-jsonlite::fromJSON(file.path(out,'stage-manifest.json'))
 expect_identical(digest::digest(file=file.path(out,'stage.rds'),algo='sha256'),m$stage_sha256)
 expect_length(s$old,346L);expect_setequal(names(s$old),names(s$native))
 expect_true(all(purrr::map_chr(file.path(root,s$inputs$path),~digest::digest(file=.x,algo='sha256'))==s$inputs$sha256))
 for(id in names(s$packets)) {
  p<-s$packets[[id]];expect_false(any(c('score','actual_outcome','sp_w','sp_d','sp_l','handicap')%in%names(p)))
  if(!p$market_available)next
  ref<-s$references[[id]];expect_identical(names(ref$model$grid),c('home_goals','away_goals','probability'))
  expect_equal(sum(ref$model$grid$probability),1,tolerance=1e-12)
  expect_true(all(ref$model$euro$quote_at<s$old[[id]]$base$cutoff$cutoff_utc))
  for(kind in c('euro','asian'))for(i in seq_len(nrow(ref$model[[kind]]))) {
   q<-ref$model[[kind]][i,]
   if(kind=='asian')q<-dplyr::select(q,company_id,fixture_id,quote_at,handicap,home_decimal,away_decimal)
   eid<-paste0(kind,'-',q$company_id)
   row<-ref$evidence_rows[[match(eid,purrr::map_chr(ref$evidence_rows,'evidence_id'))]]
   expect_identical(row$source_hash,beidan:::.score_margin_hash(q))
  }
 }
 # Regression: 26102 source column order must not reject validated quote rows.
 d<-jsonlite::fromJSON(file.path(root,'results/fm15-26102-20261012/market-diagnostic-manifest.json'))
 original<-readRDS(file.path(root,'results/fm15-26102-20261012',d$diagnostic_file))
 expect_true(s$packets[['26102:4']]$market_available)
 expect_equal(s$references[['26102:4']]$model$parameters,original$references[['26102:4']]$model$parameters,tolerance=1e-12)
 expect_equal(s$references[['26102:4']]$model$grid,original$references[['26102:4']]$model$grid,tolerance=1e-12)
})

test_that('FM16 sealed forecasts, reviews and same-fixture metric accounting agree', {
 root<-Sys.getenv('FM16_BACKTEST_ROOT');skip_if(!nzchar(root),'Explicit diagnostic input root required')
 out<-file.path(root,'results/fm16-three-issues-20261012');x<-readRDS(file.path(out,'forecasts.rds'));m<-jsonlite::fromJSON(file.path(out,'manifest.json'))
 expect_identical(digest::digest(file=file.path(out,'forecasts.rds'),algo='sha256'),m$forecast_sha256)
 expect_true(m$root_prior_outcome_knowledge);expect_false(anyDuplicated(x$audit$fixture_id)>0L)
 expect_equal(nrow(x$probabilities),346L*3L*3L)
 for(id in names(x$entries)) {
  e<-x$entries[[id]];expect_identical(e$review$author,'ROOT_CODEX')
  expected<-e$review$confidence%in%c('low','uncertain')&&e$review$market_sufficient&&e$review$market_consistent
  expect_identical(e$selection$selected_source,if(expected)'market'else'native')
  expect_identical(e$selection$base$grid,if(expected)e$market$grid else e$native$grid)
  canonical<-e$selection$base;canonical$source_hashes$selection_receipt<-NULL
  expect_identical(beidan:::.score_margin_hash(canonical),e$selection$receipt$output_hash)
  for(r in e$results) {
   expect_true(inherits(r$final$grid,'tbl_df'));expect_equal(sum(r$final$grid$probability),1,tolerance=1e-12)
   expect_lte(length(r$policy$core_margins),6L)
  }
 }
 metrics<-readr::read_csv(file.path(out,'metrics.csv'),show_col_types=FALSE)
 scores<-readr::read_csv(file.path(out,'scores.csv'),show_col_types=FALSE)
 labels<-readr::read_csv(file.path(out,'labels.csv'),show_col_types=FALSE)
 expect_equal(nrow(labels),345L);expect_true(all(is.finite(metrics$brier)&is.finite(metrics$logloss)))
 for(i in seq_len(nrow(metrics))) {
  r<-metrics[i,];z<-dplyr::filter(scores,issue_id==r$issue_id,comparison==r$comparison,cohort==r$cohort,model==r$model)
  expect_equal(nrow(z),r$n);expect_equal(sum(z$top1),r$hits1);expect_equal(sum(z$top2),r$hits2)
  expect_equal(mean(z$brier),r$brier);expect_equal(mean(z$logloss),r$logloss)
 }
 counts<-metrics |> dplyr::group_by(issue_id,comparison,cohort) |> dplyr::summarise(ns=dplyr::n_distinct(n),.groups='drop')
 expect_true(all(counts$ns==1L))
})

test_that('rendering rejects evaluation from a different forecast', {
 root<-Sys.getenv('FM16_BACKTEST_ROOT');skip_if(!nzchar(root),'Explicit diagnostic input root required')
 td<-tempfile('fm16-report-');dir.create(td);on.exit(unlink(td,recursive=TRUE),add=TRUE)
 out<-file.path(root,'results/fm16-three-issues-20261012')
 files<-c('manifest.json','evaluation.json','replay.json','forecasts.rds','metrics.csv','coverage.csv')
 expect_true(all(file.copy(file.path(out,files),td)))
 ev<-jsonlite::fromJSON(file.path(td,'evaluation.json'));ev$forecast_sha256<-paste(rep('0',64),collapse='')
 jsonlite::write_json(ev,file.path(td,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
 qmd<-readLines(file.path(root,'quarto/fm16_three_issues_20261012.qmd'))
 qmd<-gsub("root<-normalizePath('..');out<-file.path(root,'results/fm16-three-issues-20261012')",paste0('root<-',encodeString(root,quote='"'),';out<-',encodeString(td,quote='"')),qmd,fixed=TRUE)
 qp<-file.path(td,'mismatch.qmd');writeLines(qmd,qp)
 status<-suppressWarnings(system2('quarto',c('render',shQuote(qp),'--no-cache'),stdout=file.path(td,'render.log'),stderr=file.path(td,'render.log'),env=paste0('R_LIBS_USER=',shQuote(file.path(root,'r_lib')))))
 expect_false(status==0L)
 expect_match(paste(readLines(file.path(td,'render.log')),collapse='\n'),'forecast_sha256.*not TRUE')
})

test_that('evaluation rejects a changed comparator before labels are opened', {
 root<-Sys.getenv('FM16_BACKTEST_ROOT');skip_if(!nzchar(root),'Explicit diagnostic input root required')
 td<-tempfile('fm16-evaluation-');dir.create(td);on.exit(unlink(td,recursive=TRUE),add=TRUE)
 rd<-file.path(td,'results');dir.create(rd)
 target<-file.path(rd,'fm16-three-issues-20261012');dir.create(target)
 expect_true(all(file.copy(file.path(root,'results/fm16-three-issues-20261012',c('manifest.json','forecasts.rds','stage.rds','replay.json')),target)))
 expect_true(file.symlink(file.path(root,'results/fm16-release-20261012'),file.path(rd,'fm16-release-20261012')))
 expect_true(file.symlink(file.path(root,'results/fm15-26102-20261012'),file.path(rd,'fm15-26102-20261012')))
 old<-file.path(rd,'fm15-two-issues-20261012');dir.create(old)
 original<-file.path(root,'results/fm15-two-issues-20261012')
 s<-readRDS(file.path(target,'stage.rds'));batch<-basename(s$inputs$path[grepl('fm15-two-issues.+/batch-',s$inputs$path)])
 expect_length(batch,1L)
 expect_true(file.symlink(file.path(original,'native-stage.rds'),file.path(old,'native-stage.rds')))
 expect_true(file.copy(file.path(original,batch),file.path(old,batch)))
 con<-file(file.path(old,batch),'ab');writeBin(as.raw(0),con);close(con)
 log<-file.path(td,'evaluate.log')
 status<-suppressWarnings(system2('/opt/R/4.6.1/bin/Rscript',c(shQuote(file.path(root,'r/fm16_three_issue_evaluate.R')),shQuote(td)),stdout=log,stderr=log,env=paste0('R_LIBS_USER=',shQuote(file.path(root,'r_lib')))))
 expect_false(status==0L);expect_match(paste(readLines(log),collapse='\n'),'Comparator/source snapshot hash differs; labels remain unopened')
})
