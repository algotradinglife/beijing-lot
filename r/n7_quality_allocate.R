# Fixed quality-band selection over existing BREADTH opening prefixes.
# pool/scenarios use shared capital contracts; explicit matching cutoff maps.
# quality_fraction in (0,1] is a relative coverage/CNY floor among currently
# affordable unopened groups. selector UNION or OVERLAP; no fitting, labels,
# RNG, IO, new groups, depth changes or copies. Returns shared metrics, selected
# indices, complete candidate trace and cash. Opportunity initialization remains
# unchanged. Missing/invalid contracts fail; exhausted/empty pools retain cash.
n7_quality_allocate <- function(pool,scenarios,cutoffs,budget_cny,quality_fraction,selector) {
  stopifnot(identical(pool$cutoffs,cutoffs),identical(scenarios$cutoffs,cutoffs),
    length(cutoffs)>0,pool$mode=='BREADTH',selector %in% c('UNION','OVERLAP'),
    length(quality_fraction)==1,is.finite(quality_fraction),quality_fraction>0,quality_fraction<=1,
    length(budget_cny)==1,is.finite(budget_cny),budget_cny>=0,budget_cny%%2==0)
  n7_capital_evaluate(pool,integer(),scenarios,cutoffs,budget_cny)
  opts<-pool$options
  ids<-vapply(opts,function(o)o$sleeve_id,numeric(1))
  costs<-vapply(opts,function(o)o$stake,numeric(1))
  coverage<-vapply(opts,function(o)o$coverage,numeric(1))
  expected<-vapply(opts,function(o)o$expected_gross,numeric(1))
  stopifnot(!anyDuplicated(ids),all(is.finite(ids)),all(is.finite(costs)),all(costs>0 & costs%%2==0),
    all(is.finite(coverage)),all(coverage>=0 & coverage<=1),
    all(is.finite(expected)),all(expected>=0),
    all(vapply(opts,function(o)o$unit_copies==1,logical(1))),
    all(scenarios$hits %in% c(0,1)))
  for(o in opts)stopifnot(length(o$fixtures)==7,!anyDuplicated(o$fixtures),
    all(is.finite(o$fixtures)),all(o$fixtures>=1 & o$fixtures==floor(o$fixtures)))
  selected<-pool$opportunity_options
  n7_capital_evaluate(pool,selected,scenarios,cutoffs,budget_cny)
  trace<-list()
  for(step in seq_len(length(opts)+1L)) {
    cash<-budget_cny-sum(costs[selected])
    candidates<-setdiff(pool$opening_options,selected)
    candidates<-candidates[costs[candidates]<=cash]
    if(!length(candidates))break
    covered<-rowSums(scenarios$hits[,selected,drop=FALSE])>0
    efficiency<-coverage[candidates]/costs[candidates]
    admitted<-efficiency>=quality_fraction*max(efficiency)
    scores<-dplyr::bind_rows(lapply(seq_along(candidates),function(k) {
      j<-candidates[k]
      overlaps<-vapply(selected,function(old)length(intersect(opts[[j]]$fixtures,opts[[old]]$fixtures)),numeric(1))
      tibble::tibble(option=j,sleeve_id=ids[j],stake=costs[j],efficiency=efficiency[k],
        eligible=admitted[k],
        marginal_union=mean(!covered & scenarios$hits[,j]>0),
        max_overlap=if(length(overlaps))max(overlaps) else 0,
        mean_overlap=if(length(overlaps))mean(overlaps) else 0,
        value_rate=(expected[j]-costs[j])/costs[j])
    }))
    eligible<-which(scores$eligible);s<-scores[eligible,]
    ranked<-if(selector=='UNION')order(-s$marginal_union/s$stake,-s$value_rate,-s$efficiency,s$sleeve_id) else
      order(s$max_overlap,s$mean_overlap,-s$marginal_union/s$stake,-s$efficiency,s$sleeve_id)
    chosen<-s$option[ranked[1]]
    trace[[step]]<-scores |> dplyr::mutate(step=step,cash_before=cash,chosen=option==chosen)
    selected<-c(selected,chosen)
  }
  list(selected=selected,metrics=n7_capital_evaluate(pool,selected,scenarios,cutoffs,budget_cny),
    candidates=dplyr::bind_rows(trace),stop_reason='NO_AFFORDABLE_UNOPENED_GROUP',
    quality_fraction=quality_fraction,selector=selector,cutoffs=cutoffs,historical_admission=FALSE)
}
