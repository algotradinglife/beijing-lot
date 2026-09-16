# Retrospective truncation of frozen purchased prefixes; never selects new groups.
# g: n7_return_attribution groups joined to stage; one row per issue/arm/seed/sleeve.
# caps: positive integer ticket counts; unit_cny explicit CNY per ticket.
# Outputs descriptive phase tails and same-group truncated ledgers/summaries.
# No IO, fitting or future decision. Saved funds stay cash; no redistribution.
joint_return_depth_diagnostic <- function(g,caps,unit_cny) {
  stopifnot(nrow(g)>0,!anyDuplicated(g[c('issue','arm','seed','sleeve_id')]),
    !anyNA(g[c('stage','depth','stake','actual_rank','actual_gross_cny','copies')]),
    length(unit_cny)==1,is.finite(unit_cny),unit_cny>0,
    length(caps)>0,!anyDuplicated(caps),all(is.finite(caps)),all(caps>=1 & caps==floor(caps)),
    all(is.finite(g$actual_gross_cny)),all(g$actual_gross_cny>=0),
    all(g$depth>=1 & g$depth==floor(g$depth)),all(g$copies>=1 & g$copies==floor(g$copies)),
    all(g$actual_rank>=1 & g$actual_rank==floor(g$actual_rank)),
    all(abs(g$stake-unit_cny*g$depth*g$copies)<1e-8))
  ledger<-tidyr::crossing(g,cap=caps) |> dplyr::mutate(
    truncated_depth=pmin(depth,cap),cost=unit_cny*truncated_depth*copies,
    payout=as.numeric(actual_rank<=truncated_depth)*actual_gross_cny*copies,
    pnl=payout-cost,saved=stake-cost)
  totals<-ledger |> dplyr::group_by(stage,arm,cap) |> dplyr::summarise(
    groups=dplyr::n(),hits=sum(actual_rank<=truncated_depth),hit_issues=dplyr::n_distinct(issue[payout>0]),
    stake=sum(cost),gross=sum(payout),net=sum(pnl),cash_saved=sum(saved),.groups='drop') |>
    dplyr::mutate(roi=net/stake)
  winners<-g |> dplyr::filter(actual_rank<=depth) |> dplyr::mutate(payout=actual_gross_cny*copies)
  tails<-winners |> dplyr::group_by(stage,arm) |> dplyr::summarise(
    winners=dplyr::n(),median_payout=median(payout),p90_payout=as.numeric(stats::quantile(payout,.9)),
    mean_payout=mean(payout),over1000_share=mean(payout>1000),
    over1000_gross_share=if(sum(payout)>0)sum(payout[payout>1000])/sum(payout) else NA_real_,
    largest5_gross=sum(head(sort(payout,decreasing=TRUE),5)),.groups='drop')
  list(ledger=ledger,totals=totals,tails=tails)
}
