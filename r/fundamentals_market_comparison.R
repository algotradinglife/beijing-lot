# Fixed inverse-price sensitivity, not a learned league-strength conversion.
# All lambdas are goals/match. alpha is in [0,1], cap in [0,1). Pure, no I/O.
bounded_market_lambdas <- function(market, home_away, alpha, cap) {
  for (v in list(market,home_away)) if (!is.numeric(v) || length(v)!=2L ||
      anyNA(v) || any(!is.finite(v)) || any(v<=0)) stop('Positive paired lambdas required')
  if (length(alpha)!=1L || length(cap)!=1L || anyNA(c(alpha,cap)) ||
      any(!is.finite(c(alpha,cap))) || alpha<0 || alpha>1 || cap<0 || cap>=1) stop('Invalid correction policy')
  market+pmax(-cap*market,pmin(cap*market,alpha*(home_away-market)))
}

# Poisson grid projections used by the existing shape evaluator/coverage rules.
# No outcome inputs. Tail probability is bounded by the supplied tolerance.
market_score_projection <- function(lambda, handicap, tail_tolerance) {
  g <- illustrative_score_grid(lambda[1],lambda[2],handicap,tail_tolerance)$grid
  g$net <- g$home_goals-g$away_goals
  g$outcome <- g$handicap_outcome
  total <- g$home_goals+g$away_goals
  p <- list(lambda_home=lambda[1],lambda_away=lambda[2],
    finite_mean_total=sum(total*g$probability),finite_mean_net=sum(g$net*g$probability),
    boundary_mass=sum(g$probability[g$home_goals==max(g$home_goals) | g$away_goals==max(g$away_goals)]))
  for(d in c('W','D','L')) p[[d]] <- sum(g$probability[g$outcome==d])
  p$ordinary_W <- sum(g$probability[g$net>0]);p$ordinary_D <- sum(g$probability[g$net==0]);p$ordinary_L <- sum(g$probability[g$net<0])
  for(k in 2:4) {
    p[[paste0('home_ge',k)]] <- sum(g$probability[g$net>=k])
    p[[paste0('away_ge',k)]] <- sum(g$probability[g$net<= -k])
  }
  for(k in 5:6) p[[paste0('total_ge',k)]] <- sum(g$probability[total>=k])
  list(grid=g,fields=p)
}

# Declare all scenarios before labels. Same matched sample across four models.
# Explicit cutoffs must match the sealed base and quote receipts. League catalog
# describes dated participation only; it does not force a direction or estimate
# a cross-league coefficient. Missing/ambiguous identities stay in status table.
# Returns existing shape-evaluator schema plus quote/correction diagnostics.
prepare_market_comparison <- function(models, quotes, cutoffs, league_catalog,
    corrections, cap, residual_limit, project_root, generated_at) {
  fields <- c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')
  if (!identical(models$seal,digest::digest(models[fields],algo='sha256')) ||
      !identical(models$historical_admission,FALSE) ||
      !identical(cutoffs,lapply(models$experiments,`[[`,'cutoffs')) ||
      !identical(quotes$historical_admission,FALSE)) stop('Sealed diagnostic inputs/cutoffs required')
  quote_fields <- c('rows','companies','receipts','implementation_hashes','historical_admission')
  if(is.null(quotes$canonical_json) || is.null(quotes$seal) || !length(quotes$implementation_hashes) ||
     !identical(quotes$seal,digest::digest(quotes$canonical_json,algo='sha256',serialize=FALSE))) stop('Invalid quote seal')
  # Reticulate simplifies homogeneous Python lists to R vectors. Normalize both
  # sides through the same JSON reader; allow only floating round-trip precision.
  quote_view <- quotes[quote_fields]
  for(i in seq_along(quote_view$receipts)) quote_view$receipts[[i]]$receipt$selected_ids <-
    as.list(unlist(quote_view$receipts[[i]]$receipt$selected_ids,use.names=FALSE))
  canonical <- jsonlite::fromJSON(quotes$canonical_json,simplifyVector=TRUE)
  roundtrip <- jsonlite::fromJSON(jsonlite::toJSON(quote_view,auto_unbox=TRUE,
    digits=17,null='null'),simplifyVector=TRUE)
  if(!isTRUE(all.equal(roundtrip,canonical[quote_fields],check.attributes=TRUE,
    tolerance=1e-14))) stop('Quote artifact mutated')
  if (!is.numeric(corrections) || !identical(names(corrections),c('corrected10','corrected20')) ||
      !identical(unname(corrections),c(.1,.2)) || !is.numeric(residual_limit) ||
      length(residual_limit)!=1 || is.na(residual_limit) || !is.finite(residual_limit) || residual_limit<=0) stop('Invalid fixed scenarios')
  bounded_market_lambdas(c(1,1),c(1,1),corrections[1],cap)
  if (!is.data.frame(league_catalog) || !all(c('league','country','tier') %in% names(league_catalog)) ||
      anyNA(league_catalog) || anyDuplicated(league_catalog$league) || any(league_catalog$tier<1)) stop('Invalid explicit league catalog')
  q <- dplyr::bind_rows(quotes$rows)
  if (anyDuplicated(q[c('issue','slot','provider_id')])) stop('Duplicate quotes')
  for(i in seq_len(nrow(q))) if(!identical(q$capture_sha256[i],
      digest::digest(file=q$capture_path[i],algo='sha256'))) stop('Capture envelope changed')
  if (!is.character(generated_at) || length(generated_at)!=1L || is.na(generated_at) ||
      !grepl('^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$',generated_at)) stop('UTC generation timestamp required')
  for (file in names(quotes$implementation_hashes)) if (!identical(quotes$implementation_hashes[[file]],
      digest::digest(file=file.path(project_root,file),algo='sha256'))) stop('Quote implementation changed')
  for (file in names(models$implementation_hashes)) if (!identical(unname(models$implementation_hashes[[file]]),
      digest::digest(file=file.path(project_root,file),algo='sha256'))) stop('Base implementation changed')
  fixtures <- grids <- choices <- statuses <- league_evidence <- list()
  policy <- tibble::tibble(scenario=c('baseline','market','corrected10','corrected20'))
  for(issue in names(models$experiments)) {
    e <- models$experiments[[issue]]
    for (i in which(e$fixtures$variant=='raw' & e$fixtures$status=='OK_DIAGNOSTIC')) {
      f <- e$fixtures[i,]
      windows <- Filter(function(w)w$slot==f$slot,e$source_windows)
      if(length(windows)!=1L) stop('Unique selected history window required')
      w <- windows[[1]]
      history <- lapply(c('home_window','away_window'),function(side)
        vapply(w[[side]],function(h)if(is.null(h$competition_name)) NA_character_ else h$competition_name,character(1)))
      leagues <- lapply(history,function(h)unique(h[h %in% league_catalog$league]))
      if(any(lengths(leagues)!=1L)) next
      h <- league_catalog[league_catalog$league==leagues[[1]],]
      a <- league_catalog[league_catalog$league==leagues[[2]],]
      if (nrow(h)!=1L || nrow(a)!=1L || anyNA(h) || anyNA(a) || h$country!=a$country || h$tier==a$tier) next
      league_evidence[[paste(issue,f$slot,sep='/')]] <- w
      quote <- q[q$issue==issue & q$slot==f$slot,]
      status <- tibble::tibble(issue=issue,slot=f$slot,provider_id=f$provider_id,home=f$home,away=f$away,
        home_league=h$league,away_league=a$league,status='MARKET_UNAVAILABLE',companies=0L,max_market_residual=NA_real_)
      if(nrow(quote)) {
        if(nrow(quote)!=1L || quote$provider_id!=f$provider_id ||
           !identical(quote$cutoff_utc,cutoffs[[issue]][[as.character(f$slot)]])) stop('Market identity/cutoff mismatch')
        status$status <- quote$status;status$companies <- quote$companies
      }
      if(status$status!='OK_DIAGNOSTIC') {statuses[[length(statuses)+1L]] <- status;next}
      receipts <- Filter(function(r)r$issue==issue && r$slot==f$slot,quotes$receipts)
      if(length(receipts)!=1L || !identical(receipts[[1]]$receipt$historical_admission,FALSE)) stop('Missing quote receipt')
      receipt <- receipts[[1]]$receipt
      if(is.null(receipts[[1]]$receipt_json) || is.null(receipt$identity) ||
         !identical(receipt$identity,digest::digest(receipts[[1]]$receipt_json,algo='sha256',serialize=FALSE))) stop('Invalid quote receipt identity')
      if(!identical(receipt$target_issue,issue) || is.null(receipt$cutoff_ts) ||
         !isTRUE(as.numeric(readr::parse_datetime(receipt$cutoff_ts))==as.numeric(readr::parse_datetime(quote$cutoff_utc))) ||
         !identical(receipt$implementation_hashes,quotes$implementation_hashes) ||
         !identical(receipt$source_hashes[[quote$capture_path]],quote$capture_sha256)) stop('Quote receipt binding mismatch')
      company_rows <- Filter(function(r)r$issue==issue && r$slot==f$slot,quotes$companies)
      ids <- vapply(company_rows,`[[`,character(1),'quote_id')
      if(length(ids)!=quote$companies || anyDuplicated(ids) ||
         !identical(unname(ids),unname(unlist(receipt$selected_ids)))) stop('Selected company binding mismatch')
      for(column in c('odds_W','odds_D','odds_L')) {
        average <- mean(vapply(company_rows,`[[`,numeric(1),column))
        if(!isTRUE(abs(average-quote[[column]])<1e-12)) stop('Aggregate market odds mismatch')
      }
      odds <- c(W=unname(quote$odds_W),D=unname(quote$odds_D),L=unname(quote$odds_L))
      market <- tryCatch(market_handicap_proxy(odds,f$handicap,models$parameters$tail_tolerance,
        1e-6,c(.05,8),c(1.5,1)),error=function(e)e)
      if(inherits(market,'error')) {
        status$status <- 'POISSON_PRICE_FIT_REJECTED';statuses[[length(statuses)+1L]] <- status;next
      }
      ml <- c(market$lambda_home,market$lambda_away);raw <- c(f$lambda_home,f$lambda_away)
      lambdas <- list(baseline=raw,market=ml,
        corrected10=bounded_market_lambdas(ml,raw,corrections[1],cap),
        corrected20=bounded_market_lambdas(ml,raw,corrections[2],cap))
      projections <- lapply(lambdas,market_score_projection,handicap=f$handicap,tail_tolerance=models$parameters$tail_tolerance)
      residuals <- vapply(projections,function(p)max(abs(unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])-market$ordinary_target)),numeric(1))
      status$max_market_residual <- max(residuals[-1])
      if(status$max_market_residual>residual_limit) {
        status$status <- 'CORRECTION_MARKET_DRIFT_REJECTED';statuses[[length(statuses)+1L]] <- status;next
      }
      statuses[[length(statuses)+1L]] <- status
      for (name in names(projections)) {
        p <- projections[[name]];row <- f
        for(column in names(p$fields)) row[[column]] <- p$fields[[column]]
        row$market_residual <- residuals[name]
        row$home_league <- h$league;row$away_league <- a$league;row$companies <- quote$companies
        key <- paste(f$slot,'raw',sep='/')
        choice_input <- stats::setNames(list(list(fixtures=row,grids=stats::setNames(list(p$grid),key),
          cutoffs=e$cutoffs[as.character(f$slot)])),issue)
        choices[[length(choices)+1L]] <- dplyr::mutate(score_coverage_choices(choice_input),scenario=name)
        fixtures[[length(fixtures)+1L]] <- dplyr::mutate(row,issue=issue,scenario=name,.before=1)
        grids[[paste(issue,f$slot,name,sep='/')]] <- p$grid
      }
    }
  }
  if(!length(fixtures)) stop('No common eligible market sample')
  status_table <- dplyr::bind_rows(statuses)
  unresolved <- dplyr::anti_join(q,status_table,by=c('issue','slot','provider_id'))
  if(nrow(unresolved)) status_table <- dplyr::bind_rows(status_table,
    dplyr::transmute(unresolved,issue,slot,provider_id,status='CROSS_TIER_EVIDENCE_UNRESOLVED',companies))
  files <- unique(c(names(models$implementation_hashes),'r/fundamentals_market_comparison.R',
    'r/strength_market_scenario.R','r/fundamentals_score_shape.R'))
  hashes <- stats::setNames(vapply(file.path(project_root,files),digest::digest,character(1),file=TRUE,algo='sha256'),files)
  artifact <- list(fixtures=dplyr::bind_rows(fixtures),grids=grids,choices=dplyr::bind_rows(choices),
    receipt=list(kind='IN_SAMPLE_FIXED_SCENARIOS_NOT_FITTED',historical_admission=FALSE,
      source_model_seal=models$seal,cutoffs=cutoffs,scenarios=policy,league_catalog=league_catalog,
      correction_alpha=corrections,relative_cap=cap,market_residual_limit=residual_limit,
      quote_inputs=quotes,statuses=status_table,selected_windows=league_evidence,input_provenance=models$provenance,
      implementation_hashes=as.list(hashes),generated_at=generated_at,
      market_constraints='1X2_ONLY; OU_AND_AH_UNAVAILABLE',
      support='FINITE_INDEPENDENT_POISSON; OUTSIDE_SUPPORT_ZERO'))
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}
