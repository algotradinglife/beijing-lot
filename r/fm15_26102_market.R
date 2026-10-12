# Independent prior-cutoff pricing diagnostics; never replace native lambda.
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
out <- file.path(root,'results/fm15-26102-20261012')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm15-version-20261012/library'))
m <- fromJSON(file.path(out,'native-manifest.json'));np<-file.path(out,m$native_file)
stopifnot(digest::digest(file=np,algo='sha256')==m$sha256)
native <- readRDS(np);stopifnot(beidan:::.score_margin_hash(native)==m$object_hash)
packets <- ledger <- selected <- list();paths <- c(np,file.path(root,'r/fm15_26102_market.R'),file.path(out,'market-fixtures.json'))
for(id in names(native$entries)) {
  e <- native$entries[[id]];f<-e$fixture
  path <- file.path(out,'market-captures',paste0(gsub(':','_',id),'.json'))
  quotes <- list(euro=tibble(fixture_id=character(),company_id=character(),quote_at=as.POSIXct(character(),tz='UTC'),odds_home=double(),odds_draw=double(),odds_away=double()),asian=tibble(fixture_id=character(),company_id=character(),quote_at=as.POSIXct(character(),tz='UTC'),handicap=double(),home_decimal=double(),away_decimal=double()),totals=tibble(fixture_id=character(),company_id=character(),quote_at=as.POSIXct(character(),tz='UTC'),line=double(),over_decimal=double(),under_decimal=double()));errors<-character()
  if(!file.exists(path)) errors <- 'MISSING_CAPTURE' else {
    paths<-c(paths,path);rec<-fromJSON(path,simplifyVector=FALSE)
    stopifnot(rec$fixture_list_sha256==digest::digest(file=file.path(out,'market-fixtures.json'),algo='sha256'),rec$fixture$home_nowscore==f$home,rec$fixture$away_nowscore==f$away,rec$fixture$fixture_id==id,rec$fixture$provider_id_nowscore==f$provider_id,lubridate::ymd_hms(rec$fixture$kickoff_at,tz='UTC')-lubridate::hours(24)==f$cutoff_utc)
    for(cap in rec$captures) if(!is.null(cap$sha256)) {
      raw <- if(startsWith(cap$raw_path,'/')) cap$raw_path else file.path(root,cap$raw_path)
      stopifnot(digest::digest(file=raw,algo='sha256')==cap$sha256);paths<-c(paths,raw)
    }
    for(kind in names(quotes)) {
      q<-bind_rows(rec[[kind]])
      if(!nrow(q)) {errors<-c(errors,paste0('EMPTY_',kind));next}
      stopifnot(all(q$fixture_id==id))
      q<-q |> mutate(company_id=as.character(company_id),quote_at=lubridate::ymd_hms(quote_at,tz='UTC'))
      stopifnot(!anyNA(q$quote_at))
      q<-q |> filter(quote_at<f$cutoff_utc,as.numeric(difftime(f$cutoff_utc,quote_at,units='hours'))<=48)
      if(kind=='euro')q<-q |> filter(company_id %in% c('281','115','82','432'))
      canonical<-c('fixture_id','company_id','quote_at',if(kind=='euro')c('odds_home','odds_draw','odds_away')else if(kind=='asian')c('handicap','home_decimal','away_decimal')else c('line','over_decimal','under_decimal'))
      q<-q |> select(all_of(canonical)) |> distinct()
      numerical<-setdiff(canonical,c('fixture_id','company_id','quote_at'))
      stopifnot(all(vapply(q[numerical],is.numeric,logical(1))),all(is.finite(as.matrix(q[numerical]))))
      prices<-if(kind=='euro')c('odds_home','odds_draw','odds_away')else if(kind=='asian')c('home_decimal','away_decimal')else c('over_decimal','under_decimal')
      stopifnot(all(as.matrix(q[prices])>1))
      if(kind=='asian')stopifnot(all(q$handicap*4==round(q$handicap*4)))
      stopifnot(!anyDuplicated(q[c('company_id','quote_at')]))
      quotes[[kind]]<-q |> arrange(company_id,desc(quote_at)) |> group_by(company_id) |> slice_head(n=1L) |> ungroup()
      if(!nrow(q))errors<-c(errors,paste0('NO_PRIOR_SUPPORTED_',kind))
    }
  }
  euro<-quotes$euro;pricing<-NULL
  if(nrow(euro)) {
    stopifnot(all(as.matrix(select(euro,odds_home,odds_draw,odds_away))>1))
    prices<-euro |> transmute(W=1/odds_home,D=1/odds_draw,L=1/odds_away) |> mutate(total=W+D+L,across(c(W,D,L),~.x/total))
    pricing<-prices |> summarise(across(c(W,D,L),mean)) |> pivot_longer(everything(),names_to='outcome',values_to='probability')
  }
  total<-NULL
  if(nrow(quotes$totals))total<-tryCatch(beidan:::total_market_constraint(quotes$totals |> transmute(company=company_id,line,over_hk=over_decimal-1,under_hk=under_decimal-1),c(.1,12)),error=function(e)list(error=conditionMessage(e)))
  margins<-e$grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |> summarise(probability=sum(probability),.groups='drop') |> arrange(desc(probability),margin)
  missing<-list(lineups='Unavailable before cutoff',injuries='Unavailable before cutoff',opponent_strength='Not implemented in native venue estimator',international_rank='Unavailable before cutoff',market=paste(errors,collapse=';'))
  packets[[id]]<-list(fixture_id=id,cutoff_utc=format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),base_hash=beidan:::.score_margin_hash(e$grid),home=f$home,away=f$away,competition=e$roster$league,native_parameters=e$native$parameters,native_rates=e$native$rates,top_margins=head(margins,7L),independent_market=pricing,total_constraint=total,asian_quotes=quotes$asian,total_quotes=quotes$totals,euro_quotes=quotes$euro,article_facts=list(),missing=missing)
  selected[[id]]<-quotes
  ledger[[id]]<-tibble(fixture_id=id,market_state=if(length(errors))'INCOMPLETE'else'COMPLETE',reason=paste(errors,collapse=';'))
}
paths<-unique(paths);inputs<-tibble(path=substring(paths,nchar(root)+2L),sha256=map_chr(paths,~digest::digest(file=.x,algo='sha256')))
stage<-list(packets=packets,ledger=bind_rows(ledger),selected=selected,inputs=inputs,loaded_OU_implementation=beidan:::.score_margin_hash(list(bodies=lapply(list(beidan:::total_market_constraint,beidan:::asian_total_probability),function(f)paste(deparse(body(f)),collapse='\n')),bounds=c(.1,12),R=as.character(getRversion()),stats=as.character(packageVersion('stats')))),quote_policy=list(max_quote_age_hours=48,euro_companies=c('281','115','82','432'),time_evidence='HISTORICAL_QUOTE_PROXY_ONLY'))
id<-beidan:::.score_margin_hash(stage);path<-file.path(out,paste0('market-',substr(id,1,12),'.rds'))
if(file.exists(path))stopifnot(identical(readRDS(path),stage))else saveRDS(stage,path)
write_json(list(stage_file=basename(path),object_hash=id,sha256=digest::digest(file=path,algo='sha256')),file.path(out,'market-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(stage$ledger,file.path(out,'market-ledger.csv'))
write_json(list(model='FM-1.5.0',fixtures=unname(packets)),file.path(out,'review-inputs.json'),auto_unbox=TRUE,pretty=TRUE,digits=17,POSIXt='ISO8601',na='null')
print(count(stage$ledger,market_state))
