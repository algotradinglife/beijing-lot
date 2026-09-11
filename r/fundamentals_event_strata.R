# Post-settlement descriptive stratification. No fitted bins or routing.
# observations is event_calibration() output; features is one unique fixture
# row, probabilities/features from the frozen prematch package. Missing feature
# values are explicit MISSING strata. Each dimension is analysed separately;
# repeated memberships across dimensions are never independent observations.
# Return tidy summary: actual-predicted error in percentage points, Brier,
# sample size and distinct issues. Fixed bins are labels, not selection rules.
event_strata <- function(observations,features) {
 keys<-c('issue','slot','provider_id')
 fields<-c('competition','cup','neutral','history_mode','market_total','giving_overall_ppg','giving_venue_ppg',
 'home_overall_goals_for_pg','away_overall_goals_for_pg','home_venue_goals_against_pg',
 'away_venue_goals_against_pg','giving_big_win_rate')
 stopifnot(all(c(keys,fields) %in% names(features)),!anyDuplicated(features[keys]),
  !anyDuplicated(observations[c(keys,'model','event')]),nrow(observations)>0)
 f<-dplyr::select(features,dplyr::all_of(c(keys,fields))) |> dplyr::mutate(feature_present=TRUE)
 x<-dplyr::left_join(observations,f,by=keys,relationship='many-to-one')
 stopifnot(all(!is.na(x$feature_present)),all(is.finite(x$probability)),!anyNA(x$observed))
 x<-x |> dplyr::mutate(
  league=competition,competition_type=dplyr::if_else(cup==1,'CUP','OTHER'),
  venue_mode=dplyr::if_else(neutral==1,'NEUTRAL',history_mode),
  handicap_depth=as.character(pmin(abs(handicap),2)),
  probability_band=as.character(cut(probability,c(0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1),include.lowest=TRUE)),
  market_total_band=as.character(cut(market_total,c(-Inf,2.5,3.5,Inf),right=FALSE)),
  giving_overall_ppg_gap=as.character(cut(giving_overall_ppg,c(-Inf,0,.5,1,Inf),right=FALSE)),
  giving_venue_ppg_gap=as.character(cut(giving_venue_ppg,c(-Inf,0,.5,1,Inf),right=FALSE)),
  home_scoring=as.character(cut(home_overall_goals_for_pg,c(-Inf,1,2,Inf),right=FALSE)),
  away_scoring=as.character(cut(away_overall_goals_for_pg,c(-Inf,1,2,Inf),right=FALSE)),
  home_venue_conceding=as.character(cut(home_venue_goals_against_pg,c(-Inf,1,2,Inf),right=FALSE)),
  away_venue_conceding=as.character(cut(away_venue_goals_against_pg,c(-Inf,1,2,Inf),right=FALSE)),
  giving_historical_big_win=as.character(cut(giving_big_win_rate,c(-Inf,.1,.3,Inf),right=FALSE)))
 dims<-c('league','competition_type','venue_mode','handicap_depth','probability_band','market_total_band',
 'giving_overall_ppg_gap','giving_venue_ppg_gap','home_scoring','away_scoring','home_venue_conceding',
 'away_venue_conceding','giving_historical_big_win')
 x |> dplyr::select(dplyr::all_of(c(keys,'model','event','probability','observed',dims))) |>
  tidyr::pivot_longer(dplyr::all_of(dims),names_to='dimension',values_to='stratum') |>
  dplyr::mutate(stratum=dplyr::coalesce(stratum,'MISSING')) |>
  dplyr::group_by(model,event,dimension,stratum) |>
  dplyr::summarise(n=dplyr::n(),issues=dplyr::n_distinct(issue),actual=sum(observed),
   predicted_percent=100*mean(probability),actual_percent=100*mean(observed),
   error_pp=actual_percent-predicted_percent,brier=mean((probability-observed)^2),.groups='drop')
}
