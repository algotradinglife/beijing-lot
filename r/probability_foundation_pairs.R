# Descriptive paired probability evaluation, independent of ticket selection.
# frame follows strategy_probability_diagnostics' long-table contract. baseline
# names one model; strata/breaks/outcomes are explicit descriptive categories.
# tolerance is the absolute probability-change threshold for unchanged.
# Returns common fixture scores, nonbaseline paired changes and stratum summaries.
# Does not fit/calibrate/select, has no I/O, and never clips zero probabilities.
probability_foundation_pairs <- function(frame,baseline,strata,outcomes,breaks,tolerance) {
 stopifnot(length(baseline)==1,is.character(baseline),!is.na(baseline),baseline %in% frame$model,
  dplyr::n_distinct(frame$model)>=2,length(tolerance)==1,is.finite(tolerance),tolerance>=0,tolerance<1)
 diagnostics<-strategy_probability_diagnostics(frame,strata,outcomes,breaks)
 keys<-c('issue','slot','provider_id','model')
 detail<-frame |> dplyr::mutate(class_order=match(outcome,outcomes)) |>
  dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |>
  dplyr::arrange(dplyr::desc(probability),class_order,.by_group=TRUE) |>
  dplyr::summarise(actual_outcome=dplyr::first(actual_outcome),actual_probability=probability[outcome==actual_outcome],
   top1_mass=probability[1],top2_mass=sum(head(probability,2)),top1_outcome=outcome[1],
   excluded_outcome=if(length(outcomes)==3)outcome[3] else NA_character_,.groups='drop')
 # Fixed Top2-set comparisons require the football three-class universe.
 stopifnot(length(outcomes)==3)
 scores<-dplyr::left_join(diagnostics$scores,detail,by=keys,relationship='one-to-one')
 base<-scores |> dplyr::filter(model==baseline) |> dplyr::select(-dplyr::all_of(c(strata,'model')))
 names(base)[!names(base) %in% keys[1:3]]<-paste0('base_',names(base)[!names(base) %in% keys[1:3]])
 pairs<-scores |> dplyr::filter(model!=baseline) |> dplyr::left_join(base,by=keys[1:3],relationship='many-to-one')
 fixed<-frame |> dplyr::select(dplyr::all_of(keys),outcome,probability)
 pairs<-pairs |> dplyr::left_join(fixed,by=c(stats::setNames(keys,keys),'base_excluded_outcome'='outcome'),relationship='one-to-one') |>
  dplyr::mutate(baseline=baseline,actual_probability_delta=actual_probability-base_actual_probability,
   actual_probability_movement=dplyr::case_when(actual_probability_delta>tolerance~'UP',actual_probability_delta< -tolerance~'DOWN',TRUE~'UNCHANGED'),
   top1_mass_delta=top1_mass-base_top1_mass,top2_mass_delta=top2_mass-base_top2_mass,
   baseline_top2_mass=1-probability,baseline_top2_mass_delta=baseline_top2_mass-base_top2_mass,
   brier_delta=brier-base_brier,log_loss_delta=log_loss-base_log_loss,
   top1_changed=top1_outcome!=base_top1_outcome,top2_changed=excluded_outcome!=base_excluded_outcome,
   top1_rescued=top1 & !base_top1,top1_lost=!top1 & base_top1,top2_rescued=top2 & !base_top2,top2_lost=!top2 & base_top2) |>
  dplyr::select(-probability)
 summary<-pairs |> dplyr::group_by(dplyr::across(dplyr::all_of(c(strata,'model','baseline')))) |>
  dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
   actual_probability_delta=mean(actual_probability_delta),up=sum(actual_probability_movement=='UP'),
   down=sum(actual_probability_movement=='DOWN'),unchanged=sum(actual_probability_movement=='UNCHANGED'),
   brier_delta=mean(brier_delta),log_loss_delta=mean(log_loss_delta),
   top1_mass_delta=mean(top1_mass_delta),top2_mass_delta=mean(top2_mass_delta),
   baseline_top2_mass_delta=mean(baseline_top2_mass_delta),
   top1_rescued=sum(top1_rescued),top1_lost=sum(top1_lost),top2_rescued=sum(top2_rescued),top2_lost=sum(top2_lost),
   top1_changed=sum(top1_changed),top2_changed=sum(top2_changed),.groups='drop')
 list(scores=scores,pairs=pairs,summary=summary,calibration=diagnostics$calibration)
}
