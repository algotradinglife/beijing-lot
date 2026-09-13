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
                              opportunity_cap_cny,group_cap_cny,unit_cny,rule) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,
    identical(attr(features,'cutoffs'),cutoffs),
    !anyDuplicated(features$sleeve_id),unit_cny==2,group_cap_cny==30,
    core_count>=1,core_count==floor(core_count),core_count<nrow(features),
    is.finite(opportunity_cap_cny),opportunity_cap_cny>=0,
    opportunity_cap_cny%%unit_cny==0,rule %in% c('PROB','VALUE'),
    all(is.finite(as.matrix(features[c('coverage_64','coverage_15','expected_net_64','expected_net_15')]))))
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
  list(core_ids=features$sleeve_id[core],opportunity_ids=features$sleeve_id[opportunity],
    opportunity_depth=as.integer(group_cap_cny/unit_cny),
    opportunity_stake_cny=count*group_cap_cny,ledger=ledger,cutoffs=cutoffs,
    historical_admission=FALSE,rule=rule)
}

# Expand the validated prefix option pool with per-sleeve unit multiplicities.
# Probability coverage is unchanged by copies; stake and payouts scale. Roles
# stay disjoint; selected opportunities are required options in the shared MILP.
n7_core_option_pool <- function(base,partition,cutoffs,mode,max_copies) {
  stopifnot(identical(base$cutoffs,cutoffs),identical(partition$cutoffs,cutoffs),
    mode %in% c('BREADTH','DEPTH','MULTIPLY'),max_copies>=1,
    max_copies==floor(max_copies),!anyDuplicated(partition$core_ids),
    !anyDuplicated(partition$opportunity_ids),
    !length(intersect(partition$core_ids,partition$opportunity_ids)))
  opts<-list();required<-integer()
  for(o in base$options) {
    stopifnot(o$stake==2*o$depth)
    if(o$sleeve_id %in% partition$core_ids && (mode=='DEPTH' || o$depth<=64)) {
      copies<-if(mode=='MULTIPLY')seq_len(max_copies) else 1L
      for(m in copies) {
        z<-o;z$unit_copies<-m;z$role<-'CORE'
        z$stake<-o$stake*m;z$expected_gross<-o$expected_gross*m
        z$state_payout<-o$state_payout*m
        opts[[length(opts)+1L]]<-z
      }
    }
    if(o$sleeve_id %in% partition$opportunity_ids && o$depth==partition$opportunity_depth) {
      z<-o;z$unit_copies<-1L;z$role<-'OPPORTUNITY'
      opts[[length(opts)+1L]]<-z;required<-c(required,length(opts))
    }
  }
  stopifnot(length(required)==length(partition$opportunity_ids),length(opts)>0)
  pool<-base;pool$options<-opts;pool$required_options<-required
  pool$partition<-partition;pool
}
