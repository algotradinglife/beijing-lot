# Replay the shared R sampler from explicit frozen fixture probabilities/seeds.
# JSON request on stdin; JSON matrices on stdout. No labels or filesystem writes.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1L)
source(file.path(args[1],'r/n7_joint_sleeves.R'))
x<-jsonlite::fromJSON(paste(readLines(file('stdin'),warn=FALSE),collapse='\n'),simplifyVector=FALSE)
bundle<-jsonlite::fromJSON(gzfile(x$bundle),simplifyVector=FALSE)
stopifnot(identical(bundle$cutoffs,x$cutoffs))
pool<-list(fixtures=bundle$expanded_pool$fixtures,cutoffs=x$cutoffs)
RNGkind('Mersenne-Twister','Inversion','Rejection')
result<-lapply(x$seeds,function(seed)list(
 train=n7_joint_worlds(pool,x$cutoffs,seed,x$allocation_worlds),
 evaluation=n7_joint_worlds(pool,x$cutoffs,seed+x$evaluation_seed_offset,x$evaluation_worlds)))
names(result)<-as.character(unlist(x$seeds))
cat(jsonlite::toJSON(result,auto_unbox=TRUE,digits=NA))
