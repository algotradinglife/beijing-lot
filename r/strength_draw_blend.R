# Fixed retrospective mixing of frozen strength draw and market WDL.
# Label-free rows require issue, cutoff_ts, fixture_decision_ts, q_W/D/L, p_D.
# Explicit shared Cutoff must match the frozen issue clock; this is not new
# historical learning or proof of prospective source availability. No I/O/fits.
strength_draw_blend <- function(frame, cutoff, weights) {
 required<-c('issue','slot','provider_id','handicap','cutoff_ts','fixture_decision_ts','q_W','q_D','q_L','p_D')
 stopifnot(all(required %in% names(frame)),!anyNA(frame[required]))
 core<-reticulate::import('src.temporal_learning.core')
 stopifnot(nrow(frame)>0,length(unique(frame$issue))==1,length(unique(frame$cutoff_ts))==1,
  isTRUE(cutoff==core$Cutoff$decision_epoch(unique(frame$issue),unique(frame$cutoff_ts))),
  !any(c('actual','actual_outcome','actual_direction') %in% names(frame)),
  !anyDuplicated(frame[c('issue','slot','provider_id')]),
  length(weights)>0,!anyDuplicated(weights),all(is.finite(weights)),all(weights>=0 & weights<=1))
 for(t in frame$fixture_decision_ts)stopifnot(isTRUE(core$utc(t)>=cutoff$cutoff_ts))
 q<-as.matrix(frame[c('q_W','q_D','q_L')])
 stopifnot(all(is.finite(q)),all(q>0),all(abs(rowSums(q)-1)<1e-10),
  all(is.finite(frame$p_D)),all(frame$p_D>=0 & frame$p_D<1))
 out<-list()
 for(w in weights) {
  d<-(1-w)*frame$q_D+w*frame$p_D
  out[[length(out)+1L]]<-dplyr::transmute(frame,issue,slot,provider_id,handicap,
   model=paste0('BLEND_',w),W=q_W*(1-d)/(1-q_D),D=d,L=q_L*(1-d)/(1-q_D))
 }
 dplyr::bind_rows(out)
}
