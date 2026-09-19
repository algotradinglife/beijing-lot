# Fixed prediction-only candidate gate. shape must be n7_purchase_shape output
# from this pool/cutoff, one row per sleeve. minimum_mass64 favours a concentrated
# head; max_cost_ratio limits cost_0.25 relative to the median eligible candidate
# cost before filtering. Reciprocal lower bound forms a symmetric multiplicative
# band. Inf disables similarity filtering. No labels/history fit/I/O.
n7_purchase_group_filter <- function(pool,shape,cutoffs,minimum_mass64,
                                     minimum_core,maximum_opportunity,max_cost_ratio) {
 stopifnot(identical(pool$cutoffs,cutoffs),identical(attr(shape,'cutoffs'),cutoffs),
  identical(attr(shape,'prediction_hash'),digest::digest(list(pool$fixtures,pool$options),algo='sha256')),
  length(cutoffs)>0,length(pool$opportunity_options)==0,
  all(c('sleeve_id','mass_64','cost_0.25','core_count','opportunity_count') %in% names(shape)),
  !anyDuplicated(shape$sleeve_id),!anyNA(shape),
  length(minimum_mass64)==1,is.finite(minimum_mass64),minimum_mass64>=0,minimum_mass64<=1,
  length(minimum_core)==1,minimum_core %in% 0:7,
  length(maximum_opportunity)==1,maximum_opportunity %in% 0:7,
  length(max_cost_ratio)==1,!is.na(max_cost_ratio),max_cost_ratio>=1)
 ids<-vapply(pool$options,`[[`,numeric(1),'sleeve_id')
 stopifnot(setequal(unique(ids),shape$sleeve_id),all(is.finite(shape[['cost_0.25']])),all(shape[['cost_0.25']]>0))
 reference<-if(nrow(shape))stats::median(shape[['cost_0.25']]) else NA_real_
 keep<-shape$mass_64>=minimum_mass64 & shape$core_count>=minimum_core &
  shape$opportunity_count<=maximum_opportunity & shape[['cost_0.25']]<=reference*max_cost_ratio &
  shape[['cost_0.25']]>=reference/max_cost_ratio
 ix<-which(ids %in% shape$sleeve_id[keep]);out<-pool
 out$options<-pool$options[ix]
 out$opening_options<-match(intersect(pool$opening_options,ix),ix)
 out$group_gate<-list(reference_cost=reference,minimum_mass64=minimum_mass64,
  minimum_core=minimum_core,maximum_opportunity=maximum_opportunity,max_cost_ratio=max_cost_ratio,
  admitted_ids=shape$sleeve_id[keep],shape_hash=digest::digest(shape,algo='sha256'))
 out
}
