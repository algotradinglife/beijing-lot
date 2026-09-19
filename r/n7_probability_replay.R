# Rebuild only probabilities of an existing frozen seven-fixture universe.
# The original raw-market prices, fixture membership and canonical states stay
# fixed. Explicit target cutoff and prediction identity bind a diagnostic copy;
# never reuse the original seal to represent a changed probability model.
# prediction: unique issue/slot/provider_id, new_W/D/L. No outcome labels.
n7_probability_bundle <- function(bundle, prediction, cutoffs, model_identity) {
 stopifnot(identical(bundle$cutoffs,cutoffs),identical(bundle$historical_admission,FALSE),
  length(model_identity)==1,is.character(model_identity),nzchar(model_identity),
  nrow(prediction)==length(bundle$expanded_pool$fixtures),
  !anyDuplicated(prediction[c('issue','slot','provider_id')]),
  !any(c('actual','actual_direction') %in% names(prediction)))
 p<-as.matrix(prediction[c('new_W','new_D','new_L')])
 stopifnot(all(is.finite(p)),all(p>0),all(abs(rowSums(p)-1)<1e-10))
 n7_sleeve_tables(bundle,cutoffs,model_identity)
 out<-bundle
 for(i in seq_along(out$expanded_pool$fixtures)) {
  f<-out$expanded_pool$fixtures[[i]]
  j<-which(prediction$issue==f$issue & prediction$slot==f$slot & prediction$provider_id==f$provider_id)
  stopifnot(length(j)==1)
  f$p_W<-unname(p[j,1]);f$p_D<-unname(p[j,2]);f$p_L<-unname(p[j,3])
  out$expanded_pool$fixtures[[i]]<-f
 }
 for(i in seq_along(out$sleeves)) {
  g<-out$sleeves[[i]];e<-g$enumeration
  e$fixtures<-out$expanded_pool$fixtures[as.integer(unlist(g$fixture_indices))+1L]
  states<-matrix(as.integer(unlist(e$states)),nrow=2187,byrow=TRUE)
  prob<-rep(1,2187)
  for(k in seq_len(7)) {
   f<-e$fixtures[[k]];prob<-prob*c(f$p_W,f$p_D,f$p_L)[states[,k]+1L]
  }
  e$probability<-as.list(prob)
  e$expected_contribution<-as.list(prob*as.numeric(unlist(e$estimated_payout)))
  e$source_enumeration_seal<-e$seal;e$model_identity<-model_identity
  e$seal<-digest::digest(e[names(e)!='seal'],algo='sha256')
  g$enumeration<-e;g$options<-list();out$sleeves[[i]]<-g
 }
 out$source_bundle_seal<-bundle$seal
 out$model_identity<-model_identity
 out$seal<-digest::digest(out[names(out)!='seal'],algo='sha256')
 out
}

# Same SP gate, 25%-style prefix partition, joint-world allocator and unit as
# previous experiments; every parameter explicit. Returns the full surface,
# legal pool, shared scenarios and selected option indices for independent replay.
# Does not read settlement. Lack of legal/affordable groups retains cash.
n7_probability_allocate <- function(bundle, cutoffs, model_identity, python,
                                    target_coverage, group_cap, minimum_sp,
                                    budget_cny, unit_cny, payout_factor, seed,
                                    worlds_count, max_actions) {
 base<-n7_capital_options(bundle,cutoffs,python,model_identity,15L,unit_cny,payout_factor)
 features<-n7_core_curve_features(base$surface,cutoffs,cutoffs,target_coverage,unit_cny)
 part<-n7_sweet_union_partition(features,cutoffs,cutoffs,target_coverage,group_cap,unit_cny)
 depths<-sort(unique(c(15L,unlist(part$opening_depths))))
 base<-n7_capital_options(bundle,cutoffs,python,model_identity,depths,unit_cny,payout_factor)
 gate<-n7_sp_filter(base,part,cutoffs,minimum_sp)
 pool<-n7_core_option_pool(base,gate$partition,cutoffs,'BREADTH',1)
 worlds<-n7_joint_worlds(pool,cutoffs,seed,worlds_count)
 scenarios<-n7_joint_returns(pool,worlds,cutoffs)
 fit<-n7_core_allocate(pool,scenarios,cutoffs,budget_cny,'any_hit',max_actions,'OPEN_FIRST')
 stopifnot(fit$stop_reason!='ACTION_LIMIT')
 list(surface=base$surface,gate=gate,pool=pool,worlds=worlds,scenarios=scenarios,fit=fit)
}
