#' Inspect independently replayed market histories at explicit fixture cutoffs.
#'
#' Diagnostic only: no fitting, source routing, price blending or probability
#' production. Quote admission uses shared temporal_learning historical proxies;
#' collected-after-cutoff bytes never become observed historical availability.
#' @param scope Tibble unique fixture_id, issue_id, provider_id_nowscore,
#'   home_nowscore, away_nowscore, home_id, away_id, kickoff_at text with timezone, cutoff_utc UTC
#'   POSIXct; original metadata columns may also be present.
#' @param packets Named list of replay_fixture_capture outputs, one per scope row.
#' @param policy Explicit list max_quote_age_hours (>0) and euro_companies
#'   (unique nonempty source-company strings). No policy optimization.
#' @param repository_root Existing project root with .venv and shared backend.
#' @return List of validated tibbles history, latest, coverage and cutoff receipts.
#'   history rows are original source quote occurrences, keyed fixture/market/seq;
#'   latest rows are latest prior company quotes (stable original-order tie), with
#'   age in hours and supported/fresh flags. Coverage has one fixture/market row.
#'   Numeric prices include stake; AH is signed home-added goal handicap.
#'   Identity-conflicted quotes remain visible but are not marked qualified.
#' @keywords internal
.InspectRecapturedMarkets <- function(scope, packets, policy, repository_root) {
  checkmate::assert_tibble(scope,min.rows=1L)
  required <- c('fixture_id','issue_id','provider_id_nowscore','home_nowscore','away_nowscore','kickoff_at','home_id','away_id','cutoff_utc')
  if(!all(required %in% names(scope)))stop('Explicit fixture cutoff scope required')
  for(k in setdiff(required,'cutoff_utc'))checkmate::assert_character(scope[[k]],any.missing=FALSE,min.chars=1L)
  if(!inherits(scope$cutoff_utc,'POSIXct')||anyNA(scope$cutoff_utc)||any(!is.finite(as.numeric(scope$cutoff_utc)))||anyDuplicated(scope$fixture_id))stop('Unique typed cutoff scope required')
  if(!is.list(packets)||!setequal(names(packets),scope$fixture_id)||anyDuplicated(names(packets)))stop('Exact packet scope required')
  checkmate::assert_names(names(policy),identical.to=c('max_quote_age_hours','euro_companies'))
  checkmate::assert_number(policy$max_quote_age_hours,lower=0,finite=TRUE)
  if(policy$max_quote_age_hours==0)stop('Positive quote age required')
  checkmate::assert_character(policy$euro_companies,min.len=1L,any.missing=FALSE,min.chars=1L,unique=TRUE)
  repository_root<-normalizePath(repository_root,mustWork=TRUE)
  reticulate::use_python(file.path(repository_root,'.venv/bin/python'),required=TRUE)
  sys<-reticulate::import('sys',convert=FALSE)
  if(normalizePath(reticulate::py_to_r(sys$prefix))!=normalizePath(file.path(repository_root,'.venv')))stop('Explicit project Python required')
  sys$path$insert(0L,file.path(repository_root,'packages/beidan/inst/python'))
  shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
  backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
  schema<-tibble::tibble(fixture_id=character(),market=character(),sequence=integer(),company_id=character(),quote_at=as.POSIXct(character(),tz='UTC'),odds_home=double(),odds_draw=double(),odds_away=double(),handicap=double(),home_decimal=double(),away_decimal=double(),line=double(),over_decimal=double(),under_decimal=double(),source_url=character(),evidence_id=character(),prior=logical())
  histories<-latest<-coverage<-receipts<-list()
  for(i in seq_len(nrow(scope))) {
    f<-scope[i,];id<-f$fixture_id;p<-packets[[id]]
    for(k in c('fixture_id','provider_id_nowscore','home_nowscore','away_nowscore','kickoff_at'))if(!identical(p$fixture[[k]],f[[k]]))stop('Packet fixture binding differs')
    if(!identical(p$expected_team_ids,list(home_id=f$home_id,away_id=f$away_id)))stop('Native team scope binding differs')
    if(!p$identity_status %in% c('EXACT','EXACT_IDS','UNVERIFIED','NAME_OR_CLOCK_CONFLICT','NATIVE_ID_CONFLICT','TEAM_ID_CONFLICT'))stop('Unknown identity status')
    cutoff<-list(issue_id=f$issue_id,cutoff_utc=f$cutoff_utc)
    ct<-shared$Cutoff$decision_epoch(f$issue_id,format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
    rows<-list()
    for(kind in c('euro','asian','totals')) {
      qq<-dplyr::bind_rows(p[[kind]])
      if(!nrow(qq))next
      if(any(qq$fixture_id!=id))stop('Quote fixture differs')
      price<-switch(kind,euro=c('odds_home','odds_draw','odds_away'),asian=c('home_decimal','away_decimal'),totals=c('over_decimal','under_decimal'))
      for(k in price)checkmate::assert_numeric(qq[[k]],finite=TRUE,any.missing=FALSE,lower=1)
      if(any(as.matrix(qq[price])<=1))stop('Decimal prices must exceed one')
      for(k in intersect(c('handicap','line'),names(qq))) {
        checkmate::assert_numeric(qq[[k]],finite=TRUE,any.missing=FALSE)
        if(any(qq[[k]]*4!=round(qq[[k]]*4)))stop('Quarter-goal line required')
      }
      checkmate::assert_character(qq$company_id,any.missing=FALSE,min.chars=1L)
      checkmate::assert_character(qq$quote_at,any.missing=FALSE,min.chars=1L)
      if(any(!grepl('(Z|[+-][0-9]{2}:[0-9]{2})$',qq$quote_at)))stop('Explicit quote timezone required')
      qq$quote_at<-as.POSIXct(lubridate::ymd_hms(qq$quote_at,tz='UTC',quiet=TRUE),tz='UTC')
      if(anyNA(qq$quote_at))stop('Malformed quote clock')
      qq<-qq |> dplyr::mutate(market=kind,sequence=seq_len(nrow(qq)),evidence_id=paste0(kind,':',sequence))
      missing<-setdiff(names(schema),names(qq));for(k in missing)qq[[k]]<-vctrs::vec_init(schema[[k]],nrow(qq))
      rows[[kind]]<-qq |> dplyr::select(dplyr::all_of(names(schema)))
    }
    q<-dplyr::bind_rows(c(list(schema),rows))
    fixture<-tibble::tibble(fixture_id=id,issue_id=f$issue_id,home=f$home_nowscore,away=f$away_nowscore)
    binding<-list(packet=digest::digest(p,algo='sha256'),scope=digest::digest(f,algo='sha256'),policy=digest::digest(policy,algo='sha256'),audit_code=digest::digest(paste(deparse(.InspectRecapturedMarkets),collapse='\n'),algo='sha256'))
    receipt<-list(cutoff=cutoff,input_hashes=binding,intended_use='HISTORICAL_DIAGNOSTIC',admission_state='NO_SOURCE_QUOTES')
    if(nrow(q)) {
      evidence<-lapply(seq_len(nrow(q)),function(j)list(evidence_id=q$evidence_id[j],fixture_id=id,source_hash=digest::digest(q[j,],algo='sha256'),row_key=q$evidence_id[j],issue_code='MARKET_QUOTE_PROXY',issue_year=as.integer(format(q$quote_at[j],'%Y',tz='UTC')),label_available_ts=format(q$quote_at[j],'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),data_available_ts=format(q$quote_at[j],'%Y-%m-%dT%H:%M:%SZ',tz='UTC')))
      admitted<-tryCatch({
        context<-backend$build_adjustment_evidence_context(evidence,as.list(fixture),ct,binding,shared$AvailabilityPolicy$historical_proxy('FM17_RECAPTURE_QUOTE_CLOCK_ONLY'),'HISTORICAL_DIAGNOSTIC',repository_root)
        reticulate::py_to_r(backend$export_adjustment_evidence_context(context,as.list(fixture),as.numeric(f$cutoff_utc),'HISTORICAL_DIAGNOSTIC',repository_root))
      },error=function(err) {
        if(!grepl('no rows|insufficient|empty|No prior',conditionMessage(err),ignore.case=TRUE))stop(err)
        list(evidence=list(),receipt=list(error=conditionMessage(err),input_hashes=binding,cutoff=cutoff))
      })
      ids<-dplyr::bind_rows(admitted$evidence)
      q$prior<-if(nrow(ids))q$evidence_id %in% ids$evidence_id else rep(FALSE,nrow(q))
      receipt<-list(cutoff=cutoff,input_hashes=binding,intended_use='HISTORICAL_DIAGNOSTIC',admission_state=if(any(q$prior))'PRIOR_PROXY_QUOTES'else'NO_PRIOR_QUOTES',shared=admitted$receipt)
    }
    histories[[id]]<-q
    l<-q |> dplyr::filter(prior) |> dplyr::arrange(market,company_id,dplyr::desc(quote_at),sequence) |> dplyr::group_by(market,company_id) |> dplyr::slice_head(n=1L) |> dplyr::ungroup() |> dplyr::mutate(age_hours=as.numeric(difftime(f$cutoff_utc,quote_at,units='hours')),fresh=age_hours<=policy$max_quote_age_hours,supported=market!='euro'|company_id %in% policy$euro_companies,identity_status=p$identity_status,qualified=fresh&supported&identity_status %in% c('EXACT','EXACT_IDS'))
    latest[[id]]<-l
    for(kind in c('euro','asian','totals')) {
      h<-q[q$market==kind,];z<-l[l$market==kind,]
      coverage[[length(coverage)+1L]]<-tibble::tibble(fixture_id=id,issue_id=f$issue_id,market=kind,cutoff_utc=f$cutoff_utc,identity_status=p$identity_status,source_rows=nrow(h),prior_rows=sum(h$prior),companies=nrow(z),fresh_companies=sum(z$fresh),supported_fresh_companies=sum(z$fresh&z$supported),qualified_companies=sum(z$qualified),newest_age_hours=if(nrow(z))min(z$age_hours)else NA_real_,status=if(!nrow(h))'NO_PARSED_QUOTES'else if(!any(h$prior))'NO_PRIOR_QUOTES'else if(!any(z$fresh))'ONLY_OLDER_QUOTES'else if(!any(z$fresh&z$supported))'ONLY_OUTSIDE_FIXED_BASKET'else if(!p$identity_status %in% c('EXACT','EXACT_IDS'))'IDENTITY_REVIEW_REQUIRED'else'QUALIFIED_PROXY')
    }
    receipt$output_hash<-digest::digest(list(history=q,latest=l),algo='sha256');receipts[[id]]<-receipt
  }
  list(history=dplyr::bind_rows(c(list(schema),histories)),latest=dplyr::bind_rows(latest),coverage=dplyr::bind_rows(coverage),receipts=receipts,policy=policy)
}
