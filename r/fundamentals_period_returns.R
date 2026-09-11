# Descriptive accounting of settled groups; no forecasting, fitting or routing.
# rows: one issue/policy with groups,hits,stake,gross,net; groups: one purchased
# group with issue,policy,group,stake,gross,hit. Amounts CNY, hit logical.
# Explicit issue_order and equal block_size; incomplete blocks fail. Return
# block summary plus first-to-last recovery change decomposed into hit-rate and
# winning-payout effects (symmetric attribution, not causal). Inputs unmodified.
n6_period_returns <- function(rows, groups, issue_order, block_size) {
 stopifnot(is.character(issue_order),length(issue_order)>0,!anyNA(issue_order),!anyDuplicated(issue_order),
  length(block_size)==1,is.numeric(block_size),is.finite(block_size),block_size>=1,
  block_size==as.integer(block_size),length(issue_order)%%block_size==0,
  all(c('issue','policy','groups','hits','stake','gross','net') %in% names(rows)),
  all(c('issue','policy','group','stake','gross','hit') %in% names(groups)),
  is.logical(groups$hit),!anyNA(groups),!anyNA(rows[c('issue','policy','groups','hits','stake','gross','net')]),
  !anyDuplicated(rows[c('policy','issue')]),!anyDuplicated(groups[c('policy','issue','group')]),
  setequal(rows$policy,groups$policy),all(groups$stake>0),all(groups$gross>=0),
  all(groups$hit==(groups$gross>0)),all(abs(rows$net-(rows$gross-rows$stake))<1e-7))
 stopifnot(nrow(rows)>0,nrow(groups)>0,
  all(vapply(rows[c("groups","hits","stake","gross","net")],function(x) is.numeric(x)&&all(is.finite(x)),logical(1))),
  all(vapply(groups[c("group","stake","gross")],function(x) is.numeric(x)&&all(is.finite(x)),logical(1))))
 for (p in unique(rows$policy)) {
  stopifnot(setequal(rows$issue[rows$policy==p],issue_order),
   length(unique(groups$stake[groups$policy==p]))==1)
 }
 check <- groups |> dplyr::group_by(policy,issue) |>
  dplyr::summarise(check_groups=dplyr::n(),check_hits=sum(hit),check_stake=sum(stake),check_gross=sum(gross),.groups='drop')
 stopifnot(nrow(check)==nrow(rows))
 check <- dplyr::left_join(rows,check,by=c('policy','issue'),relationship='one-to-one')
 stopifnot(!anyNA(check[c("check_groups","check_hits","check_stake","check_gross")]),all(check$groups==check$check_groups),all(check$hits==check$check_hits),
  all(abs(check$stake-check$check_stake)<1e-7),all(abs(check$gross-check$check_gross)<1e-7))
 blocks <- tibble::tibble(issue=issue_order,block=(seq_along(issue_order)-1L)%/%block_size+1L)
 g <- dplyr::left_join(groups,blocks,by='issue',relationship='many-to-one')
 x <- dplyr::left_join(rows,blocks,by='issue',relationship='many-to-one')
 stopifnot(!anyNA(g$block),!anyNA(x$block))
 summary <- g |> dplyr::group_by(policy,block) |>
  dplyr::summarise(groups=dplyr::n(),winning_groups=sum(hit),group_cost=unique(stake),
   total_stake=sum(stake),total_gross=sum(gross),net=total_gross-total_stake,
   hit_rate=mean(hit),mean_winning_gross=if(any(hit))mean(gross[hit]) else NA_real_,
   median_winning_gross=if(any(hit))stats::median(gross[hit]) else NA_real_,
   required_mean_gross=if(any(hit))total_stake/sum(hit) else NA_real_,
   recovery=total_gross/total_stake,ROI_percent=100*(recovery-1),
   top3_gross_share=if(sum(gross)>0)sum(head(sort(gross,decreasing=TRUE),3))/sum(gross) else NA_real_,
   net_without_best_group=net-max(gross),.groups='drop') |>
  dplyr::rename(stake=total_stake,gross=total_gross)
 periods <- x |> dplyr::group_by(policy,block) |>
  dplyr::summarise(hit_issues=sum(hits>0),profit_issues=sum(net>0),.groups='drop')
 summary <- dplyr::left_join(summary,periods,by=c('policy','block'),relationship='one-to-one') |>
  dplyr::mutate(start_issue=issue_order[(block-1L)*block_size+1L],end_issue=issue_order[block*block_size])
 first <- summary |> dplyr::filter(block==1) |>
  dplyr::select(policy,h1=hit_rate,a1=mean_winning_gross,cost=group_cost,r1=recovery)
 last <- summary |> dplyr::filter(block==max(block)) |>
  dplyr::select(policy,h3=hit_rate,a3=mean_winning_gross,r3=recovery)
 change <- dplyr::inner_join(first,last,by='policy',relationship='one-to-one') |>
  dplyr::mutate(recovery_change_pp=100*(r3-r1),
   hit_effect_pp=100*(h3-h1)*(a3+a1)/(2*cost),
   payout_effect_pp=100*(a3-a1)*(h3+h1)/(2*cost))
 list(summary=summary,change=change)
}
