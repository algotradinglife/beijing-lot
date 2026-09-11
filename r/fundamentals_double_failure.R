# Descriptive settlement diagnosis; no learning or prediction. rows: unique
# issue/policy with groups,hits,status; legs: issue/policy/group/slot, role A/D/C,
# logical hit. Each group must have two A singles and four D plus one C double.
# Return group errors, missed-active issue diagnosis, policy summaries and
# leg-occurrence hit rates. No-bet issues are separately counted, not failures.
# Oracle repairs describe where errors occurred, never achievable forecasts.
double_failure_summary <- function(rows,legs) {
 stopifnot(all(c('issue','policy','groups','hits','status') %in% names(rows)),
  all(c('issue','policy','group','slot','role','hit') %in% names(legs)),
  !anyNA(rows[c('issue','policy','groups','hits','status')]),!anyNA(legs),
  !anyDuplicated(rows[c('issue','policy')]),!anyDuplicated(legs[c('issue','policy','group','slot')]),
  is.logical(legs$hit),all(legs$role %in% c('A','D','C')),
  all(rows$status %in% c('COMPLETE','NO_BET')),
  all((rows$status=='NO_BET')==(rows$groups==0)),all(rows$hits>=0),all(rows$hits<=rows$groups))
 g<-legs |> dplyr::group_by(issue,policy,group) |>
  dplyr::summarise(n=dplyr::n(),a=sum(role=='A'),d=sum(role=='D'),c=sum(role=='C'),
   single_errors=sum(!hit & role=='A'),double_errors=sum(!hit & role!='A'),
   stable_errors=sum(!hit & role=='D'),disagreement_errors=sum(!hit & role=='C'),.groups='drop')
 stopifnot(all(g$n==7),all(g$a==2),all(g$d==4),all(g$c==1))
 checks<-g |> dplyr::group_by(issue,policy) |>
  dplyr::summarise(count=dplyr::n(),wins=sum(single_errors+double_errors==0),.groups='drop')
 stopifnot(nrow(dplyr::anti_join(checks,rows,by=c('issue','policy')))==0)
 checked<-dplyr::left_join(rows,checks,by=c('issue','policy'),relationship='one-to-one') |>
  dplyr::mutate(count=dplyr::coalesce(count,0L),wins=dplyr::coalesce(wins,0L))
 stopifnot(all(checked$count==checked$groups),all(checked$wins==checked$hits))
 missed<-rows |> dplyr::filter(groups>0,hits==0) |> dplyr::select(issue,policy)
 mg<-dplyr::inner_join(g,missed,by=c('issue','policy'),relationship='many-to-one')
 per_issue<-mg |> dplyr::group_by(issue,policy) |>
  dplyr::summarise(groups=dplyr::n(),single_only_groups=sum(single_errors>0 & double_errors==0),
   double_only_groups=sum(single_errors==0 & double_errors>0),both_error_groups=sum(single_errors>0 & double_errors>0),
   repair_singles=any(double_errors==0),repair_doubles=any(single_errors==0),
   one_single_away=any(single_errors==1 & double_errors==0),
   one_double_away=any(single_errors==0 & double_errors==1),.groups='drop') |>
  dplyr::mutate(category=dplyr::case_when(repair_singles & repair_doubles~'EITHER',
   repair_singles~'SINGLES_ONLY',repair_doubles~'DOUBLES_ONLY',TRUE~'BOTH_REQUIRED'))
 summary<-rows |> dplyr::group_by(policy) |>
  dplyr::summarise(issues=dplyr::n(),no_bet=sum(groups==0),hit_issues=sum(hits>0),missed_active=sum(groups>0 & hits==0),.groups='drop')
 totals<-per_issue |> dplyr::group_by(policy) |>
  dplyr::summarise(single_only_groups=sum(single_only_groups),double_only_groups=sum(double_only_groups),
   both_error_groups=sum(both_error_groups),repair_singles=sum(repair_singles),repair_doubles=sum(repair_doubles),
   singles_only_issues=sum(category=='SINGLES_ONLY'),doubles_only_issues=sum(category=='DOUBLES_ONLY'),
   either_issues=sum(category=='EITHER'),both_required_issues=sum(category=='BOTH_REQUIRED'),
   one_single_away=sum(one_single_away),one_double_away=sum(one_double_away),.groups='drop')
 summary<-dplyr::left_join(summary,totals,by='policy',relationship='one-to-one') |>
  dplyr::mutate(dplyr::across(-policy,~tidyr::replace_na(.x,0)))
 stopifnot(all(summary$missed_active==summary$singles_only_issues+summary$doubles_only_issues+summary$either_issues+summary$both_required_issues))
 rates<-dplyr::inner_join(legs,missed,by=c('issue','policy'),relationship='many-to-one') |>
  dplyr::group_by(policy,role) |> dplyr::summarise(occurrences=dplyr::n(),hits=sum(hit),hit_percent=100*mean(hit),.groups='drop')
 list(summary=summary,per_issue=per_issue,groups=g,missed_leg_rates=rates)
}
