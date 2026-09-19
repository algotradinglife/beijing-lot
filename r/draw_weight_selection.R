# Select a fixed-grid blend weight using only shared admitted earlier predictions.
# History comes from the shared prior-label reader; BASE_D/TOTAL_D must be frozen
# earlier forecasts, never predictions fitted on these rows. Long component only
# is normalized for equal-history selection; recent component is not used.
# No writes; probabilities are fractions; minimize three-outcome Brier, ties low.
draw_weight_fit <- function(history,block,cutoff,repository_root,source_hashes,
                            weights,delay_hours,minimum_ess,python) {
 stopifnot(length(weights)>1,all(is.finite(weights)),all(weights>=0 & weights<=1),
 identical(sort(unique(weights)),weights),all(c('BASE_D','TOTAL_D') %in% names(history)),
 all(is.finite(history$BASE_D)),all(is.finite(history$TOTAL_D)),
 all(history$BASE_D>0 & history$BASE_D<1),all(history$TOTAL_D>0 & history$TOTAL_D<1))
 reticulate::use_python(python,required=TRUE)
 stopifnot(isTRUE(cutoff==reticulate::import('src.temporal_learning.core')$Cutoff$decision_epoch(block$fit_issue,block$fit_cutoff_ts)))
 implementation<-digest::digest(file=file.path(repository_root,'r/draw_weight_selection.R'),algo='sha256')
 source_hashes$weight_implementation<-implementation
 ctx<-reticulate::import('src.draw_refresh_context')$draw_refresh_context_json(
 jsonlite::toJSON(history,dataframe='rows',auto_unbox=TRUE,digits=NA),
 jsonlite::toJSON(block,auto_unbox=TRUE,digits=NA),repository_root=repository_root,
 source_hashes_json=jsonlite::toJSON(source_hashes,auto_unbox=TRUE),delay_hours=delay_hours,recent_issues=3L,minimum_ess=minimum_ess)
 h<-dplyr::bind_rows(jsonlite::fromJSON(ctx,simplifyVector=FALSE)$rows)
 scores<-list()
 for(arm in c('BASE','TOTAL'))for(w in weights) {
  d<-h$q_D+w*(h[[paste0(arm,'_D')]]-h$q_D)
  pw<-h$q_W*(1-d)/(1-h$q_D);pl<-h$q_L*(1-d)/(1-h$q_D)
  loss<-(pw-(h$actual=='W'))^2+(d-(h$actual=='D'))^2+(pl-(h$actual=='L'))^2
  scores[[length(scores)+1L]]<-tibble::tibble(arm=arm,weight=w,brier=stats::weighted.mean(loss,h$long_mass))
 }
 scores<-dplyr::bind_rows(scores)
 chosen<-scores |> dplyr::arrange(arm,brier,weight) |> dplyr::group_by(arm) |> dplyr::slice_head(n=1) |> dplyr::ungroup()
 a<-list(block=block,context_json=ctx,scores=scores,chosen=chosen,implementation=implementation,
 parameters=list(weights=weights,delay_hours=delay_hours,minimum_ess=minimum_ess,selection_policy='NORMALIZED_LONG_COMPONENT_ONLY'),historical_admission=FALSE)
 a$seal<-digest::digest(a,algo='sha256');a
}

# Apply selected weights only at the assigned target cutoff; preserve market W:L.
# Input is label-free, unique fixture rows; no source or outcome reads.
draw_weight_predict <- function(artifact,frame,cutoff,repository_root) {
 stopifnot(identical(digest::digest(artifact[names(artifact)!='seal'],algo='sha256'),artifact$seal),
 identical(digest::digest(file=file.path(repository_root,'r/draw_weight_selection.R'),algo='sha256'),artifact$implementation),
 !any(c('actual','actual_direction','actual_outcome','actual_home','actual_away') %in% names(frame)),
 all(c('issue','slot','provider_id','fixture_decision_ts','q_W','q_D','q_L','BASE_D','TOTAL_D') %in% names(frame)),
 nrow(frame)>0,!anyNA(frame),!anyDuplicated(frame[c('issue','slot','provider_id')]),all(frame$issue==cutoff$target_issue))
 q<-as.matrix(frame[c('q_W','q_D','q_L','BASE_D','TOTAL_D')]);stopifnot(all(is.finite(q)),all(q>0 & q<1),all(abs(rowSums(q[,1:3,drop=FALSE])-1)<1e-10))
 core<-reticulate::import('src.temporal_learning.core')
 stopifnot(isTRUE(reticulate::import('src.temporal_learning.frozen_blocks')$verify_block_target(artifact$block,cutoff)))
 for(t in frame$fixture_decision_ts)stopifnot(isTRUE(core$utc(t)>=cutoff$cutoff_ts))
 ctx<-jsonlite::fromJSON(artifact$context_json,simplifyVector=FALSE)
 reticulate::import('src.temporal_learning.provenance')$verify_implementation_closure(reticulate::import('pathlib')$Path(repository_root),ctx$receipt$implementation)
 out<-list()
 for(arm in c('BASE','TOTAL')) {
  z<-frame;w<-artifact$chosen$weight[artifact$chosen$arm==arm];stopifnot(length(w)==1)
  z$D<-z$q_D+w*(z[[paste0(arm,'_D')]]-z$q_D)
  z$W<-z$q_W*(1-z$D)/(1-z$q_D);z$L<-z$q_L*(1-z$D)/(1-z$q_D)
  z$model<-paste0(arm,'_SELECTED');z$weight<-w;z$model_seal<-artifact$seal;out[[arm]]<-z
 }
 dplyr::bind_rows(out)
}
