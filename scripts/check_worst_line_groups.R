# Independent ticket settlement replay; no allocator/settlement helper used.
args<-commandArgs(TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);out<-cfg$output
receipt<-jsonlite::fromJSON(file.path(out,'receipt.json'))
for(n in names(receipt$files))stopifnot(digest::digest(file=file.path(out,n),algo='sha256')==receipt$files[[n]])
for(n in names(receipt$code))stopifnot(digest::digest(file=file.path(cfg$repository_root,n),algo='sha256')==receipt$code[[n]])
manifest<-jsonlite::fromJSON(cfg$manifest)
labels<-do.call(rbind,lapply(seq_len(nrow(manifest$labels)),function(i){p<-manifest$labels$path[i];stopifnot(digest::digest(file=p,algo='sha256')==manifest$labels$sha256[i]);read.csv(p,colClasses=c(issue='character',provider_id='character'))[,c('issue','slot','provider_id','handicap','actual_direction','spf_sp')]}))
x<-read.csv(file.path(out,'periods.csv'),colClasses=c(issue='character'))
freeze<-jsonlite::fromJSON(file.path(out,'freeze.json'),simplifyVector=FALSE)
checked<-0L
for(id in names(freeze$bindings)){
 b<-freeze$bindings[[id]];stopifnot(digest::digest(file=b$path,algo='sha256')==b$sha256)
 plans<-readRDS(b$path)
 for(policy in names(plans)){
  p<-plans[[policy]];f<-p$fixtures
  k<-paste(f$issue,f$slot,f$provider_id,f$handicap);lk<-paste(labels$issue,labels$slot,labels$provider_id,labels$handicap)
  stopifnot(!anyDuplicated(lk));j<-match(k,lk);stopifnot(!anyNA(j));l<-labels[j,]
  hits<-0L;gross<-0
  for(i in seq_len(nrow(p$tickets))){t<-p$tickets[i,];ix<-p$groups$fixture_index[p$groups$group_id==t$group_id];stopifnot(length(ix)==7)
   digits<-match(l$actual_direction[ix],c('W','D','L'))-1L
   state<-0L;for(v in digits)state<-3L*state+v
   if(t$state_id==state+1L){hits<-hits+1L;gross<-gross+2*0.65*prod(l$spf_sp[ix])}
  }
  z<-x[x$issue==id & x$policy==policy,];stopifnot(nrow(z)==1,z$stake==2*nrow(p$tickets),z$hits==hits,abs(z$gross-gross)<1e-7)
  checked<-checked+nrow(p$tickets)
 }
}
stopifnot(all(abs(x$net_change-x$saved_stake-x$return_change)<1e-7))
cat('PASS:',length(freeze$bindings),'issues;',checked,'tickets independently settled\n')
