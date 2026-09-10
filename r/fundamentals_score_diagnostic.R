# Prepare all declared issue/variant distributions before evaluating any results.
# Flatten each issue's decision rows independently; differently sized issue
# lists are observations, never columns. Empty inputs keep a typed join schema.
# Input: sealed provenance list; output: one row per declared decision, no writes.
score_adjudication_table <- function(provenance) {
  rows <- lapply(provenance,function(p)dplyr::bind_rows(p$adjudications))
  dplyr::bind_rows(c(list(tibble::tibble(issue=character(),slot=integer(),exclude=logical())),unname(rows)))
}

# Caller sources python_bridge, probability_exploration, fundamentals_home_away
# and goal_distribution_experiment. No new statistical estimator lives here.
# Inputs: inventory list with issue, roster_path, response_paths, fixture_count,
# exact cutoffs; explicit fixed parameters; repo/interpreter/cache paths.
# Output: sealed in-memory descriptive experiments, gates and file/code hashes.
prepare_issue_score_models <- function(inventories, python, project_root, cache_dir,
    window, minimum, top_n, mixture_scales, mixture_weights, tail_tolerance) {
  issues <- vapply(inventories,`[[`,character(1),'issue')
  if (!length(issues) || anyDuplicated(issues)) stop('Unique declared issues required')
  integers <- c(window,minimum,top_n,vapply(inventories,`[[`,numeric(1),'fixture_count'))
  if (anyNA(integers) || any(!is.finite(integers)) || any(integers<1 | integers!=floor(integers))) stop('Positive integer counts required')
  module <- project_python_module('src.fundamentals_score_diagnostic',project_root,python,convert=FALSE)
  experiments <- list(); gates <- list(); provenance <- list(); scores <- list()
  for (input in inventories) {
    x <- reticulate::py_to_r(module$prepare_score_diagnostic(input$roster_path,
      input$response_paths,issue=input$issue,cutoffs=input$cutoffs,
      expected_fixture_count=as.integer(input$fixture_count),window=as.integer(window),
      minimum=as.integer(minimum),repository_root=project_root,cache_dir=cache_dir,
      adjudications=input$adjudications))
    baseline <- home_away_probabilities(x$windows,dplyr::bind_rows(x$handicaps),
      input$cutoffs,top_n,tail_tolerance)
    experiments[[input$issue]] <- goal_distribution_experiment(baseline,input$cutoffs,
      mixture_scales,mixture_weights,tail_tolerance)
    e <- experiments[[input$issue]]
    for (i in which(e$fixtures$status=='OK_DIAGNOSTIC')) {
      f <- e$fixtures[i,];key <- paste(f$slot,f$variant,sep='/')
      top <- utils::head(dplyr::arrange(e$grids[[key]],dplyr::desc(probability),home_goals+away_goals,home_goals),top_n)
      scores[[paste(input$issue,key,sep='/')]] <- dplyr::mutate(top,issue=input$issue,
        slot=f$slot,provider_id=f$provider_id,variant=f$variant,rank=seq_len(nrow(top)),.before=1)
    }
    gates[[input$issue]] <- dplyr::bind_rows(x$gates)
    provenance[[input$issue]] <- x[c('input_file_hashes','implementation_hashes','source_policy','adjudications','review_context','review_queue')]
  }
  files <- c('r/python_bridge.R','r/fundamentals_score_diagnostic.R',
    'r/fundamentals_home_away.R','r/probability_exploration.R','r/goal_distribution_experiment.R',
    'src/fundamentals_score_diagnostic.py','r/fundamentals_score_review.R')
  hashes <- vapply(file.path(project_root,files),digest::digest,character(1),file=TRUE,algo='sha256')
  score_template <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),variant=character(),
    rank=integer(),home_goals=integer(),away_goals=integer(),probability=double(),outcome=character())
  artifact <- list(experiments=experiments,scores=dplyr::bind_rows(c(list(score_template),scores)),
    coverage_choices=score_coverage_choices(experiments),
    provenance=provenance,implementation_hashes=stats::setNames(hashes,files),
    parameters=list(window=window,minimum=minimum,top_n=top_n,mixture_scales=mixture_scales,
      mixture_weights=mixture_weights,tail_tolerance=tail_tolerance),
    gates=dplyr::bind_rows(gates),historical_admission=FALSE)
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}

# Read published outcomes only after checking the sealed distributions. Exact
# issue/slot/provider joins are delegated to the existing evaluator. No tuning.
# Returns per-issue metric tables; never chooses a winning variant or pools
# repeated target fixtures as independent validation samples.
evaluate_issue_score_models <- function(models, inventories, python, project_root) {
  issues <- vapply(inventories,`[[`,character(1),'issue')
  if (anyDuplicated(issues) || !setequal(issues,names(models$experiments)) ||
      !identical(models$seal,digest::digest(models[c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')],algo='sha256'))) stop('Sealed model/issue mismatch')
  module <- project_python_module('src.fundamentals_home_away',project_root,python,convert=FALSE)
  summaries <- list(); fixtures <- list()
  for (input in inventories) {
    e <- models$experiments[[input$issue]]
    bindings <- models$provenance[[input$issue]]$input_file_hashes
    key <- names(bindings)[normalizePath(names(bindings),mustWork=FALSE)==normalizePath(input$roster_path)]
    if (length(key)!=1L || !identical(digest::digest(file=input$roster_path,algo='sha256'),bindings[[key]])) stop('Roster input changed after model preparation')
    labels <- reticulate::py_to_r(module$roster_observed_results(input$roster_path,
      issue=input$issue,slots=as.list(unique(e$fixtures$slot))))
    for (i in seq_along(labels)) for (k in c('actual_home','actual_away')) {
      if (is.null(labels[[i]][[k]])) labels[[i]][k] <- list(NA_integer_)
    }
    result <- evaluate_goal_distributions(e,dplyr::bind_rows(labels))
    summaries[[input$issue]] <- dplyr::mutate(result$summary,issue=input$issue,.before=1)
    fixtures[[input$issue]] <- dplyr::mutate(result$fixtures,issue=input$issue,.before=1)
  }
  stopifnot(identical(models$seal,digest::digest(models[c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')],algo='sha256')))
  list(summary=dplyr::bind_rows(summaries),fixtures=dplyr::bind_rows(fixtures),seal=models$seal)
}

# Fixed retrospective raw-baseline coverage rules; no labels or tuning. Inputs
# are the existing cutoff-bound experiments. W/D/L ties use that order; score
# ties use total then home goals. Returns identity-keyed choices, no stakes/ROI.
score_coverage_choices <- function(experiments) {
  rows <- list()
  template <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),
    rule=character(),selected=character(),main_choices=integer(),protect_home=integer(),
    protect_away=integer(),model_coverage=double())
  for (issue in names(experiments)) {
    e <- experiments[[issue]]
    if (!length(e$cutoffs) || !setequal(names(e$cutoffs),as.character(unique(e$fixtures$slot)))) stop('Coverage cutoff mismatch')
    for (i in which(e$fixtures$variant=='raw' & e$fixtures$status=='OK_DIAGNOSTIC')) {
      f <- e$fixtures[i,]; probs <- unlist(f[c('W','D','L')])
      if (anyNA(probs) || any(!is.finite(probs)) || any(probs<0) || abs(sum(probs)-1)>1e-10) stop('Invalid coverage probabilities')
      ranked <- names(probs)[order(-probs,seq_along(probs))]
      g <- dplyr::arrange(e$grids[[paste(f$slot,'raw',sep='/')]],dplyr::desc(probability),home_goals+away_goals,home_goals)
      for (rule in c('single','single_protect1','double','double_protect1','single_plus_draw_protect1')) {
        dirs <- switch(rule,single=ranked[1],single_protect1=ranked[1],double=ranked[1:2],
          double_protect1=ranked[1:2],single_plus_draw_protect1=unique(c(ranked[1],'D')))
        protection <- if (grepl('protect1$',rule)) utils::head(g[!g$outcome %in% dirs & g$probability>0,],1) else g[FALSE,]
        rows[[length(rows)+1L]] <- tibble::tibble(issue=issue,slot=as.integer(f$slot),provider_id=f$provider_id,
          rule=rule,selected=paste(dirs,collapse=','),main_choices=length(dirs),
          protect_home=if(nrow(protection)) as.integer(protection$home_goals) else NA_integer_,
          protect_away=if(nrow(protection)) as.integer(protection$away_goals) else NA_integer_,
          model_coverage=sum(probs[dirs])+sum(protection$probability))
      }
    }
  }
  dplyr::bind_rows(c(list(template),rows))
}

# Evaluate sealed diagnostic choices against already evaluated fixtures. Main
# and protection hits are disjoint; cancelled/unavailable rows never enter n.
# Returns per-fixture and per-issue/rule tables; no pooled sample or profitability.
score_coverage_summary <- function(choices, evaluation) {
  labels <- dplyr::filter(evaluation$fixtures,variant=='raw',scorable)
  if (anyDuplicated(choices[c('issue','slot','provider_id','rule')])) stop('Duplicate coverage choices')
  expected <- dplyr::distinct(labels,issue,slot,provider_id)
  actual <- dplyr::distinct(choices,issue,slot,provider_id)
  if (nrow(dplyr::anti_join(expected,actual,by=c('issue','slot','provider_id')))) stop('Missing coverage choices')
  rows <- dplyr::inner_join(choices,dplyr::select(labels,issue,slot,provider_id,actual_home,actual_away,handicap),
    by=c('issue','slot','provider_id'),relationship='many-to-one')
  net <- rows$actual_home-rows$actual_away+rows$handicap
  rows$actual_direction <- ifelse(net>0,'W',ifelse(net==0,'D','L'))
  rows$main_hit <- vapply(seq_len(nrow(rows)),function(i)rows$actual_direction[i] %in% strsplit(rows$selected[i],',',fixed=TRUE)[[1]],logical(1))
  rows$protect_hit <- !rows$main_hit & !is.na(rows$protect_home) & rows$actual_home==rows$protect_home & rows$actual_away==rows$protect_away
  rows$covered <- rows$main_hit | rows$protect_hit
  summary <- dplyr::summarise(dplyr::group_by(rows,issue,rule),n=dplyr::n(),
    main_hits=sum(main_hit),protection_adds=sum(protect_hit),covered_count=sum(covered),
    coverage=mean(covered),model_coverage=mean(model_coverage),average_main_choices=mean(main_choices),.groups='drop')
  list(fixtures=rows,summary=summary)
}
