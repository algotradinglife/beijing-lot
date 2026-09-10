# Simultaneous handicap-group projection, preserving conditional score ratios.
# Missing probability means abstention. Conflicting positive signals or impossible
# joint mass leave baseline unchanged. Weights and original cutoffs are explicit.
fuse_expert_score_grid <- function(grid,handicap,draw_probability,cover_probability,
                                  weight,cutoff,owner_exception) {
  if(is.null(cutoff) || !owner_exception %in% c('SAMPLE_IN_EXPLORATION_ONLY','FROZEN_NEW_ISSUE_DIAGNOSTIC')) stop('Cutoff/retrospective exception required')
  if(length(handicap)!=1 || !is.finite(handicap) || handicap%%1!=0 ||
     length(weight)!=1 || !is.finite(weight) || weight<0 || weight>1) stop('Invalid fusion policy')
  for(p in list(draw_probability,cover_probability))
    if(length(p)!=1 || (!is.na(p) && (!is.finite(p) || p<=0 || p>=1))) stop('Invalid expert probability')
  if(!is.na(cover_probability) && abs(handicap)<2) stop('Cover expert outside large-handicap scope')
  g <- score_shape_grid(grid,1,1,1)
  g$outcome <- ifelse(g$net+handicap>0,'W',ifelse(g$net+handicap==0,'D','L'))
  mass <- stats::setNames(vapply(c('W','D','L'),function(d)sum(g$probability[g$outcome==d]),numeric(1)),c('W','D','L'))
  target <- mass;active <- c();q <- c()
  if(!is.na(draw_probability)) {active <- c(active,'D');q <- c(q,draw_probability)}
  cover_direction <- if(handicap<0) 'W' else 'L'
  if(!is.na(cover_probability)) {active <- c(active,cover_direction);q <- c(q,cover_probability)}
  status <- 'UNCHANGED'
  if(weight>0 && length(active)) {
    desired <- (1-weight)*mass[active]+weight*q
    conflict <- (!is.na(draw_probability) && !is.na(cover_probability) && draw_probability>=.6 && cover_probability>=.6) || sum(desired)>=1
    if(conflict) status <- 'CONFLICT_KEEP_BASELINE'
    else {
      other <- setdiff(names(mass),active)
      if(any(mass[active]<=0) || sum(mass[other])<=0) stop('Missing group support')
      target[active] <- desired
      target[other] <- mass[other]*(1-sum(desired))/sum(mass[other])
      scale <- stats::setNames(rep(0,3),names(mass))
      supported <- mass>0
      scale[supported] <- target[supported]/mass[supported]
      g$probability <- g$probability*unname(scale[g$outcome])
      status <- 'ADJUSTED'
    }
  }
  if(any(!is.finite(g$probability)) || any(g$probability<0) || abs(sum(g$probability)-1)>1e-10) stop('Invalid projected grid')
  list(grid=g,probabilities=target,status=status)
}

# Compare declared expert-fusion rules with the accepted baseline, same fixtures.
# Reads inventoried expert/shape evidence only. No fitting, new scrape, or writes.
compare_expert_coverage <- function(experts_path,shapes_path,cutoffs,owner_exception,project_root) {
  if(!identical(owner_exception,'SAMPLE_IN_EXPLORATION_ONLY')) stop('Retrospective exception required')
  experts <- jsonlite::read_json(experts_path,simplifyVector=TRUE)
  shapes <- jsonlite::read_json(shapes_path,simplifyVector=TRUE)
  if(!identical(cutoffs,experts$inputs$receipt$cutoffs) ||
     !identical(experts$inputs$receipt$source_hashes$labels,digest::digest(file=shapes_path,algo='sha256')))
    stop('Accepted shape/cutoff binding mismatch')
  f <- dplyr::filter(shapes$evaluation$fixtures,scenario=='baseline')
  keys <- c('issue','slot','provider_id')
  d <- dplyr::filter(experts$results$draw$predictions,model=='d1_b5')
  h <- dplyr::filter(experts$results$high$predictions,model=='d2_b5')
  if(anyDuplicated(f[keys]) || anyDuplicated(d[keys]) || anyDuplicated(h[keys]) ||
     nrow(f)!=nrow(d) || nrow(dplyr::anti_join(f,d,by=keys)) ||
     !setequal(paste(h$issue,h$slot,h$provider_id),paste(f$issue[abs(f$handicap)>=2],f$slot[abs(f$handicap)>=2],f$provider_id[abs(f$handicap)>=2]))) stop('Expert fixture identity mismatch')
  for(name in c('draw','high')) {
    r <- experts$results[[name]]$receipt
    if(!identical(r$cutoff,cutoffs) || !identical(r$deployable,FALSE) ||
       !identical(r$owner_exception,owner_exception) || !identical(unlist(r$bounds),c(.2,.6))) stop('Expert policy binding mismatch')
  }
  policy <- tibble::tibble(scenario=c('baseline','draw_half','high_half','both_half','both_negative_half','both_full'),
    draw=c(FALSE,TRUE,FALSE,TRUE,TRUE,TRUE),high=c(FALSE,FALSE,TRUE,TRUE,TRUE,TRUE),
    negative_only=c(FALSE,FALSE,FALSE,FALSE,TRUE,FALSE),weight=c(0,.5,.5,.5,.5,1))
  all <- grids <- list()
  for(k in seq_len(nrow(policy))) {
    cfg <- policy[k,]; experiments <- list(); diagnostics <- list()
    for(i in seq_len(nrow(f))) {
      row <- f[i,]; key <- paste(row$issue,row$slot,'baseline',sep='/')
      dr <- dplyr::filter(d,issue==row$issue,slot==row$slot,provider_id==row$provider_id)
      hi <- dplyr::filter(h,issue==row$issue,slot==row$slot,provider_id==row$provider_id)
      for(signal in list(dr,hi)) if(nrow(signal)) {
        if(!is.finite(signal$probability) || signal$probability<=0 || signal$probability>=1 ||
           signal$home!=row$home || signal$away!=row$away) stop('Expert orientation/probability mismatch')
        expected <- if(signal$probability<=.2) 'NEGATIVE' else if(signal$probability>=.6) 'POSITIVE' else 'ABSTAIN'
        if(signal$signal!=expected) stop('Expert signal mismatch')
      }
      dp <- if(cfg$draw && dr$signal!='ABSTAIN') dr$probability else NA_real_
      hp <- if(cfg$high && nrow(hi) && hi$signal!='ABSTAIN' && (!cfg$negative_only || hi$signal=='NEGATIVE')) hi$probability else NA_real_
      projected <- fuse_expert_score_grid(shapes$scenarios$grids[[key]],row$handicap,dp,hp,cfg$weight,
        cutoffs[[row$issue]][[as.character(row$slot)]],owner_exception)
      for(field in c('W','D','L')) row[[field]] <- unname(projected$probabilities[field])
      issue <- row$issue;slot <- as.character(row$slot)
      if(is.null(experiments[[issue]])) experiments[[issue]] <- list(fixtures=NULL,grids=list(),cutoffs=list())
      experiments[[issue]]$fixtures <- dplyr::bind_rows(experiments[[issue]]$fixtures,row)
      experiments[[issue]]$grids[[paste(slot,'raw',sep='/')]] <- projected$grid
      experiments[[issue]]$cutoffs[[slot]] <- cutoffs[[issue]][[slot]]
      diagnostics[[i]] <- tibble::tibble(issue=issue,slot=row$slot,provider_id=row$provider_id,
        home=row$home,away=row$away,fusion=projected$status,W=row$W,D=row$D,L=row$L,draw_signal=dr$signal,
        high_signal=if(nrow(hi))hi$signal else 'OUTSIDE_SCOPE')
      g <- projected$grid;g$issue <- issue;g$slot <- row$slot;g$provider_id <- row$provider_id;g$scenario <- cfg$scenario
      grids[[length(grids)+1L]] <- g
    }
    choices <- dplyr::filter(score_coverage_choices(experiments),rule=='double_protect1')
    evaluation <- list(fixtures=dplyr::mutate(f,scorable=TRUE))
    evaluated <- score_coverage_summary(choices,evaluation)$fixtures
    if(cfg$scenario=='baseline') {
      accepted <- dplyr::left_join(dplyr::select(evaluated,dplyr::all_of(keys)),f,by=keys,relationship='one-to-one')
      for(field in c('selected','protect_home','protect_away','main_hit','protect_hit','covered'))
        if(!isTRUE(all.equal(evaluated[[field]],accepted[[field]],check.attributes=FALSE))) stop('Accepted baseline parity mismatch')
    }
    all[[k]] <- dplyr::left_join(evaluated,dplyr::bind_rows(diagnostics),by=keys,relationship='one-to-one') |>
      dplyr::mutate(scenario=cfg$scenario)
  }
  rows <- dplyr::bind_rows(all)
  base <- dplyr::filter(rows,scenario=='baseline') |> dplyr::select(dplyr::all_of(keys),baseline_covered=covered,baseline_selected=selected,
      baseline_protect_home=protect_home,baseline_protect_away=protect_away)
  rows <- dplyr::left_join(rows,base,by=keys,relationship='many-to-one') |>
    dplyr::mutate(gained=covered & !baseline_covered,lost=!covered & baseline_covered)
  combined <- dplyr::bind_rows(dplyr::mutate(rows,period=issue),dplyr::mutate(rows,period='ALL'))
  summary <- combined |> dplyr::group_by(scenario,period) |> dplyr::summarise(n=dplyr::n(),
    main_hits=sum(main_hit),protection_adds=sum(protect_hit),covered=sum(covered),hit_rate=covered/n,
    gained=sum(gained),lost=sum(lost),net_gain=gained-lost,conflicts=sum(fusion=='CONFLICT_KEEP_BASELINE'),.groups='drop')
  list(fixtures=rows,summary=summary,scores=dplyr::bind_rows(grids),scope=experts$inputs$scope,
    receipt=list(kind='OWNER_AUTHORIZED_SAME_SAMPLE_EXPERT_COVERAGE',cutoffs=cutoffs,owner_exception=owner_exception,
      historical_admission=FALSE,deployable=FALSE,policy=policy,models=list(draw='d1_b5',high='d2_b5'),
      source_hashes=list(experts=digest::digest(file=experts_path,algo='sha256'),shapes=digest::digest(file=shapes_path,algo='sha256')),
      implementation_hashes=stats::setNames(lapply(c('r/fundamentals_expert_coverage.R','r/fundamentals_score_shape.R','r/fundamentals_score_diagnostic.R'),function(p)digest::digest(file=file.path(project_root,p),algo='sha256')),c('r/fundamentals_expert_coverage.R','r/fundamentals_score_shape.R','r/fundamentals_score_diagnostic.R'))))
}
