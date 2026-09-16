# Independent report cohort reconciliation after the physical-ticket replay.
# Run from repository root: Rscript scripts/check_n7_purchase_cohorts.R PARAMS OUTPUT
args<-commandArgs(TRUE);stopifnot(length(args)==2)
params<-jsonlite::fromJSON(args[1]);report<-params$output
receipt_path<-file.path(report,'receipt.json')
receipt<-jsonlite::fromJSON(receipt_path,simplifyVector=FALSE)
parents<-list();parent_hashes<-character()
for(name in c('main','structure')) {
 path<-file.path(params[[name]],'plans-receipt.json')
 raw<-readBin(path,'raw',n=file.info(path)$size);sha<-params[[paste0(name,'_sha256')]]
 stopifnot(is.character(sha),length(sha)==1,nzchar(sha),
  digest::digest(raw,serialize=FALSE,algo='sha256')==sha)
 parents[[name]]<-jsonlite::fromJSON(rawToChar(raw),simplifyVector=FALSE)
 parent_hashes<-c(parent_hashes,sha)
}
stopifnot(identical(unname(parent_hashes),unlist(receipt$parent_hashes,use.names=FALSE)),
 identical(parents$main$scope,parents$structure$scope),
 identical(receipt$scope,parents$main$scope),
 identical(parents$structure$parent_receipt_sha256,parent_hashes[1]),
 identical(params$labels_sha256,receipt$labels_sha256),
 digest::digest(file=params$labels,algo='sha256')==params$labels_sha256)
raw<-readBin(params$catalog,'raw',n=file.info(params$catalog)$size)
stopifnot(digest::digest(raw,serialize=FALSE,algo='sha256')==parents$main$catalog_sha256,
 identical(receipt$catalog_sha256,parents$main$catalog_sha256))
catalog<-jsonlite::fromJSON(rawToChar(raw))
stopifnot(identical(catalog$issues$issue,unlist(parents$main$scope)))
policies<-unlist(lapply(parents,function(p)vapply(p$policies,`[[`,character(1),'id')),use.names=FALSE)
for(name in c('rows.csv','cohort_summary.csv')) {
 sha<-receipt$files[[name]]
 stopifnot(is.character(sha),length(sha)==1,nzchar(sha),
  digest::digest(file=file.path(report,name),algo='sha256')==sha)
}
config_path<-'config/top2_outside_validation.json';sha<-receipt$code[[config_path]]
stopifnot(is.character(sha),length(sha)==1,nzchar(sha),
 digest::digest(file=config_path,algo='sha256')==sha)
config<-jsonlite::fromJSON(config_path)
periods<-read.csv(file.path(report,'rows.csv'),colClasses=c(issue='character'))
observed<-read.csv(file.path(report,'cohort_summary.csv'))
source('r/n7_purchase_cohort_audit.R')
verified<-n7_purchase_cohort_audit(periods,observed,unlist(receipt$scope),
 unlist(c(config$issues,config$excluded_drawdown_issues),use.names=FALSE),policies,1024,100000)
jsonlite::write_json(list(status='PASS',issues=length(receipt$scope),
 policies=length(unique(verified$policy)),cohort_rows=nrow(verified),
 scope='ALL/ORIGINAL/ADDITIONAL complete scope, funded accounting and independent drawdown',
 report_receipt_sha256=digest::digest(file=receipt_path,algo='sha256'),
 implementation=as.list(setNames(vapply(c('r/n7_purchase_cohort_audit.R',
 'scripts/check_n7_purchase_cohorts.R'),digest::digest,character(1),file=TRUE,algo='sha256'),
 c('r/n7_purchase_cohort_audit.R','scripts/check_n7_purchase_cohorts.R')))),
 args[2],auto_unbox=TRUE,pretty=TRUE)
