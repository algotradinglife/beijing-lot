# Refill filtered candidate sets using frozen Top2-weighted sampling. base and
# partition are validated capital inputs; cutoffs must match both. Indices are
# 1-based and retained IDs unchanged. Returns groups, admission ledger and attempt
# count; bounded shortfalls/empty pools are explicit. No labels, fitting or I/O.
# Seed is local (withr restores the caller RNG). Invalid contracts stop.
n7_sp_refill <- function(base, partition, cutoffs, minimum_sp, candidate_count,
                         seed, maximum_attempts, n) {
  stopifnot(n==7, length(n)==1, length(candidate_count)==1,
    is.finite(candidate_count),candidate_count>=1,candidate_count==floor(candidate_count),
    length(seed)==1,is.finite(seed),seed>=0,seed<=.Machine$integer.max,seed==floor(seed),
    length(maximum_attempts)==1,is.finite(maximum_attempts),maximum_attempts>=1,
    maximum_attempts==floor(maximum_attempts))
  gate<-n7_sp_filter(base,partition,cutoffs,minimum_sp)
  original<-base$options[!duplicated(vapply(base$options,`[[`,numeric(1),'sleeve_id'))]
  stopifnot(length(original)<=candidate_count)
  groups<-lapply(original,function(o)list(sleeve_id=o$sleeve_id,
    fixtures=o$fixtures,origin='RETAINED'))
  keys<-vapply(groups,function(g)paste(sort(g$fixtures),collapse=','),character(1))
  stopifnot(!anyDuplicated(keys))
  groups<-groups[gate$groups$eligible[match(vapply(groups,function(g)as.character(g$sleeve_id),character(1)),gate$groups$sleeve_id)]]
  eligible<-gate$fixtures$fixture_index[gate$fixtures$eligible]
  weights<-vapply(base$fixtures[eligible],function(f)
    sum(sort(unlist(f[c('p_W','p_D','p_L')]),decreasing=TRUE)[1:2]),numeric(1))
  limit<-if(length(eligible)<n)0 else min(candidate_count,choose(length(eligible),n))
  next_id<-max(vapply(original,`[[`,numeric(1),'sleeve_id'))+1
  attempts<-0L
  withr::with_seed(seed, {
    while(length(groups)<limit && attempts<maximum_attempts) {
      attempts<-attempts+1L
      ix<-sort(eligible[sample.int(length(eligible),n,replace=FALSE,prob=weights)])
      key<-paste(ix,collapse=',')
      seen<-vapply(groups,function(g)paste(sort(g$fixtures),collapse=','),character(1))
      if(!key %in% seen) {
        groups[[length(groups)+1L]]<-list(sleeve_id=next_id,fixtures=ix,origin='REFILL_TOP2')
        next_id<-next_id+1
      }
    }
  })
  list(groups=groups,fixtures=gate$fixtures,attempts=attempts,
    requested=candidate_count,actual=length(groups),cutoffs=cutoffs,
    status=if(length(groups)==candidate_count)'COMPLETE' else 'BOUNDED_SHORTFALL',
    historical_admission=FALSE)
}
