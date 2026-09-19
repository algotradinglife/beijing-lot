# Fixed, untuned diagnostic variants of an already frozen handicap model.
# Inputs: sealed draw_handicap artifact, label-free fixture frame, shared Cutoff,
# explicit policies and runtime. Output: probabilities and cutoff/source/code
# receipt. No target outcomes, fitting, selection or filesystem writes.
# Weak variants multiply the correction; sparse weights use frozen cell N;
# local gate requires enough historical support and a Wilson interval excluding
# the target raw draw probability in the same direction as the frozen correction.
draw_correction_candidates <- function(artifact, frame, cutoff, alpha, weak_weights,
                                      sparse_strength, local_minimum, local_z,
                                      repository_root, python) {
 stopifnot(length(weak_weights)>0,all(is.finite(weak_weights)),all(weak_weights>0 & weak_weights<1),
  !anyDuplicated(weak_weights),length(sparse_strength)==1,is.finite(sparse_strength),sparse_strength>0,
  length(local_minimum)==1,is.finite(local_minimum),local_minimum>0,
  length(local_z)==1,is.finite(local_z),local_z>0,
  !any(c('actual','actual_outcome','actual_direction') %in% names(frame)))
 z<-draw_handicap_predict(artifact,frame,cutoff,alpha,repository_root,python)
 n<-pmax(z$h_n,1);rate<-z$h_rate
 centre<-(rate+local_z^2/(2*n))/(1+local_z^2/n)
 radius<-local_z*sqrt(rate*(1-rate)/n+local_z^2/(4*n^2))/(1+local_z^2/n)
 gate<-z$h_n>=local_minimum & ((centre-radius>z$q_D & z$new_D>z$q_D) |
  (centre+radius<z$q_D & z$new_D<z$q_D))
 weights<-list(RAW=rep(0,nrow(z)),DYNAMIC=rep(1,nrow(z)))
 for(w in weak_weights)weights[[paste0('WEAK_',format(w,trim=TRUE))]]<-rep(w,nrow(z))
 weights$SPARSE<-z$h_n/(z$h_n+sparse_strength)
 weights$LOCAL<-as.numeric(gate)
 out<-list()
 for(name in names(weights)) {
  w<-weights[[name]];d<-z$q_D+w*(z$new_D-z$q_D)
  out[[name]]<-dplyr::transmute(z,issue,slot,provider_id,handicap,fixture_decision_ts,
   model=name,W=q_W*(1-d)/(1-q_D),D=d,L=q_L*(1-d)/(1-q_D),
   correction_weight=w,h_n,h_rate,local_lower=centre-radius,local_upper=centre+radius)
 }
 rows<-dplyr::bind_rows(out)
 ctx<-jsonlite::fromJSON(artifact$parent$context_json,simplifyVector=FALSE)
 receipt<-list(cutoff_identity=cutoff$identity,cutoff_ts=as.character(cutoff$cutoff_ts),
  target_issue=cutoff$target_issue,parent_model_seal=artifact$seal,
  historical_context=ctx$receipt,parameters=list(alpha=alpha,weak_weights=weak_weights,
   sparse_strength=sparse_strength,local_minimum=local_minimum,local_z=local_z),
  implementation_sha256=digest::digest(file=file.path(repository_root,'r/draw_correction_candidates.R'),algo='sha256'),
  input_sha256=digest::digest(frame,algo='sha256'),output_sha256=digest::digest(rows,algo='sha256'),
  historical_admission=FALSE)
 list(rows=rows,receipt=receipt)
}
