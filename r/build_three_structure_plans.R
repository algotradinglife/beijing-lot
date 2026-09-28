# Reproduce #543 from an explicit frozen real-input snapshot; no network or bets.
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=2L) stop('Usage: Rscript r/build_three_structure_plans.R INPUT_RDS OUTPUT_RDS')
devtools::load_all('packages/beidan',quiet=TRUE)
bundle <- readRDS(args[[1]])
epoch <- beidan::prepare_match_inputs(bundle$inputs,bundle$decision_at,
  bundle$market_policy,window_hours=bundle$window_hours)
projected <- beidan::estimate_match_probabilities(epoch,bundle$model_config)
settings <- beidan::parlay_settings(reset=TRUE)
scores <- beidan::parlay_role_scores(projected$probabilities,projected$cutoff)
patterns <- list(`3333222`=c(3L,3L,3L,3L,2L,2L,2L),
  `3322221`=c(3L,3L,2L,2L,2L,2L,1L),`3222221`=c(3L,2L,2L,2L,2L,2L,1L))
outputs <- list()
# One start offset per eligible fixture explores all offsets of the existing
# deterministic role constructor, without enumerating all possible fixture sets.
n_candidates <- as.integer(dplyr::n_distinct(projected$probabilities$fixture_id))
for (pattern in names(patterns)) {
  cat('Building',pattern,'with',n_candidates,'candidate offsets\n');flush.console()
  pool <- beidan::parlay_construct_role_groups(scores,projected$cutoff,
    settings=settings,pattern=patterns[[pattern]],n_candidates=n_candidates,
    probabilities=projected$probabilities,prematch_sp=epoch$prematch_sp)
  evaluated <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=bundle$group_budget_cny,
    budget_cny=bundle$budget_cny,constraints=bundle$constraints,improve=TRUE,
    improvement_policy=list(max_passes=1L,rank_window=3L,max_evaluations=8L))
  saveRDS(evaluated,paste0(args[[2]],'.',pattern,'.evaluated.rds'))
  sheet <- beidan::parlay_betting_sheet(evaluated$final,bundle$capture_selection$schedule)
  sheet$groups <- dplyr::arrange(sheet$groups,dplyr::desc(coverage_probability),group_id)
  outputs[[pattern]] <- list(evaluated=evaluated,sheet=sheet,pool=pool)
  print(sheet$groups)
  # Save checkpoints so a slow later structure never hides completed work.
  saveRDS(list(input_path=args[[1]],input_hash=digest::digest(file=args[[1]],algo='sha256'),
    bundle=bundle,epoch=epoch,projected=projected,outputs=outputs,
    n_candidates=n_candidates,patterns=patterns),args[[2]])
}
cat('ALL THREE COMPLETE\n')
