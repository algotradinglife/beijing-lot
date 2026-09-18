# Explicit integration fixture: a completed combined report with immutable
# verified parent receipts. Run after rendering, never against live outputs.
testthat::test_that('combined proof rejects rehashed ledger and scope mutations',{
 fixture<-Sys.getenv('EIGHT_STRATEGY_REPORT_FIXTURE')
 testthat::skip_if(!nzchar(fixture),'requires an explicitly completed report fixture')
 repository<-normalizePath(file.path(testthat::test_path(),'..','..'))
 script<-file.path(repository,'scripts/check_eight_strategy_combined.R')
 testthat::expect_true(file.exists(file.path(fixture,'receipt.json')))
 for(kind in c('CONTROL','GROUP','REQUESTED_SCOPE','CURVE')) {
  directory<-tempfile('eight-proof-');dir.create(directory)
  paths<-list.files(fixture,full.names=TRUE)
  testthat::expect_true(all(file.copy(paths,directory)))
  receipt_path<-file.path(directory,'receipt.json')
  receipt<-jsonlite::fromJSON(receipt_path,simplifyVector=FALSE)
  if(kind=='REQUESTED_SCOPE')receipt$requested_issues<-head(receipt$requested_issues,-1L)
  if(kind %in% c('GROUP','CURVE')) {
   name<-if(kind=='GROUP')'groups.csv' else 'curves.csv'
   path<-file.path(directory,name)
   x<-readr::read_csv(path,col_types=readr::cols(.default='c'),show_col_types=FALSE)
   if(kind=='GROUP')x$gross[1]<-as.character(as.double(x$gross[1])+1)
   else x$issue[2]<-'INVALID_ISSUE'
   readr::write_csv(x,path)
   receipt$files[[name]]<-digest::digest(file=path,algo='sha256')
  }
  jsonlite::write_json(receipt,receipt_path,auto_unbox=TRUE,digits=NA)
  log<-file.path(directory,'proof.log')
  status<-system2(file.path(R.home('bin'),'Rscript'),c('--vanilla',shQuote(script),shQuote(directory)),stdout=log,stderr=log)
  if(kind=='CONTROL')testthat::expect_equal(status,0,info=paste(readLines(log),collapse='\n'))
  else testthat::expect_false(identical(status,0L),info=kind)
  unlink(directory,recursive=TRUE)
 }
})

testthat::test_that('parent replay checks probabilities, depth and excluded fixtures',{
 fixture<-Sys.getenv('EIGHT_STRATEGY_REPORT_FIXTURE')
 testthat::skip_if(!nzchar(fixture),'requires an explicitly completed report fixture')
 repository<-normalizePath(file.path(testthat::test_path(),'..','..'))
 combined<-jsonlite::fromJSON(file.path(fixture,'receipt.json'))
 parent<-dirname(combined$config$reports$receipt[1])
 script<-file.path(repository,'scripts/check_eight_strategy_report.R')
 for(kind in c('CONTROL','DEPTH','COVERAGE','ESTIMATE','EXCLUDED_FIXTURE')) {
  directory<-tempfile('eight-parent-proof-');dir.create(directory)
  testthat::expect_true(all(file.copy(list.files(parent,full.names=TRUE),directory)))
  receipt_path<-file.path(directory,'receipt.json')
  receipt<-jsonlite::fromJSON(receipt_path,simplifyVector=FALSE)
  if(kind %in% c('DEPTH','COVERAGE','ESTIMATE')) {
   path<-file.path(directory,'groups.csv')
   x<-readr::read_csv(path,col_types=readr::cols(.default='c'),show_col_types=FALSE)
   field<-switch(kind,DEPTH='depth',COVERAGE='coverage',ESTIMATE='expected_gross')
   x[[field]][1]<-as.character(as.double(x[[field]][1])+1)
   readr::write_csv(x,path);receipt$files[['groups.csv']]<-digest::digest(file=path,algo='sha256')
  }
  if(kind=='EXCLUDED_FIXTURE') {
   unavailable<-readr::read_csv(file.path(parent,'unavailable-issues.csv'),col_types=readr::cols(issue='c'),show_col_types=FALSE)
   testthat::expect_gt(nrow(unavailable),0)
   id<-unavailable$issue[1]
   freeze<-jsonlite::fromJSON(receipt$config$top2$receipt,simplifyVector=FALSE)
   plan<-readRDS(freeze$bindings[[id]]$path)
   plan$fresh$fixtures$p_W[1]<-plan$fresh$fixtures$p_W[1]+.01
   path<-file.path(directory,'changed-plan.rds');saveRDS(plan,path)
   freeze$bindings[[id]]$path<-path;freeze$bindings[[id]]$sha256<-digest::digest(file=path,algo='sha256')
   path<-file.path(directory,'changed-freeze.json');jsonlite::write_json(freeze,path,auto_unbox=TRUE,digits=NA)
   receipt$config$top2$receipt<-path;receipt$config$top2$sha256<-digest::digest(file=path,algo='sha256')
  }
  jsonlite::write_json(receipt,receipt_path,auto_unbox=TRUE,digits=NA)
  log<-file.path(directory,'proof.log')
  status<-system2(file.path(R.home('bin'),'Rscript'),c('--vanilla',shQuote(script),shQuote(directory)),stdout=log,stderr=log)
  if(kind=='CONTROL')testthat::expect_equal(status,0,info=paste(readLines(log),collapse='\n'))
  else testthat::expect_false(identical(status,0L),info=kind)
  unlink(directory,recursive=TRUE)
 }
})
