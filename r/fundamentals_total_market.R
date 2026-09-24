library(beidan)


# Reads bound file hashes only; never reads target labels or writes files.
prepare_total_market_comparison <- function(market, totals, cutoffs, project_root,
    generated_at, total_bounds, correction_alpha, residual_limit, tail_tolerance, rho) {
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
    p <- total_constrained_projection(constraint$lambda_total,target,f$handicap,tail_tolerance,rho)
    share <- p$fields$lambda_home/constraint$lambda_total
    raw_share <- base$lambda_home/(base$lambda_home+base$lambda_away)
    corrected_share <- (1-correction_alpha)*share+correction_alpha*raw_share
    cp <- market_score_projection(constraint$lambda_total*c(corrected_share,1-corrected_share),f$handicap,tail_tolerance,rho)
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
