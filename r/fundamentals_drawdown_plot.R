# Describe a verified funded equity ledger, including period zero. CNY units.
# Requires model/policy/label/issue/period/equity_cny/drawdown_cny; unique periods
# 0..n per model/policy, positive initial capital, finite nonnegative equity.
# Returns ordered rows, per-policy maximum CNY and percentage drawdowns, and a
# faceted underwater ggplot. Percent uses each period's prior running peak,
# not initial capital. First occurrence identifies tied maximum CNY drawdowns.
# No learning, selection, I/O or changes to the supplied ledger; invalid data fails.
strategy_drawdown_report <- function(curves) {
 required <- c('model','policy','label','issue','period','equity_cny','drawdown_cny')
 stopifnot(nrow(curves)>0,all(required %in% names(curves)),
  !anyNA(curves[c('model','policy','label','period','equity_cny','drawdown_cny')]),
  !anyDuplicated(curves[c('model','policy','period')]),
  all(is.finite(curves$equity_cny)),all(curves$equity_cny>=0),
  all(is.finite(curves$drawdown_cny)),all(curves$drawdown_cny>=0))
 pieces <- curves |> dplyr::arrange(model,policy,period) |>
  dplyr::group_by(model,policy) |> dplyr::group_split() |> as.list()
 for(i in seq_along(pieces)) {
  x <- pieces[[i]]
  stopifnot(identical(as.numeric(x$period),as.numeric(seq_len(nrow(x))-1L)),
   x$equity_cny[1]>0,dplyr::n_distinct(x$label)==1)
  x$peak_cny <- cummax(x$equity_cny)
  stopifnot(all(abs(x$drawdown_cny-(x$peak_cny-x$equity_cny))<1e-7))
  x$drawdown_percent <- 100*x$drawdown_cny/x$peak_cny
  pieces[[i]] <- x
 }
 rows <- dplyr::bind_rows(pieces)
 summary <- rows |> dplyr::group_by(model,policy,label) |>
  dplyr::summarise(max_drawdown_cny=max(drawdown_cny),max_drawdown_percent=max(drawdown_percent),
   max_cny_period=period[which.max(drawdown_cny)],max_cny_issue=issue[which.max(drawdown_cny)],
   current_drawdown_cny=dplyr::last(drawdown_cny),.groups='drop')
 dots <- rows |> dplyr::group_by(model,policy) |> dplyr::slice_max(drawdown_cny,n=1,with_ties=FALSE) |> dplyr::ungroup()
 plot <- ggplot2::ggplot(rows,ggplot2::aes(period,-drawdown_cny,colour=label,group=policy))+
  ggplot2::geom_hline(yintercept=0,colour='grey55',linetype=2)+
  ggplot2::geom_line(linewidth=.7)+ggplot2::geom_point(data=dots,size=2)+
  ggplot2::facet_wrap(~model,ncol=2)+
  ggplot2::labs(x='期次顺序（0 为起始资金）',y='回撤（元；相对历史资金峰值）',colour=NULL)+
  ggplot2::theme_minimal(base_size=12,base_family='Noto Sans CJK SC')+
  ggplot2::theme(legend.position='bottom',panel.grid.minor=ggplot2::element_blank())
 list(rows=rows,summary=summary,plot=plot)
}
