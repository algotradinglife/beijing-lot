# Reconstruct frozen current grids using the already accepted projection API.
# No model training, new market fitting or settlement reads.
args <- commandArgs(TRUE)
stopifnot(length(args)==2)
parent <- args[1]; out <- args[2]
stopifnot(!file.exists(file.path(out,'scores.json')))
modules <- c('python_bridge','probability_exploration','fundamentals_home_away',
 'goal_distribution_experiment','fundamentals_score_diagnostic','fundamentals_score_shape',
 'fundamentals_high_margin','fundamentals_three_issue_experts','fundamentals_expert_coverage',
 'fundamentals_next_issue','fundamentals_ev_returns','fundamentals_market_comparison',
 'fundamentals_total_market','fundamentals_retraining','eight_issue_holdout','nowscore_query',
 'fundamentals_returns','fundamentals_selection_comparison','fundamentals_direct_score_returns',
 'eight_issue_returns','fundamentals_n_comparison','fundamentals_pure_parlay','fundamentals_draw_fusion',
 'fundamentals_draw_snapshot','fundamentals_signal_rate_projection')
paths <- c(paste0('r/',modules,'.R'),'scripts/prepare_conflict_action_scores.R')
implementation <- as.list(stats::setNames(vapply(paths,digest::digest,character(1),file=TRUE,algo='sha256'),paths))
for(name in modules) source(paste0('r/',name,'.R'))
inputs <- jsonlite::read_json(file.path(parent,'inputs.json'),simplifyVector=TRUE)
for(path in names(inputs$source_hashes)) stopifnot(identical(digest::digest(file=path,algo='sha256'),inputs$source_hashes[[path]]))
keys <- c('issue','slot','provider_id')
required <- dplyr::filter(inputs$rows,weight==.5)
base <- 'data/derived/fundamentals_417'
endpoint_path <- file.path(base,'integration-weight-v3/endpoints.json')
high_path <- file.path(base,'consistent-experts-101-v1/high.json')
pp <- jsonlite::read_json(endpoint_path,simplifyVector=TRUE)$rows
high <- jsonlite::read_json(high_path,simplifyVector=TRUE)$rows |> dplyr::rename(issue=issue_code)
accepted <- jsonlite::read_json(file.path(base,'integration-weight-v3/candidates.json'))
stopifnot(identical(digest::digest(file=high_path,algo='sha256'),accepted$high_sha256))
grids <- list();sources <- list();notes <- list()
for(study in c('train-eight-test-eight-v2','cv-sixteen-test-sixteen-v1','cv-thirtytwo-test-sixteen-v1')) {
 path <- file.path(base,study,'predictions.json');old <- jsonlite::read_json(path,simplifyVector=TRUE)
 stopifnot(identical(digest::digest(file=path,algo='sha256'),inputs$source_hashes[[path]]))
 control <- old$selected
 control$fixtures <- dplyr::semi_join(dplyr::filter(control$fixtures,scenario=='baseline'),required,by=keys)
 control$scores <- dplyr::semi_join(dplyr::filter(control$scores,scenario=='baseline'),required,by=keys)
 pred <- dplyr::semi_join(pp,control$fixtures,by=keys)
 pred$draw_probability <- .5*pred$baseline_draw+.5*pred$expert_draw
 adjusted <- signal_rate_score_choices(control,pred,high,control$cutoffs,.5)
 for(i in seq_len(nrow(control$fixtures))) {
  f <- control$fixtures[i,];id <- paste(f$issue,f$slot,sep='/')
  current <- dplyr::filter(adjusted$scores,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
  market <- old$market$grids[[id]]
  stopifnot(!is.null(market),identical(old$market$cutoffs[[f$issue]][[as.character(f$slot)]],inputs$cutoffs[[f$issue]][[as.character(f$slot)]]))
  grid <- dplyr::full_join(dplyr::select(current,home_goals,away_goals,p=probability),
    dplyr::select(market,home_goals,away_goals,q=probability),by=c('home_goals','away_goals'),relationship='one-to-one') |>
    dplyr::mutate(p=dplyr::coalesce(p,0),q=dplyr::coalesce(q,0)) |>
    dplyr::arrange(home_goals,away_goals)
  stopifnot(abs(sum(grid$p)-1)<1e-9,abs(sum(grid$q)-1)<1e-9,all(grid$p>=0),all(grid$q>=0))
  margin <- grid$home_goals-grid$away_goals+f$handicap
  direction <- ifelse(margin>0,'W',ifelse(margin==0,'D','L'))
  expected <- dplyr::filter(required,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
  stopifnot(nrow(expected)==1)
  for(d in c('W','D','L')) {
   stopifnot(abs(sum(grid$p[direction==d])-expected[[paste0('p_',d)]])<1e-12,
             abs(sum(grid$q[direction==d])-expected[[paste0('q_',d)]])<1e-12)
  }
  stopifnot(is.null(grids[[id]]));grids[[id]] <- grid
 }
 notes[[study]] <- dplyr::select(adjusted$signals,dplyr::all_of(keys),fusion)
 sources[[path]] <- digest::digest(file=path,algo='sha256')
 cat('SCORES',study,nrow(control$fixtures),'\n');flush.console()
}
stopifnot(length(grids)==nrow(required))
for(path in paths) stopifnot(identical(digest::digest(file=path,algo='sha256'),implementation[[path]]))
sources[[file.path(parent,'inputs.json')]] <- digest::digest(file=file.path(parent,'inputs.json'),algo='sha256')
sources[[endpoint_path]] <- digest::digest(file=endpoint_path,algo='sha256')
sources[[high_path]] <- digest::digest(file=high_path,algo='sha256')
jsonlite::write_json(list(grids=grids,notes=dplyr::bind_rows(notes),source_hashes=sources,
 implementation_hashes=implementation,cutoffs=inputs$cutoffs,historical_admission=FALSE),
 file.path(out,'scores.json'),dataframe='rows',auto_unbox=TRUE,na='null',digits=16)
