# Label-free feature contract. Probabilities are fractions; handicap is signed.
# No I/O; cutoff is explicit and actual chronology is verified by fit/predict.
strength_draw_ridge_features <- function(frame, cutoff, include_strength) {
 stopifnot(!is.null(cutoff),is.logical(include_strength),length(include_strength)==1,
 all(c('q_W','q_D','q_L','p_D','handicap') %in% names(frame)),nrow(frame)>0)
 q<-as.matrix(frame[c('q_W','q_D','q_L')])
 stopifnot(all(is.finite(q)),all(q>0),all(q<1),all(abs(rowSums(q)-1)<1e-10),
 all(is.finite(frame$handicap)),all(is.finite(frame$p_D)),all(frame$p_D>0 & frame$p_D<1))
 X<-cbind(market_logit=qlogis(frame$q_D),balance=abs(frame$q_W-frame$q_L),handicap=frame$handicap)
 if(include_strength)X<-cbind(X,strength_logit=qlogis(frame$p_D))
 X
}

# Fixed ridge penalty, prior-only standardization; shared context owns admission.
# Reads verified archive via shared reader, returns sealed artifact; no writes.
strength_draw_ridge_fit <- function(fixtures, block, cutoff, label_path,label_sha256,
 repository_root,source_hashes,include_strength,penalty,delay_hours,minimum_ess) {
 stopifnot(length(penalty)==1,is.finite(penalty),penalty>0)
 implementation<-digest::digest(file=file.path(repository_root,'r/strength_draw_ridge.R'),algo='sha256')
 source_hashes$r_implementation<-implementation
 ctx<-reticulate::import('src.strength_draw_context')$strength_draw_context(
 jsonlite::toJSON(fixtures,dataframe='rows',auto_unbox=TRUE,digits=NA),block,cutoff,
 label_path=label_path,label_sha256=label_sha256,delay_hours=delay_hours,minimum_ess=minimum_ess,
 repository_root=repository_root,source_hashes=source_hashes)
 rows<-dplyr::bind_rows(jsonlite::fromJSON(ctx,simplifyVector=FALSE)$rows)
 X<-strength_draw_ridge_features(rows,cutoff,include_strength)
 center<-colMeans(X);scale<-apply(X,2,stats::sd);scale[scale==0]<-1
 X<-sweep(sweep(X,2,center),2,scale,'/')
 y<-as.integer(rows$actual=='D');off<-qlogis(rows$q_D)
 stopifnot(length(unique(y))==2)
 fit<-mgcv::gam(y~offset(off)+X,family=stats::binomial(),weights=rows$weight,
 paraPen=list(X=list(diag(ncol(X)),sp=penalty)))
 stopifnot(isTRUE(fit$converged),all(is.finite(stats::coef(fit))))
 artifact<-list(coefficients=stats::coef(fit),center=center,scale=scale,context_json=ctx,
 block=block,implementation=implementation,runtime=list(R=as.character(getRversion()),mgcv=as.character(utils::packageVersion('mgcv'))),
 parameters=list(include_strength=include_strength,penalty=penalty,delay_hours=delay_hours,minimum_ess=minimum_ess),historical_admission=FALSE)
 artifact$seal<-digest::digest(artifact,algo='sha256');artifact
}

# Exact frozen block target; outputs W/D/L, preserving raw market W:L.
strength_draw_ridge_predict <- function(artifact,frame,cutoff,repository_root) {
 stopifnot(identical(digest::digest(artifact[names(artifact)!='seal'],algo='sha256'),artifact$seal),
 identical(digest::digest(file=file.path(repository_root,'r/strength_draw_ridge.R'),algo='sha256'),artifact$implementation),
 all(c('issue','slot','provider_id','fixture_decision_ts') %in% names(frame)),!anyNA(frame),
 !anyDuplicated(frame[c('issue','slot','provider_id')]),all(frame$issue==cutoff$target_issue),
 !any(c('actual','actual_direction','actual_outcome') %in% names(frame)))
 stopifnot(isTRUE(reticulate::import('src.temporal_learning.frozen_blocks')$verify_block_target(artifact$block,cutoff)))
 core<-reticulate::import('src.temporal_learning.core')
 for(t in frame$fixture_decision_ts)stopifnot(isTRUE(core$utc(t)>=cutoff$cutoff_ts))
 ctx<-jsonlite::fromJSON(artifact$context_json,simplifyVector=FALSE)
 reticulate::import('src.temporal_learning.provenance')$verify_implementation_closure(
 reticulate::import('pathlib')$Path(repository_root),ctx$receipt$implementation)
 X<-strength_draw_ridge_features(frame,cutoff,artifact$parameters$include_strength)
 X<-sweep(sweep(X,2,artifact$center),2,artifact$scale,'/')
 frame$D<-plogis(qlogis(frame$q_D)+as.vector(cbind(1,X)%*%artifact$coefficients))
 frame$W<-frame$q_W*(1-frame$D)/(1-frame$q_D);frame$L<-frame$q_L*(1-frame$D)/(1-frame$q_D)
 stopifnot(all(frame$D>0 & frame$D<1))
 frame$model_seal<-artifact$seal;frame
}
