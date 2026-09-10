# Apply an already calibrated handicap-draw mass once, retaining the original
# high-margin expert's explicit weight. Pure projection: no learning or I/O.
# Zero/one draw probabilities are valid; unsupported positive mass fails.
# Impossible joint masses retain the baseline and report a conflict.
project_signal_rate_grid <- function(grid,handicap,draw_probability,high_probability,
                                     high_weight,cutoff) {
  if(length(cutoff)!=1 || is.na(cutoff) || !nzchar(cutoff) ||
     length(handicap)!=1 || !is.finite(handicap) || handicap%%1!=0 ||
     length(high_weight)!=1 || !is.finite(high_weight) || high_weight<0 || high_weight>1)
    stop('Explicit cutoff and valid projection parameters required')
  if(length(draw_probability)!=1 || !is.finite(draw_probability) || draw_probability<0 || draw_probability>1)
    stop('Invalid calibrated draw mass')
  if(length(high_probability)!=1 || (!is.na(high_probability) &&
     (!is.finite(high_probability) || high_probability<0 || high_probability>1 || abs(handicap)<2)))
    stop('Invalid high-margin probability/scope')
  g <- score_shape_grid(grid,1,1,1)
  g$outcome <- ifelse(g$net+handicap>0,'W',ifelse(g$net+handicap==0,'D','L'))
  mass <- stats::setNames(vapply(c('W','D','L'),function(d)sum(g$probability[g$outcome==d]),numeric(1)),c('W','D','L'))
  desired <- c(D=draw_probability)
  if(!is.na(high_probability) && high_weight>0) {
    direction <- if(handicap<0) 'W' else 'L'
    desired[direction] <- (1-high_weight)*mass[direction]+high_weight*high_probability
  }
  status <- 'ADJUSTED'; target <- mass
  if(sum(desired)>1 || (length(desired)>1 && sum(desired)>=1)) {
    status <- 'CONFLICT_KEEP_BASELINE'
  } else {
    other <- setdiff(names(mass),names(desired))
    if(any(mass[names(desired)]==0 & desired>0) ||
       (sum(mass[other])==0 && sum(desired)<1)) stop('Missing group support')
    target[names(desired)] <- desired
    target[other] <- if(sum(mass[other])>0) mass[other]*(1-sum(desired))/sum(mass[other]) else 0
    scale <- stats::setNames(rep(0,3),names(mass)); ok <- mass>0
    scale[ok] <- target[ok]/mass[ok]
    g$probability <- g$probability*unname(scale[g$outcome])
  }
  if(any(!is.finite(g$probability)) || any(g$probability<0) || abs(sum(g$probability)-1)>1e-10)
    stop('Invalid projected grid')
  list(grid=g,probabilities=target,status=status)
}

# Project all fixtures from a frozen baseline and choose two outcomes using the
# authoritative selector. Predictions and high signals join by exact identity.
# Cutoffs are supplied explicitly and must match the baseline. No labels or I/O.
signal_rate_score_choices <- function(control,predictions,high_signals,cutoffs,high_weight) {
  if(!identical(control$cutoffs,cutoffs)) stop('Cutoff mismatch')
  keys <- c('issue','slot','provider_id')
  base <- dplyr::filter(control$fixtures,scenario=='baseline')
  for(x in list(base,predictions,high_signals)) if(anyDuplicated(x[keys])) stop('Duplicate fixture identity')
  if(nrow(predictions)!=nrow(base) || nrow(dplyr::anti_join(base,predictions,by=keys)) ||
     nrow(dplyr::anti_join(base,high_signals,by=keys))) stop('Missing prediction identities')
  signals <- dplyr::left_join(predictions,dplyr::select(high_signals,dplyr::all_of(keys),high_probability,high_signal),
    by=keys,relationship='one-to-one')
  choices <- grids <- notes <- list()
  for(i in seq_len(nrow(base))) {
    f <- base[i,]; s <- dplyr::filter(signals,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
    g <- dplyr::filter(control$scores,issue==f$issue,slot==f$slot,provider_id==f$provider_id,scenario=='baseline') |>
      dplyr::select(home_goals,away_goals,probability,outcome)
    hp <- if(s$high_signal %in% c('POSITIVE','NEGATIVE')) s$high_probability else NA_real_
    z <- project_signal_rate_grid(g,f$handicap,s$draw_probability,hp,high_weight,
      cutoffs[[f$issue]][[as.character(f$slot)]])
    fixture <- tibble::tibble(slot=f$slot,provider_id=f$provider_id,handicap=f$handicap,
      variant='raw',status='OK_DIAGNOSTIC',W=unname(z$probabilities['W']),D=unname(z$probabilities['D']),L=unname(z$probabilities['L']))
    experiment <- list(cutoffs=cutoffs[[f$issue]][as.character(f$slot)],fixtures=fixture,
      grids=stats::setNames(list(z$grid),paste(f$slot,'raw',sep='/')))
    choice <- dplyr::filter(score_coverage_choices(stats::setNames(list(experiment),f$issue)),rule=='double_protect1')
    choice$home <- f$home; choice$away <- f$away; choice$handicap <- f$handicap; choice$scenario <- 'retrained'
    choices[[i]] <- choice
    grids[[i]] <- dplyr::mutate(z$grid,issue=f$issue,slot=f$slot,provider_id=f$provider_id,scenario='retrained')
    notes[[i]] <- dplyr::mutate(s,fusion=z$status)
  }
  list(fixtures=dplyr::bind_rows(choices),scores=dplyr::bind_rows(grids),signals=dplyr::bind_rows(notes),cutoffs=cutoffs)
}
