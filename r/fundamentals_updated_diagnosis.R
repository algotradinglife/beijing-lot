# Descriptive diagnosis of settled, frozen holdings. No prediction or selection.
# Inputs: fixtures (unique issue/slot/provider_id, p/q WDL, competition, handicap),
# legs (unique issue/policy/group/slot, role A/D/C, support 3/1/0, hit 0/1),
# issues (unique issue/policy, settled groups/hits/stake/gross/net/status).
# Returns tidy role, stratum, group-failure and payout tables. Rates are percent;
# money is CNY. Missing SP is allowed only for fixtures outside winning groups.
# Stops on missing identities, duplicate keys, invalid probabilities or accounting.
updated_scope_diagnosis <- function(fixtures, legs, issues) {
  keys <- c('issue','slot','provider_id')
  stopifnot(!anyDuplicated(fixtures[keys]), !anyDuplicated(legs[c('issue','policy','group','slot')]),
    !anyDuplicated(issues[c('issue','policy')]), !anyNA(legs),
    all(legs$role %in% c('A','D','C')), all(legs$hit %in% 0:1),
    all(grepl('^[310]{1,2}$',legs$support)), all(fixtures$actual %in% c('W','D','L')),
    all(issues$status %in% c('COMPLETE','NO_BET')))
  for (prefix in c('p','q')) {
    m <- as.matrix(fixtures[paste0(prefix,c('_W','_D','_L'))])
    stopifnot(all(is.finite(m)),all(m>=0),all(abs(rowSums(m)-1)<1e-8))
  }
  pm<-as.matrix(fixtures[c('p_W','p_D','p_L')]);qm<-as.matrix(fixtures[c('q_W','q_D','q_L')])
  pt<-max.col(pm,ties.method='first');qt<-max.col(qm,ties.method='first')
  # First-index order ties match the frozen Python W/D/L ordering.
  pl<-apply(pm,1,function(z) order(-z)[3]);ql<-apply(qm,1,function(z) order(-z)[3])
  all_fixtures<-fixtures |> dplyr::mutate(
    baseline_top1_hit=c('W','D','L')[pt]==actual,market_top1_hit=c('W','D','L')[qt]==actual,
    baseline_top2_hit=c('W','D','L')[pl]!=actual,market_top2_hit=c('W','D','L')[ql]!=actual,
    excluded_zero=handicap==0 & pl!=ql,
    anchor=pt==qt & qm[cbind(seq_len(nrow(qm)),qt)]>=.5 & !excluded_zero)
  available<-all_fixtures |> dplyr::group_by(cohort) |> dplyr::summarise(n=dplyr::n(),
    dplyr::across(dplyr::ends_with('_hit'),~100*mean(.x)),.groups='drop')
  direction_rows<-list()
  for (model in c('baseline','market')) {
    top<-if(model=='baseline') pt else qt
    last<-if(model=='baseline') pl else ql
    for (j in seq_len(3)) {
      direction_rows[[length(direction_rows)+1L]]<-tibble::tibble(
        cohort=fixtures$cohort,model=model,direction=c('W','D','L')[j],handicap=as.character(fixtures$handicap),
        selected=top==j,actual=fixtures$actual==c('W','D','L')[j],
        covered=last!=j)
    }
  }
  direction_data<-dplyr::bind_rows(direction_rows)
  directions<-dplyr::bind_rows(direction_data,dplyr::mutate(direction_data,handicap='ALL')) |>
    dplyr::group_by(cohort,model,handicap,direction) |>
    dplyr::summarise(hits=sum(selected & actual),top2_hits=sum(covered & actual),
      selected_count=sum(selected),actual_count=sum(actual),.groups='drop') |>
    dplyr::mutate(precision_percent=100*hits/dplyr::na_if(selected_count,0L),
      recall_percent=100*hits/dplyr::na_if(actual_count,0L),top2_recall_percent=100*top2_hits/dplyr::na_if(actual_count,0L))
  pairs<-dplyr::bind_rows(
    tibble::tibble(cohort=fixtures$cohort,model='baseline',handicap=as.character(fixtures$handicap),excluded=c('W','D','L')[pl],hit=all_fixtures$baseline_top2_hit),
    tibble::tibble(cohort=fixtures$cohort,model='market',handicap=as.character(fixtures$handicap),excluded=c('W','D','L')[ql],hit=all_fixtures$market_top2_hit))
  pairs<-dplyr::bind_rows(pairs,dplyr::mutate(pairs,handicap='ALL')) |>
    dplyr::group_by(cohort,model,handicap,excluded) |> dplyr::summarise(n=dplyr::n(),hits=sum(hit),hit_percent=100*mean(hit),.groups='drop')
  handicap_accuracy<-directions |> dplyr::group_by(cohort,model,handicap) |>
    dplyr::summarise(n=sum(selected_count),top1_hits=sum(hits),.groups='drop') |>
    dplyr::left_join(pairs |> dplyr::group_by(cohort,model,handicap) |>
      dplyr::summarise(pair_n=sum(n),top2_hits=sum(hits),.groups='drop'),
      by=c('cohort','model','handicap'),relationship='one-to-one') |>
    dplyr::mutate(top1_percent=100*top1_hits/n,top2_percent=100*top2_hits/n)
  stopifnot(all(handicap_accuracy$n==handicap_accuracy$pair_n))
  pools<-all_fixtures |> dplyr::group_by(cohort,issue) |> dplyr::summarise(
    available=dplyr::n(),excluded_zero=sum(excluded_zero),anchors=sum(anchor),.groups='drop')
  x <- dplyr::left_join(legs, dplyr::select(fixtures,-cohort),by=keys,relationship='many-to-one')
  stopifnot(!anyNA(x$actual), all(x$hit == mapply(grepl,unname(c(W='3',D='1',L='0')[x$actual]),x$support,fixed=TRUE)))
  x <- x |> dplyr::mutate(
    predicted=p_W*grepl('3',support)+p_D*grepl('1',support)+p_L*grepl('0',support),
    market=q_W*grepl('3',support)+q_D*grepl('1',support)+q_L*grepl('0',support),
    depth=as.character(handicap), month=substr(issue,1,4),
    disagreement=as.character(cut((abs(p_W-q_W)+abs(p_D-q_D)+abs(p_L-q_L))/2,c(0,.1,.2,1),include.lowest=TRUE)),
    market_band=as.character(cut(market,c(0,.5,.6,.7,.8,.9,1),include.lowest=TRUE)))
  groups <- x |> dplyr::group_by(cohort,issue,policy,group) |> dplyr::summarise(
    n=dplyr::n(), singles=sum(role=='A'), single_errors=sum(role=='A' & hit==0),
    double_errors=sum(role!='A' & hit==0), misses=sum(hit==0),
    p_product=prod(predicted),q_product=prod(market),
    gross=if(all(hit==1)) 2*.65*prod(spf_sp) else 0,.groups='drop')
  stopifnot(all(groups$singles==2),all(groups$n %in% 5:7),!anyNA(groups$gross))
  check <- groups |> dplyr::group_by(issue,policy) |> dplyr::summarise(
    check_groups=dplyr::n(),check_hits=sum(misses==0),check_gross=sum(gross),
    check_stake=sum(2*2^(n-2)),.groups='drop')
  check <- dplyr::left_join(issues,check,by=c('issue','policy'),relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(dplyr::starts_with('check_'),~tidyr::replace_na(.x,0)))
  stopifnot(all(check$groups==check$check_groups),all(check$hits==check$check_hits),
    all(abs(check$gross-check$check_gross)<1e-6),all(check$stake==check$check_stake),
    all(abs(check$net-(check$gross-check$stake))<1e-6))
  unique <- x |> dplyr::distinct(cohort,issue,policy,slot,provider_id,role,support,.keep_all=TRUE)
  views <- dplyr::bind_rows(dplyr::mutate(x,view='holdings'),dplyr::mutate(unique,view='unique_support'))
  rates <- views |> dplyr::group_by(cohort,policy,view,role) |> dplyr::summarise(
    n=dplyr::n(),hit_percent=100*mean(hit),p_percent=100*mean(predicted),q_percent=100*mean(market),.groups='drop')
  strata <- views |> tidyr::pivot_longer(c(competition,depth,month,disagreement,market_band),names_to='dimension',values_to='stratum') |>
    dplyr::group_by(cohort,policy,view,role,dimension,stratum) |> dplyr::summarise(
      n=dplyr::n(),hits=sum(hit),hit_percent=100*mean(hit),q_percent=100*mean(market),.groups='drop')
  failures <- groups |> dplyr::mutate(cause=dplyr::case_when(misses==0~'HIT',single_errors==0~'DOUBLES_ONLY',
    double_errors==0~'SINGLES_ONLY',TRUE~'BOTH')) |>
    dplyr::group_by(cohort,policy,cause) |> dplyr::summarise(groups=dplyr::n(),one_away=sum(misses==1),.groups='drop')
  payout <- groups |> dplyr::group_by(cohort,policy) |> dplyr::summarise(groups=dplyr::n(),wins=sum(misses==0),
    group_hit_percent=100*mean(misses==0),p_percent=100*mean(p_product),q_percent=100*mean(q_product),
    mean_winning_gross=mean(gross[gross>0]),.groups='drop') |>
    dplyr::left_join(issues |> dplyr::group_by(cohort,policy) |> dplyr::summarise(
      active=sum(stake>0),hit_issues=sum(hits>0),stake=sum(stake),gross=sum(gross),net=sum(net),
      ROI_percent=100*sum(net)/sum(stake),.groups='drop'),by=c('cohort','policy'),relationship='one-to-one')
  blockers <- x |> dplyr::filter(hit==0) |> dplyr::group_by(cohort,policy,issue,slot,home,away,role,support,competition) |>
    dplyr::summarise(failed_holdings=dplyr::n(),.groups='drop') |> dplyr::arrange(dplyr::desc(failed_holdings))
  list(rates=rates,strata=strata,failures=failures,payout=payout,blockers=blockers,groups=groups,available=available,pools=pools,directions=directions,pairs=pairs,handicap_accuracy=handicap_accuracy)
}
