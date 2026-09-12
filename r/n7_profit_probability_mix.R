# Descriptive post-settlement accounting; no fit, selection or ticket construction.
# Input: exactly PROB/PROFIT rows per issue/seed, CNY stake/gross/net and hit counts.
# Explicit order, positive initial capital and period budget. Returns tidy funded
# periods, curves and summaries. MIX_NORMALIZED halves each sleeve (not executable
# CNY2 tickets); MIX_FULL holds both complete sleeves. No I/O; invalid inputs stop.
n7_profit_probability_mix <- function(rows, issue_order, initial_capital_cny, budget_cny) {
  stopifnot(all(c('issue','seed','ranking','stake','gross','net','hits') %in% names(rows)),
    nrow(rows)>0, !anyNA(rows), !anyDuplicated(rows[c('issue','seed','ranking')]),
    setequal(rows$ranking,c('PROB','PROFIT')),is.numeric(budget_cny),length(budget_cny)==1,
    is.finite(budget_cny),budget_cny>0)
  for(n in c('stake','gross','net','hits')) stopifnot(is.numeric(rows[[n]]),all(is.finite(rows[[n]])))
  stopifnot(all(rows$stake>=0),all(rows$stake<=budget_cny),all(rows$gross>=0),all(rows$hits>=0),
    all(abs(rows$gross-rows$stake-rows$net)<1e-7))
  a<-rows |> dplyr::filter(ranking=='PROB')
  b<-rows |> dplyr::filter(ranking=='PROFIT')
  pair<-dplyr::inner_join(a,b,by=c('issue','seed'),suffix=c('_prob','_profit'),relationship='one-to-one')
  stopifnot(nrow(pair)==nrow(a),nrow(pair)==nrow(b))
  pieces<-list()
  for(kind in c('PROB','PROFIT','MIX_NORMALIZED','MIX_FULL')) {
    weights<-switch(kind,PROB=c(1,0),PROFIT=c(0,1),MIX_NORMALIZED=c(.5,.5),MIX_FULL=c(1,1))
    z<-pair |> dplyr::transmute(issue,seed,model=as.character(seed),policy=kind,
      stake=weights[1]*stake_prob+weights[2]*stake_profit,
      gross=weights[1]*gross_prob+weights[2]*gross_profit,
      hits=as.integer((weights[1]>0 & hits_prob>0)|(weights[2]>0 & hits_profit>0)),
      budget_cny=budget_cny*sum(weights)) |>
      dplyr::mutate(net=gross-stake,cash_cny=budget_cny-stake,status=ifelse(stake>0,'COMPLETE','NO_BET'))
    pieces[[kind]]<-z
  }
  planned<-dplyr::bind_rows(pieces)
  curves<-strategy_equity_curves(planned,issue_order,initial_capital_cny)
  funded<-curves |> dplyr::filter(period>0) |>
    dplyr::mutate(stake=funded_stake_cny,net=funded_net_cny,gross=stake+net,hits=ifelse(stopped,0L,hits),
      roi_percent=ifelse(stake>0,100*net/stake,NA_real_))
  summary<-funded |> dplyr::group_by(seed,policy) |> dplyr::summarise(
    stake=sum(stake),net=sum(net),roi_percent=if(stake>0)100*net/stake else NA_real_,
    hit_issues=sum(hits>0),profitable_issues=sum(funded_net_cny>0),
    max_drawdown=max(drawdown_cny),ending_capital=dplyr::last(equity_cny),stopped_issues=sum(stopped),.groups='drop')
  list(periods=funded,curves=curves,summary=summary,pairs=pair)
}
