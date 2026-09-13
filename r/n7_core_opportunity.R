# #433 prediction-only curve features and explicit core/opportunity partitions.
# Native fixture Cutoff validation belongs to n7_joint_validate at the input
# boundary; these functions require its exact map and do not fit history.

# surface: n7_sleeve_tables output. Costs CNY, probabilities fractions, entropy
# nats. Returns a sleeve tibble bound to the supplied cutoff identity. No I/O.
n7_core_curve_features <- function(surface,cutoffs,expected_cutoffs,targets,unit_cny) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,
    unit_cny==2,all(is.finite(targets)),all(targets>0 & targets<=1),
    length(targets)>0,!anyDuplicated(targets))
  curves<-n7_capital_curves(surface,cutoffs,expected_cutoffs,unit_cny)
  base<-tibble::as_tibble(surface$summary)
  stopifnot(!anyDuplicated(base$sleeve_id),
    setequal(as.character(base$sleeve_id),rownames(surface$prob_mat)),
    all(is.finite(base$entropy)),all(base$entropy>=0))
  rows<-lapply(seq_len(nrow(base)),function(j) {
    id<-as.character(base$sleeve_id[j]);z<-curves[as.character(curves$sleeve_id)==id,]
    z<-z[order(z$depth),];p<-diff(z$coverage)
    result<-tibble::tibble(sleeve_id=base$sleeve_id[j],origin=base$origin[j],
      entropy=base$entropy[j],effective_states=exp(base$entropy[j]),
      normalized_entropy=base$entropy[j]/log(2187),
      expected_rank_cost_cny=sum(p*unit_cny*(1:2187)))
    for(k in c(15,32,64,128,256)) {
      selected<-z[z$depth==k,]
      result[[paste0('coverage_',k)]]<-selected$coverage
      result[[paste0('expected_net_',k)]]<-selected$expected_net
      result[[paste0('expected_roi_',k)]]<-selected$expected_roi
    }
    result$gain_64_to_128<-result$coverage_128-result$coverage_64
    for(t in targets) {
      # Shared exact threshold contract, including the tau=1 convention.
      resolved<-n7_capital_resolve(z,'coverage',setNames(t,id),4374,1e-12,cutoffs,expected_cutoffs)
      name<-paste0('target_',format(t,scientific=FALSE),'_cost_cny')
      result[[name]]<-resolved$total_stake
    }
    result
  })
  out<-dplyr::bind_rows(rows);attr(out,'cutoffs')<-cutoffs;out
}

# Fixed policy partition: core ranks by Top64 mass, tie by expected net and ID.
# Opportunity ranks remaining groups by Top15 mass or Top15 expected net, then
# the other metric and ID. Flat groups receive no automatic positive-value label.
# Cap is an upper bound: unfillable remainder stays in core budget, not fabricated
# opportunities. Returns disjoint IDs, fixed opportunity cost and full rank ledger.
n7_core_partition <- function(features,cutoffs,expected_cutoffs,core_count,
                              opportunity_cap_cny,group_cap_cny,unit_cny,rule,core_open_coverage) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,
    identical(attr(features,'cutoffs'),cutoffs),
    !anyDuplicated(features$sleeve_id),unit_cny==2,group_cap_cny==30,
    core_count>=1,core_count==floor(core_count),core_count<=nrow(features),
    is.finite(opportunity_cap_cny),opportunity_cap_cny>=0,
    opportunity_cap_cny%%unit_cny==0,rule %in% c('PROB','VALUE'),
    all(is.finite(as.matrix(features[c('coverage_64','coverage_15','expected_net_64','expected_net_15')]))))
  target_name<-paste0('target_',format(core_open_coverage,scientific=FALSE),'_cost_cny')
  stopifnot(core_open_coverage>0,core_open_coverage<=1,target_name %in% names(features),
    all(is.finite(features[[target_name]])),all(features[[target_name]]>0),
    all(features[[target_name]]%%unit_cny==0))
  order_core<-order(-features$coverage_64,-features$expected_net_64,features$sleeve_id)
  core<-order_core[seq_len(core_count)];other<-setdiff(seq_len(nrow(features)),core)
  score<-if(rule=='PROB')features$coverage_15 else features$expected_net_15
  tie<-if(rule=='PROB')features$expected_net_15 else features$coverage_15
  ranked<-other[order(-score[other],-tie[other],features$sleeve_id[other])]
  count<-min(length(ranked),floor(opportunity_cap_cny/group_cap_cny))
  opportunity<-head(ranked,count)
  ledger<-features;ledger$core_rank<-match(seq_len(nrow(features)),order_core)
  ledger$opportunity_rank<-match(seq_len(nrow(features)),ranked)
  ledger$role<-ifelse(seq_len(nrow(features)) %in% core,'CORE',
    ifelse(seq_len(nrow(features)) %in% opportunity,'OPPORTUNITY','UNFUNDED_CANDIDATE'))
  list(core_ids=features$sleeve_id[core],
    opening_depths=stats::setNames(features[[target_name]][core]/unit_cny,as.character(features$sleeve_id[core])),opportunity_ids=features$sleeve_id[opportunity],
    opportunity_depth=as.integer(group_cap_cny/unit_cny),
    opportunity_stake_cny=count*group_cap_cny,ledger=ledger,cutoffs=cutoffs,
    historical_admission=FALSE,rule=rule)
}

# Build legal options; core opening depths are exact coverage-target crossings.
# MULTIPLY buys copies of that initial prefix, not larger prefixes. No I/O.
n7_core_option_pool <- function(base,partition,cutoffs,mode,max_copies) {
  stopifnot(identical(base$cutoffs,cutoffs),identical(partition$cutoffs,cutoffs),
    mode %in% c('BREADTH','DEPTH','MULTIPLY'),length(max_copies)==1,
    is.finite(max_copies),max_copies>=1,max_copies==floor(max_copies),
    !anyDuplicated(partition$core_ids),!anyDuplicated(partition$opportunity_ids),
    !length(intersect(partition$core_ids,partition$opportunity_ids)))
  out<-base;out$options<-list();opening<-integer();opportunity<-integer()
  for(o in base$options) {
    id<-as.character(o$sleeve_id)
    core<-o$sleeve_id %in% partition$core_ids
    opp<-o$sleeve_id %in% partition$opportunity_ids
    depth<-if(core)partition$opening_depths[[id]] else partition$opportunity_depth
    if(!core && !opp)next
    keep<-if(core && mode=='DEPTH')o$depth>=depth else o$depth==depth
    if(!keep)next
    stopifnot(o$stake==2*o$depth)
    copies<-if(core && mode=='MULTIPLY')seq_len(max_copies) else 1L
    for(m in copies) {
      z<-o;z$unit_copies<-m;z$role<-if(core)'CORE' else 'OPPORTUNITY'
      z$stake<-o$stake*m;z$expected_gross<-o$expected_gross*m
      z$state_payout<-o$state_payout*m
      out$options[[length(out$options)+1L]]<-z
      if(core && o$depth==depth && m==1)opening<-c(opening,length(out$options))
      if(opp)opportunity<-c(opportunity,length(out$options))
    }
  }
  stopifnot(length(opening)==length(partition$core_ids),
    length(opportunity)==length(partition$opportunity_ids),
    !anyDuplicated(vapply(out$options,function(o)paste(o$sleeve_id,o$depth,o$unit_copies),character(1))))
  out$opening_options<-opening;out$opportunity_options<-opportunity
  out$mode<-mode;out
}

# Sequential breadth-first allocator on shared prediction scenarios. Budget is an
# upper bound in CNY; expected_net scores marginal expected net per added CNY.
# any_hit scores marginal union probability per CNY, with expected value ties.
# All affordable unopened core prefixes must be bought before depth or copies.
# Returns selected option indices, model accounting, action/stop audit and cash.
# No actual results, history fitting, persistence or randomness are introduced.
n7_core_allocate <- function(pool,scenarios,cutoffs,budget_cny,objective,max_actions) {
  stopifnot(identical(pool$cutoffs,cutoffs),identical(scenarios$cutoffs,cutoffs),
    objective %in% c('any_hit','expected_net'),budget_cny>=0,budget_cny%%2==0,
    is.finite(budget_cny),is.finite(max_actions),max_actions>=1,max_actions==floor(max_actions),
    pool$mode %in% c('BREADTH','DEPTH','MULTIPLY'))
  # Shared accounting boundary validates scenario dimensions, values and budget.
  n7_capital_evaluate(pool,integer(),scenarios,cutoffs,budget_cny)
  opts<-pool$options
  ids<-vapply(opts,function(o)o$sleeve_id,numeric(1))
  stake<-vapply(opts,function(o)o$stake,numeric(1))
  expected<-vapply(opts,function(o)o$expected_gross,numeric(1))
  copies<-vapply(opts,function(o)o$unit_copies,numeric(1))
  depth<-vapply(opts,function(o)o$depth,numeric(1))
  stopifnot(all(is.finite(stake)),all(stake>0),all(stake%%2==0),
    all(is.finite(expected)),all(expected>=0),
    all(pool$opening_options %in% seq_along(opts)),
    all(pool$opportunity_options %in% seq_along(opts)))
  selected<-pool$opportunity_options
  initial<-n7_capital_evaluate(pool,selected,scenarios,cutoffs,budget_cny)
  ledger<-list();opening_stop<-NULL;stop_reason<-NULL
  for(step in seq_len(max_actions)) {
    # Boundary validation above is once per allocation. Candidate scoring needs
    # only union events and exact linear value, not full risk tables per trial.
    current_stake<-sum(stake[selected])
    current_events<-rowSums(scenarios$hits[,selected,drop=FALSE])
    current<-list(cash=budget_cny-current_stake,stake=current_stake,
      any_hit=mean(current_events>0),expected_net=sum(expected[selected])-current_stake)
    unopened<-pool$opening_options[!ids[pool$opening_options] %in% ids[selected]]
    affordable<-unopened[stake[unopened]<=current$cash]
    if(length(affordable)) {
      candidates<-affordable;phase<-'OPEN'
    } else {
      if(is.null(opening_stop))opening_stop<-if(length(unopened))'NO_AFFORDABLE_NEW_CORE' else 'ALL_CORE_OPEN'
      if(pool$mode=='BREADTH') {stop_reason<-'BREADTH_COMPLETE';break}
      candidates<-which(ids %in% ids[selected] & !seq_along(opts) %in% selected)
      candidates<-candidates[vapply(candidates,function(j) {
        old<-selected[ids[selected]==ids[j]]
        opts[[j]]$role=='CORE' && length(old)==1 &&
          stake[j]>stake[old] && stake[j]-stake[old]<=current$cash &&
          if(pool$mode=='DEPTH')depth[j]>depth[old] else
            (depth[j]==depth[old] && copies[j]==copies[old]+1)
      },logical(1))]
      phase<-pool$mode
      if(!length(candidates)) {stop_reason<-'NO_AFFORDABLE_LEGAL_ACTION';break}
    }
    # Evaluate counterfactual actions only against frozen model worlds.
    scores<-lapply(candidates,function(j) {
      old<-selected[ids[selected]==ids[j]]
      proposal<-c(setdiff(selected,old),j)
      proposal_stake<-sum(stake[proposal])
      removed<-if(length(old))scenarios$hits[,old] else 0
      v<-list(stake=proposal_stake,expected_net=sum(expected[proposal])-proposal_stake,
        any_hit=mean(current_events-removed+scenarios$hits[,j]>0))
      cost<-v$stake-current$stake
      tibble::tibble(option=j,cost=cost,
        hit_gain=v$any_hit-current$any_hit,
        net_gain=v$expected_net-current$expected_net,
        value_rate=(v$expected_net-current$expected_net)/cost)
    })
    scores<-dplyr::bind_rows(scores)
    primary<-if(objective=='any_hit')scores$hit_gain/scores$cost else scores$value_rate
    best<-order(-primary,-scores$value_rate,-scores$hit_gain,ids[scores$option],scores$option)[1]
    row<-scores[best,];j<-row$option
    stopifnot(row$cost>=2)
    ledger[[step]]<-tibble::tibble(step=step,phase=phase,sleeve_id=ids[j],option=j,
      depth=depth[j],copies=copies[j],added_stake=row$cost,cash_before=current$cash,
      affordable_new_core_count=length(affordable),unopened_core_count=length(unopened),
      cheapest_unopened_cost=if(length(unopened))min(stake[unopened]) else NA_real_,
      opening_stop=if(is.null(opening_stop))NA_character_ else opening_stop,
      marginal_hit=row$hit_gain,marginal_expected_net=row$net_gain)
    selected<-c(selected[ids[selected]!=ids[j]],j)
  }
  if(is.null(stop_reason))stop_reason<-'ACTION_LIMIT'
  list(selected=selected,metrics=n7_capital_evaluate(pool,selected,scenarios,cutoffs,budget_cny),
    actions=dplyr::bind_rows(ledger),opening_stop=opening_stop,stop_reason=stop_reason,
    initial_opportunity_stake=initial$stake,cutoffs=cutoffs)
}
