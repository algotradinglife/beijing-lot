# Prepare a refilled capital pool from immutable JSON text. All business constants,
# cutoff identities and Python interpreter are explicit. Uses authoritative state
# enumeration and curve/admission functions; no labels, fitting or persistence.
# Return the refill ledger, full-state JSON, capital pool and admission partition.
# Unchanged groups return unchanged input JSON; empty groups retain original
# surfaces with empty admission, allowing the existing allocator to hold cash.
n7_sp_refill_prepare <- function(bundle_json,cutoffs,python,model_id,minimum_sp,
  candidate_count,seed,maximum_attempts,depths,reference_targets,target,cap_cny,
  unit_cny,payout_factor,n) {
  stopifnot(length(bundle_json)==1,is.character(bundle_json),unit_cny==2,
    payout_factor==.65,n==7,target %in% reference_targets)
  bundle<-jsonlite::fromJSON(bundle_json,simplifyVector=FALSE)
  stopifnot(identical(bundle$cutoffs,cutoffs))
  initial<-n7_capital_options(bundle,cutoffs,python,model_id,15L,unit_cny,payout_factor)
  features<-n7_core_curve_features(initial$surface,cutoffs,cutoffs,reference_targets,unit_cny)
  partition<-n7_sweet_union_partition(features,cutoffs,cutoffs,target,cap_cny,unit_cny)
  original_parts<-lapply(reference_targets,function(t)
    n7_sweet_union_partition(features,cutoffs,cutoffs,t,cap_cny,unit_cny))
  original_grid<-sort(unique(c(depths,unlist(lapply(original_parts,`[[`,'opening_depths')))))
  refill<-n7_sp_refill(initial,partition,cutoffs,minimum_sp,candidate_count,seed,maximum_attempts,n)
  unchanged<-length(refill$groups)==length(bundle$sleeves) &&
    all(vapply(refill$groups,function(g)g$origin=='RETAINED',logical(1)))
  materialized<-bundle_json
  if(!unchanged && length(refill$groups)) {
    reticulate::use_python(python,required=TRUE)
    json<-reticulate::import('json',convert=FALSE)
    adapter<-reticulate::import('src.n7_sp_refill',convert=FALSE)
    object<-adapter$materialize_refill(json$loads(bundle_json),
      json$loads(as.character(jsonlite::toJSON(refill$groups,auto_unbox=TRUE,digits=NA))),
      cutoffs=json$loads(as.character(jsonlite::toJSON(cutoffs,auto_unbox=TRUE))),
      unit_cny=unit_cny,payout_factor=payout_factor)
    materialized<-reticulate::py_to_r(json$dumps(object))
    bundle<-jsonlite::fromJSON(materialized,simplifyVector=FALSE)
    initial<-n7_capital_options(bundle,cutoffs,python,model_id,15L,unit_cny,payout_factor)
    features<-n7_core_curve_features(initial$surface,cutoffs,cutoffs,reference_targets,unit_cny)
  }
  parts<-lapply(reference_targets,function(t)
    n7_sweet_union_partition(features,cutoffs,cutoffs,t,cap_cny,unit_cny))
  partition<-parts[[match(target,reference_targets)]]
  new_ids<-vapply(Filter(function(g)g$origin=='REFILL_TOP2',refill$groups),
    function(g)as.character(g$sleeve_id),character(1))
  new_openings<-partition$opening_depths[intersect(names(partition$opening_depths),new_ids)]
  grid<-sort(unique(c(original_grid,unlist(new_openings))))
  base<-n7_capital_options(bundle,cutoffs,python,model_id,grid,unit_cny,payout_factor)
  base$options<-Filter(function(o)o$depth %in% original_grid ||
    (as.character(o$sleeve_id) %in% names(new_openings) &&
     o$depth==new_openings[[as.character(o$sleeve_id)]]),base$options)
  refill$original_depth_grid<-original_grid
  refill$new_group_opening_depths<-as.list(new_openings)
  gate<-n7_sp_filter(base,partition,cutoffs,minimum_sp)
  list(base=base,partition=gate$partition,refill=refill,bundle_json=materialized,
    unchanged=unchanged,cutoffs=cutoffs,historical_admission=FALSE)
}
