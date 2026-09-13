# Post-settlement #425 diagnostic; does not touch #433 decision artifacts.
args<-commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==3,!file.exists(args[2]),dir.exists(args[1]),file.exists(args[3]))
reticulate::use_python(args[3],required=TRUE)
reader<-reticulate::import('src.n7_rank_diagnostic',convert=TRUE)
source('r/n7_rank_diagnostic.R')
freeze<-jsonlite::fromJSON(file.path(args[1],'plans-frozen.json'),simplifyVector=FALSE)
issues<-unlist(freeze$receipt$issues);targets<-seq(.15,.5,.05)
parts<-vector('list',length(issues))
for(i in seq_along(issues)) {
  x<-jsonlite::fromJSON(reader$load_rank_issue(args[1],issues[i]))
  stopifnot(x$freeze_seal==freeze$seal)
  parts[[i]]<-n7_rank_diagnostic(x,2,.65,targets)
  if(i%%10==0)message('Threshold diagnostic ',i,'/',length(issues))
}
rows<-dplyr::bind_rows(parts)
payload<-list(rows=rows,targets=targets,issue_order=issues,freeze_seal=freeze$seal,
  evidence_class='POST_SETTLEMENT_DIAGNOSTIC',historical_admission=FALSE,
  generation_time=format(Sys.time(),tz='UTC',usetz=TRUE),R=as.character(getRversion()),
  source_hashes=list(freeze=digest::digest(file=file.path(args[1],'plans-frozen.json'),algo='sha256'),
    evaluation=digest::digest(file=file.path(args[1],'evaluation-receipt.json'),algo='sha256'),
    reader=digest::digest(file='src/n7_rank_diagnostic.py',algo='sha256'),
    rank=digest::digest(file='r/n7_rank_diagnostic.R',algo='sha256'),
    entry=digest::digest(file='scripts/prepare_n7_threshold_scatter.R',algo='sha256')))
body<-as.character(jsonlite::toJSON(payload,auto_unbox=TRUE,digits=NA,dataframe='rows'))
archive<-list(schema='bj433_threshold_scatter_v1',body=body,
  sha256=digest::digest(charToRaw(body),algo='sha256',serialize=FALSE))
jsonlite::write_json(archive,args[2],auto_unbox=TRUE,digits=NA)
