# First reuse the independent direct settlement replay, then independently
# check purchased states against frozen original enumeration and declared scores.
source('scripts/check_worst_line_groups.R')
features<-read.csv(file.path(out,'fixture-features.csv'),colClasses=c(issue='character',provider_id='character'))
policies<-data.frame(policy=c('BASE','WEAK_HALF','WEAK_DROP','STRONG_HALF','STRONG_DROP','ALL_DROP'),minimum=c(.5,.5,.5,1,1,0),weight=c(1,.5,0,.5,0,0))
ng<-0L
for(id in names(freeze$bindings)){
 ref<-freeze$bindings[[id]];stopifnot(digest::digest(file=ref$bundle_path,algo='sha256')==ref$bundle_sha256)
 con<-if(grepl('\\.gz$',ref$bundle_path))gzfile(ref$bundle_path) else file(ref$bundle_path)
 b<-jsonlite::fromJSON(paste(readLines(con,warn=FALSE),collapse='\n'),simplifyVector=FALSE);close(con)
 plans<-readRDS(ref$path)
 for(policy in names(plans)){
  plan<-plans[[policy]];cfgp<-policies[policies$policy==policy,];f<-plan$fixtures
  j<-match(paste(f$issue,f$slot,f$provider_id),paste(features$issue,features$slot,features$provider_id));stopifnot(!anyNA(j));ev<-features[j,]
  ranks<-apply(as.matrix(f[c('p_W','p_D','p_L')]),1,function(z)order(-z,seq_along(z)))
  third<-ranks[3,];treated<-if(cfgp$minimum==0)rep(TRUE,nrow(f)) else ev$degree>=cfgp$minimum & ev$signal %in% c('W','L')
  for(gid in unique(plan$tickets$group_id)){
   g<-b$sleeves[[which(vapply(b$sleeves,function(g)g$id,numeric(1))==gid)]]
   states<-matrix(as.integer(unlist(g$enumeration$states)),nrow=2187,byrow=TRUE)+1L
   ix<-as.integer(unlist(g$fixture_indices))+1L
   score<-as.numeric(unlist(g$enumeration$probability));count<-rep(0L,2187)
   for(k in 1:7)if(treated[ix[k]])count<-count+as.integer(states[,k]==third[ix[k]])
   score<-score*cfgp$weight^count
   order_ids<-order(-score,seq_along(score));allowed<-order_ids[score[order_ids]>0]
   bought<-plan$tickets$state_id[plan$tickets$group_id==gid]
   stopifnot(setequal(bought,head(allowed,length(bought))))
   if(cfgp$weight==0)stopifnot(all(count[bought]==0))
   ng<-ng+1L
  }
 }
}
cat('PASS:',ng,'selected group supports/rankings independently verified\n')
