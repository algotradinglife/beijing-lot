# Descriptive attribution of frozen N7 holdings, not learning or selection.
# legs: one issue/group/slot/provider row with support in 3/1/0; audit: unique
# READY issue/slot/provider rows with handicap and actual_direction W/D/L.
# Returns leg, group, fixture and issue tibbles. Counts are holdings unless
# explicitly grouped by fixture. Missing identities/outcomes fail. No I/O.
missed_issue_diagnostics <- function(legs,audit) {
 keys <- c('issue','slot','provider_id')
 stopifnot(nrow(legs)>0,all(c(keys,'group','support','handicap') %in% names(legs)),
  all(c(keys,'status','actual_direction','handicap') %in% names(audit)),
  !anyNA(legs[c(keys,'group','support','handicap')]),!anyNA(audit[keys]),
  is.character(legs$issue),is.character(legs$provider_id),
  is.character(audit$issue),is.character(audit$provider_id),
  !anyDuplicated(legs[c('issue','group','slot')]),!anyDuplicated(audit[keys]),
  all(grepl('^(3|1|0|31|30|10|13|03|01)$',legs$support)))
 x <- dplyr::left_join(legs,dplyr::select(audit,dplyr::all_of(keys),status,actual_direction,
                   audit_handicap=handicap),by=keys,relationship='many-to-one')
 stopifnot(!anyNA(x[c('status','actual_direction','audit_handicap')]),all(x$status=='READY'),
  all(x$actual_direction %in% c('W','D','L')),all(x$handicap==x$audit_handicap))
 x <- x |> dplyr::mutate(actual_code=unname(c(W='3',D='1',L='0')[actual_direction]),
   single=nchar(support)==1L,hit=mapply(grepl,actual_code,support,fixed=TRUE))
 groups <- x |> dplyr::group_by(issue,group) |> dplyr::summarise(n=dplyr::n(),
   misses=sum(!hit),single_misses=sum(single & !hit),double_misses=sum(!single & !hit),.groups='drop')
 stopifnot(all(groups$n==7))
 issues <- groups |> dplyr::group_by(issue) |> dplyr::summarise(groups=dplyr::n(),
   winning_groups=sum(misses==0),nearest_misses=min(misses),one_away_groups=sum(misses==1),
   single_error_groups=sum(single_misses>0),double_error_groups=sum(double_misses>0),.groups='drop') |>
   dplyr::mutate(whole_issue_missed=winning_groups==0)
 fixtures <- x |> dplyr::group_by(issue,slot,provider_id) |> dplyr::summarise(
   groups_held=dplyr::n(),groups_missed=sum(!hit),single_misses=sum(single & !hit),
   double_misses=sum(!single & !hit),.groups='drop')
 list(legs=tibble::as_tibble(x),groups=groups,fixtures=fixtures,issues=issues)
}
