# Descriptive post-settlement statistics only, no fitting or decision selection.
# results: one row per partition/issue/policy, explicit depth1/2 and OLD controls.
# CNY budget=stake+cash; ROI uses stake, budget_return uses assigned budget.
# Returns a tibble of aggregate economics, capital risk, and paired OLD lifts.
compression_bridge_summary <- function(results, initial_capital_cny) {
 stopifnot(nrow(results)>0, length(initial_capital_cny)==1, is.finite(initial_capital_cny), initial_capital_cny>0,
  !anyDuplicated(results[c('partition','issue','policy')]), all(results$depth %in% 1:2),
  all(is.finite(results$net)), all(results$stake>=0), all(results$cash_cny>=0),
  all(abs(results$stake+results$cash_cny-results$budget_cny)<1e-8), all(results$budget_cny>0))
 baseline <- results |> dplyr::filter(kind=='OLD') |> dplyr::select(partition,issue,depth,old_net=net,old_budget=budget_cny)
 x <- dplyr::left_join(results,baseline,by=c('partition','issue','depth'),relationship='many-to-one')
 stopifnot(!anyNA(x$old_net),all(x$old_budget==x$budget_cny))
 x <- x |> dplyr::arrange(partition,policy,issue) |> dplyr::mutate(lift=net-old_net)
 core <- integration_weight_summary(x)
 extra <- x |> dplyr::group_by(partition,policy) |> dplyr::summarise(
  depth=dplyr::first(depth),kind=dplyr::first(kind),budget_cny=sum(budget_cny),cash_cny=sum(cash_cny),
  any_payout=sum(hits>0),model_union=mean(model_union),fixture_hhi=mean(fixture_hhi),
  repeat_units=sum(repeat_units),matched_lift=sum(lift),
  ex_largest_issue=issue[which.max(net)],ex_largest_net=sum(net)-max(net),
  ex_largest_matched_lift=sum(lift)-lift[which.max(net)],
  ex_largest_lift_issue=issue[which.max(lift)],ex_largest_lift=sum(lift)-max(lift),
  longest_losing_run={run<-rle(net<0);max(c(0L,run$lengths[run$values]))},
  worst_5_loss=if(dplyr::n()>=5) max(0,-min(stats::filter(net,rep(1,5),sides=1),na.rm=TRUE)) else NA_real_,
  worst_10_loss=if(dplyr::n()>=10) max(0,-min(stats::filter(net,rep(1,10),sides=1),na.rm=TRUE)) else NA_real_,
  worst_20_loss=if(dplyr::n()>=20) max(0,-min(stats::filter(net,rep(1,20),sides=1),na.rm=TRUE)) else NA_real_,
  payout_hhi=if(sum(gross)>0) sum((gross/sum(gross))^2) else NA_real_,.groups='drop')
 dplyr::left_join(core,extra,by=c('partition','policy'),relationship='one-to-one') |>
  dplyr::mutate(budget_return=net_cny/budget_cny,ending_capital=initial_capital_cny+net_cny)
}

# Return every one-factor paired contrast (after-before), holding other three
# factors and depth fixed. Input includes all16 factorial cells per issue/depth.
# Issue is the observation unit; no tickets are treated as independent samples.
# Positive prefix effect means RESELECT minus PRESERVE; other effects are
# COMPRESSED-TOP2, FREE-STRICT and REPEAT_BEST-HOLD. Fails on missing pairs.
compression_bridge_contrasts <- function(results) {
 x <- results |> dplyr::filter(kind=='FACTORIAL')
 stopifnot(nrow(x)>0,!anyDuplicated(x[c('partition','issue','policy')]))
 factors <- c('preserve_prefix','quality','overlap','cash_policy')
 levels <- list(preserve_prefix=c('TRUE','FALSE'),quality=c('TOP2','COMPRESSED'),overlap=c('STRICT','FREE'),cash_policy=c('HOLD','REPEAT_BEST'))
 x <- x |> dplyr::mutate(dplyr::across(dplyr::all_of(factors),as.character))
 stopifnot(all(vapply(factors,function(f) all(x[[f]] %in% levels[[f]]),logical(1))))
 pairs <- lapply(factors,function(f) {
  keys <- c('partition','issue','depth',setdiff(factors,f))
  before <- x[x[[f]]==levels[[f]][1],] |> dplyr::select(dplyr::all_of(keys),before_net=net,before_stake=stake,before_union=model_union,before_budget=budget_cny)
  after <- x[x[[f]]==levels[[f]][2],] |> dplyr::select(dplyr::all_of(keys),after_net=net,after_stake=stake,after_union=model_union,after_budget=budget_cny)
  z <- dplyr::full_join(before,after,by=keys,relationship='one-to-one')
  stopifnot(!anyNA(z),all(z$before_budget==z$after_budget))
  z$context <- apply(z[setdiff(factors,f)],1,paste,collapse=' / ')
  z |> dplyr::transmute(partition,issue,depth,factor=f,context,net_delta=after_net-before_net,
   stake_delta=after_stake-before_stake,union_delta=after_union-before_union)
 })
 rows <- dplyr::bind_rows(pairs)
 totals <- rows |> dplyr::group_by(partition,depth,factor,context) |> dplyr::summarise(
  issues=dplyr::n(),net_delta=sum(net_delta),stake_delta=sum(stake_delta),union_delta=mean(union_delta),.groups='drop')
 # Compute the tail from issue rows, before the aggregate shadows the column.
 tails <- rows |> dplyr::group_by(partition,depth,factor,context) |> dplyr::summarise(ex_largest_delta=sum(net_delta)-max(net_delta),.groups='drop')
 list(rows=rows,summary=dplyr::left_join(totals,tails,by=c('partition','depth','factor','context'),relationship='one-to-one'))
}
