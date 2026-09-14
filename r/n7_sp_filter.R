# Fixed, prediction-only fixture SP gate. No fitting, labels, RNG or I/O.
# base: validated capital options with 1-based option fixture indices. partition:
# core/opportunity admission with exact cutoff map. minimum_sp: finite >=1,
# decimal price 1/q at probability Top1 (ties W,D,L). Remove SP strictly below
# threshold. Return filtered partition plus fixture/group diagnostic tibbles;
# preserve fixture indices, probabilities and option order. Missing/invalid input
# or mismatched cutoffs fails. Entirely filtered pools are valid and retain cash.
n7_sp_filter <- function(base, partition, cutoffs, minimum_sp) {
  stopifnot(identical(base$cutoffs,cutoffs),identical(partition$cutoffs,cutoffs),
    length(cutoffs)>0,length(minimum_sp)==1,is.numeric(minimum_sp),
    is.finite(minimum_sp),minimum_sp>=1,length(base$fixtures)>0)
  fixtures <- dplyr::bind_rows(lapply(seq_along(base$fixtures),function(i) {
    f<-base$fixtures[[i]];p<-unlist(f[c('p_W','p_D','p_L')],use.names=FALSE)
    q<-unlist(f[c('q_W','q_D','q_L')],use.names=FALSE)
    stopifnot(length(p)==3,length(q)==3,all(is.finite(p)),all(is.finite(q)),
      all(p>=0),all(q>0),all(q<=1),abs(sum(p)-1)<1e-8,abs(sum(q)-1)<1e-8)
    k<-which.max(p);sp<-1/q[k]
    tibble::tibble(fixture_index=i,top1=c('W','D','L')[k],probability=p[k],
      estimated_sp=sp,eligible=sp>=minimum_sp)
  }))
  groups <- dplyr::bind_rows(lapply(base$options,function(o) {
    ix<-o$fixtures
    stopifnot(length(ix)==7,!anyDuplicated(ix),all(is.finite(ix)),
      all(ix==floor(ix)),all(ix>=1 & ix<=nrow(fixtures)))
    tibble::tibble(sleeve_id=as.character(o$sleeve_id),
      eligible=all(fixtures$eligible[ix]),min_sp=min(fixtures$estimated_sp[ix]))
  })) |> dplyr::distinct()
  stopifnot(!anyDuplicated(groups$sleeve_id),
    all(as.character(c(partition$core_ids,partition$opportunity_ids)) %in% groups$sleeve_id))
  keep<-groups$sleeve_id[groups$eligible]
  out<-partition
  out$core_ids<-out$core_ids[as.character(out$core_ids) %in% keep]
  out$opening_depths<-out$opening_depths[names(out$opening_depths) %in% as.character(out$core_ids)]
  out$opportunity_ids<-out$opportunity_ids[as.character(out$opportunity_ids) %in% keep]
  out$opportunity_stake_cny<-length(out$opportunity_ids)*out$opportunity_depth*2
  list(partition=out,fixtures=fixtures,groups=groups,minimum_sp=minimum_sp,
    cutoffs=cutoffs,historical_admission=FALSE)
}

# Partition fixed policies into exact deterministic equivalence classes within
# ONE issue/cutoff. No cache, historical learning or cross-issue reuse. Each
# class retains all original row IDs; equality requires identical admitted
# partition, mode, objective and allocation order. Gate ledgers remain per row.
# Returns gates and integer row-index classes; invalid policy columns fail.
n7_sp_policy_groups <- function(base,partition,cutoffs,policies) {
  stopifnot(is.data.frame(policies),nrow(policies)>0,
    all(c('id','minimum_sp','mode','objective','allocation_order') %in% names(policies)),
    !anyNA(policies),!anyDuplicated(policies$id))
  thresholds<-unique(policies$minimum_sp)
  gate_values<-lapply(thresholds,function(t)n7_sp_filter(base,partition,cutoffs,t))
  gates<-gate_values[match(policies$minimum_sp,thresholds)]
  classes<-list();descriptors<-list()
  for(i in seq_len(nrow(policies))) {
    descriptor<-list(partition=gates[[i]]$partition,mode=policies$mode[i],
      objective=policies$objective[i],allocation_order=policies$allocation_order[i])
    found<-which(vapply(descriptors,identical,logical(1),y=descriptor))
    if(length(found))classes[[found[1]]]<-c(classes[[found[1]]],i)
    else {descriptors[[length(descriptors)+1L]]<-descriptor;classes[[length(classes)+1L]]<-i}
  }
  stopifnot(identical(sort(unlist(classes)),seq_len(nrow(policies))))
  list(gates=gates,classes=classes,cutoffs=cutoffs)
}
