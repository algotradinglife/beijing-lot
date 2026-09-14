# Reconstruct group settlement with authoritative n7_quality_settlement before
# attribution. Explicit prediction/funded/rank contracts follow that function.
# Returns TRUE invisibly; missing/extra/duplicate identities or any changed
# group field fails, even when issue totals are unchanged. No IO or learning.
n7_verify_attribution_groups <- function(groups, predictions, funded, ranks) {
  expected<-n7_quality_settlement(predictions,funded,ranks)$groups
  keys<-c('issue','arm','seed','sleeve_id')
  stopifnot(all(names(expected) %in% names(groups)),!anyDuplicated(groups[keys]),
    nrow(groups)==nrow(expected),!anyNA(groups[names(expected)]),
    nrow(dplyr::anti_join(groups,expected,by=keys))==0)
  if(nrow(expected)==0)return(invisible(TRUE))
  paired<-dplyr::inner_join(expected,groups,by=keys,suffix=c('_expected','_actual'),relationship='one-to-one')
  for(n in setdiff(names(expected),keys)) {
    x<-paired[[paste0(n,'_expected')]];y<-paired[[paste0(n,'_actual')]]
    if(is.numeric(x))stopifnot(all(is.finite(y)),all(abs(x-y)<1e-7)) else stopifnot(identical(x,y))
  }
  invisible(TRUE)
}

# Retrospective accounting only: never selects, fits or recommends tickets.
# groups: one frozen settled issue/arm/seed/sleeve row, fields stake/gross/net
# (CNY), coverage (0..1), expected_gross (CNY), depth/copies and logical hit.
# plans: complete issue/arm/seed grid including empty plans; variant, budget_cny,
# stake/gross/net/hits. issue_order: explicit complete chronological identifiers.
# trim_k: positive integer counts of winning groups to remove, per configuration.
# Returns paired group ledger, plan attribution, configuration contributions,
# descriptive feature summaries and two explicitly hindsight-only trim tables.
# No IO or historical learning. Missing/duplicate keys, changed retained groups,
# unmatched identities, incomplete variants or inconsistent accounting fail.
n7_exchange_attribution <- function(groups, plans, issue_order, trim_k) {
  keys<-c('issue','arm','seed'); cfg<-c('variant','budget_cny','seed')
  gcols<-c(keys,'sleeve_id','stake','gross','net','coverage','expected_gross','depth','copies','hit')
  pcols<-c(keys,cfg,'stake','gross','net','hits')
  stopifnot(all(gcols %in% names(groups)),all(pcols %in% names(plans)),
    nrow(plans)>0,!anyNA(groups[gcols]),!anyNA(plans[unique(pcols)]),
    !anyDuplicated(groups[c(keys,'sleeve_id')]),!anyDuplicated(plans[keys]),
    !anyNA(issue_order),!anyDuplicated(issue_order),setequal(issue_order,plans$issue),
    length(trim_k)>0,all(is.finite(trim_k)),all(trim_k>0 & trim_k==floor(trim_k)),
    !anyDuplicated(trim_k),all(plans$variant %in% c('JOINT','EXCHANGE11','EXCHANGE12')),
    all(vapply(groups[c('stake','gross','net','coverage','expected_gross','depth','copies')],
      function(x) all(is.finite(x)),logical(1))),
    all(vapply(plans[c('stake','gross','net','hits','budget_cny')],function(x) all(is.finite(x)),logical(1))),
    is.logical(groups$hit),all(groups$coverage>=0 & groups$coverage<=1),
    all(groups$stake>0 & groups$stake==2*groups$depth),all(groups$depth==floor(groups$depth)),
    all(groups$copies==1),all(groups$gross>=0),all(groups$expected_gross>=0),
    all(groups$gross[!groups$hit]==0),all(abs(groups$net-(groups$gross-groups$stake))<1e-7),
    all(plans$stake>=0 & plans$stake<=plans$budget_cny),
    all(abs(plans$net-(plans$gross-plans$stake))<1e-7),
    nrow(dplyr::anti_join(groups,plans,by=keys))==0)
  sums<-groups |> dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |>
    dplyr::summarise(g_stake=sum(stake),g_gross=sum(gross),g_net=sum(net),g_hits=sum(hit),.groups='drop')
  check<-plans |> dplyr::left_join(sums,by=keys,relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(dplyr::starts_with('g_'),~tidyr::replace_na(.x,0)))
  for(n in c('stake','gross','net','hits'))stopifnot(all(abs(check[[n]]-check[[paste0('g_',n)]])<1e-6))
  g<-groups |> dplyr::left_join(plans |> dplyr::select(dplyr::all_of(c(keys,'variant','budget_cny'))),
    by=keys,relationship='many-to-one')
  b<-g |> dplyr::filter(variant=='JOINT') |> dplyr::select(-arm,-variant)
  bp<-plans |> dplyr::filter(variant=='JOINT') |> dplyr::select(-arm,-variant)
  stopifnot(!anyDuplicated(bp[c('issue','seed','budget_cny')]))
  ledgers<-list(); comparisons<-list()
  for(v in setdiff(unique(plans$variant),'JOINT')) {
    target<-plans |> dplyr::filter(variant==v)
    pk<-c('issue','seed','budget_cny')
    stopifnot(nrow(target)==nrow(bp),nrow(dplyr::anti_join(target,bp,by=pk))==0)
    pair<-target |> dplyr::left_join(bp,by=pk,suffix=c('','_base'),relationship='one-to-one') |>
      dplyr::mutate(delta_net=net-net_base,delta_stake=stake-stake_base,
        outcome=dplyr::case_when(hits_base==0 & hits>0~'rescued',hits_base>0 & hits==0~'lost',
          hits_base>0 & hits>0~'both_hit',TRUE~'both_miss'),
        block=ceiling(match(issue,issue_order)/50))
    a<-g |> dplyr::filter(variant==v) |> dplyr::select(-arm,-variant)
    lk<-c(pk,'sleeve_id')
    ledger<-dplyr::full_join(b,a,by=lk,suffix=c('_base','_new'),relationship='one-to-one') |>
      dplyr::mutate(variant=v,role=dplyr::case_when(is.na(stake_base)~'added',
        is.na(stake_new)~'removed',TRUE~'retained'))
    retained<-ledger |> dplyr::filter(role=='retained')
    for(n in c('stake','gross','net','coverage','expected_gross','depth','copies','hit'))
      stopifnot(all(abs(retained[[paste0(n,'_base')]]-retained[[paste0(n,'_new')]])<1e-7))
    ledger<-ledger |> dplyr::mutate(
      stake= dplyr::coalesce(stake_new,stake_base),gross=dplyr::coalesce(gross_new,gross_base),
      coverage=dplyr::coalesce(coverage_new,coverage_base),
      expected_gross=dplyr::coalesce(expected_gross_new,expected_gross_base),
      delta_stake=tidyr::replace_na(stake_new,0)-tidyr::replace_na(stake_base,0),
      delta_gross=tidyr::replace_na(gross_new,0)-tidyr::replace_na(gross_base,0),
      delta_net=delta_gross-delta_stake) |>
      dplyr::left_join(pair |> dplyr::select(dplyr::all_of(pk),outcome,block),by=pk,relationship='many-to-one')
    terms<-ledger |> dplyr::group_by(dplyr::across(dplyr::all_of(pk))) |>
      dplyr::summarise(added_gross=sum(gross[role=='added']),removed_gross=sum(gross[role=='removed']),
        cost_change=sum(delta_stake),ledger_net=sum(delta_net),.groups='drop')
    pair<-pair |> dplyr::left_join(terms,by=pk,relationship='one-to-one') |>
      dplyr::mutate(dplyr::across(c(added_gross,removed_gross,cost_change,ledger_net),~tidyr::replace_na(.x,0)))
    stopifnot(all(abs(pair$delta_net-pair$ledger_net)<1e-6),all(abs(pair$delta_stake-pair$cost_change)<1e-6))
    ledgers[[v]]<-ledger;comparisons[[v]]<-pair
  }
  stopifnot(length(ledgers)>0)
  ledger<-dplyr::bind_rows(ledgers); paired<-dplyr::bind_rows(comparisons)
  contributions<-paired |> dplyr::group_by(dplyr::across(dplyr::all_of(c(cfg,'outcome')))) |>
    dplyr::summarise(issues=dplyr::n(),added_gross=sum(added_gross),removed_gross=sum(removed_gross),
      cost_change=sum(cost_change),delta_net=sum(delta_net),.groups='drop')
  features<-ledger |> dplyr::group_by(dplyr::across(dplyr::all_of(c(cfg,'role','block')))) |>
    dplyr::summarise(groups=dplyr::n(),mean_coverage=mean(coverage),hit_rate=mean(gross>0),
      mean_stake=mean(stake),mean_estimated_return=mean(expected_gross/stake),
      gross=sum(gross),stake=sum(stake),.groups='drop')
  totals<-plans |> dplyr::group_by(dplyr::across(dplyr::all_of(cfg))) |>
    dplyr::summarise(net=sum(net),stake=sum(stake),.groups='drop')
  trims<-list()
  for(k in trim_k) {
    top<-g |> dplyr::filter(net>0,hit) |> dplyr::group_by(dplyr::across(dplyr::all_of(cfg))) |>
      dplyr::arrange(dplyr::desc(net),issue,sleeve_id,.by_group=TRUE) |>
      dplyr::slice_head(n=k) |> dplyr::summarise(removed_net=sum(net),removed_stake=sum(stake),.groups='drop')
    t<-totals |> dplyr::left_join(top,by=cfg,relationship='one-to-one') |>
      dplyr::mutate(dplyr::across(c(removed_net,removed_stake),~tidyr::replace_na(.x,0)),k=k,
        trimmed_net=net-removed_net,trimmed_stake=stake-removed_stake)
    base<-t |> dplyr::filter(variant=='JOINT') |> dplyr::select(budget_cny,seed,base_trimmed_net=trimmed_net)
    trims[[as.character(k)]]<-t |> dplyr::left_join(base,by=c('budget_cny','seed'),relationship='many-to-one') |>
      dplyr::mutate(delta_trimmed_net=trimmed_net-base_trimmed_net)
  }
  adverse<-list()
  for(k in trim_k) {
    winners<-ledger |> dplyr::filter(role=='added',gross>0) |>
      dplyr::group_by(dplyr::across(dplyr::all_of(cfg))) |>
      dplyr::arrange(dplyr::desc(gross),issue,sleeve_id,.by_group=TRUE) |>
      dplyr::slice_head(n=k) |> dplyr::summarise(suppressed_gross=sum(gross),.groups='drop')
    adverse[[as.character(k)]]<-paired |> dplyr::group_by(dplyr::across(dplyr::all_of(cfg))) |>
      dplyr::summarise(delta_net=sum(delta_net),.groups='drop') |>
      dplyr::left_join(winners,by=cfg,relationship='one-to-one') |>
      dplyr::mutate(suppressed_gross=tidyr::replace_na(suppressed_gross,0),k=k,
        stressed_delta_net=delta_net-suppressed_gross)
  }
  list(ledger=ledger,paired=paired,contributions=contributions,features=features,
    trims=dplyr::bind_rows(trims),adverse=dplyr::bind_rows(adverse))
}
