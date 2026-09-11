# Descriptive all-fixture calibration, never a learned probability adjustment.
# events: unique issue/slot/provider_id/model/event, probability [0,1].
# audit: unique READY identities, integer score and handicap. Returns tidy
# joined observations and aggregate probabilities/frequencies/Brier scores.
# No independence-based confidence claims, fitting, selection or I/O.
event_calibration <- function(events,audit) {
 keys <- c('issue','slot','provider_id')
 allowed <- c('ordinary_draw','handicap_draw','home_ge2','away_ge2','home_ge3','away_ge3','total_ge5','giving_cover')
 stopifnot(nrow(events)>0,!anyNA(events),!anyDuplicated(events[c(keys,'model','event')]),
  all(events$event %in% allowed),all(is.finite(events$probability)),
  all(events$probability>=0 & events$probability<=1),!anyDuplicated(audit[keys]))
 x <- dplyr::left_join(events,dplyr::select(audit,dplyr::all_of(keys),status,actual_home,actual_away,handicap),
                      by=keys,relationship='many-to-one')
 stopifnot(!anyNA(x),all(is.finite(x$actual_home)),all(is.finite(x$actual_away)),all(is.finite(x$handicap)),all(x$status=='READY'),all(x$actual_home>=0),all(x$actual_away>=0),
  all(x$actual_home==floor(x$actual_home)),all(x$actual_away==floor(x$actual_away)),
  all(x$handicap==floor(x$handicap)),!any(x$event=='giving_cover' & x$handicap==0))
 x <- x |> dplyr::mutate(margin=actual_home-actual_away,observed=dplyr::case_when(
  event=='ordinary_draw'~margin==0,event=='handicap_draw'~margin+handicap==0,
  event=='home_ge2'~margin>=2,event=='away_ge2'~margin<= -2,
  event=='home_ge3'~margin>=3,event=='away_ge3'~margin<= -3,
  event=='total_ge5'~actual_home+actual_away>=5,
  event=='giving_cover'~dplyr::if_else(handicap<0,margin+handicap>0,margin+handicap<0)))
 s <- x |> dplyr::group_by(model,event) |> dplyr::summarise(n=dplyr::n(),actual=sum(observed),
  expected=sum(probability),predicted_percent=100*mean(probability),actual_percent=100*mean(observed),
  error_pp=actual_percent-predicted_percent,brier=mean((probability-observed)^2),.groups='drop')
 list(observations=x,summary=s)
}
