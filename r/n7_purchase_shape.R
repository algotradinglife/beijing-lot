# Prediction-only shape descriptors for already admitted seven-fixture groups.
# One row per sleeve. Prefix probabilities use original state mass, never purchase
# weights. Rank cost counts CNY2 tickets. role thresholds are explicit research
# constants: core requires Top1 >= core_probability AND p2-p3 >= clear_gap;
# opportunity has Top1 < opportunity_probability; all others are middle.
# These are probability descriptors, not validated empirical confidence scores.
# No fitting, labels, RNG or I/O. Exact cutoff map binds the input pool.
n7_purchase_shape <- function(pool,cutoffs,prefixes,targets,unit_cny,
                              core_probability,opportunity_probability,clear_gap) {
 stopifnot(identical(pool$cutoffs,cutoffs),length(cutoffs)>0,
  length(unit_cny)==1,is.numeric(unit_cny),is.finite(unit_cny),
  length(core_probability)==1,is.finite(core_probability),
  length(opportunity_probability)==1,is.finite(opportunity_probability),
  length(clear_gap)==1,is.finite(clear_gap),
  length(prefixes)>0,!anyDuplicated(prefixes),all(prefixes %in% 1:2187),
  length(targets)>0,!anyDuplicated(targets),all(is.finite(targets)),all(targets>0 & targets<1),
  unit_cny==2,core_probability>opportunity_probability,core_probability<=1,
  opportunity_probability>=0,clear_gap>=0,clear_gap<=1)
 opts<-pool$options[!duplicated(vapply(pool$options,`[[`,numeric(1),'sleeve_id'))]
 rows<-lapply(opts,function(o) {
  p<-o$state_probability
  stopifnot(length(p)==2187,all(is.finite(p)),all(p>=0),abs(sum(p)-1)<1e-8)
  pp<-sort(p,decreasing=TRUE);cumulative<-cumsum(pp)
  f<-dplyr::bind_rows(pool$fixtures[o$fixtures])
  q<-t(apply(as.matrix(f[c('p_W','p_D','p_L')]),1,sort,decreasing=TRUE))
  stopifnot(nrow(q)==7,all(is.finite(q)),all(q>=0),all(abs(rowSums(q)-1)<1e-8))
  gap12<-q[,1]-q[,2];gap23<-q[,2]-q[,3]
  core<-q[,1]>=core_probability & gap23>=clear_gap
  chance<-q[,1]<opportunity_probability
  row<-tibble::tibble(sleeve_id=o$sleeve_id,core_count=sum(core),middle_count=sum(!core & !chance),
   opportunity_count=sum(chance),mean_top1=mean(q[,1]),mean_top2=mean(q[,1]+q[,2]),
   minimum_gap12=min(gap12),minimum_gap23=min(gap23),ambiguous_count=sum(gap23<clear_gap),
   entropy=-sum(p[p>0]*log(p[p>0])),top2_mass=prod(q[,1]+q[,2]))
  for(k in prefixes)row[[paste0('mass_',k)]]<-cumulative[k]
  for(t in targets)row[[paste0('cost_',format(t,scientific=FALSE))]]<-which(cumulative>=t)[1]*unit_cny
  row
 })
 schema<-tibble::tibble(sleeve_id=double(),core_count=integer(),middle_count=integer(),
  opportunity_count=integer(),mean_top1=double(),mean_top2=double(),minimum_gap12=double(),
  minimum_gap23=double(),ambiguous_count=integer(),entropy=double(),top2_mass=double())
 for(k in prefixes)schema[[paste0('mass_',k)]]<-double()
 for(t in targets)schema[[paste0('cost_',format(t,scientific=FALSE))]]<-double()
 result<-dplyr::bind_rows(schema,rows);attr(result,'cutoffs')<-cutoffs
 attr(result,'prediction_hash')<-digest::digest(list(pool$fixtures,pool$options),algo='sha256')
 attr(result,'parameters')<-list(prefixes=prefixes,targets=targets,unit_cny=unit_cny,
  core_probability=core_probability,opportunity_probability=opportunity_probability,clear_gap=clear_gap)
 result
}
