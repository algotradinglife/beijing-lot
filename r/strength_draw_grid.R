# Fixed expansion grid fit on shared prior context. Inputs are label-free frozen
# forecasts; paths/hash/cutoff and all policies explicit. Reads labels only via
# the shared Python reader. No writes; returns cells and immutable receipt seal.
strength_draw_grid_fit <- function(fixtures, block, cutoff, label_path, label_sha256,
                                  repository_root, source_hashes, market_edges,
                                  strength_edges, prior_strength, delay_hours, minimum_ess) {
 stopifnot(length(prior_strength)==1,is.finite(prior_strength),prior_strength>0)
 implementation<-digest::digest(file=file.path(repository_root,'r/strength_draw_grid.R'),algo='sha256')
 source_hashes$r_implementation<-implementation
 ctx<-reticulate::import('src.strength_draw_context')$strength_draw_context(
  jsonlite::toJSON(fixtures,dataframe='rows',auto_unbox=TRUE,digits=NA),block,cutoff,
  label_path=label_path,label_sha256=label_sha256,delay_hours=delay_hours,minimum_ess=minimum_ess,
  repository_root=repository_root,source_hashes=source_hashes)
 context<-jsonlite::fromJSON(ctx,simplifyVector=FALSE)
 rows<-dplyr::bind_rows(context$rows)
 bins<-reticulate::import('src.probability_foundation_draw',convert=FALSE)$draw_cells(
  reticulate::r_to_py(as.data.frame(rows)),cutoff,market_edges=market_edges,
  secondary_edges=strength_edges,version='market-strength-draw-1.0.0-diagnostic')
 rows<-jsonlite::fromJSON(reticulate::py_to_r(bins$to_json(orient='records',double_precision=15L)))
 cells<-rows |> dplyr::group_by(market_bin,secondary_bin) |> dplyr::summarise(
  n=sum(weight),draws=sum(weight*(actual=='D')),.groups='drop')
 artifact<-list(cells=cells,context_json=ctx,block=block,implementation=implementation,
  binning_implementation=digest::digest(file=file.path(repository_root,'src/probability_foundation_draw.py'),algo='sha256'),
  parameters=list(market_edges=market_edges,strength_edges=strength_edges,prior_strength=prior_strength,
   delay_hours=delay_hours,minimum_ess=minimum_ess),historical_admission=FALSE)
 artifact$seal<-digest::digest(artifact,algo='sha256');artifact
}

# Apply only to an exact target in the immutable shared block. Retains market
# W:L and falls back to the declared market prior in unseen cells. No labels/I/O
# except implementation verification. Returns one row per input fixture.
strength_draw_grid_predict <- function(artifact, frame, cutoff, repository_root) {
 stopifnot(identical(digest::digest(artifact[names(artifact)!='seal'],algo='sha256'),artifact$seal),
  identical(digest::digest(file=file.path(repository_root,'r/strength_draw_grid.R'),algo='sha256'),artifact$implementation),
  identical(digest::digest(file=file.path(repository_root,'src/probability_foundation_draw.py'),algo='sha256'),artifact$binning_implementation),
  all(c('issue','slot','provider_id','fixture_decision_ts','q_W','q_D','q_L','p_D') %in% names(frame)),
  nrow(frame)>0,!anyNA(frame),!anyDuplicated(frame[c('issue','slot','provider_id')]),
  all(frame$issue==cutoff$target_issue),!any(c('actual','actual_direction','actual_outcome') %in% names(frame)))
 stopifnot(isTRUE(reticulate::import('src.temporal_learning.frozen_blocks')$verify_block_target(artifact$block,cutoff)))
 core<-reticulate::import('src.temporal_learning.core')
 for(t in frame$fixture_decision_ts)stopifnot(isTRUE(core$utc(t)>=cutoff$cutoff_ts))
 q<-as.matrix(frame[c('q_W','q_D','q_L')]);stopifnot(all(is.finite(q)),all(q>0),all(abs(rowSums(q)-1)<1e-10))
 ctx<-jsonlite::fromJSON(artifact$context_json,simplifyVector=FALSE)
 reticulate::import('src.temporal_learning.provenance')$verify_implementation_closure(
  reticulate::import('pathlib')$Path(repository_root),ctx$receipt$implementation)
 p<-artifact$parameters
 bins<-reticulate::import('src.probability_foundation_draw',convert=FALSE)$draw_cells(
  reticulate::r_to_py(as.data.frame(frame)),cutoff,market_edges=p$market_edges,
  secondary_edges=p$strength_edges,version='market-strength-draw-1.0.0-diagnostic')
 z<-jsonlite::fromJSON(reticulate::py_to_r(bins$to_json(orient='records',double_precision=15L)))
 z<-dplyr::left_join(z,artifact$cells,by=c('market_bin','secondary_bin'),relationship='many-to-one')
 for(n in c('n','draws'))z[[n]][is.na(z[[n]])]<-0
 z$D<-(z$draws+p$prior_strength*z$q_D)/(z$n+p$prior_strength)
 z$W<-z$q_W*(1-z$D)/(1-z$q_D);z$L<-z$q_L*(1-z$D)/(1-z$q_D)
 z$model_seal<-artifact$seal;z
}
