# Read only declared prediction columns/grids from inventoried diagnostic reports.
# Inputs include old exploratory reports; their labels do not enter the output.
# source_paths are bound explicitly. Cutoffs are the per-fixture historical maps.
ev_control_inputs <- function(previous_path,next_path,cutoffs) {
  a <- jsonlite::read_json(previous_path,simplifyVector=TRUE)
  b <- jsonlite::read_json(next_path,simplifyVector=TRUE)
  fields <- c('issue','slot','provider_id','scenario','home','away','handicap','selected','protect_home','protect_away')
  rows <- dplyr::bind_rows(dplyr::select(dplyr::filter(a$fixtures,scenario %in% c('baseline','both_half')),dplyr::all_of(fields)),
                          dplyr::select(b$fixtures,dplyr::all_of(fields)))
  score_fields <- c('issue','slot','provider_id','scenario','home_goals','away_goals','probability','outcome')
  scores <- list(dplyr::select(dplyr::filter(a$scores,scenario %in% c('baseline','both_half')),dplyr::all_of(score_fields)))
  for(scenario in c('baseline','both_half')) {
    e <- b$predictions[[if(scenario=='baseline') 'baseline' else 'adjusted']]
    for(i in which(rows$issue %in% unique(b$fixtures$issue) & rows$scenario==scenario)) {
      f <- rows[i,];g <- e$grids[[paste(f$slot,'raw',sep='/')]]
      scores[[length(scores)+1L]] <- dplyr::mutate(g,issue=f$issue,slot=f$slot,provider_id=f$provider_id,scenario=scenario) |> dplyr::select(dplyr::all_of(score_fields))
    }
  }
  if(anyDuplicated(rows[c('issue','slot','provider_id','scenario')])) stop('Duplicate control predictions')
  for(i in seq_len(nrow(rows))) if(is.null(cutoffs[[rows$issue[i]]][[as.character(rows$slot[i])]])) stop('Missing control cutoff')
  list(fixtures=rows,scores=dplyr::bind_rows(scores),cutoffs=cutoffs,
    source_hashes=list(previous=digest::digest(file=previous_path,algo='sha256'),next_issue=digest::digest(file=next_path,algo='sha256')))
}

# Fixed Euro+OU inversion for every declared control fixture, without league
# filtering. Uses the sealed canonical quote payload as authoritative. The
# ordinary-probability residual is disclosed, not used for outcome-based pruning.
# Returns market score grids and a full status denominator, no settlement input.
ev_market_probabilities <- function(euro_path,total_path,fixtures,cutoffs,project_root,tail_tolerance) {
  e <- jsonlite::read_json(euro_path,simplifyVector=TRUE);t <- jsonlite::read_json(total_path,simplifyVector=TRUE)
  for(x in list(e,t)) if(!identical(x$seal,digest::digest(x$canonical_json,algo='sha256',serialize=FALSE))) stop('Market quote seal mismatch')
  euro <- jsonlite::parse_json(e$canonical_json,simplifyVector=TRUE)
  total <- jsonlite::parse_json(t$canonical_json,simplifyVector=TRUE)
  if(!identical(total$euro_seal,e$seal) || !identical(total$cutoffs,cutoffs)) stop('Market cutoff/source mismatch')
  for(group in list(total$capture_hashes,total$implementation_hashes,euro$implementation_hashes))
    for(path in names(group)) if(!identical(group[[path]],digest::digest(file=if(grepl('^/',path)) path else file.path(project_root,path),algo='sha256'))) stop('Market source/code changed')
  for(name in c('euro','total')) {
    payload <- get(name)
    if(!length(payload$rows)) payload$rows <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),status=character())
    assign(name,payload)
  }
  statuses <- grids <- list()
  cases <- dplyr::distinct(fixtures,issue,slot,provider_id,handicap)
  for(i in seq_len(nrow(cases))) {
    f <- cases[i,];q <- dplyr::filter(euro$rows,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
    u <- dplyr::filter(total$rows,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
    row <- dplyr::mutate(f,status='MARKET_UNAVAILABLE',market_residual=NA_real_,lambda_home=NA_real_,lambda_away=NA_real_)
    if(nrow(q)==1 && nrow(u)==1) {
      if(q$status!='OK_DIAGNOSTIC' || u$status!='OK_DIAGNOSTIC') row$status <- paste(q$status,u$status,sep='/')
      else {
        if(q$cutoff_utc!=cutoffs[[f$issue]][[as.character(f$slot)]] || u$cutoff_utc!=q$cutoff_utc ||
           !identical(q$capture_sha256,digest::digest(file=q$capture_path,algo='sha256'))) stop('Euro cutoff/capture changed')
        selected <- dplyr::filter(total$selected,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
        constraint <- total_market_constraint(selected,c(.1,16))
        odds <- unlist(q[c('odds_W','odds_D','odds_L')]);target <- (1/odds)/sum(1/odds)
        p <- total_constrained_projection(constraint$lambda_total,target,f$handicap,tail_tolerance,rho)
        row$status <- 'READY';row$market_residual <- p$fields$market_residual
        row$lambda_home <- p$fields$lambda_home;row$lambda_away <- p$fields$lambda_away
        grids[[paste(f$issue,f$slot,sep='/')]] <- p$grid
      }
    }
    statuses[[i]] <- row
  }
  list(status=dplyr::bind_rows(statuses),grids=grids,cutoffs=cutoffs,receipt=list(euro_seal=e$seal,total_seal=t$seal,
    source_hashes=list(euro=digest::digest(file=euro_path,algo='sha256'),total=digest::digest(file=total_path,algo='sha256')),
    market_residual_policy='DISCLOSE_NOT_REJECT',sp_proxy='1 / normalized_market_option_probability',historical_admission=FALSE))
}

# Form fixed p/q factors for already nominated double outcomes and BF option.
# Aggregate lottery "other" score categories through the existing Python map.
# Every factor uses model probability and market probability, never final SP.
ev_candidate_factors <- function(control,market,python,project_root) {
  if(!identical(control$cutoffs,market$cutoffs)) stop('Factor cutoff mismatch')
  module <- project_python_module('src.nowscore_settlement',project_root,python,convert=FALSE)
  all_scores <- dplyr::bind_rows(list(control$scores,dplyr::bind_rows(market$grids))) |>
    dplyr::distinct(home_goals,away_goals)
  all_scores$option <- vapply(seq_len(nrow(all_scores)),function(i)reticulate::py_to_r(module$expected_option(
    list(play='bf',score=paste(all_scores$home_goals[i],all_scores$away_goals[i],sep=':')))),character(1))
  rows <- list()
  for(i in seq_len(nrow(control$fixtures))) {
    f <- control$fixtures[i,];key <- paste(f$issue,f$slot,sep='/');mg <- market$grids[[key]]
    if(is.null(mg)) next
    g <- dplyr::filter(control$scores,issue==f$issue,slot==f$slot,provider_id==f$provider_id,scenario==f$scenario)
    for(z in list(g,mg)) if(!nrow(z) || any(!is.finite(z$probability)) || any(z$probability<0) || abs(sum(z$probability)-1)>1e-8) stop('Normalized score distributions required')
    p <- stats::setNames(vapply(c('W','D','L'),function(d)sum(g$probability[g$outcome==d]),numeric(1)),c('W','D','L'))
    q <- stats::setNames(vapply(c('W','D','L'),function(d)sum(mg$probability[mg$outcome==d]),numeric(1)),c('W','D','L'))
    option <- reticulate::py_to_r(module$expected_option(list(play='bf',score=paste(f$protect_home,f$protect_away,sep=':'))))
    g <- dplyr::left_join(g,all_scores,by=c('home_goals','away_goals'),relationship='many-to-one')
    mg <- dplyr::left_join(mg,all_scores,by=c('home_goals','away_goals'),relationship='many-to-one')
    pp <- sum(g$probability[g$option==option]);pq <- sum(mg$probability[mg$option==option])
    dirs <- strsplit(f$selected,',',fixed=TRUE)[[1]]
    if(any(!is.finite(q)) || any(q<=0) || !is.finite(pq) || pq<=0 || length(dirs)!=2 || anyDuplicated(dirs) || !all(dirs %in% c('W','D','L'))) stop('Positive complete market prices required')
    row <- dplyr::mutate(f,main_factor=sum(p[dirs]/q[dirs]),protection_factor=pp/pq,
       protection_probability=pp,market_protection_probability=pq,protection_sp_proxy=1/pq,protection_option=option)
    for(d in c('W','D','L')) {row[[paste0('p_',d)]] <- unname(p[d]);row[[paste0('q_',d)]] <- unname(q[d]);row[[paste0('sp_proxy_',d)]] <- unname(1/q[d])}
    rows[[length(rows)+1L]] <- row
  }
  if(!length(rows)) return(dplyr::mutate(control$fixtures[0,],main_factor=numeric(),protection_factor=numeric()))
  dplyr::bind_rows(rows)
}

# Fixed-budget EV selection for both control distributions; same market pool.
# Shared Cutoff instances are passed to the domain solver. Only model p/q enters
# ranking. Persists an immutable prediction artifact before any settlement call.
ev_seven_plans <- function(factors,control,market,python,project_root,output_path) {
  module <- project_python_module('src.fundamentals_ev_portfolio',project_root,python,convert=FALSE)
  temporal <- project_python_module('src.temporal_learning',project_root,python,convert=FALSE)
  plans <- solutions <- summaries <- list()
  for(issue in unique(control$fixtures$issue)) {
    for(scenario in c('baseline','both_half')) {
      rows <- dplyr::filter(factors,.data$issue==.env$issue,.data$scenario==.env$scenario)
      key <- paste(issue,scenario,sep='/')
      if(nrow(rows)<7) {
        summaries[[key]] <- tibble::tibble(issue=issue,scenario=scenario,candidates=nrow(rows),status='FEWER_THAN_SEVEN_MARKET_MATCHES',expected_gross=NA_real_,expected_net=NA_real_,expected_roi=NA_real_)
        next
      }
      pycuts <- lapply(control$cutoffs[[issue]],function(stamp)temporal$Cutoff$decision_epoch(issue,stamp))
      inputs <- lapply(seq_len(nrow(rows)),function(i)as.list(rows[i,c('issue','slot','provider_id','main_factor','protection_factor')]))
      sol <- reticulate::py_to_r(module$optimize_seven_ev(inputs,cutoffs=pycuts,
        owner_exception='OWNER_AUTHORIZED_HISTORICAL_RETURNS',n=7L,unit_cny=2L,budget_cny=1024L,
        main_multiples=3L,payout_factor=.65))
      selected <- dplyr::left_join(dplyr::select(dplyr::bind_rows(sol$selected),issue,slot,provider_id),rows,
        by=c('issue','slot','provider_id'),relationship='one-to-one')
      plan <- seven_double_plan(selected,control$cutoffs,7,2,1024,3,.65,'OWNER_AUTHORIZED_HISTORICAL_RETURNS')
      if(!isTRUE(all.equal(plan$legs$protection_stake,vapply(sol$selected,`[[`,numeric(1),'protection_stake')))) stop('Optimizer/stake ledger mismatch')
      plans[[key]] <- plan;solutions[[key]] <- sol
      summaries[[key]] <- tibble::tibble(issue=issue,scenario=scenario,candidates=nrow(rows),status='PLANNED',
        expected_gross=sol$expected_gross,expected_net=sol$expected_net,expected_roi=sol$expected_roi)
    }
  }
  provenance <- project_python_module('src.temporal_learning.provenance',project_root,python,convert=FALSE)
  path_module <- reticulate::import('pathlib',convert=FALSE)
  closure <- reticulate::py_to_r(provenance$implementation_closure(path_module$Path(project_root),
    c('src.fundamentals_ev_portfolio','src.nowscore_settlement'),distributions=c('numpy','scipy')))
  r_files <- c('r/fundamentals_ev_returns.R','r/fundamentals_returns.R','r/python_bridge.R',
    'r/nowscore_query.R','r/fundamentals_market_comparison.R','r/fundamentals_total_market.R','r/probability_exploration.R')
  r_hashes <- stats::setNames(lapply(r_files,function(p)digest::digest(file=file.path(project_root,p),algo='sha256')),r_files)
  artifact <- list(implementation=list(python=closure,r=r_hashes),plans=plans,solutions=solutions,summary=dplyr::bind_rows(summaries),factors=factors,
    control_sources=control$source_hashes,market_receipt=market$receipt,cutoffs=control$cutoffs,
    owner_exception='OWNER_AUTHORIZED_HISTORICAL_RETURNS',historical_admission=FALSE)
  encoded <- as.character(jsonlite::toJSON(artifact,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null'))
  dir.create(dirname(output_path),recursive=TRUE,showWarnings=FALSE)
  if(file.exists(output_path)) {
    if(!identical(readChar(output_path,file.info(output_path)$size,useBytes=TRUE),encoded)) stop('Frozen EV selections changed')
  } else writeChar(encoded,output_path,eos=NULL,useBytes=TRUE)
  c(artifact,list(prediction_sha256=digest::digest(file=output_path,algo='sha256')))
}

# Settlement stage is separate from the optimizer and consumes only audited
# actual winning SP. Baseline and expert portfolios may choose different seven.
ev_settle_plans <- function(predictions,audit,python,project_root) {
  provenance <- project_python_module('src.temporal_learning.provenance',project_root,python,convert=FALSE)
  provenance$verify_implementation_closure(reticulate::import('pathlib',convert=FALSE)$Path(project_root),predictions$implementation$python)
  for(p in names(predictions$implementation$r)) if(!identical(predictions$implementation$r[[p]],digest::digest(file=file.path(project_root,p),algo='sha256'))) stop('Frozen R implementation changed')
  summaries <- details <- list()
  for(key in names(predictions$plans)) {
    r <- settle_seven_double(predictions$plans[[key]],audit,python,project_root)
    scenario <- strsplit(key,'/',fixed=TRUE)[[1]][2]
    summaries[[key]] <- dplyr::mutate(r$summary,scenario=scenario)
    details[[key]] <- dplyr::mutate(r$legs,scenario=scenario)
  }
  summary <- if(length(summaries)) dplyr::bind_rows(summaries) else tibble::tibble(issue=character(),scenario=character(),main_hits=integer(),parlay_hit=logical(),protection_hits=integer(),main_stake=double(),protection_stake=double(),main_gross=double(),protection_gross=double(),gross=double(),net=double(),roi=double())
  list(summary=summary,legs=dplyr::bind_rows(details),prediction_sha256=predictions$prediction_sha256)
}
