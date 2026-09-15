# Fixed block draw calibration. Probability units are fractions; history rows
# are unique fixtures, never reused tickets. Python owns shared chronology and
# component weights. No files, network or target labels are read by prediction.

# Fit cell summaries through shared context; explicit parameters are not tuned.
# Long cell rates shrink toward each target market probability; recent cell
# rates shrink toward the frozen long estimate, using shared effective N.
draw_refresh_fit <- function(history, block, cutoff, repository_root, source_hashes,
                             market_edges, gap_edges, prior_strength, recent_strength,
                             delay_hours, recent_issues, minimum_ess, python) {
 stopifnot(length(python)==1,file.exists(python),is.finite(prior_strength),prior_strength>0,
  is.finite(recent_strength),recent_strength>0)
 reticulate::use_python(python,required=TRUE)
 core<-reticulate::import('src.temporal_learning.core')
 stopifnot(isTRUE(cutoff==core$Cutoff$decision_epoch(block$fit_issue,block$fit_cutoff_ts)))
 adapter<-reticulate::import('src.draw_refresh_context')
 ctx_json<-adapter$draw_refresh_context_json(
  jsonlite::toJSON(history,dataframe='rows',auto_unbox=TRUE,digits=NA),
  jsonlite::toJSON(block,auto_unbox=TRUE,digits=NA),repository_root=repository_root,
  source_hashes_json=jsonlite::toJSON(source_hashes,auto_unbox=TRUE),
  delay_hours=delay_hours,recent_issues=as.integer(recent_issues),minimum_ess=minimum_ess)
 ctx<-jsonlite::fromJSON(ctx_json,simplifyVector=FALSE)
 rows<-dplyr::bind_rows(ctx$rows)
 binning<-reticulate::import('src.probability_foundation_draw',convert=FALSE)
 rows<-binning$draw_cells(reticulate::r_to_py(as.data.frame(rows)),cutoff,
  market_edges=market_edges,secondary_edges=gap_edges,version='market-balance-draw-1.0.0-diagnostic')
 rows<-jsonlite::fromJSON(reticulate::py_to_r(rows$to_json(orient='records',double_precision=15L)))
 cells<-rows |> dplyr::group_by(market_bin,secondary_bin) |> dplyr::summarise(
  n_long=dplyr::n(),long_rate=sum(long_mass*(actual=='D'))/sum(long_mass),
  recent_rows=sum(recent_mass>0),recent_issue_count=dplyr::n_distinct(issue_code[recent_mass>0]),
  recent_ess=if(sum(recent_mass)>0)core$effective_sample_size(reticulate::np_array(recent_mass)) else 0,
  recent_rate=if(sum(recent_mass)>0)sum(recent_mass*(actual=='D'))/sum(recent_mass) else 0,
  .groups='drop')
 artifact<-list(cells=cells,context_json=ctx_json,block=block,
  parameters=list(market_edges=market_edges,gap_edges=gap_edges,prior_strength=prior_strength,
   recent_strength=recent_strength,delay_hours=delay_hours,recent_issues=recent_issues,minimum_ess=minimum_ess),
  implementation_sha256=digest::digest(file=file.path(repository_root,'r/draw_refresh.R'),algo='sha256'),
  historical_admission=FALSE)
 artifact$seal<-digest::digest(artifact,algo='sha256');artifact
}

# Apply a sealed artifact only within its assigned ten-issue (or explicit)
# block. alpha is the explicit recent component share in [0,1). Empty cells
# retain raw q; sparse recent cells shrink toward the long component.
# Returns target fixture rows with new_W/D/L, support and correction details.
draw_refresh_predict <- function(artifact, frame, cutoff, alpha, repository_root, python) {
 stopifnot(length(alpha)==1,is.finite(alpha),alpha>=0,alpha<1,
  identical(digest::digest(artifact[names(artifact)!='seal'],algo='sha256'),artifact$seal),
  identical(digest::digest(file=file.path(repository_root,'r/draw_refresh.R'),algo='sha256'),artifact$implementation_sha256),
  !'actual' %in% names(frame),!'actual_direction' %in% names(frame),nrow(frame)>0,
  !anyDuplicated(frame[c('issue','slot','provider_id')]),length(python)==1,file.exists(python))
 reticulate::use_python(python,required=TRUE)
 core<-reticulate::import('src.temporal_learning.core')
 blocks<-reticulate::import('src.temporal_learning.frozen_blocks')
 stopifnot(isTRUE(blocks$verify_block_target(artifact$block,cutoff)),
  all(frame$issue==cutoff$target_issue))
 core$WalkForwardRunner()$run(reticulate::r_to_py(data.frame(issue_code=frame$issue,
  fixture_decision_ts=frame$fixture_decision_ts)),function(epoch,target) {
   stopifnot(isTRUE(epoch==cutoff));TRUE
  })
 ctx<-jsonlite::fromJSON(artifact$context_json,simplifyVector=FALSE)
 reticulate::import('src.temporal_learning.provenance')$verify_implementation_closure(
  reticulate::import('pathlib')$Path(repository_root),ctx$receipt$implementation)
 p<-artifact$parameters
 z<-reticulate::import('src.probability_foundation_draw',convert=FALSE)$draw_cells(
  reticulate::r_to_py(as.data.frame(frame)),cutoff,market_edges=p$market_edges,
  secondary_edges=p$gap_edges,version='market-balance-draw-1.0.0-diagnostic')
 z<-jsonlite::fromJSON(reticulate::py_to_r(z$to_json(orient='records',double_precision=15L)))
 stopifnot(all(z$q_D>0 & z$q_D<1),all(z$q_W>0),all(z$q_L>0))
 z<-dplyr::left_join(z,artifact$cells,by=c('market_bin','secondary_bin'),relationship='many-to-one')
 for(n in c('n_long','long_rate','recent_rows','recent_issue_count','recent_ess','recent_rate'))z[[n]][is.na(z[[n]])]<-0
 z$long_D<-(z$n_long*z$long_rate+p$prior_strength*z$q_D)/(z$n_long+p$prior_strength)
 z$recent_D<-(z$recent_ess*z$recent_rate+p$recent_strength*z$long_D)/(z$recent_ess+p$recent_strength)
 z$new_D<-(1-alpha)*z$long_D+alpha*z$recent_D
 z$effective_recent_share<-alpha*z$recent_ess/(z$recent_ess+p$recent_strength)
 z$new_W<-z$q_W*(1-z$new_D)/(1-z$q_D)
 z$new_L<-z$q_L*(1-z$new_D)/(1-z$q_D)
 z$model_seal<-artifact$seal;z$alpha<-alpha;z
}
