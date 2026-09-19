# Descriptive rank-2/rank-3 calibration, no fit, selection or I/O.
# frame: unique issue/slot/provider_id/model, stage, signed integer handicap,
# actual_outcome W/D/L, p_W/p_D/p_L. All models cover identical fixtures.
# Fractions and probabilities use 0..1; deterministic ties W,D,L.
# Explicit bins are descriptive only. The issue residual variance is the
# independent-fixture reference, not an independence claim or significance test.
# Requires strategy_probability_diagnostics(); returns fixture, cell and issue
# tables. Invalid/empty/duplicate/missing/inconsistent observations fail.
third_outcome_diagnostics <- function(frame,gap_breaks,third_breaks) {
 keys<-c('issue','slot','provider_id','model')
 stopifnot(all(c(keys,'stage','handicap','actual_outcome','p_W','p_D','p_L') %in% names(frame)),
  !anyDuplicated(frame[keys]),is.numeric(frame$handicap),
  all(is.finite(frame$handicap)),all(frame$handicap==round(frame$handicap)),
  is.numeric(gap_breaks),is.numeric(third_breaks),
  length(gap_breaks)>=2,length(third_breaks)>=2,
  !anyNA(gap_breaks),!anyNA(third_breaks),
  gap_breaks[1]==0,tail(gap_breaks,1)==1,all(diff(gap_breaks)>0),
  third_breaks[1]==0,tail(third_breaks,1)==1,all(diff(third_breaks)>0))
 long<-frame |> tidyr::pivot_longer(c(p_W,p_D,p_L),names_prefix='p_',
  names_to='outcome',values_to='probability')
 checked<-strategy_probability_diagnostics(long,c('stage','handicap'),c('W','D','L'),third_breaks)
 ranked<-long |> dplyr::mutate(class_order=match(outcome,c('W','D','L'))) |>
  dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |>
  dplyr::arrange(dplyr::desc(probability),class_order,.by_group=TRUE) |>
  dplyr::summarise(stage=dplyr::first(stage),handicap=dplyr::first(handicap),
   actual_outcome=dplyr::first(actual_outcome),p1=probability[1],p2=probability[2],p3=probability[3],
   first=outcome[1],second=outcome[2],third=outcome[3],.groups='drop') |>
  dplyr::mutate(gap23=p2-p3,third_hit=actual_outcome==third,second_hit=actual_outcome==second,
   gap_bin=cut(gap23,gap_breaks,include.lowest=TRUE),
   third_bin=cut(p3,third_breaks,include.lowest=TRUE))
 stopifnot(!anyNA(ranked))
 cells<-ranked |> dplyr::group_by(stage,model,handicap,third,gap_bin,third_bin) |>
  dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
   predicted_third=mean(p3),observed_third=mean(third_hit),
   predicted_second=mean(p2),observed_second=mean(second_hit),.groups='drop')
 issues<-ranked |> dplyr::group_by(stage,model,issue) |>
  dplyr::summarise(fixtures=dplyr::n(),expected_third=sum(p3),actual_third=sum(third_hit),
   independent_variance=sum(p3*(1-p3)),.groups='drop') |>
  dplyr::mutate(residual=actual_third-expected_third,
   expected_fraction=expected_third/fixtures,actual_fraction=actual_third/fixtures,
   standardized_residual=ifelse(independent_variance>0,residual/sqrt(independent_variance),NA_real_))
 list(fixtures=ranked,cells=cells,issues=issues,probability_summary=checked$summary)
}

# Descriptive dependence among funded groups. One row per model/issue/sleeve/
# fixture with p3 and observed third_hit. Seven distinct slots per group.
# Exact variance reference shares one Bernoulli fixture outcome across groups;
# it assumes independence BETWEEN distinct fixtures, not between reused groups.
# Returns group third-count distribution and fixture fanout plus issue moments.
third_outcome_group_risk <- function(members) {
 keys<-c('model','issue','sleeve_id','slot')
 stopifnot(nrow(members)>0,all(c(keys,'provider_id','p3','third_hit') %in% names(members)),
  !anyNA(members[c(keys,'provider_id','p3','third_hit')]),!anyDuplicated(members[keys]),
  is.logical(members$third_hit),all(is.finite(members$p3)),all(members$p3>=0 & members$p3<=1))
 unique_fixture<-members |> dplyr::distinct(model,issue,slot,provider_id,p3,third_hit)
 stopifnot(!anyDuplicated(unique_fixture[c('model','issue','slot')]))
 groups<-members |> dplyr::group_by(model,issue,sleeve_id) |>
  dplyr::summarise(fixtures=dplyr::n(),thirds=sum(third_hit),
   expected_all_top2=prod(1-p3),actual_all_top2=all(!third_hit),.groups='drop')
 stopifnot(all(groups$fixtures==7))
 fanout<-members |> dplyr::group_by(model,issue,slot,provider_id,p3,third_hit) |>
  dplyr::summarise(groups=dplyr::n(),.groups='drop')
 periods<-dplyr::group_split(dplyr::group_by(members,model,issue));moments<-list()
 for(z in periods) {
  sets<-split(z$slot,z$sleeve_id);u<-z |> dplyr::distinct(slot,p3,third_hit)
  survival<-setNames(1-u$p3,as.character(u$slot))
  means<-vapply(sets,function(slots)prod(survival[as.character(slots)]),numeric(1))
  covariance<-0
  if(length(sets)>1)for(i in 1:(length(sets)-1))for(j in (i+1):length(sets)) {
   joint<-prod(survival[as.character(union(sets[[i]],sets[[j]]))])
   covariance<-covariance+2*(joint-means[i]*means[j])
  }
  g<-groups |> dplyr::filter(model==z$model[1],issue==z$issue[1])
  fan<-fanout |> dplyr::filter(model==z$model[1],issue==z$issue[1])
  moments[[length(moments)+1L]]<-tibble::tibble(model=z$model[1],issue=z$issue[1],groups=length(sets),
   unique_fixtures=nrow(u),expected_thirds=sum(u$p3),actual_thirds=sum(u$third_hit),
   group_third_exposures=sum(g$thirds),groups_with_third=sum(g$thirds>0),
   expected_all_top2=sum(means),actual_all_top2=sum(g$actual_all_top2),
   independent_groups_variance=sum(means*(1-means)),shared_fixtures_variance=unname(sum(means*(1-means))+covariance),
   max_third_fanout=if(any(fan$third_hit))max(fan$groups[fan$third_hit]) else 0L)
 }
 list(groups=groups,fanout=fanout,issues=dplyr::bind_rows(moments))
}
