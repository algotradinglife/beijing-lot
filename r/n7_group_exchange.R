# Fixed-neighborhood local search on BREADTH prefixes. Explicit matching cutoff
# maps, initial option indices, CNY budget, and maximum additions (1 or 2).
# Mandatory opportunity options cannot be removed. Each accepted move strictly
# increases covered scenario count, hence at most nrow(hits) moves. Ties use
# total estimated net, lower stake, sorted numeric sleeve IDs. No fitting, RNG,
# labels, IO, depth changes or new options. Returns selected indices, shared
# metrics and accepted-move ledger. Invalid contracts fail; empty pools hold cash.
n7_group_exchange <- function(pool,scenarios,cutoffs,initial,budget_cny,max_add) {
  stopifnot(length(cutoffs)>0,pool$mode=='BREADTH',length(max_add)==1,max_add %in% c(1L,2L),
    length(budget_cny)==1,is.finite(budget_cny),budget_cny>=0,budget_cny%%2==0)
  n7_capital_evaluate(pool,initial,scenarios,cutoffs,budget_cny)
  opts<-pool$options;k<-length(opts)
  ids<-vapply(opts,function(o)o$sleeve_id,numeric(1))
  costs<-vapply(opts,function(o)o$stake,numeric(1))
  expected<-vapply(opts,function(o)o$expected_gross,numeric(1))
  stopifnot(!anyDuplicated(ids),all(is.finite(ids)),all(ids>=0 & ids<1e10 & ids==floor(ids)),
    all(is.finite(costs)),all(costs>0 & costs%%2==0),all(is.finite(expected)),all(expected>=0),
    all(vapply(opts,function(o)o$unit_copies==1,logical(1))),
    !anyDuplicated(pool$opening_options),!anyDuplicated(pool$opportunity_options),
    all(c(pool$opening_options,pool$opportunity_options) %in% seq_len(k)),
    all(pool$opportunity_options %in% initial),
    all(initial %in% c(pool$opening_options,pool$opportunity_options)))
  selected<-initial;ledger<-list();hit<-scenarios$hits
  for(step in seq_len(nrow(hit)+1L)) {
    old_count<-sum(rowSums(hit[,selected,drop=FALSE])>0)
    available<-setdiff(pool$opening_options,selected)
    additions<-as.list(available)
    if(max_add==2 && length(available)>=2)additions<-c(additions,utils::combn(available,2,simplify=FALSE))
    removable<-c(0L,setdiff(selected,pool$opportunity_options))
    moves<-list();plans<-list()
    for(remove in removable)for(add in additions) {
      candidate<-c(setdiff(selected,remove),add)
      stake<-sum(costs[candidate]);if(stake>budget_cny)next
      count<-sum(rowSums(hit[,candidate,drop=FALSE])>0)
      if(count<=old_count)next
      j<-length(moves)+1L;plans[[j]]<-candidate
      moves[[j]]<-tibble::tibble(index=j,removed=remove,added=paste(add,collapse=','),
        covered=count,stake=stake,expected_net=sum(expected[candidate]-costs[candidate]),
        identity=paste(sprintf('%010.0f',sort(ids[candidate])),collapse=','))
    }
    if(!length(moves))break
    scores<-dplyr::bind_rows(moves)
    chosen<-order(-scores$covered,-scores$expected_net,scores$stake,scores$identity)[1]
    row<-scores[chosen,]
    ledger[[length(ledger)+1L]]<-row |> dplyr::mutate(step=step,previous_covered=old_count,
      gain_worlds=covered-old_count,previous_stake=sum(costs[selected]),
      removed_id=if(removed==0)NA_real_ else ids[removed],
      added_ids=paste(ids[as.integer(strsplit(added,',',fixed=TRUE)[[1]])],collapse=','))
    selected<-plans[[row$index]]
  }
  list(selected=selected,metrics=n7_capital_evaluate(pool,selected,scenarios,cutoffs,budget_cny),
    actions=dplyr::bind_rows(ledger),stop_reason='NO_STRICTLY_IMPROVING_EXCHANGE',
    cutoffs=cutoffs,max_add=max_add,historical_admission=FALSE)
}
