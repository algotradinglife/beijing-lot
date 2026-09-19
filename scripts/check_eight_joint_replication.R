# Exact selected-state replication against the two original JOINT freezes.
# Usage: Rscript FILE NEW_RECEIPT OLD_MAIN_RECEIPT OLD_STRUCTURE_RECEIPT OUTPUT
# No target labels or purchase implementation imports.
args<-commandArgs(TRUE);stopifnot(length(args)==4,!file.exists(args[4]))
receipts<-lapply(args[1:3],jsonlite::fromJSON,simplifyVector=FALSE)
stopifnot(all(vapply(receipts,function(x)x$status=='FROZEN_NOT_SETTLED',logical(1))))
current<-receipts[[1]];old<-receipts[[2]];structure<-receipts[[3]]
stopifnot(identical(old$scope,structure$scope))
issues<-unlist(old$scope)
stopifnot(all(issues %in% names(current$bindings)))
checked<-0L
for(id in issues) {
 records<-list()
 for(k in seq_along(receipts)) {
  binding<-receipts[[k]]$bindings[[id]]
  path<-if(k==1)binding$path else file.path(dirname(args[k]),binding$file)
  stopifnot(digest::digest(file=path,algo='sha256')==binding$sha256)
  z<-readRDS(path)
  stopifnot(identical(z$seal,digest::digest(z[names(z)!='seal'],algo='sha256')),z$issue==id)
  records[[k]]<-z
 }
 stopifnot(identical(records[[1]]$fixtures,records[[2]]$fixtures),
  identical(records[[1]]$cutoffs,records[[2]]$cutoffs),
  identical(records[[1]]$cutoffs,records[[3]]$cutoffs))
 for(policy in c('JOINT','DEPTH_OPEN','U4','CONFIDENCE')) {
  source<-if(policy=='CONFIDENCE')records[[3]] else records[[2]]
  a<-records[[1]]$arms[[policy]]$options;b<-source$arms[[policy]]$options
  stopifnot(length(a)==length(b))
  for(j in seq_along(a))for(field in c('sleeve_id','fixtures','state_ids','stake'))
   stopifnot(identical(a[[j]][[field]],b[[j]][[field]]))
  checked<-checked+1L
 }
 if(checked%%400L==0L)message('REPLICATED ',checked,' plans')
}
jsonlite::write_json(list(status='PASS',issues=length(issues),plans=checked,
 inputs=setNames(lapply(args[1:3],function(p)digest::digest(file=p,algo='sha256')),args[1:3]),
 scope='Exact fixtures, cutoffs, selected groups, canonical state IDs and stakes; no settlement'),
 args[4],auto_unbox=TRUE,pretty=TRUE)
