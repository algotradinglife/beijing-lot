# Shorten frozen funded probability prefixes; no labels, fitting, RNG or IO.
# curves: one group/depth row for every depth 0..2187 with coverage and expected
# gross in CNY; funded: one issue/arm/seed/group, copies and CNY stake. rules:
# unique variant with mode original/cap/fraction/coverage and numeric value.
# Explicit cutoff maps must match. Returns one funded group/rule, never extends
# original depth. Saved funds are cash; copies remain unchanged. Invalid or
# missing inputs fail. Empty funded input returns a typed empty result.
n7_prefix_stop <- function(curves,funded,rules,cutoffs,expected_cutoffs,unit_cny) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,unit_cny==2,
    dplyr::n_distinct(funded$issue)<=1,nrow(rules)>0,!anyNA(rules),!anyDuplicated(rules$variant),
    all(rules$mode %in% c('original','cap','fraction','coverage')),
    all(is.finite(rules$value)),
    !anyDuplicated(funded[c('issue','arm','seed','sleeve_id')]),
    all(is.finite(funded$depth)),all(funded$depth %in% 1:2187),
    all(funded$copies>=1 & funded$copies==floor(funded$copies)),
    all(funded$stake==funded$depth*funded$copies*unit_cny))
  for(i in seq_len(nrow(rules))) {
    m<-rules$mode[i];v<-rules$value[i]
    stopifnot(if(m=='cap')v %in% 1:2187 else if(m %in% c('fraction','coverage'))v>0 && v<=1 else v==1)
  }
  curves$sleeve_id<-as.character(curves$sleeve_id);funded$sleeve_id<-as.character(funded$sleeve_id)
  stopifnot(!anyDuplicated(curves[c('sleeve_id','depth')]),
    all(funded$sleeve_id %in% curves$sleeve_id))
  for(id in unique(curves$sleeve_id)) {
    z<-curves[curves$sleeve_id==id,];z<-z[order(z$depth),]
    stopifnot(identical(as.integer(z$depth),0:2187),all(is.finite(z$coverage)),
      z$coverage[1]==0,abs(tail(z$coverage,1)-1)<1e-8,
      all(diff(z$coverage)>=-1e-12),all(is.finite(z$expected_gross)),
      all(z$expected_gross>=0),all(diff(z$expected_gross)>=-1e-10))
  }
  original<-funded |> dplyr::rename(original_depth=depth,original_stake=stake,
    original_coverage=coverage,original_expected_gross=expected_gross)
  original<-original |> dplyr::left_join(curves |> dplyr::select(sleeve_id,depth,coverage,expected_gross),
    by=c('sleeve_id','original_depth'='depth'),relationship='many-to-one')
  stopifnot(all(abs(original$original_coverage-original$coverage)<1e-9),
    all(abs(original$original_expected_gross-original$expected_gross*original$copies)<1e-6))
  original<-original |> dplyr::select(-coverage,-expected_gross)
  parts<-lapply(seq_len(nrow(rules)),function(i) {
    x<-original;m<-rules$mode[i];v<-rules$value[i];x$variant<-rep(rules$variant[i],nrow(x))
    target<-if(m=='original')x$original_depth else if(m=='cap')rep(v,nrow(x)) else
      if(m=='fraction')pmax(1,floor(x$original_depth*v)) else {
        ids<-unique(curves$sleeve_id)
        depths<-vapply(ids,function(id)min(curves$depth[curves$sleeve_id==id & curves$coverage>=v-1e-12]),numeric(1))
        unname(depths[match(x$sleeve_id,ids)])
      }
    x$depth<-pmin(x$original_depth,target)
    x<-x |> dplyr::left_join(curves |> dplyr::select(sleeve_id,depth,coverage,expected_gross),
      by=c('sleeve_id','depth'),relationship='many-to-one')
    x |> dplyr::mutate(stake=depth*copies*unit_cny,expected_gross=expected_gross*copies,
      saved_stake=original_stake-stake,lost_coverage=original_coverage-coverage)
  })
  dplyr::bind_rows(parts)
}
