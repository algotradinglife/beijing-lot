# Thin worker: manifest, output, python, worker index, worker count, freeze/verify.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==6)
for(f in c('n7_sleeve_tables','n7_joint_sleeves','joint_payout_exposure','joint_payout_study'))source(paste0('r/',f,'.R'))
runtime<-jsonlite::fromJSON('config/n7_joint_runtime.json')
stopifnot(as.character(getRversion())==runtime$R,
 all(vapply(names(runtime$r_packages),function(p)as.character(utils::packageVersion(p))==runtime$r_packages[[p]],logical(1))))
m<-jsonlite::fromJSON(args[1],simplifyVector=FALSE)
worker<-as.integer(args[4]);workers<-as.integer(args[5]);stopifnot(worker>=1,worker<=workers)
for(i in seq_along(m$jobs))if((i-1L)%%workers==worker-1L){
 job<-m$jobs[[i]]
 path<-file.path(args[2],'plans',paste0(job$issue,'.json.gz'))
 if(args[6]=='freeze')joint_payout_freeze_issue(job,m$config,args[3],path) else {
  stopifnot(args[6]=='verify')
  reticulate::use_python(args[3],required=TRUE)
  reader<-reticulate::import('src.strategy_diagnostic_inputs',convert=TRUE)
  b<-jsonlite::fromJSON(reader$read_verified_bundle_json(job$path,job$sha256),simplifyVector=FALSE)
  plan<-jsonlite::fromJSON(gzfile(path),simplifyVector=FALSE)
  joint_payout_verify_metrics(b,plan,m$config,args[3])
 }
 cat(args[6],' ',i,'/',length(m$jobs),' issue ',job$issue,'\n',sep='');flush.console()
}
