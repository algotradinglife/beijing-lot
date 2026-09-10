# Descriptive accounting of already settled, frozen plans; no learning or
# strategy selection. One input row per model/policy/issue, CNY amounts.
# issue_order explicitly supplies chronology. All series must cover it exactly.
# Returns a tidy ledger including period zero. shadow_equity_cny continues the
# original plans even when unfundable (diagnostic only); equity_cny permanently
# holds cash after the first unaffordable whole plan. No deposits, partial plans,
# borrowing or intra-issue recycling; all returns settle before the next issue.
# Missing, duplicate, unsettled or inconsistent inputs fail. No I/O.
strategy_equity_curves <- function(periods, issue_order, initial_capital_cny) {
 required <- c('model','policy','issue','status','stake','gross','net','budget_cny','cash_cny')
 stopifnot(all(required %in% names(periods)), nrow(periods)>0,
  is.character(issue_order),length(issue_order)>0,!anyNA(issue_order),!anyDuplicated(issue_order),
  is.numeric(initial_capital_cny),length(initial_capital_cny)==1,
  is.finite(initial_capital_cny),initial_capital_cny>0,
  !anyNA(periods[c('model','policy','issue')]),
  !anyDuplicated(periods[c('model','policy','issue')]),
  all(periods$status %in% c('COMPLETE','NO_BET')))
 for(n in c('stake','gross','net','budget_cny','cash_cny'))
  stopifnot(is.numeric(periods[[n]]),all(is.finite(periods[[n]])))
 stopifnot(all(periods$stake>=0),all(periods$gross>=0),all(periods$budget_cny>0),
  all(periods$cash_cny>=0),all(abs(periods$stake+periods$cash_cny-periods$budget_cny)<1e-7),
  all(abs(periods$gross-periods$stake-periods$net)<1e-7),
  all(periods$stake[periods$status=='NO_BET']==0),
  all(periods$gross[periods$status=='NO_BET']==0))
 pieces <- periods |> dplyr::group_by(model,policy) |> dplyr::group_split()
 out <- vector('list',length(pieces))
 for(k in seq_along(pieces)) {
  x <- pieces[[k]]
  stopifnot(setequal(x$issue,issue_order),nrow(x)==length(issue_order))
  x <- x[match(issue_order,x$issue),]
  balance <- initial_capital_cny; stopped <- FALSE
  x$opening_cny <- x$equity_cny <- x$funded_net_cny <- x$funded_stake_cny <- 0
  x$stopped <- x$stop_started <- FALSE
  for(i in seq_len(nrow(x))) {
   x$opening_cny[i] <- balance
   if(!stopped && balance+1e-8<x$stake[i]) {
    stopped <- TRUE; x$stop_started[i] <- TRUE
   }
   if(!stopped) {
    x$funded_stake_cny[i] <- x$stake[i]
    x$funded_net_cny[i] <- x$net[i]
    balance <- balance+x$net[i]
   }
   x$equity_cny[i] <- balance; x$stopped[i] <- stopped
  }
  x$period <- seq_len(nrow(x))
  x$shadow_equity_cny <- initial_capital_cny+cumsum(x$net)
  zero <- x[1,]; zero$issue <- NA_character_;zero$period <- 0L
  for(n in c('stake','gross','net','budget_cny','cash_cny','funded_stake_cny','funded_net_cny')) zero[[n]] <- 0
  zero$status <- 'INITIAL';zero$stopped <- zero$stop_started <- FALSE
  zero$opening_cny <- zero$equity_cny <- zero$shadow_equity_cny <- initial_capital_cny
  x <- dplyr::bind_rows(zero,x)
  x$cumulative_net_cny <- x$equity_cny-initial_capital_cny
  x$capital_return_percent <- 100*x$cumulative_net_cny/initial_capital_cny
  x$drawdown_cny <- cummax(x$equity_cny)-x$equity_cny
  out[[k]] <- x
 }
 dplyr::bind_rows(out)
}

# Plot a prepared ledger with caller-supplied strategy labels and facet models.
# mode is funded or shadow; returns a ggplot, no writes. Stop crosses only in
# funded mode. Values are CNY, x is the explicit sequential issue index.
plot_strategy_equity <- function(curves, mode, initial_capital_cny) {
 stopifnot(mode %in% c('funded','shadow'),length(mode)==1,
  all(c('label','model','policy','period','equity_cny','shadow_equity_cny','stop_started') %in% names(curves)))
 y <- if(mode=='funded') 'equity_cny' else 'shadow_equity_cny'
 ticks <- pretty(range(curves[[y]],initial_capital_cny))
 p <- ggplot2::ggplot(curves,ggplot2::aes(x=period,y=.data[[y]],colour=label,group=policy))+
  ggplot2::geom_hline(yintercept=initial_capital_cny,colour='grey55',linetype=2)+
  ggplot2::geom_line(linewidth=.7)+ggplot2::facet_wrap(~model,ncol=2)+
  ggplot2::scale_y_continuous(breaks=ticks,labels=format(ticks,scientific=FALSE,big.mark=',',trim=TRUE))+
  ggplot2::labs(x='期次顺序（0 为起始资金）',y='账户资金（元）',colour=NULL)+
  ggplot2::theme_minimal(base_size=12,base_family='Noto Sans CJK SC')+
  ggplot2::theme(legend.position='bottom',panel.grid.minor=ggplot2::element_blank())+
  ggplot2::guides(colour=ggplot2::guide_legend(ncol=2))
 if(mode=='funded') p <- p+ggplot2::geom_point(data=curves[curves$stop_started,],shape=4,size=3,stroke=1,show.legend=FALSE)
 p
}
