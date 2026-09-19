# Live-free integration checks: fresh Quarto processes must reject mismatched
# input identities before reading fixture labels or producing research plans.
testthat::test_that('Top2 QMD entry points reject foreign catalog and stale replay evidence', {
 root<-normalizePath(file.path('..','..'));withr::local_dir(root)
 q<-Sys.getenv('QUARTO_BIN');py<-Sys.getenv('RETICULATE_PYTHON')
 testthat::expect_true(file.exists(q));testthat::expect_true(file.exists(py))
 tmp<-withr::local_tempdir();mock<-file.path(tmp,'mock');dir.create(mock)
 cfg<-jsonlite::fromJSON('config/top2_outside_validation.json')
 p<-file.path(tmp,'params.json');log<-file.path(tmp,'render.log')
 out<-file.path(tmp,'rejected-catalog')
 jsonlite::write_json(list(study=mock,output=out,python=py,catalog_sha256=paste(rep('0',64),collapse='')),p,auto_unbox=TRUE)
 status<-suppressWarnings(system2(q,c('render','quarto/177_top2_outside_validation.qmd',
  '--execute-dir',shQuote(root),'--execute-params',shQuote(p)),stdout=log,stderr=log))
 testthat::expect_true(status!=0)
 testthat::expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Configured catalog identity mismatch')
 testthat::expect_false(dir.exists(out))
 parent<-file.path(mock,'plans-receipt.json')
 jsonlite::write_json(list(scope=as.list(cfg$issues),implementation=list()),parent,auto_unbox=TRUE)
 jsonlite::write_json(list(status='PASS',allocations=4*length(cfg$issues),plans_receipt_sha256='foreign-plans'),
  file.path(mock,'independent-replay.json'),auto_unbox=TRUE)
 out<-file.path(tmp,'rejected-replay')
 jsonlite::write_json(list(study=mock,output=out,python=py,labels='must-not-be-read',
  receipt_sha256=digest::digest(file=parent,algo='sha256')),p,auto_unbox=TRUE)
 status<-suppressWarnings(system2(q,c('render','quarto/178_top2_outside_fixed.qmd',
  '--execute-dir',shQuote(root),'--execute-params',shQuote(p)),stdout=log,stderr=log))
 testthat::expect_true(status!=0)
 testthat::expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Parent replay receipt identity mismatch')
 testthat::expect_length(list.files(out,all.files=TRUE,no..=TRUE),0)
 evidence_path<-file.path(mock,'independent-replay.json')
 report_receipt<-file.path(tmp,'report-receipt.json')
 jsonlite::write_json(list(status='PASS',config_sha256=digest::digest(file='config/top2_outside_validation.json',algo='sha256'),
  gated_independent=digest::digest(file=evidence_path,algo='sha256'),gated_plans='requested-plans',
  fixed_independent='unused',fixed_plans='unused'),report_receipt,auto_unbox=TRUE)
 out<-file.path(tmp,'rejected-report')
 jsonlite::write_json(list(gated=mock,fixed=mock,output=out,receipt=report_receipt,
  receipt_sha256=digest::digest(file=report_receipt,algo='sha256')),p,auto_unbox=TRUE)
 status<-suppressWarnings(system2(q,c('render','quarto/179_top2_outside_conclusion.qmd',
  '--execute-dir',shQuote(root),'--execute-params',shQuote(p)),stdout=log,stderr=log))
 testthat::expect_true(status!=0)
 testthat::expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Report upstream replay identity mismatch')
 testthat::expect_false(dir.exists(out))

})
