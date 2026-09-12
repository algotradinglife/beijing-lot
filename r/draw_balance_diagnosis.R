# Descriptive, post-settlement bin counts; never a fitting or selection interface.
# fixtures: unique issue/slot/provider_id, cohort, actual W/D/L, p/q_W/D/L.
# Edges: explicit probability fractions from 0 to 1. Empty bins retain NA rates.
# Output: one row per cohort/model/draw-bin/absolute-WL-gap-bin; rates in percent.
# No I/O. Missing identities/outcomes/probabilities and invalid edges stop.
draw_balance_cells <- function(fixtures, draw_edges, gap_edges) {
  keys<-c('issue','slot','provider_id')
  stopifnot(!anyNA(fixtures[c(keys,'cohort','actual')]),!anyDuplicated(fixtures[keys]),
    all(fixtures$actual %in% c('W','D','L')))
  for(edges in list(draw_edges,gap_edges)) stopifnot(length(edges)>=2,
    all(is.finite(edges)),all(diff(edges)>0),edges[1]==0,tail(edges,1)==1)
  tables<-list();matrices<-list()
  for(prefix in c('p','q')) {
    probability<-as.matrix(fixtures[paste0(prefix,c('_W','_D','_L'))])
    stopifnot(all(vapply(fixtures[paste0(prefix,c('_W','_D','_L'))],is.numeric,logical(1))))
    storage.mode(probability)<-'double'
    stopifnot(all(is.finite(probability)),all(probability>=0),
      all(abs(rowSums(probability)-1)<1e-10))
    matrices[[prefix]]<-probability
  }
  for(model in c('strength','market','strength_draw_market_gap')) {
    draw_probability<-matrices[[if(model=='market') 'q' else 'p']][,2]
    gap_probability<-matrices[[if(model=='strength') 'p' else 'q']]
    rows<-tibble::tibble(cohort=fixtures$cohort,model=model,
      draw_probability=draw_probability,gap=abs(gap_probability[,1]-gap_probability[,3]),
      draw=fixtures$actual=='D') |>
      dplyr::mutate(draw_band=cut(draw_probability,draw_edges,right=FALSE,include.lowest=TRUE),
        gap_band=cut(gap,gap_edges,right=FALSE,include.lowest=TRUE))
    tables[[model]]<-rows |>
      dplyr::group_by(cohort,model,draw_band,gap_band,.drop=FALSE) |>
      dplyr::summarise(n=dplyr::n(),draws=sum(draw),
        predicted_draws=sum(draw_probability),.groups='drop') |>
      dplyr::mutate(actual_percent=100*draws/dplyr::na_if(n,0L),
        predicted_percent=100*predicted_draws/dplyr::na_if(n,0L),
        residual_pp=actual_percent-predicted_percent)
  }
  result<-dplyr::bind_rows(tables)
  if(nrow(fixtures)==0) return(result[0,])
  result
}

# Render one source pairing's cell rates. Same 0-60% colour scale throughout;
# values beyond 60% saturate, while exact annotations retain observed rates.
# Sparse cells n<30 use pale fill; every populated cell displays count and rate.
# Returns ggplot; saving and output paths belong to the QMD caller.
plot_draw_balance <- function(cells, model) {
  stopifnot(length(model)==1,model %in% c('strength','market','strength_draw_market_gap'))
  cross<-model=='strength_draw_market_gap'
  rows<-cells |> dplyr::filter(.data$model==.env$model) |>
    dplyr::mutate(cohort=factor(cohort,levels=c('old48','new100')),
      label=ifelse(n>0,sprintf('%.1f%%\nn=%d',actual_percent,n),''),
      support=ifelse(n>=30,'n >= 30','n < 30'))
  ggplot2::ggplot(rows,ggplot2::aes(draw_band,gap_band,fill=actual_percent))+
    ggplot2::geom_tile(ggplot2::aes(alpha=support),colour='white')+
    ggplot2::geom_text(ggplot2::aes(label=label),size=3)+
    ggplot2::facet_wrap(~cohort,nrow=1)+
    ggplot2::scale_fill_gradient(low='#fff7ec',high='#e6550d',limits=c(0,60),
      oob=scales::squish,na.value='#eeeeee',name='Actual draw (%)')+
    ggplot2::scale_alpha_manual(values=c('n >= 30'=1,'n < 30'=.3),guide='none')+
    ggplot2::labs(title=if(cross) 'Strength draw probability x market W-L gap' else paste(if(model=='market') 'Market' else 'Strength','probabilities'),
      x=if(cross) 'Strength handicap draw probability bin' else 'Handicap draw probability bin',
      y=if(cross) 'Absolute market handicap W-L probability gap bin' else 'Absolute handicap W-L probability gap bin',
      caption='Fractions on axes. Labels: actual draw rate / sample count. Pale cells: n < 30. Grey: empty.')+
    ggplot2::theme_minimal(base_size=11)+
    ggplot2::theme(axis.text.x=ggplot2::element_text(angle=35,hjust=1))
}
