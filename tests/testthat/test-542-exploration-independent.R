testthat::test_that("scenario runner retains independently calculated depth, cost and epoch", {
 cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
 p <- tibble::tibble(fixture_id=rep(c("26098:A","26098:B"),each=3),outcome=rep(c("W","D","L"),2),probability=c(.5,.4,.1,.8,.15,.05))
 settings <- beidan::parlay_settings(); settings$n_legs <- 2L
 pool <- IndependentRankedPool(p,cutoff,settings,c(2L,1L))
 scenarios <- tibble::tibble(scenario_id=c("deep","shallow","empty"),pattern="dual",group_budget_cny=c(4,2,4),budget_cny=c(4,4,0),max_reuse=1L,max_overlap=0L,label=c("a","b","c"))
 x <- beidan::parlay_explore_portfolios(list(dual=pool),scenarios)
 testthat::expect_equal(x$summary$actual_coverage,c(.72,.4,0))
 testthat::expect_equal(x$summary$spent_cny,c(4,2,0))
 testthat::expect_equal(x$summary$unspent_cny,c(0,2,0))
 testthat::expect_identical(names(x$results),scenarios$scenario_id)
 testthat::expect_identical(x$summary$label,scenarios$label)
 testthat::expect_false(any(x$summary$ev_available))
 testthat::expect_true(all(is.na(x$summary$ev_net_cny[1:2])))
 testthat::expect_identical(x$cutoff,cutoff)
 bad <- pool; bad$cutoff$cutoff_utc <- cutoff$cutoff_utc+1
 testthat::expect_error(beidan::parlay_explore_portfolios(list(dual=bad),scenarios[0,]),"cutoff")
 later <- cutoff; later$cutoff_utc <- cutoff$cutoff_utc+3600
 rebuilt <- IndependentRankedPool(p,later,settings,c(2L,1L))
 testthat::expect_error(beidan::parlay_explore_portfolios(list(dual=pool,later=rebuilt),scenarios),"cutoff")
})

#' Read one actual lab code chunk for integration tests.
#' @param label Exact chunk label.
#' @return Parsed expressions from the current QMD, not a copied implementation.
ReadExplorationChunk <- function(label) {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  lines <- readLines(file.path(root,"quarto/parlay_combination_lab.qmd"))
  start <- match(paste0("#| label: ",label),lines)
  stopifnot(!is.na(start))
  finish <- which(seq_along(lines)>start & lines=="```")[[1]]
  return(parse(text=lines[seq.int(start+1L,finish-1L)]))
}

testthat::test_that("actual QMD requires explicit scenario and prefix selection", {
  env <- new.env(parent=globalenv())
  env$budget_comparison <- tibble::tibble(scenario_id=c("S001","S001"),
    prefix_groups=c(0L,1L),cost_cny=c(0,64))
  invisible(utils::capture.output(eval(ReadExplorationChunk("choose-scenario"),env)))
  testthat::expect_false(env$selection_is_explicit)
  testthat::expect_equal(nrow(env$selected_config),0L)
  invisible(utils::capture.output(eval(ReadExplorationChunk("refine-selected"),env)))
  testthat::expect_null(env$role_evaluation)
  env$params <- list(selected_scenario_id="S001",selected_prefix_groups=1L)
  invisible(utils::capture.output(eval(ReadExplorationChunk("choose-scenario"),env)))
  testthat::expect_true(env$selection_is_explicit)
  testthat::expect_equal(env$selected_config$cost_cny,64)
  env$params$selected_prefix_groups <- 0L
  testthat::expect_error(eval(ReadExplorationChunk("choose-scenario"),env))
  env$params <- list(selected_scenario_id="unknown",selected_prefix_groups=1L)
  testthat::expect_error(eval(ReadExplorationChunk("choose-scenario"),env))
  env$params <- list(selected_scenario_id="S001")
  testthat::expect_error(eval(ReadExplorationChunk("choose-scenario"),env))
})
