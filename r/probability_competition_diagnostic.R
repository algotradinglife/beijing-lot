# Descriptive frozen-score decomposition. No learning, future routing or I/O.
# frame: one row per issue/slot/provider_id/model, stage, stratum, finite value.
# Non-common categories are counted explicitly, never imputed. All weights are
# descriptive sample shares. Requires strategy_composition_diagnostics.
probability_competition_decomposition <- function(frame, reference, target) {
 required<-c('issue','slot','provider_id','model','stage','stratum','value')
 stopifnot(all(required %in% names(frame)),nrow(frame)>0,!anyNA(frame[required]),
  all(is.finite(frame$value)),!anyDuplicated(frame[c('issue','slot','provider_id','model')]))
 results<-cells<-coverage<-list()
 for(m in unique(frame$model)) {
  t<-dplyr::filter(frame,model==m,stage %in% c(reference,target))
  common<-intersect(t$stratum[t$stage==reference],t$stratum[t$stage==target])
  if(!length(common))stop('No common strata')
  coverage[[m]]<-t |> dplyr::group_by(stage) |> dplyr::summarise(total=dplyr::n(),
   included=sum(stratum %in% common),excluded=sum(!stratum %in% common),.groups='drop') |>
   dplyr::mutate(model=m,reference=reference,target=target)
  d<-strategy_composition_diagnostics(t |> dplyr::filter(stratum %in% common) |>
   dplyr::transmute(segment=stage,stratum,value),reference,target)
  results[[m]]<-dplyr::mutate(d$summary,model=m)
  cells[[m]]<-dplyr::mutate(d$cells,reference=reference,target=target,model=m)
 }
 list(summary=dplyr::bind_rows(results),cells=dplyr::bind_rows(cells),coverage=dplyr::bind_rows(coverage))
}

# Metadata labels are descriptive only. The explicit dictionary defines category
# meanings; unmatched competitions stay UNKNOWN, not guessed from names.
probability_competition_tags <- function(labels, dictionary) {
 stopifnot(all(c('issue','slot','provider_id','competition') %in% names(labels)),
  all(c('competition','competition_type','tier','evidence') %in% names(dictionary)),
  !anyDuplicated(labels[c('issue','slot','provider_id')]),!anyDuplicated(dictionary$competition),
  !anyNA(labels),!anyNA(dictionary))
 z<-dplyr::left_join(labels,dictionary,by='competition',relationship='many-to-one')
 for(n in c('competition_type','tier','evidence'))z[[n]][is.na(z[[n]])]<-'UNKNOWN'
 z
}
