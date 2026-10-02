# Direct driver tests keep the initial greedy selection explicit.
role_driver_case <- function(empty = FALSE, optimal = FALSE) {
  cutoff <- list(issue_id = "26098", cutoff_utc = lubridate::ymd_hms("2026-09-26 12:00:00", tz = "UTC"))
  p <- tibble::tibble(fixture_id = rep(paste0("26098:", 1:4), each = 3),
    outcome = rep(c("W", "D", "L"), 4),
    probability = c(.5,.49,.01,.7,.28,.02,.85,.1,.05,.8,.15,.05))
  if (empty) p <- p[0, ]
  settings <- parlay_settings(); settings$n_legs <- 2L
  pool <- parlay_construct_role_groups(parlay_role_scores(p, cutoff), cutoff,
    settings, c(2L,1L), 2L, p)
  if (!empty) {
    ids <- if (optimal) c("26098:1","26098:3","26098:2","26098:4") else
      c("26098:1","26098:4","26098:2","26098:3")
    legs <- pool$role_legs; legs$fixture_id <- ids
    legs <- beidan:::.parlay_role_refresh_masks(legs,p)
    pool <- beidan:::.parlay_role_with_legs(pool,legs)
  }
  constraints <- list(max_reuse = 1L, max_overlap = 0L)
  packages <- beidan:::.parlay_role_packages(pool,p,pool$prematch_sp,cutoff,4,"probability")
  selected <- beidan:::.parlay_role_select(packages$packages,packages$stack,2,8,
    constraints,packages$fixture_sets)
  return(list(portfolio=pool, initial_purchases=selected$new_purchases,
    initial_value=beidan:::.parlay_role_objective(selected$new_purchases,"probability"),
    initial_selected_ids=selected$selected_ids,initial_selection=selected$selection,
    probabilities=p,prematch_sp=pool$prematch_sp,cutoff=cutoff,objective="probability",
    group_budget_cny=4,budget_cny=8,constraints=constraints,
    policy=list(max_passes=2L,rank_window=3L,max_evaluations=60L),improve=TRUE))
}

test_that("driver disabled returns the exact initial state without attempts", {
  args <- role_driver_case(); args$improve <- FALSE
  x <- do.call(beidan:::.parlay_role_improve_portfolio,args)
  expect_identical(x$purchases,args$initial_purchases)
  expect_identical(x$portfolio,args$portfolio)
  expect_identical(x$selection,args$initial_selection)
  expect_identical(x$evaluations,0L)
  expect_identical(x$passes_run,0L)
  expect_identical(x$changes,beidan:::.parlay_role_eval_empty("changes"))
})

test_that("driver accepts first gain and agrees with evaluator integration", {
  args <- role_driver_case(); before <- rlang::hash(args$portfolio)
  x <- do.call(beidan:::.parlay_role_improve_portfolio,args)
  y <- parlay_evaluate_portfolio(args$portfolio,group_budget_cny=4,budget_cny=8,
    constraints=args$constraints,improvement_policy=args$policy)
  expect_equal(args$initial_value,1.625)
  expect_equal(x$value,1.6255)
  expect_identical(x$changes,y$changes)
  expect_identical(x$selection,y$selection)
  expect_identical(x$evaluations,y$diagnostics$evaluations)
  expect_identical(x$passes_run,y$diagnostics$passes_run)
  expect_identical(rlang::hash(args$portfolio),before)
  expect_true(all(x$changes$delta > 0))
  args$policy$max_passes <- 1L
  first <- do.call(beidan:::.parlay_role_improve_portfolio,args)
  expect_identical(nrow(first$changes),1L)
  expect_identical(first$changes,x$changes[1,])
})

test_that("driver stops for no improvement and respects attempt cap", {
  args <- role_driver_case(optimal=TRUE)
  x <- do.call(beidan:::.parlay_role_improve_portfolio,args)
  expect_identical(nrow(x$changes),0L)
  expect_identical(x$passes_run,1L)
  expect_identical(x$purchases,args$initial_purchases)
  args <- role_driver_case(); args$policy$max_evaluations <- 1L
  limited <- do.call(beidan:::.parlay_role_improve_portfolio,args)
  expect_identical(limited$evaluations,1L)
  expect_identical(limited$passes_run,1L)
})

test_that("empty driver is safe and empty public result keeps early-return semantics", {
  args <- role_driver_case(empty=TRUE)
  x <- do.call(beidan:::.parlay_role_improve_portfolio,args)
  expect_identical(x$purchases,args$initial_purchases)
  expect_identical(nrow(x$changes),0L)
  expect_identical(x$evaluations,0L)
  expect_identical(x$passes_run,1L)
  y <- parlay_evaluate_portfolio(args$portfolio,constraints=args$constraints)
  expect_identical(y$diagnostics$passes_run,0L)
  expect_identical(y$diagnostics$evaluations,0L)
  bad <- args$portfolio; bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc + 1
  expect_error(parlay_evaluate_portfolio(bad,constraints=args$constraints),"cutoff")
  bad <- args$portfolio; bad$cutoff_hash <- NULL
  expect_error(parlay_evaluate_portfolio(bad,constraints=args$constraints),"cutoff")
})
