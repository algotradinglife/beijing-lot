# Post-settlement descriptive diagnosis; never returns a selection or fitted rule.
# Inputs: frozen one-fixture factors/features/audit, original group legs and one
# row per issue with original hits. IDs/joins/probabilities are validated. Missing
# feature strata remain MISSING. Outputs separate hypothetical all-fixture Top1/2,
# actual unique fixture/support and repeated holdings; never pool these denominators.
category_diagnostics <- function(factors,features,legs,audit,issues) {
 keys<-c('issue','slot','provider_id')
 probs<-c('p_W','p_D','p_L','q_W','q_D','q_L')
 fields<-c('competition','cup','expected_total','market_total','giving_venue_ppg','home_venue_n','away_venue_n')
 stopifnot(!anyDuplicated(factors[keys]),!anyDuplicated(factors[c("issue","slot")]),!anyDuplicated(features[keys]),!anyDuplicated(audit[keys]),
  !anyDuplicated(issues$issue),setequal(unique(factors$issue),issues$issue),
  all(is.finite(as.matrix(factors[probs]))),all(as.matrix(factors[probs])>=0),
  all(abs(rowSums(factors[c('p_W','p_D','p_L')])-1)<1e-8),
  all(abs(rowSums(factors[c('q_W','q_D','q_L')])-1)<1e-8))
 diag<-missed_issue_diagnostics(legs,audit)
 control<-dplyr::left_join(diag$issues,issues,by='issue',relationship='one-to-one')
 stopifnot(!anyNA(control$hits),all(control$winning_groups==control$hits))
 f<-dplyr::left_join(factors,dplyr::select(features,dplyr::all_of(c(keys,fields)),feature_present=dplyr::all_of('status')),
  by=keys,relationship='one-to-one') |>
  dplyr::left_join(dplyr::select(audit,dplyr::all_of(keys),actual_direction,audit_handicap=handicap,status),by=keys,relationship='one-to-one') |>
  dplyr::left_join(dplyr::select(issues,issue,hits),by='issue',relationship='many-to-one')
 stopifnot(!anyNA(f[c('feature_present','actual_direction','audit_handicap','hits')]),
  all(f$status=='READY'),all(f$handicap==f$audit_handicap),all(f$actual_direction %in% c('W','D','L')))
 pm<-as.matrix(f[c('p_W','p_D','p_L')]);qm<-as.matrix(f[c('q_W','q_D','q_L')])
 order_p<-t(apply(pm,1,order,decreasing=TRUE));codes<-c('3','1','0')
 top<-codes[order_p[,1]]
 pair<-paste0(ifelse(order_p[,3]!=1,'3',''),ifelse(order_p[,3]!=2,'1',''),ifelse(order_p[,3]!=3,'0',''))
 f<-f |> dplyr::mutate(
  period=ifelse(hits==0,'MISSED','HIT'),
  conflict=ifelse(order_p[,1]==max.col(qm,ties.method='first'),'AGREE',
   ifelse(rowSums(abs(pm-qm))/2>=.15,'STRONG_DIFF','MILD_DIFF')),
  depth=as.character(pmin(abs(handicap),2)),league=trimws(competition),
  family=dplyr::case_when(grepl('友谊',competition)~'FRIENDLY',grepl('附',competition)~'PLAYOFF',
   cup==1~'OTHER_CUP_FLAG',cup==0~'OTHER_CUP_ZERO',TRUE~'MISSING'),
  total_gap=as.character(cut(abs(expected_total-market_total),c(0,.5,1,Inf),right=FALSE)),
  venue_ppg_gap=ifelse(handicap==0,'NO_HANDICAP',as.character(cut(giving_venue_ppg,c(-Inf,0,.5,1,Inf),right=FALSE))),
  history_n=as.character(pmin(home_venue_n,away_venue_n)))
 observed<-diag$legs |> dplyr::left_join(dplyr::select(diag$groups,issue,group,misses),by=c('issue','group'),relationship='many-to-one') |>
  dplyr::transmute(issue,slot,provider_id,group,support,one_away_blocker=!hit & misses==1)
 held<-dplyr::left_join(observed,f,by=keys,relationship='many-to-one')
 stopifnot(!anyNA(held[c('p_W','p_D','p_L','status')]))
 unique<-held |> dplyr::group_by(issue,slot,provider_id,support) |>
  dplyr::slice_head(n=1) |> dplyr::ungroup() |> dplyr::mutate(group=0L,one_away_blocker=FALSE)
 all<-dplyr::bind_rows(dplyr::mutate(f,support=top),dplyr::mutate(f,support=pair)) |>
  dplyr::mutate(group=0L,one_away_blocker=FALSE)
 x<-dplyr::bind_rows(dplyr::mutate(all,view='ALL_AVAILABLE'),dplyr::mutate(unique,view='SELECTED_UNIQUE'),dplyr::mutate(held,view='HOLDINGS')) |>
  dplyr::mutate(role=ifelse(nchar(support)==1,'SINGLE','DOUBLE'),
   actual_code=unname(c(W='3',D='1',L='0')[actual_direction]),
   hit=mapply(grepl,actual_code,support,fixed=TRUE),
   predicted=p_W*grepl('3',support)+p_D*grepl('1',support)+p_L*grepl('0',support),
   market=q_W*grepl('3',support)+q_D*grepl('1',support)+q_L*grepl('0',support),
   probability_band=as.character(cut(predicted,c(0,.5,.6,.7,.8,.9,1),include.lowest=TRUE)))
 sliced<-dplyr::bind_rows(dplyr::mutate(x,slice='ALL'),dplyr::mutate(x,slice=period))
 dims<-c('conflict','depth','league','family','total_gap','venue_ppg_gap','history_n','probability_band')
 long<-sliced |> dplyr::select(issue,slot,provider_id,view,slice,role,hit,predicted,market,one_away_blocker,dplyr::all_of(dims)) |>
  tidyr::pivot_longer(dplyr::all_of(dims),names_to='dimension',values_to='stratum') |>
  dplyr::mutate(stratum=dplyr::coalesce(stratum,'MISSING'))
 summary<-long |> dplyr::group_by(view,slice,role,dimension,stratum) |> dplyr::summarise(
  n=dplyr::n(),issues=dplyr::n_distinct(issue),hits=sum(hit),misses=sum(!hit),
  actual_percent=100*mean(hit),predicted_percent=100*mean(predicted),market_percent=100*mean(market),
  error_pp=actual_percent-predicted_percent,one_away_blockers=sum(one_away_blocker),.groups='drop')
 list(summary=summary,observations=x,original_groups=diag$groups,original_issues=diag$issues)
}
