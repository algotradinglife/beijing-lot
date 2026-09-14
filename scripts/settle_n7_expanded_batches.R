# Post-freeze current SQLite query, identity audit and candidate rank settlement.
# Business operations use the existing five-play R query/audit and rank APIs.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);library(dplyr)
source('r/nowscore_query.R');source('r/python_bridge.R');source('r/fundamentals_returns.R')
source('r/n7_sleeve_tables.R');source('r/n7_capital_depth.R');source('r/n7_rank_diagnostic.R')
reticulate::use_python(cfg$python,required=TRUE)
study<-cfg$study;input<-file.path(study,'settlement-inputs')
receipt<-jsonlite::fromJSON(file.path(input,'receipt.json'))
for(n in names(receipt$files))stopifnot(digest::digest(file=file.path(input,n),algo='sha256')==receipt$files[[n]])
for(p in names(receipt$source_hashes))stopifnot(digest::digest(file=p,algo='sha256')==receipt$source_hashes[[p]])
labels<-jsonlite::fromJSON(file.path(input,'labels.json'))
catalog<-jsonlite::fromJSON(file.path(input,'catalog.json'))
stopifnot(!anyDuplicated(labels[c('issue','slot','provider_id')]),!dir.exists(cfg$output_dir))
dir.create(cfg$output_dir,recursive=TRUE)
code<-c('r/nowscore_query.R','r/python_bridge.R','r/fundamentals_returns.R',
 'r/n7_sleeve_tables.R','r/n7_capital_depth.R','r/n7_rank_diagnostic.R','scripts/settle_n7_expanded_batches.R')
identities<-vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)
db_sha<-digest::digest(file=cfg$db_path,algo='sha256')
ranks<-list();status<-list();audit_rows<-list();files<-character()
for(k in seq_len(nrow(catalog$issues))) {
 item<-catalog$issues[k,];issue<-item$issue
 f<-labels |> filter(.data$issue==.env$issue)
 completed<-f |> filter(result_state=='完场',is.finite(actual_home),is.finite(actual_away))
 if(nrow(completed)!=nrow(f)) {
  status[[k]]<-tibble(issue=issue,status='PENDING_ROSTER_OUTCOME',fixtures=nrow(f),unresolved=nrow(f)-nrow(completed))
  next
 }
 x<-fundamentals_settlement_audit(cfg$db_path,completed,cfg$python,cfg$repository_root)
 ap<-paste0('audit-',issue,'.json')
 jsonlite::write_json(x,file.path(cfg$output_dir,ap),auto_unbox=TRUE,digits=15,na='null',null='null')
 files<-c(files,ap);a<-x$fixtures
 bad<-is.na(a$status)|grepl('spf:IDENTITY',a$status)|!is.finite(a$spf_sp)|a$spf_sp<=0
 audit_rows[[k]]<-a
 if(any(bad)) {
  status[[k]]<-tibble(issue=issue,status='PENDING_SETTLEMENT_AUDIT',fixtures=nrow(f),unresolved=sum(bad))
  next
 }
 stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
 b<-jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE)
 v<-n7_sleeve_tables(b,b$cutoffs,cfg$model_id)
 curves<-n7_capital_curves(v,b$cutoffs,b$cutoffs,2)
 sleeves<-bind_rows(lapply(b$sleeves,function(s)tibble(id=s$id,fixture_indices=list(as.integer(unlist(s$fixture_indices))),origin=s$origin)))
 r<-n7_rank_diagnostic(list(issue=issue,cutoffs=b$cutoffs,curves=curves,audit=a,
   fixtures=bind_rows(b$expanded_pool$fixtures),sleeves=sleeves,evidence_class='POST_SETTLEMENT_DIAGNOSTIC'),2,.65,c(.15,.20,.25,.50))
 ranks[[k]]<-r |> mutate(cohort=item$cohort)
 status[[k]]<-tibble(issue=issue,status='SETTLED',fixtures=nrow(f),unresolved=0)
 if(k%%10==0)message('Current SQLite settled ',k,'/',nrow(catalog$issues),' candidate issues')
}
stopifnot(db_sha==digest::digest(file=cfg$db_path,algo='sha256'),
 identical(identities,vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)))
readr::write_csv(bind_rows(ranks),file.path(cfg$output_dir,'ranks.csv'))
readr::write_csv(bind_rows(status),file.path(cfg$output_dir,'status.csv'))
readr::write_csv(bind_rows(audit_rows),file.path(cfg$output_dir,'fixture-audit.csv'))
files<-c(files,'ranks.csv','status.csv','fixture-audit.csv')
jsonlite::write_json(list(status='AUDIT_COMPLETE',config=cfg,db_sha256=db_sha,
 source_receipt_sha256=digest::digest(file=file.path(input,'receipt.json'),algo='sha256'),
 files=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),algo='sha256',file=TRUE),files)),
 implementation=as.list(identities),historical_admission=FALSE),file.path(cfg$output_dir,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
message('Current settlement audit and ranks complete')
