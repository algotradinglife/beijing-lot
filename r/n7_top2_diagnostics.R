# Post-settlement paired diagnostics; no fitting, routing, or I/O.
# ranks: one issue/arm/sleeve_id, complete PROB/SOFT/HARD/FULL per model,
# actual_rank (extended settlement order), purchase_rank (NA when forbidden),
# actual_legal, actual_top2, actual_gross_cny (already includes payout factor).
# funded: unique issue/arm/sleeve_id with depth,stake; amounts CNY, one copy.
# Returns complete-flow replacements plus a SAME original groups/depths
# counterfactual for SOFT/HARD only. FULL is not truncated into another policy.
n7_top2_diagnostics <- function(ranks,funded) {
 keys<-c('issue','arm','sleeve_id')
 stopifnot(nrow(ranks)>0,all(c(keys,'actual_rank','purchase_rank','actual_legal',
  'actual_top2','actual_gross_cny') %in% names(ranks)),
  all(c(keys,'depth','stake') %in% names(funded)),
  !anyDuplicated(ranks[keys]),!anyDuplicated(funded[keys]),
  !anyNA(ranks[c(keys,'actual_rank','actual_legal','actual_top2','actual_gross_cny')]),
  is.logical(ranks$actual_legal),is.logical(ranks$actual_top2),
  all(ranks$actual_rank %in% 1:2187),
  all(ranks$actual_legal==!is.na(ranks$purchase_rank)),
  all(ranks$purchase_rank[ranks$actual_legal] %in% 1:2187),
  all(is.finite(ranks$actual_gross_cny)),all(ranks$actual_gross_cny>=0),
  !anyNA(funded[c(keys,'depth','stake')]),all(funded$depth %in% 1:128),
  all(funded$stake==2*funded$depth),nrow(dplyr::anti_join(funded,ranks,by=keys))==0)
 z<-ranks |> dplyr::mutate(model=sub('_[^_]+$','',arm),mode=sub('^.*_','',arm))
 stopifnot(all(z$mode %in% c('PROB','SOFT','HARD','FULL')))
 stopifnot(all(z$actual_rank[z$actual_legal]==z$purchase_rank[z$actual_legal]),
  all(z$actual_legal[z$mode %in% c('PROB','SOFT')]),
  all(z$actual_legal[z$mode %in% c('HARD','FULL')]==z$actual_top2[z$mode %in% c('HARD','FULL')]),
  all(z$actual_rank[!z$actual_legal]>128))
 check<-z |> dplyr::group_by(issue,model,sleeve_id) |> dplyr::summarise(
  modes=dplyr::n_distinct(mode),top2=dplyr::n_distinct(actual_top2),
  payout=dplyr::n_distinct(actual_gross_cny),.groups='drop')
 stopifnot(all(check$modes==4),all(check$top2==1),all(check$payout==1))
 z<-z |> dplyr::left_join(funded |> dplyr::select(dplyr::all_of(keys),depth,stake),
  by=keys,relationship='one-to-one') |>
  dplyr::mutate(depth=tidyr::replace_na(depth,0),stake=tidyr::replace_na(stake,0),
   hit=actual_legal & actual_rank<=depth,gross=ifelse(hit,actual_gross_cny,0))
 stopifnot(all(z$depth[z$mode=='FULL'] %in% c(0,128)))
 base<-z |> dplyr::filter(mode=='PROB') |>
  dplyr::select(issue,model,sleeve_id,base_depth=depth,base_stake=stake,base_hit=hit,base_gross=gross)
 paired<-z |> dplyr::left_join(base,by=c('issue','model','sleeve_id'),relationship='many-to-one')
 flow<-paired |> dplyr::group_by(model,mode) |> dplyr::summarise(
  candidates=dplyr::n(),bought_groups=sum(depth>0),winning_groups=sum(hit),
  rescued_groups=sum(hit & !base_hit),lost_groups=sum(!hit & base_hit),
  third_lost_groups=sum(!hit & base_hit & !actual_top2),
  rescued_gross=sum(gross[hit & !base_hit]),lost_gross=sum(base_gross[!hit & base_hit]),
  stake_change=sum(stake-base_stake),net_change=sum(gross-stake-base_gross+base_stake),.groups='drop')
 fixed_groups<-paired |> dplyr::filter(mode %in% c('SOFT','HARD'),base_depth>0) |>
  dplyr::mutate(fixed_hit=actual_legal & tidyr::replace_na(purchase_rank<=base_depth,FALSE),
   fixed_gross=ifelse(fixed_hit,actual_gross_cny,0))
 fixed<-fixed_groups |>
  dplyr::group_by(model,mode) |> dplyr::summarise(groups=dplyr::n(),stake=sum(base_stake),
   original_hits=sum(base_hit),fixed_hits=sum(fixed_hit),
   rescued=sum(fixed_hit & !base_hit),lost=sum(!fixed_hit & base_hit),
   gross_change=sum(fixed_gross-base_gross),.groups='drop')
 list(paired=paired,flow=flow,fixed_depth=fixed,fixed_groups=fixed_groups)
}

# Descriptive all-seven Top2 calibration. Both tables must contain identical
# PROB candidate keys; missing either side is an error, never implicit exclusion.
# coverage supplies top2_mass, ranks supplies logical actual_top2. Other policies
# are excluded explicitly to avoid counting each candidate four times.
n7_top2_joint_calibration <- function(coverage,ranks,breaks) {
 keys<-c('issue','arm','sleeve_id')
 stopifnot(all(c(keys,'top2_mass') %in% names(coverage)),
  all(c(keys,'actual_top2') %in% names(ranks)),is.numeric(breaks),length(breaks)>=2,
  breaks[1]==0,tail(breaks,1)==1,all(diff(breaks)>0))
 a<-coverage |> dplyr::filter(grepl('_PROB$',arm)) |>
  dplyr::select(dplyr::all_of(keys),top2_mass)
 b<-ranks |> dplyr::filter(grepl('_PROB$',arm)) |>
  dplyr::select(dplyr::all_of(keys),actual_top2)
 stopifnot(nrow(a)>0,nrow(b)>0,!anyNA(a),!anyNA(b),
  !anyDuplicated(a[keys]),!anyDuplicated(b[keys]),is.logical(b$actual_top2),
  all(is.finite(a$top2_mass)),all(a$top2_mass>=0 & a$top2_mass<=1),
  nrow(dplyr::anti_join(a,b,by=keys))==0,nrow(dplyr::anti_join(b,a,by=keys))==0)
 joined<-dplyr::inner_join(a,b,by=keys,relationship='one-to-one') |>
  dplyr::mutate(prob_model=sub('_PROB$','',arm),mass_bin=cut(top2_mass,breaks,include.lowest=TRUE))
 summary<-joined |> dplyr::group_by(prob_model,mass_bin) |>
  dplyr::summarise(groups=dplyr::n(),issues=dplyr::n_distinct(issue),
   predicted=mean(top2_mass),observed=mean(actual_top2),.groups='drop')
 list(joined=joined,summary=summary)
}
