# Descriptive post-settlement diagnosis of existing frozen allocations. No fitting,
# new probabilities or target-period decisions. Costs CNY; ranks are 1-based.
# Inputs: candidate diagnostic rows, funded sleeve ledger, original result rows;
# explicit baseline arm/budget/depth grid. Tied cheapest sleeves are all retained.
# Returns candidate and period ledgers; missing/duplicate identity/grid fails.
n7_missed_candidates <- function(rows,allocations,results,baseline_arm,budget_cny,depths) {
  stopifnot(is.character(rows$fixture_slots),nrow(rows)>0,!anyDuplicated(rows[c('issue','sleeve_id')]),
    all(is.finite(depths)),all(depths>=1 & depths<=2187),all(depths==floor(depths)),
    !anyDuplicated(depths),budget_cny>0,budget_cny%%2==0,
    all(is.finite(rows$top64_coverage)),all(is.finite(rows$model_expected_hit_cost_cny)))
  b <- results |> dplyr::filter(!reference,arm==baseline_arm,.data$budget_cny==.env$budget_cny)
  stopifnot(nrow(b)>0,!anyDuplicated(b[c('issue','seed')]),
    setequal(b$issue,rows$issue),all(b$stake==budget_cny))
  rank <- rows |> dplyr::group_by(issue) |> dplyr::mutate(
    model_coverage_rank=dplyr::min_rank(dplyr::desc(top64_coverage)),
    model_cost_rank=dplyr::min_rank(model_expected_hit_cost_cny),
    cheapest=actual_hit_cost_cny==min(actual_hit_cost_cny)) |> dplyr::ungroup()
  a <- allocations |> dplyr::filter(arm==baseline_arm) |>
    dplyr::mutate(sleeve_id=as.character(sleeve_id)) |>
    dplyr::select(issue,seed,sleeve_id,depth)
  stopifnot(!anyDuplicated(a[c('issue','seed','sleeve_id')]))
  grid <- b |> dplyr::select(issue,seed,baseline_hits=hits) |>
    dplyr::inner_join(rank,by='issue',relationship='many-to-many') |>
    dplyr::left_join(a,by=c('issue','seed','sleeve_id'),relationship='one-to-one')
  grid$depth[is.na(grid$depth)] <- 0
  grid <- grid |> dplyr::mutate(funded=depth>0,covered=depth>=actual_rank,
    diagnosis=dplyr::case_when(!funded~'UNFUNDED',!covered~'UNDERDEPTH',TRUE~'HIT'),
    additional_cost_cny=pmax(0,actual_rank-depth)*2)
  check <- grid |> dplyr::group_by(issue,seed) |> dplyr::summarise(
    replay=sum(covered),expected=dplyr::first(baseline_hits),stake=sum(depth)*2,.groups='drop')
  stopifnot(all(check$replay==check$expected),all(check$stake==budget_cny))
  missed <- grid |> dplyr::filter(baseline_hits==0,cheapest)
  missed$allowed_depth <- vapply(missed$actual_rank,function(r) {
    eligible <- depths[depths>=r & 2*depths<=budget_cny]
    if(length(eligible))min(eligible) else NA_real_
  },numeric(1))
  missed$grid_additional_cost_cny <- 2*(missed$allowed_depth-missed$depth)
  missed$max_overlap_other_funded <- vapply(seq_len(nrow(missed)),function(i) {
    z<-missed[i,];others<-grid[grid$issue==z$issue & grid$seed==z$seed &
      grid$funded & grid$sleeve_id!=z$sleeve_id,]
    this<-strsplit(z$fixture_slots,',',fixed=TRUE)[[1]]
    if(!nrow(others))return(0L)
    max(vapply(strsplit(others$fixture_slots,',',fixed=TRUE),function(s)length(intersect(this,s)),integer(1)))
  },integer(1))
  periods <- missed |> dplyr::group_by(issue,seed) |> dplyr::summarise(
    cheapest_ties=dplyr::n(),any_cheapest_funded=any(funded),
    minimum_cost=dplyr::first(actual_hit_cost_cny),
    best_model_rank=min(model_coverage_rank),
    least_additional_cost=min(additional_cost_cny),
    .groups='drop')
  list(candidates=grid,cheapest=missed,periods=periods)
}

# Compare existing frozen alternatives, never adapt a policy to observed misses.
# Each arm must cover the same issue/seed grid. ROI uses actual stake; cash-only
# arms have NA ROI. Rescue/loss counts refer to matched original baseline records.
n7_missed_comparison <- function(results,baseline_arm,budget_cny) {
  y <- results |> dplyr::filter(!reference,.data$budget_cny==.env$budget_cny)
  stopifnot(nrow(y)>0,!anyDuplicated(y[c('issue','seed','arm')]))
  b <- y |> dplyr::filter(arm==baseline_arm) |>
    dplyr::select(issue,seed,baseline_hits=hits)
  stopifnot(nrow(b)>0)
  for(a in unique(y$arm))stopifnot(setequal(paste(y$issue[y$arm==a],y$seed[y$arm==a]),paste(b$issue,b$seed)))
  z <- dplyr::left_join(y,b,by=c('issue','seed'),relationship='many-to-one')
  stopifnot(!anyNA(z$baseline_hits))
  z |> dplyr::group_by(arm,seed) |> dplyr::summarise(
    hit_periods=sum(hits>0),rescued=sum(hits>0 & baseline_hits==0),
    lost=sum(hits==0 & baseline_hits>0),baseline_hit_periods=sum(baseline_hits>0),
    stake_cny=sum(stake),net_cny=sum(net),
    roi=if(sum(stake)>0)sum(net)/sum(stake) else NA_real_,.groups='drop') |>
    dplyr::mutate(net_hit_change=rescued-lost)
}
