# Fraction of the already selected historical window with team net goals > depth.
# No window selection. Requires the explicitly identified giving team exactly
# once in every fixture; wrong identities, invalid scores and empty windows fail.
historical_large_margin_rate <- function(rows,depth,team_id) {
  if(!is.data.frame(rows) || !nrow(rows) ||
     !all(c('home_id','away_id','home_goals','away_goals') %in% names(rows)) ||
     length(depth)!=1 || !is.finite(depth) || depth<2 || depth%%1!=0)
    stop('Valid historical window and depth required')
  if(anyNA(rows[c('home_id','away_id','home_goals','away_goals')]) ||
     any(!is.finite(c(rows$home_goals,rows$away_goals))) ||
     any(rows$home_goals<0 | rows$away_goals<0 | rows$home_goals%%1!=0 | rows$away_goals%%1!=0))
    stop('Invalid historical scores/identities')
  if(!is.character(team_id) || length(team_id)!=1 || is.na(team_id) || !nzchar(team_id) ||
     any((rows$home_id==team_id)+(rows$away_id==team_id)!=1) || any(rows$home_id==rows$away_id))
    stop('Historical team identity mismatch')
  net <- (rows$home_goals-rows$away_goals)*ifelse(rows$home_id==team_id,1,-1)
  mean(net>depth)
}

# Orient prematch features to the handicap-giving team, irrespective of tier.
# Only integer absolute handicaps >=2 are eligible. Same-tier fixtures are allowed.
# Input: tidy fixture table with source identity, tiers, market W/D/L, handicap
# and overall/venue expected-net and points differences. No labels or I/O.
high_margin_features <- function(x) {
  required <- c('issue','slot','provider_id','home_tier','away_tier','handicap',
    'W','D','L','market_total','overall_expected_net','venue_expected_net',
    'ppg_overall_difference','ppg_venue_difference')
  if(!all(required %in% names(x)) || anyDuplicated(x[c('issue','slot','provider_id')]) ||
     anyNA(x[c('issue','slot','provider_id')])) stop('Unique high-margin identities required')
  x <- tibble::as_tibble(x)
  numeric_fields <- setdiff(required,c('issue','slot','provider_id'))
  if(!all(vapply(x[numeric_fields],is.numeric,logical(1)))) stop('Numeric features required')
  market <- as.matrix(x[c('W','D','L')])
  if(any(!is.finite(market)) || any(market<0 | market>1) ||
     any(abs(rowSums(market)-1)>1e-10)) stop('Invalid market distribution')
  if(any(!is.finite(x$handicap)) || any(x$handicap%%1!=0) ||
     any(!is.finite(x$market_total)) || any(x$market_total<=0)) stop('Invalid handicap/total')
  known <- is.finite(x$home_tier) & is.finite(x$away_tier)
  if(any(known & (x$home_tier<1 | x$away_tier<1 | x$home_tier%%1!=0 | x$away_tier%%1!=0)))
    stop('Invalid league tiers')
  x$eligible <- abs(x$handicap)>=2
  x$status <- ifelse(x$eligible,'LARGE_HANDICAP','OUTSIDE_SCOPE')
  sign <- ifelse(x$eligible,ifelse(x$handicap<0,1,-1),NA_real_)
  x$giving_home <- ifelse(x$eligible,sign==1,NA)
  x$tier_gap <- sign*(x$away_tier-x$home_tier)
  x$giving_handicap <- sign*x$handicap
  x$giving_market_cover <- ifelse(sign==1,x$W,ifelse(sign== -1,x$L,NA_real_))
  x$giving_overall_margin <- sign*(x$overall_expected_net+x$handicap)
  x$giving_venue_margin <- sign*(x$venue_expected_net+x$handicap)
  x$giving_overall_ppg <- sign*x$ppg_overall_difference
  x$giving_venue_ppg <- sign*x$ppg_venue_difference
  x
}

# Explicit goal allocation in goals/match, oriented to the giving side.
# Market means come from the baseline score grid; history rates retain overall
# and venue windows separately. Missing/negative goals fail, never imputed.
high_margin_goal_structure <- function(x) {
  history <- as.vector(outer(c('home_overall','home_venue','away_overall','away_venue'),
                            c('goals_for_pg','goals_against_pg'),paste,sep='_'))
  required <- c('giving_home','giving_handicap','lambda_home','lambda_away','finite_mean_total',history)
  if(!all(required %in% names(x)) || !is.logical(x$giving_home) || anyNA(x$giving_home))
    stop('Giving-side goal structure required')
  fields <- c('lambda_home','lambda_away','finite_mean_total',history)
  if(!all(vapply(x[fields],is.numeric,logical(1))) ||
     any(!is.finite(as.matrix(x[fields]))) || any(as.matrix(x[fields])<0) ||
     any(x$finite_mean_total<=0) ||
     any(abs(x$lambda_home+x$lambda_away-x$finite_mean_total)>1e-8))
    stop('Invalid expected/history goals')
  x$giving_expected_goals <- ifelse(x$giving_home,x$lambda_home,x$lambda_away)
  x$receiving_expected_goals <- ifelse(x$giving_home,x$lambda_away,x$lambda_home)
  x$giving_goal_share <- x$giving_expected_goals/x$finite_mean_total
  x$market_net_to_line <- x$giving_expected_goals-x$receiving_expected_goals+x$giving_handicap
  for(view in c('overall','venue')) for(stat in c('goals_for_pg','goals_against_pg')) {
    home <- x[[paste('home',view,stat,sep='_')]]; away <- x[[paste('away',view,stat,sep='_')]]
    x[[paste('giving',view,stat,sep='_')]] <- ifelse(x$giving_home,home,away)
    x[[paste('receiving',view,stat,sep='_')]] <- ifelse(x$giving_home,away,home)
  }
  x
}

# Retrospective exploratory binary tree: handicap-giving side covers a large line.
# Same-sample owner exception mandatory. All dates/cutoffs are retained evidence,
# not prospective admission. Fixed shallow complexity and signal bounds; no search.
# Reads two declared evidence JSON files and source hash; no writes/network effects.
explore_high_margin_expert <- function(context_path,snapshot_path,cutoffs,owner_exception,
                                      project_root,bounds=c(.2,.6),feature_set='expanded') {
  if(!identical(owner_exception,'SAMPLE_IN_EXPLORATION_ONLY') || is.null(cutoffs))
    stop('Explicit retrospective exception and cutoffs required')
  if(length(bounds)!=2 || any(!is.finite(bounds)) || bounds[1]<=0 || bounds[2]>=1 || bounds[1]>=bounds[2])
    stop('Invalid signal bounds')
  if(length(feature_set)!=1 || !feature_set %in% c('total_only','goal_structure','expanded')) stop('Unknown feature set')
  context <- jsonlite::read_json(context_path,simplifyVector=TRUE)
  snapshot <- jsonlite::read_json(snapshot_path,simplifyVector=TRUE)
  if(!identical(context$comparison$receipt$cutoffs,cutoffs) ||
     !identical(snapshot$comparison$receipt$cutoffs,cutoffs)) stop('Cutoff mismatch')
  keys <- c('issue','slot','provider_id')
  f <- dplyr::filter(snapshot$comparison$fixtures,scenario=='baseline')
  c <- context$comparison$receipt$expert_evidence
  labels <- dplyr::filter(snapshot$binary$fixtures,scenario=='baseline')
  for(other in list(c,labels)) {
    if(anyDuplicated(other[keys]) || anyDuplicated(f[keys]) || nrow(other)!=nrow(f) ||
       nrow(dplyr::anti_join(f,other,by=keys))) stop('High-margin identity mismatch')
  }
  aligned_context <- dplyr::left_join(dplyr::select(f,dplyr::all_of(keys)),c,by=keys,relationship='one-to-one')
  aligned_labels <- dplyr::left_join(dplyr::select(f,dplyr::all_of(keys)),labels,by=keys,relationship='one-to-one')
  if(anyNA(f[c('home','away','handicap')]) || anyNA(aligned_labels[c('home','away','handicap')]) ||
     anyNA(aligned_context$handicap) || any(f$handicap!=aligned_context$handicap) ||
     any(f$handicap!=aligned_labels$handicap) || any(f$home!=aligned_labels$home | f$away!=aligned_labels$away))
    stop('Fixture orientation/handicap mismatch')
  for(i in seq_len(nrow(f))) {
    key <- paste(f$issue[i],f$slot[i],sep='/')
    a <- context$comparison$receipt$source_ou_receipt$source_market_receipt$selected_windows[[key]]
    b <- snapshot$comparison$receipt$source_ou_receipt$source_market_receipt$selected_windows[[key]]
    for(field in c('provider_id','home_team_id','away_team_id'))
      if(is.null(a[[field]]) || is.null(b[[field]]) || !identical(a[[field]],b[[field]]))
        stop('Canonical fixture orientation mismatch')
    if(!identical(as.character(a$provider_id),as.character(f$provider_id[i])) ||
       identical(a$home_team_id,a$away_team_id)) stop('Canonical fixture identity mismatch')
  }
  joined <- dplyr::left_join(c,dplyr::select(f,dplyr::all_of(keys),W,D,L,lambda_home,lambda_away,finite_mean_total),by=keys,relationship='one-to-one')
  features <- high_margin_features(joined)
  scope <- dplyr::select(features,dplyr::all_of(keys),handicap,eligible,status)
  features <- high_margin_goal_structure(dplyr::filter(features,eligible))
  fields <- c('tier_gap','giving_handicap','giving_market_cover','market_total',
              'giving_overall_margin','giving_venue_margin','giving_overall_ppg','giving_venue_ppg')
  history <- jsonlite::read_json(context_path)$comparison$receipt$context_inputs$receipts
  features$overall_big_win_rate <- features$venue_big_win_rate <- NA_real_
  for(i in seq_len(nrow(features))) {
    h <- Filter(function(h) identical(as.character(h$issue),as.character(features$issue[i])) &&
      h$slot==features$slot[i] && as.character(h$provider_id)==as.character(features$provider_id[i]), history)
    if(length(h)!=1) stop('Unique historical views required')
    side <- if(features$giving_home[i]) 'home' else 'away'
    identity <- context$comparison$receipt$source_ou_receipt$source_market_receipt$selected_windows[[paste(features$issue[i],features$slot[i],sep='/')]]
    if(is.null(identity) || !identical(as.character(identity$provider_id),as.character(features$provider_id[i])))
      stop('Giving team fixture identity mismatch')
    team_id <- identity[[paste0(side,'_team_id')]]
    for(view in c('overall','venue')) {
      rows <- h[[1]]$views[[paste(side,view,sep='_')]]$rows
      features[[paste0(view,'_big_win_rate')]][i] <- historical_large_margin_rate(dplyr::bind_rows(lapply(rows,function(r)r[c("home_id","away_id","home_goals","away_goals")])),abs(features$handicap[i]),team_id)
    }
  }
  fields <- c(fields,'overall_big_win_rate','venue_big_win_rate')
  if(any(!is.finite(as.matrix(features[fields]))) || any(features$giving_market_cover<=0 | features$giving_market_cover>=1))
    stop('Invalid high-margin feature values')
  labels <- dplyr::left_join(dplyr::select(features,dplyr::all_of(keys)),labels,by=keys,relationship='one-to-one')
  if(any(!is.finite(c(labels$actual_home,labels$actual_away))) ||
     any(labels$actual_home<0 | labels$actual_away<0 | labels$actual_home%%1!=0 | labels$actual_away%%1!=0))
    stop('Invalid settlement labels')
  sign <- ifelse(features$giving_home,1,-1)
  actual_net <- labels$actual_home-labels$actual_away+features$handicap
  y <- sign*actual_net>0
  if(length(y)<6 || length(unique(y))!=2) stop('Insufficient class support')
  goal_fields <- c('giving_expected_goals','receiving_expected_goals','giving_goal_share','market_net_to_line',
    as.vector(outer(c('giving_overall','giving_venue','receiving_overall','receiving_venue'),
      c('goals_for_pg','goals_against_pg'),paste,sep='_')))
  all_fields <- c(fields,goal_fields)
  fields <- switch(feature_set,total_only='market_total',goal_structure=goal_fields,expanded=all_fields)
  training <- data.frame(features[fields],target=factor(y,levels=c(FALSE,TRUE)))
  tree <- rpart::rpart(target~.,data=training,method='class',
    control=rpart::rpart.control(maxdepth=1,minsplit=6,minbucket=3,cp=0,xval=0,maxsurrogate=0,usesurrogate=0))
  nodes <- as.integer(rownames(tree$frame)[tree$where])
  leaves <- tibble::tibble(node=nodes,covered=y) |> dplyr::group_by(node) |>
    dplyr::summarise(n=dplyr::n(),covers=sum(covered),observed_rate=mean(covered),
      probability=(covers+1)/(n+2),.groups='drop')
  leaves$rule <- vapply(rpart::path.rpart(tree,nodes=leaves$node,print.it=FALSE),paste,collapse=' & ',FUN.VALUE=character(1))
  p <- leaves$probability[match(nodes,leaves$node)]
  predictions <- dplyr::select(labels,dplyr::all_of(keys),home,away)
  predictions$giving_team <- ifelse(features$giving_home,labels$home,labels$away)
  predictions$tier_gap <- features$tier_gap
  predictions$giving_handicap <- features$giving_handicap
  predictions$cover_direction <- ifelse(features$giving_home,'W','L')
  predictions$actual <- ifelse(actual_net>0,'W',ifelse(actual_net==0,'D','L'))
  predictions$covered <- y
  predictions$node <- nodes
  predictions$market_cover <- features$giving_market_cover
  predictions$expert_cover <- p
  predictions$signal <- ifelse(p<=bounds[1],'NOT_COVER',ifelse(p>=bounds[2],'COVER','ABSTAIN'))
  predictions$signal_correct <- ifelse(predictions$signal=='ABSTAIN',NA,
    ifelse(predictions$signal=='COVER',y,!y))
  signal_summary <- predictions |> dplyr::group_by(signal) |>
    dplyr::summarise(n=dplyr::n(),coverage=dplyr::n()/nrow(predictions),
      correct=if(all(is.na(signal_correct))) NA_integer_ else sum(signal_correct),
      accuracy=if(all(is.na(signal_correct))) NA_real_ else mean(signal_correct),.groups='drop')
  metrics <- tibble::tibble(model=c('market','high_margin_tree'),
    brier=c(mean((predictions$market_cover-y)^2),mean((p-y)^2)))
  list(scope=scope,predictions=predictions,leaves=leaves,signal_summary=signal_summary,metrics=metrics,
    features=dplyr::select(features,dplyr::all_of(c(keys,all_fields))),tree=tree,
    receipt=list(kind='OWNER_AUTHORIZED_SAME_SAMPLE_HIGH_MARGIN_EXPERT',
      owner_exception=owner_exception,cutoffs=cutoffs,feature_set=feature_set,historical_admission=FALSE,deployable=FALSE,
      target_labels_used=TRUE,target='GIVING_TEAM_LARGE_HANDICAP_COVER',minimum_abs_handicap=2,bounds=bounds,
      maxdepth=1,minsplit=6,minbucket=3,laplace_pseudocount=1,features=fields,
      rpart_version=as.character(utils::packageVersion('rpart')),
      source_hashes=c(context=digest::digest(file=context_path,algo='sha256'),
        snapshot=digest::digest(file=snapshot_path,algo='sha256')),
      code_hash=digest::digest(file=file.path(project_root,'r/fundamentals_high_margin.R'),algo='sha256')))
}
