source('../../r/python_bridge.R')
source('../../r/probability_exploration.R')
source('../../r/fundamentals_home_away.R')
source('../../r/goal_distribution_experiment.R')
source('../../r/fundamentals_score_diagnostic.R')

test_that('two native issues reuse the same model/evaluator with sealed projections', {
  project <- normalizePath('../..'); python <- Sys.getenv('FUNDAMENTALS_PYTHON')
  expect_true(nzchar(python))
  work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE))
  fixtures <- list(list(issue='100101',root='../fixtures/fundamentals_three_cases',
    names=c('roster','003-titan','003-nowscore'),cutoffs='cutoffs.json',n=78L),
    list(issue='100102',root='../fixtures/fundamentals_multi_issue',
    names=c('100102-roster','100102-001-titan','100102-001-nowscore'),cutoffs='100102-cutoffs.json',n=43L))
  inventory <- list()
  for (f in fixtures) {
    paths <- character()
    for (name in f$names) {
      con <- gzfile(file.path(f$root,paste0(name,'.json.gz')),'rb')
      bytes <- readBin(con,'raw',n=20000000);close(con)
      path <- file.path(work,paste0(name,'.json'));writeBin(bytes,path);paths <- c(paths,path)
    }
    inventory[[f$issue]] <- list(issue=f$issue,fixture_count=f$n,roster_path=paths[1],
      response_paths=as.list(paths[-1]),cutoffs=jsonlite::read_json(file.path(f$root,f$cutoffs)))
  }
  args <- list(inventories=inventory,python=python,project_root=project,cache_dir=NULL,
    window=10L,minimum=10L,top_n=5L,mixture_scales=c(.7,1.3),mixture_weights=c(.5,.5),tail_tolerance=1e-10)
  models <- do.call(prepare_issue_score_models,args)
  expect_named(models$experiments,c('100101','100102'))
  expect_equal(nrow(models$gates),121L)
  expect_true(all(models$gates$status=='UNAVAILABLE_FOR_FITTING'))
  expect_equal(nrow(models$experiments[['100101']]$fixtures),312L)
  expect_equal(nrow(models$experiments[['100102']]$fixtures),172L)
  good <- dplyr::bind_rows(lapply(models$experiments,`[[`,'fixtures'))
  good <- dplyr::filter(good,status=='OK_DIAGNOSTIC')
  expect_equal(good$ordinary_W+good$ordinary_D+good$ordinary_L,rep(1,nrow(good)),tolerance=1e-10)
  expect_equal(good$W+good$D+good$L,rep(1,nrow(good)),tolerance=1e-10)
  original <- models
  evaluation <- evaluate_issue_score_models(models,inventory,python,project)
  expect_identical(models,original)
  expect_equal(nrow(evaluation$fixtures),484L)
  expect_setequal(unique(evaluation$summary$issue),c('100101','100102'))
  expect_true(all(models$scores$rank<=5))
  changed <- models;changed$scores$probability[1] <- 0
  expect_error(evaluate_issue_score_models(changed,inventory,python,project),'Sealed')
  changed <- models;changed$gates$status[1] <- 'ALLOWED'
  expect_error(evaluate_issue_score_models(changed,inventory,python,project),'Sealed')
  roster <- inventory[[1]]$roster_path
  original_bytes <- readBin(roster,'raw',n=20000000)
  writeBin(c(original_bytes,charToRaw('\n')),roster)
  expect_error(evaluate_issue_score_models(models,inventory,python,project),'Roster input changed')
  writeBin(original_bytes,roster)
  sparse_args <- args;sparse_args$window <- 100000L;sparse_args$minimum <- 100000L
  sparse <- do.call(prepare_issue_score_models,sparse_args)
  expect_equal(nrow(sparse$scores),0L)
  expect_type(sparse$scores$probability,'double')
  expect_equal(nrow(evaluate_issue_score_models(sparse,inventory,python,project)$summary),0L)
  expect_error(do.call(prepare_issue_score_models,modifyList(args,list(window=10.5))),'integer')
  duplicate <- args;duplicate$inventories <- rep(inventory[1],2)
  expect_error(do.call(prepare_issue_score_models,duplicate),'Unique')
  module <- project_python_module('src.fundamentals_home_away',project,python,convert=FALSE)
  expect_true(inherits(module,'python.builtin.module'))
  expect_error(project_python_module('src.fundamentals_home_away',project,python,convert=NA),'conversion')
  previous <- Sys.getenv('RETICULATE_PYTHON',unset=NA_character_)
  on.exit(if(is.na(previous)) Sys.unsetenv('RETICULATE_PYTHON') else Sys.setenv(RETICULATE_PYTHON=previous),add=TRUE)
  Sys.setenv(RETICULATE_PYTHON='/tmp/nonmatching-python')
  expect_error(project_python_module('src.fundamentals_home_away',project,python),'conflicts')
})

test_that('neutral history orientation keeps original rows and handles either venue', {
  rows <- list(list(history_id='a',home_id='H',away_id='X',home_goals=2,away_goals=1),
    list(history_id='b',home_id='Y',away_id='H',home_goals=0,away_goals=3))
  original <- rows
  h <- orient_goal_history(rows,'H','home'); a <- orient_goal_history(rows,'H','away')
  expect_identical(rows,original)
  expect_equal(vapply(h,`[[`,numeric(1),'home_goals'),c(2,3))
  expect_equal(vapply(h,`[[`,numeric(1),'away_goals'),c(1,0))
  expect_equal(vapply(a,`[[`,numeric(1),'away_goals'),c(2,3))
  expect_equal(goal_window_descriptor(h,'raw')$home_mean,2.5)
  expect_error(orient_goal_history(rows,'Z','home'),'identity')
  expect_error(orient_goal_history(rows,'H','bad'),'orientation')
  expect_equal(orient_goal_history(list(),'H','home'),list())
})

test_that('coverage rules retain double choices and correctly compute disjoint rates', {
  grid <- tibble::tibble(home_goals=c(1L,0L,2L),away_goals=c(0L,0L,0L),
    probability=c(.5,.3,.2),outcome=c('D','L','W'))
  f <- tibble::tibble(slot=1L,provider_id='001',variant='raw',status='OK_DIAGNOSTIC',W=.2,D=.5,L=.3)
  e <- list(fixtures=f,grids=list('1/raw'=grid),cutoffs=list('1'='2009-01-01T12:00:00+08:00'))
  choices <- score_coverage_choices(list(x=e))
  expect_equal(choices$main_choices[choices$rule=='double'],2L)
  expect_equal(choices$main_choices[choices$rule=='single_plus_draw_protect1'],1L)
  expect_equal(choices$model_coverage[choices$rule=='double_protect1'],1)
  expect_equal(choices$protect_home[choices$rule=='double_protect1'],2L)
  labels <- dplyr::mutate(f,issue='x',scorable=TRUE,actual_home=2L,actual_away=0L,handicap=-1L)
  result <- score_coverage_summary(choices,list(fixtures=labels))
  row <- dplyr::filter(result$summary,rule=='double_protect1')
  expect_equal(row$main_hits,0);expect_equal(row$protection_adds,1)
  expect_equal(row$covered_count,1);expect_equal(row$coverage,1)
  # Two observations catches summarise variable-shadowing (count is not rate).
  choices2 <- dplyr::bind_rows(choices,dplyr::mutate(choices,slot=2L,provider_id='002'))
  labels2 <- dplyr::bind_rows(labels,dplyr::mutate(labels,slot=2L,provider_id='002',actual_home=3L))
  result <- score_coverage_summary(choices2,list(fixtures=labels2))
  expect_equal(dplyr::filter(result$summary,rule=='double_protect1')$coverage,.5)
  expect_error(score_coverage_summary(dplyr::bind_rows(choices,choices),list(fixtures=labels)),'Duplicate')
  expect_error(score_coverage_summary(choices[FALSE,],list(fixtures=labels)),'Missing')
  e$fixtures$status <- 'OWNER_EXCLUDED'
  empty <- score_coverage_choices(list(x=e));expect_equal(nrow(empty),0L)
  expect_equal(nrow(score_coverage_summary(empty,list(fixtures=dplyr::mutate(labels,scorable=FALSE)))$summary),0L)
  e$cutoffs <- list();expect_error(score_coverage_choices(list(x=e)),'cutoff')
})

test_that('approved saved fixtures propagate neutral mode, sparse support and seal', {
  project <- normalizePath('../..');python <- Sys.getenv('FUNDAMENTALS_PYTHON')
  folder <- '../fixtures/fundamentals_adjudications';input <- jsonlite::read_json(file.path(folder,'inputs.json'))
  work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE))
  for (name in c('roster.json.gz',unlist(input$responses))) {
    con <- gzfile(file.path(folder,name),'rb');bytes <- readBin(con,'raw',n=20000000);close(con)
    writeBin(bytes,file.path(work,sub('.gz$','',name)))
  }
  inventory <- list(list(issue='100101',fixture_count=78L,roster_path=file.path(work,'roster.json'),
    response_paths=as.list(file.path(work,sub('.gz$','',unlist(input$responses)))),
    cutoffs=input$cutoffs,adjudications=input$adjudications))
  models <- prepare_issue_score_models(inventory,python,project,NULL,10L,10L,5L,c(.7,1.3),c(.5,.5),1e-10)
  e <- models$experiments[['100101']]
  expect_setequal(e$fixtures$slot[e$fixtures$variant=='raw' & e$fixtures$status=='OK_DIAGNOSTIC'],c(1,6,19,52,63))
  expect_equal(sum(e$fixtures$status=='OWNER_EXCLUDED'),48)
  expect_equal(e$fixtures$home_n[e$fixtures$slot==63 & e$fixtures$variant=='raw'],8)
  for (slot in c(1,52)) {
    w <- e$source_windows[[slot]]
    h <- orient_goal_history(w$home_window,w$home_team_id,'home')
    a <- orient_goal_history(w$away_window,w$away_team_id,'away')
    expected <- (mean(vapply(h,`[[`,numeric(1),'home_goals'))+mean(vapply(a,`[[`,numeric(1),'home_goals')))/2
    expect_equal(e$fixtures$lambda_home[e$fixtures$slot==slot & e$fixtures$variant=='raw'],expected)
  }
  evaluation <- evaluate_issue_score_models(models,inventory,python,project)
  expect_equal(evaluation$summary$n,rep(5L,4))
  expect_equal(score_coverage_summary(models$coverage_choices,evaluation)$summary$n,rep(5L,5))
  changed <- models;changed$coverage_choices$selected[1] <- 'W,D,L'
  expect_error(evaluate_issue_score_models(changed,inventory,python,project),'Sealed')
})

test_that('unequal per-issue decision counts form rows with an empty join schema', {
  p <- list('100101'=list(adjudications=list(list(issue='100101',slot=1L,history_mode='ALL_VENUES'),
    list(issue='100101',slot=2L,exclude=TRUE))),
    '100102'=list(adjudications=list(list(issue='100102',slot=1L,minimum=7L))),
    '100103'=list(adjudications=list()))
  result <- score_adjudication_table(p)
  expect_equal(nrow(result),3L)
  expect_equal(result$issue,c('100101','100101','100102'))
  expect_equal(result$slot,c(1L,2L,1L))
  expect_equal(result$exclude,c(NA,TRUE,NA))
  expect_equal(score_adjudication_table(list()),tibble::tibble(issue=character(),slot=integer(),exclude=logical()))
  expect_equal(nrow(score_adjudication_table(list(list(adjudications=NULL)))),0L)
})
