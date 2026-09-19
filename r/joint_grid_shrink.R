# Mix sealed fine/coarse return forecasts at one explicit target cutoff.
# frame: unique issue/cell, fine_score/coarse_score (gross/stake ratios),
# fine_ready/coarse_ready logical, cutoff_identity. No outcomes or I/O.
# input_receipt binds the plain frame, cutoff and upstream model identity.
# lambda is the fixed coarse weight in [0,1], not selected from target labels.
# Interior weights require both forecasts; endpoints require only their component.
# Unsupported cells remain UNKNOWN and cause no allocation action.
# Returns BLEND-only allocator-compatible signals (no long component is inferred);
# RECENT allocation fails closed because long_return_ratio is missing.
# Returns signals and a receipt binding inputs/parameters.
joint_grid_shrink <- function(frame, cutoff, model_receipt_sha256, lambda) {
  required<-c('issue','cell','fine_score','coarse_score','fine_ready','coarse_ready','cutoff_identity')
  stopifnot(all(required %in% names(frame)),length(lambda)==1L,is.finite(lambda),lambda>=0,lambda<=1,
    identical(cutoff$cutoff_kind,'DECISION_EPOCH'),identical(cutoff$historical_admission,FALSE),
    is.character(model_receipt_sha256),length(model_receipt_sha256)==1L,
    grepl('^[a-f0-9]{64}$',model_receipt_sha256),
    identical(cutoff$model_receipt_sha256,model_receipt_sha256),
    length(cutoff$target_issue)==1L,length(cutoff$cutoff_identity)==1L,length(cutoff$cutoff_ts)==1L,
    !anyNA(frame[c('issue','cell','cutoff_identity')]),!anyDuplicated(frame$cell),
    all(frame$issue==cutoff$target_issue),all(frame$cutoff_identity==cutoff$cutoff_identity),
    is.logical(frame$fine_ready),is.logical(frame$coarse_ready),
    !anyNA(frame[c('fine_ready','coarse_ready')]))
  plain<-frame;receipt<-attr(plain,'input_receipt');attr(plain,'input_receipt')<-NULL
  stopifnot(identical(receipt$cutoff,cutoff),identical(receipt$hash,digest::digest(plain,algo='sha256')))
  for(side in c('fine','coarse')) {
    v<-frame[[paste0(side,'_score')]][frame[[paste0(side,'_ready')]]]
    stopifnot(all(is.finite(v)),all(v>=0))
  }
  ready<-if(lambda==0)frame$fine_ready else if(lambda==1)frame$coarse_ready else frame$fine_ready & frame$coarse_ready
  score<-rep(NA_real_,nrow(frame))
  if(lambda==0)score[ready]<-frame$fine_score[ready] else if(lambda==1)score[ready]<-frame$coarse_score[ready] else
    score[ready]<-(1-lambda)*frame$fine_score[ready]+lambda*frame$coarse_score[ready]
  out<-tibble::tibble(issue=frame$issue,cell=frame$cell,return_ratio=score,
    long_return_ratio=rep(NA_real_,nrow(frame)),supported=ready,long_hit_signal=ifelse(ready,'READY','UNKNOWN'))
  attr(out,'input_receipt')<-list(cutoff=cutoff,hash=digest::digest(out,algo='sha256'),
    source_frame_sha256=receipt$hash,coarse_weight=lambda,source_model=model_receipt_sha256)
  out
}
