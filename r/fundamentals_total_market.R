# Poisson Over share of settled stake; quarter lines split into half stakes.
# lambda is goals/match, line is goals. Pure analytic projection, no history fit.
asian_total_probability <- function(lambda, line) {
  if(length(lambda)!=1L || length(line)!=1L || anyNA(c(lambda,line)) ||
     any(!is.finite(c(lambda,line))) || lambda<=0 || line<0 || line>30 || line*4!=round(line*4)) stop('Invalid total parameters')
  legs <- if(line*2==round(line*2)) line else c(floor(line*2)/2,ceiling(line*2)/2)
  over <- mean(stats::ppois(floor(legs),lambda,lower.tail=FALSE))
  under <- mean(stats::ppois(ceiling(legs)-1,lambda))
  over/(over+under)
}

# One latest quote/company; proportional inverse-decimal margin removal.
# Invert each Asian line separately, then equal-mean company lambda. No I/O.
total_market_constraint <- function(quotes, bounds) {
  if(!is.data.frame(quotes) || !all(c('company','line','over_hk','under_hk') %in% names(quotes)) ||
     !nrow(quotes) || anyNA(quotes[c('company','line','over_hk','under_hk')]) ||
     anyDuplicated(quotes$company) || any(!is.finite(c(quotes$line,quotes$over_hk,quotes$under_hk))) ||
     any(quotes$over_hk<=0 | quotes$under_hk<=0) || length(bounds)!=2L || anyNA(bounds) ||
     any(!is.finite(bounds)) || bounds[1]<=0 || bounds[2]<=bounds[1]) stop('Invalid OU quote contract')
  quotes$over_target <- (1/(1+quotes$over_hk))/(1/(1+quotes$over_hk)+1/(1+quotes$under_hk))
  quotes$lambda_total <- vapply(seq_len(nrow(quotes)),function(i) {
    stats::uniroot(function(x)asian_total_probability(x,quotes$line[i])-quotes$over_target[i],
      interval=bounds,tol=1e-10,check.conv=TRUE)$root
  },numeric(1))
  list(lambda_total=mean(quotes$lambda_total),companies=quotes)
}

# Fix OU total mean; minimize ordinary W/D/L squared residual over home lambda.
# Overidentified independent Poisson need not match all prices: report residual.
total_constrained_projection <- function(total, ordinary_target, handicap, tail_tolerance) {
  if(length(total)!=1 || is.na(total) || !is.finite(total) || total<=.1 ||
     length(ordinary_target)!=3L || anyNA(ordinary_target) || any(!is.finite(ordinary_target)) ||
     any(ordinary_target<=0) || abs(sum(ordinary_target)-1)>1e-10) stop('Invalid total/ordinary target')
  objective <- function(home) {
    p <- market_score_projection(c(home,total-home),handicap,tail_tolerance)
    sum((unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])-ordinary_target)^2)
  }
  fit <- stats::optimize(objective,c(.05,total-.05),tol=1e-10)
  p <- market_score_projection(c(fit$minimum,total-fit$minimum),handicap,tail_tolerance)
  p$fields$market_residual <- max(abs(unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])-ordinary_target))
  p
}

# Extend sealed label-free market scenarios with OU and a fixed 10% home-share
# correction, holding OU total fixed. Match explicit cutoffs and source seals.
# Reads bound file hashes only; never reads target labels or writes files.
prepare_total_market_comparison <- function(market, totals, cutoffs, project_root,
    generated_at, total_bounds, correction_alpha, residual_limit, tail_tolerance) {
  if(!identical(market$seal,digest::digest(market[c('fixtures','grids','choices','receipt')],algo='sha256')) ||
     !identical(cutoffs,market$receipt$cutoffs) || !identical(cutoffs,totals$cutoffs) ||
     !identical(totals$euro_seal,market$receipt$quote_inputs$seal) ||
     !identical(totals$historical_admission,FALSE)) stop('Matching sealed market/cutoffs required')
  if(!identical(totals$seal,digest::digest(totals$canonical_json,algo='sha256',serialize=FALSE))) stop('Invalid OU seal')
  canonical <- jsonlite::fromJSON(totals$canonical_json,simplifyVector=FALSE)
  # Canonical representation is authoritative; R view cannot silently diverge.
  for(name in names(canonical)) {
    a <- jsonlite::fromJSON(jsonlite::toJSON(totals[[name]],auto_unbox=TRUE,digits=17,null='null'),simplifyVector=TRUE)
    b <- jsonlite::fromJSON(jsonlite::toJSON(canonical[[name]],auto_unbox=TRUE,digits=17,null='null'),simplifyVector=TRUE)
    if(!isTRUE(all.equal(a,b,tolerance=1e-14,check.attributes=TRUE))) stop('OU artifact mutated')
  }
  for(group in list(totals$capture_hashes,totals$implementation_hashes,
                    market$receipt$implementation_hashes,market$receipt$quote_inputs$implementation_hashes)) {
    for(file in names(group)) if(!identical(unname(group[[file]]),digest::digest(file=file.path(project_root,file),algo='sha256'))) stop('Bound source or implementation changed')
  }
  if(length(correction_alpha)!=1 || is.na(correction_alpha) || correction_alpha!=.1 ||
     length(residual_limit)!=1 || is.na(residual_limit) || !is.finite(residual_limit) || residual_limit<=0 ||
     !is.character(generated_at) || length(generated_at)!=1 || is.na(generated_at) ||
     !grepl('^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$',generated_at)) stop('Invalid fixed OU policy')
  statuses <- dplyr::bind_rows(totals$rows)
  statuses$max_ou_market_residual <- NA_real_
  fixtures <- grids <- choices <- constraints <- list()
  for(i in which(market$fixtures$scenario=='market')) {
    f <- market$fixtures[i,];key <- paste(f$issue,f$slot,sep='/')
    idx <- which(statuses$issue==f$issue & statuses$slot==f$slot & statuses$provider_id==f$provider_id)
    if(length(idx)!=1) stop('Missing OU identity')
    if(statuses$status[idx]!='OK_DIAGNOSTIC') next
    q <- dplyr::bind_rows(Filter(function(x)x$issue==f$issue && x$slot==f$slot,canonical$selected))
    constraint <- total_market_constraint(q,total_bounds)
    base <- dplyr::filter(market$fixtures,issue==f$issue,slot==f$slot,scenario=='baseline')
    odds <- dplyr::bind_rows(Filter(function(x)x$issue==f$issue && x$slot==f$slot,market$receipt$quote_inputs$rows))
    target <- unlist(odds[c('odds_W','odds_D','odds_L')]);target <- (1/target)/sum(1/target)
    p <- total_constrained_projection(constraint$lambda_total,target,f$handicap,tail_tolerance)
    share <- p$fields$lambda_home/constraint$lambda_total
    raw_share <- base$lambda_home/(base$lambda_home+base$lambda_away)
    corrected_share <- (1-correction_alpha)*share+correction_alpha*raw_share
    cp <- market_score_projection(constraint$lambda_total*c(corrected_share,1-corrected_share),f$handicap,tail_tolerance)
    cp$fields$market_residual <- max(abs(unlist(cp$fields[c('ordinary_W','ordinary_D','ordinary_L')])-target))
    statuses$max_ou_market_residual[idx] <- max(p$fields$market_residual,cp$fields$market_residual)
    constraints[[key]] <- dplyr::mutate(constraint$companies,fixture_lambda_total=constraint$lambda_total)
    if(statuses$max_ou_market_residual[idx]>residual_limit) {statuses$status[idx] <- 'OU_1X2_RESIDUAL_REJECTED';next}
    for(name in c('baseline','market','ou_market','ou_corrected10')) {
      if(name %in% c('baseline','market')) {
        row <- if(name=='baseline') base else f
        grid <- market$grids[[paste(key,name,sep='/')]]
      } else {
        proj <- if(name=='ou_market') p else cp
        row <- f
        for(col in names(proj$fields)) row[[col]] <- proj$fields[[col]]
        grid <- proj$grid; row$scenario <- name
      }
      fixtures[[length(fixtures)+1L]] <- row
      grids[[paste(key,name,sep='/')]] <- grid
      e <- list(fixtures=row,grids=stats::setNames(list(grid),paste(f$slot,'raw',sep='/')),
        cutoffs=cutoffs[[f$issue]][as.character(f$slot)])
      choices[[length(choices)+1L]] <- dplyr::mutate(score_coverage_choices(stats::setNames(list(e),f$issue)),scenario=name)
    }
  }
  if(!length(fixtures)) stop('No common OU constrained sample')
  keys <- dplyr::distinct(dplyr::bind_rows(fixtures),issue,slot)
  statuses$compared <- paste(statuses$issue,statuses$slot) %in% paste(keys$issue,keys$slot)
  files <- unique(c(names(market$receipt$implementation_hashes),'r/fundamentals_total_market.R'))
  hashes <- stats::setNames(lapply(file.path(project_root,files),function(f)digest::digest(file=f,algo='sha256')),files)
  artifact <- list(fixtures=dplyr::bind_rows(fixtures),grids=grids,choices=dplyr::bind_rows(choices),
    receipt=list(source_model_seal=market$receipt$source_model_seal,market_seal=market$seal,
      source_market_receipt=market$receipt,cutoffs=cutoffs,quote_inputs=totals,
      scenarios=tibble::tibble(scenario=c('baseline','market','ou_market','ou_corrected10')),
      statuses=statuses,constraints=dplyr::bind_rows(constraints),total_bounds=total_bounds,
      correction_alpha=correction_alpha,residual_limit=residual_limit,tail_tolerance=tail_tolerance,
      generated_at=generated_at,implementation_hashes=hashes,historical_admission=FALSE,
      kind='FIXED_DIAGNOSTIC_PRICE_INVERSION_NO_HISTORICAL_FIT',
      market_constraints='OU_FIXED_MEAN_PLUS_LEAST_SQUARES_1X2; AH_UNAVAILABLE'))
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}
