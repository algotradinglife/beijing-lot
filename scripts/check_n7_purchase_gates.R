# Independent eligibility audit: enumerate from fixture probabilities, never call
# the production shape/filter helpers and never open settlement labels.
args<-commandArgs(TRUE);main<-args[1];structure<-args[2];output<-args[3]
m<-jsonlite::fromJSON(file.path(main,'plans-receipt.json'),simplifyVector=FALSE)
s<-jsonlite::fromJSON(file.path(structure,'plans-receipt.json'),simplifyVector=FALSE)
stopifnot(s$parent_receipt_sha256==digest::digest(file=file.path(main,'plans-receipt.json'),algo='sha256'))
checked<-0L
for(id in unlist(s$scope)) {
 mb<-m$bindings[[id]];sb<-s$bindings[[id]]
 mp<-file.path(main,mb$file);sp<-file.path(structure,sb$file)
 stopifnot(digest::digest(file=mp,algo='sha256')==mb$sha256,digest::digest(file=sp,algo='sha256')==sb$sha256)
 old<-readRDS(mp);new<-readRDS(sp);base<-old$arms$JOINT$pool
 ids<-vapply(base$options,`[[`,numeric(1),'sleeve_id');unique_ids<-unique(ids)
 mass<-cost<-core<-opportunity<-numeric(length(unique_ids))
 for(j in seq_along(unique_ids)) {
  option<-base$options[[match(unique_ids[j],ids)]];prob<-rep(1,2187)
  for(k in 1:7) {
   f<-base$fixtures[[option$fixtures[k]]];p<-c(f$p_W,f$p_D,f$p_L);ranked<-sort(p,decreasing=TRUE)
   prob<-prob*p[((0:2186 %/% 3^(7-k))%%3)+1L]
   core[j]<-core[j]+as.integer(ranked[1]>=.55 && ranked[2]-ranked[3]>=.05)
   opportunity[j]<-opportunity[j]+as.integer(ranked[1]<.4)
  }
  cumulative<-cumsum(sort(prob,decreasing=TRUE));mass[j]<-cumulative[64]
  cost[j]<-2*which(cumulative>=.25)[1]
 }
 reference<-if(length(cost))median(cost) else NA_real_
 for(arm in names(new$arms)) {
  p<-new$policies[new$policies$id==arm,];actual<-new$arms[[arm]]$pool
  expected<-unique_ids[mass>=p$minimum_mass & core>=p$minimum_core & opportunity<=p$max_opportunity & cost<=reference*p$ratio & cost>=reference/p$ratio]
  ix<-which(ids %in% expected)
  stopifnot(identical(actual$options,base$options[ix]),
   identical(actual$opening_options,match(intersect(base$opening_options,ix),ix)),
   setequal(actual$group_gate$admitted_ids,expected))
  checked<-checked+1L
 }
}
jsonlite::write_json(list(status='PASS',issues=length(s$scope),gates=checked,
 main_receipt_sha256=digest::digest(file=file.path(main,'plans-receipt.json'),algo='sha256'),
 structure_receipt_sha256=digest::digest(file=file.path(structure,'plans-receipt.json'),algo='sha256'),
 scope='Independent full-state head mass, coverage cost, fixture role and option/opening membership; no labels'),output,pretty=TRUE,auto_unbox=TRUE)
