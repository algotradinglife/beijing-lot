args <- commandArgs(TRUE)
py <- args[1]; out <- args[2]
stopifnot(!file.exists(file.path(out,'candidates.json')))
r_modules <- c('python_bridge','probability_exploration','fundamentals_home_away',
  'goal_distribution_experiment','fundamentals_score_diagnostic','fundamentals_score_shape',
  'fundamentals_high_margin','fundamentals_three_issue_experts','fundamentals_expert_coverage',
  'fundamentals_next_issue','fundamentals_ev_returns','fundamentals_market_comparison',
  'fundamentals_total_market','fundamentals_retraining','eight_issue_holdout','nowscore_query',
  'fundamentals_returns','fundamentals_selection_comparison','fundamentals_direct_score_returns',
  'eight_issue_returns','fundamentals_n_comparison','fundamentals_pure_parlay','fundamentals_draw_fusion',
  'fundamentals_draw_snapshot','fundamentals_signal_rate_projection')
for(p in r_modules)
  source(paste0('r/',p,'.R'))


base <- 'data/derived/fundamentals_417'
pred <- jsonlite::read_json(file.path(out,'endpoints.json'),simplifyVector=TRUE)$rows
high <- jsonlite::read_json(file.path(base,'consistent-experts-101-v1/high.json'),simplifyVector=TRUE)$rows |> dplyr::rename(issue=issue_code)
all <- list();all_cuts <- list();sources <- list()
implementation_paths <- c(paste0('r/',r_modules,'.R'),'scripts/prepare_integration_weight_candidates.R')
implementation_hashes <- as.list(stats::setNames(vapply(implementation_paths,digest::digest,character(1),file=TRUE,algo='sha256'),implementation_paths))
keys <- c('issue','slot','provider_id')
for(study in c('train-eight-test-eight-v2','cv-sixteen-test-sixteen-v1','cv-thirtytwo-test-sixteen-v1')) {
 path <- file.path(base,study,'predictions.json');old <- jsonlite::read_json(path,simplifyVector=TRUE)
 control <- old$selected; cuts <- control$cutoffs
 control$fixtures <- dplyr::semi_join(dplyr::filter(control$fixtures,scenario=='baseline'),pred,by=keys)
 control$scores <- dplyr::semi_join(dplyr::filter(control$scores,scenario=='baseline'),pred,by=keys)
 pp <- dplyr::semi_join(pred,control$fixtures,by=keys)
 for(weight in c(0,.1,.25,.5,.7,.75,1)) {
  pp$draw_probability <- (1-weight)*pp$baseline_draw+weight*pp$expert_draw
  adjusted <- signal_rate_score_choices(control,pp,high,cuts,.5)
  factors <- ev_candidate_factors(adjusted,old$market,py,getwd())
  factors$weight <- weight
  all[[paste(study,weight)]] <- dplyr::select(factors,dplyr::all_of(keys),weight,p_W,p_D,p_L,q_W,q_D,q_L)
  cat('PROJECTED',study,weight,'\n');flush.console()
 }
 all_cuts <- c(all_cuts,cuts)
 sources[[path]] <- digest::digest(file=path,algo='sha256')
}
stopifnot(!anyDuplicated(names(all_cuts)))
for(path in implementation_paths) stopifnot(identical(digest::digest(file=path,algo='sha256'),implementation_hashes[[path]]))
jsonlite::write_json(list(rows=dplyr::bind_rows(all),cutoffs=all_cuts,input_hashes=sources,implementation_hashes=implementation_hashes,
 endpoints_sha256=digest::digest(file=file.path(out,'endpoints.json'),algo='sha256'),
 high_sha256=digest::digest(file=file.path(base,'consistent-experts-101-v1/high.json'),algo='sha256')),
 file.path(out,'candidates.json'),dataframe='rows',auto_unbox=TRUE,na='null',digits=15)
