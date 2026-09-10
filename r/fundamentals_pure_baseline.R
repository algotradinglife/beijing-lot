# Project frozen unadjusted score grids to handicap W/D/L probabilities.
# Inputs: saved control and market objects, explicit identical fixture cutoffs.
# Output: one typed issue/slot/provider row with p_* (raw baseline) and q_*
# (Euro+OU market). Probabilities are unitless. No experts, fitting, labels or I/O.
# Missing/invalid grids, identities, cutoffs, or nonpositive market mass fail.
pure_baseline_factors <- function(control,market,cutoffs) {
 stopifnot(identical(control$cutoffs,cutoffs),identical(market$cutoffs,cutoffs))
 f <- tibble::as_tibble(control$fixtures)
 keys <- c('issue','slot','provider_id')
 stopifnot(all(c(keys,'home','away','handicap','scenario') %in% names(f)),
  !anyNA(f[c(keys,'handicap')]),!anyDuplicated(f[keys]),!anyDuplicated(f[c('issue','slot')]),
  all(f$scenario=='baseline'))
 out <- dplyr::select(f,dplyr::all_of(c(keys,'home','away','handicap')))
 for(k in c('p_W','p_D','p_L','q_W','q_D','q_L')) out[[k]] <- numeric(nrow(out))
 for(i in seq_len(nrow(f))) {
  z <- f[i,];stamp <- cutoffs[[z$issue]][[as.character(z$slot)]]
  if(is.null(stamp) || length(stamp)!=1 || is.na(stamp)) stop('Missing fixture cutoff')
  g <- dplyr::filter(control$scores,issue==z$issue,slot==z$slot,provider_id==z$provider_id,scenario=='baseline')
  mg <- market$grids[[paste(z$issue,z$slot,sep='/')]]
  status <- dplyr::filter(market$status,issue==z$issue,slot==z$slot,provider_id==z$provider_id)
  if(nrow(status)!=1 || status$status!='READY' || status$handicap!=z$handicap) stop('Market identity mismatch')
  for(prefix in c('p','q')) {
   grid <- if(prefix=='p') g else mg
   if(is.null(grid) || !nrow(grid) || anyNA(grid[c('home_goals','away_goals','probability','outcome')]) ||
      any(!is.finite(grid$probability)) || any(grid$probability<0) || abs(sum(grid$probability)-1)>1e-8)
    stop('Normalized complete score grid required')
   margin <- grid$home_goals-grid$away_goals+z$handicap
   if(any(grid$outcome!=ifelse(margin>0,'W',ifelse(margin<0,'L','D')))) stop('Handicap outcome mismatch')
   mass <- vapply(c('W','D','L'),function(d) sum(grid$probability[grid$outcome==d]),numeric(1))
   if(prefix=='q' && any(mass<=0)) stop('Positive market probabilities required')
   for(d in names(mass)) out[[paste0(prefix,'_',d)]][i] <- mass[[d]]
  }
 }
 out
}
