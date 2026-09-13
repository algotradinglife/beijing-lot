# Descriptive single-sleeve comparisons of already frozen curves. These ranks
# never remove candidates or feed the allocator. Explicit cutoff maps bind the
# source issue. Output includes full-distribution concentration and local
# dominance at the same spend/target, plus rank reversals across selected depths.
n7_capital_compare <- function(curves,depths,targets,budget_cny,tolerance,cutoffs,expected_cutoffs) {
  stopifnot(length(depths)>0,length(targets)>0,!anyDuplicated(depths),!anyDuplicated(targets))
  ids<-unique(curves$sleeve_id);rows<-list()
  for(mode in c('top_n','coverage'))for(value in if(mode=='top_n')depths else targets) {
    resolved<-n7_capital_resolve(curves,mode,stats::setNames(rep(value,length(ids)),ids),
      budget_cny,tolerance,cutoffs,expected_cutoffs)
    z<-resolved$allocation |> dplyr::left_join(curves |>
      dplyr::select(sleeve_id,depth,expected_net,expected_gross,expected_roi),
      by=c('sleeve_id','n_tickets'='depth'),relationship='one-to-one')
    z$mode<-mode;z$target<-value;z$all_sleeves_total_stake<-resolved$total_stake
    z$all_sleeves_status<-resolved$status
    z$coverage_rank<-dplyr::min_rank(dplyr::desc(z$actual_coverage))
    z$net_rank<-dplyr::min_rank(dplyr::desc(z$expected_net))
    better<-outer(z$stake,z$stake,`<=`) & outer(z$actual_coverage,z$actual_coverage,`>=`) &
      outer(z$expected_net,z$expected_net,`>=`) &
      (outer(z$stake,z$stake,`<`) | outer(z$actual_coverage,z$actual_coverage,`>`) |
       outer(z$expected_net,z$expected_net,`>`))
    z$locally_dominated<-colSums(better)>0
    rows[[length(rows)+1L]]<-z
  }
  comparisons<-dplyr::bind_rows(rows)
  concentration<-curves |> dplyr::filter(depth>0) |> dplyr::group_by(sleeve_id) |>
    dplyr::arrange(depth,.by_group=TRUE) |>
    dplyr::summarise(full_probability_hhi=sum(diff(c(0,coverage))^2),top1_probability=coverage[1],.groups='drop')
  comparisons<-dplyr::left_join(comparisons,concentration,by='sleeve_id',relationship='many-to-one')
  crossing<-list()
  for(i in seq_along(depths))for(j in seq_along(depths))if(i<j) {
    a<-comparisons[comparisons$mode=='top_n' & comparisons$target==depths[i],]
    b<-comparisons[comparisons$mode=='top_n' & comparisons$target==depths[j],]
    b<-b[match(a$sleeve_id,b$sleeve_id),]
    da<-outer(a$actual_coverage,a$actual_coverage,`-`)
    db<-outer(b$actual_coverage,b$actual_coverage,`-`)
    valid<-upper.tri(da) & abs(da)>1e-12 & abs(db)>1e-12
    crossing[[length(crossing)+1L]]<-tibble::tibble(depth_from=depths[i],depth_to=depths[j],
      comparable_pairs=sum(valid),reversed_pairs=sum(valid & da*db<0),
      spearman=if(stats::sd(a$actual_coverage)>0 && stats::sd(b$actual_coverage)>0)
        stats::cor(a$actual_coverage,b$actual_coverage,method='spearman') else NA_real_)
  }
  list(comparisons=comparisons,crossings=dplyr::bind_rows(crossing),
    candidates_before=length(ids),candidates_after=length(ids),cutoffs=cutoffs)
}

# Descriptive frontier among REGISTERED policy summaries, not a new allocator or
# proof over every possible allocation. Tolerances are explicit plot/summary
# conventions in percentage points/CNY. No historical outcome enters this view.
n7_capital_frontier <- function(answers,hit_tolerance_pp,net_tolerance_cny) {
  stopifnot(all(c('arm','budget_cny','any_hit_percent','modeled_net_cny','sleeves_median','funded_trials') %in% names(answers)),
    !anyNA(answers[c('arm','budget_cny','any_hit_percent','modeled_net_cny','funded_trials')]),
    all(answers$funded_trials>=0 & answers$funded_trials%%1==0),
    !anyDuplicated(answers[c('arm','budget_cny')]),hit_tolerance_pp>=0,net_tolerance_cny>=0)
  parts<-answers |> dplyr::group_by(budget_cny) |> dplyr::group_split()
  points<-regions<-list()
  for(x in parts) {
    # An entirely unfunded/infeasible policy is not an attainable allocation
    # optimum merely because its diagnostic zero beats negative expected net.
    eligible<-x$funded_trials>0
    x$frontier_eligible<-eligible
    p<-x$any_hit_percent[eligible];v<-x$modeled_net_cny[eligible]
    dominates<-outer(p,p,`>=`) & outer(v,v,`>=`) & (outer(p,p,`>`) | outer(v,v,`>`))
    x$registered_frontier<-x$near_registered_hit_max<-x$near_registered_net_max<-FALSE
    if(any(eligible)) {
      x$registered_frontier[eligible]<-colSums(dominates)==0
      x$near_registered_hit_max[eligible]<-p>=max(p)-hit_tolerance_pp
      x$near_registered_net_max[eligible]<-v>=max(v)-net_tolerance_cny
    }
    points[[length(points)+1L]]<-x
    regions[[length(regions)+1L]]<-tibble::tibble(budget_cny=x$budget_cny[1],
      hit_tolerance_pp=hit_tolerance_pp,net_tolerance_cny=net_tolerance_cny,
      eligible_policies=sum(eligible),unfunded_policies=sum(!eligible),
      near_hit_policies=sum(x$near_registered_hit_max),
      near_hit_sleeves_min=if(any(eligible))min(x$sleeves_median[x$near_registered_hit_max]) else NA_real_,
      near_hit_sleeves_max=if(any(eligible))max(x$sleeves_median[x$near_registered_hit_max]) else NA_real_,
      near_net_policies=sum(x$near_registered_net_max),
      near_net_sleeves_min=if(any(eligible))min(x$sleeves_median[x$near_registered_net_max]) else NA_real_,
      near_net_sleeves_max=if(any(eligible))max(x$sleeves_median[x$near_registered_net_max]) else NA_real_)
  }
  list(points=dplyr::bind_rows(points),regions=dplyr::bind_rows(regions))
}
