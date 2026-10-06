#' Raw two-fixture, explicit-cutoff backtest acceptance fixture
#' @return Label-free experiment arguments; exercised through public tests.
#' @noRd
BacktestFixture <- function() {
  fx <- epoch_fixture(2L)
  fx$inputs$prematch_sp <- tibble::tibble(fixture_id=rep(fx$inputs$fixtures$fixture_id,each=3L),
    outcome=rep(c("W","D","L"),2L),quote_at=fx$cutoff$cutoff_utc-60,
    sp_raw=rep(c(2,4,8),2L),source_url="fixture://raw")
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 4
  settings$sp_threshold <- .Machine$double.xmax
  round <- list(inputs=fx$inputs,cutoff=fx$cutoff,window_hours=c(4,28),market_policy=NULL)
  return(list(rounds=list(r1=round),strategies=list(bd=list(base="beidan",pattern=c(1L,1L))),
    settings=settings,group_budget_cny=2,max_candidates=1L))
}
#' Canonical outcome and price observation for the raw fixture
#' @param args BacktestFixture output.
#' @return Explicit postcutoff observation; no IO.
#' @noRd
BacktestObservation <- function(args) {
  r <- args$rounds$r1;c <- r$cutoff
  m <- tibble::tibble(issue_id=c$issue_id,fixture_id=r$inputs$fixtures$fixture_id,outcome="W",
    result_available_at=c$cutoff_utc+60,source_url="fixture://result")
  a <- m |> dplyr::transmute(issue_id,fixture_id,outcome,settled_sp=c(3,5),
    label_available_at=result_available_at,status="settled",source_url)
  return(list(match_results=m,settlements=a,as_of=c$cutoff_utc+120))
}
test_that("full public backtest reports hand-calculated actual and frozen money once", {
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args)
  obs <- BacktestObservation(args);before <- x
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  r <- y$round_summary
  expect_equal(r$n_tickets,1L);expect_equal(r$stake_cny,2)
  expect_equal(r$n_winning_tickets,1L)
  expect_equal(r$actual_payout_cny,2*.65*3*5)
  expect_equal(r$actual_net_cny,17.5)
  expect_equal(r$frozen_sp_payout_cny,2*.65*2*2)
  expect_equal(r$frozen_sp_net_cny,3.2)
  expect_identical(r$status,"COMPLETE")
  expect_equal(y$match_summary$hit_rate,rep(1,9))
  expect_equal(y$match_summary$n_resolved,rep(2L,9))
  expect_identical(x,before)
  z <- SummarizeCoverageAttribution(y)
  expect_identical(z$round_causes$status,"HIT")
  expect_equal(z$fixture_causes$structural_miss_groups,c(0,0))
  expect_identical(do.call(BuildProbabilityBacktest,x$receipt$input_snapshot),x)
  expect_identical(do.call(SummarizeProbabilityBacktest,y$receipt$input_snapshot),y)
})
test_that("missing prices preserve outcome hits and missing outcomes remain pending", {
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  obs$settlements <- match_typed_empty("settlements")
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  expect_equal(y$round_summary$n_winning_tickets,1)
  expect_equal(y$round_summary$n_pending_prices,1)
  expect_true(is.na(y$round_summary$actual_net_cny))
  expect_equal(y$round_summary$frozen_sp_payout_cny,5.2)
  obs$match_results$outcome[1] <- "L"
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  expect_equal(y$round_summary$actual_payout_cny,0)
  expect_equal(y$round_summary$actual_net_cny,-2)
  expect_identical(y$group_attributions$status,"STRUCTURE_MISS")
  z <- SummarizeCoverageAttribution(y)
  expect_equal(sum(z$fixture_causes$structural_miss_groups),1)
  obs$match_results <- obs$match_results[0,]
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  expect_equal(y$round_summary$n_pending_results,1)
  expect_true(is.na(y$round_summary$frozen_sp_net_cny))
  expect_true(all(is.na(y$match_summary$hit_rate)))
})
test_that("round identity, bases, fixed structures and thresholds remain separate", {
  args <- BacktestFixture();args$rounds$r2 <- args$rounds$r1
  args$rounds$r2$cutoff$cutoff_utc <- args$rounds$r1$cutoff$cutoff_utc+1
  args$rounds$r1$market_policy <- args$rounds$r2$market_policy <- list(euro=default_euro(),totals=default_totals())
  args$strategies <- list(bd=list(base="beidan",single_threshold=.45),
    dc=list(base="dc"),mixed=list(base="mixed",bd_weight=.75,pattern=c(3L,3L)))
  x <- do.call(BuildProbabilityBacktest,args)
  expect_length(x$cases,6)
  expect_identical(vapply(x$cases,`[[`,character(1),"round_id"),rep(c("r1","r2"),each=3))
  expect_identical(x$cases[[3]]$decision$adapted$pattern,c(3L,3L))
  obs <- BacktestObservation(args)
  y <- SummarizeProbabilityBacktest(x,list(r1=obs,r2=obs))
  expect_equal(nrow(y$round_summary),6)
  expect_equal(nrow(y$match_summary),54)
})
test_that("neutral and special labels never inflate prediction rates or infer refunds", {
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  obs$match_results <- obs$match_results[-1,]
  obs$settlements$outcome[1] <- "ALL";obs$settlements$status[1] <- "all_options_one";obs$settlements$settled_sp[1] <- 1
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  expect_equal(y$round_summary$actual_payout_cny,2*.65*5)
  expect_equal(y$round_summary$frozen_sp_payout_cny,2*.65*2)
  expect_true(all(y$match_summary$n_neutral==1 & y$match_summary$n_resolved==1))
  obs$settlements$status[1] <- "cancelled"
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  expect_identical(y$round_summary$status,"SPECIAL")
  expect_true(is.na(y$round_summary$actual_net_cny))
})
test_that("future visibility, malformed observations and receipt mutation fail predictably", {
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  future <- obs;future$as_of <- args$rounds$r1$cutoff$cutoff_utc+30
  y <- SummarizeProbabilityBacktest(x,list(r1=future))
  expect_equal(y$round_summary$excluded_future_rows,4)
  expect_true(is.na(y$round_summary$actual_net_cny))
  expect_error(SummarizeProbabilityBacktest(x,list(other=obs)),"round IDs")
  bad <- obs;bad$match_results$outcome[1] <- "D"
  expect_error(SummarizeProbabilityBacktest(x,list(r1=bad)),"conflict")
  bad <- obs;bad$as_of <- Sys.Date()
  expect_error(.BacktestLabels(bad,args$rounds$r1$cutoff),"as_of")
  bad <- obs;bad$match_results$result_available_at[1] <- NA
  expect_error(.BacktestLabels(bad,args$rounds$r1$cutoff))
  bad <- obs;bad$settlements$settled_sp[1] <- Inf
  expect_error(.BacktestLabels(bad,args$rounds$r1$cutoff),"SP")
  bad <- x;bad$cases[[1]]$decision$probability_base <- "dc"
  expect_error(.ValidateProbabilityBacktest(bad),"differs")
  bad <- x;bad$receipt$implementation_hash <- "old"
  expect_error(.ValidateProbabilityBacktest(bad),"differs")
  y <- SummarizeProbabilityBacktest(x,list(r1=obs));y$group_attributions$status <- "DEPTH_MISS"
  expect_error(SummarizeCoverageAttribution(y),"receipt")
  expect_error(BuildProbabilityBacktest(list(r1=args$rounds$r1),list(bad=list(base="bad")),args$settings,2))
  expect_error(.ValidateBacktestAxis(setNames(list(1,2),c("a","a"))))
})
test_that("empty experiments and no-bet rounds retain typed outputs and undefined ROI", {
  args <- BacktestFixture();args$rounds <- list()
  x <- do.call(BuildProbabilityBacktest,args)
  y <- SummarizeProbabilityBacktest(x,list())
  for(t in y[setdiff(names(y),"receipt")]) {expect_s3_class(t,"tbl_df");expect_equal(nrow(t),0)}
  expect_type(y$round_summary$stake_cny,"double")
  expect_type(y$group_attributions$winner_rank,"integer")
  z <- SummarizeCoverageAttribution(y)
  expect_equal(nrow(z$fixture_causes),0)
  args <- BacktestFixture();args$group_budget_cny <- 0
  y <- SummarizeProbabilityBacktest(do.call(BuildProbabilityBacktest,args),list(r1=BacktestObservation(args)))
  expect_identical(y$round_summary$status,"NO_BET")
  expect_true(is.na(y$round_summary$actual_roi))
  expect_equal(y$round_summary$actual_net_cny,0)
  expect_identical(SummarizeCoverageAttribution(y)$round_causes$status,"NO_BET")
})
test_that("future source changes preserve decisions and hidden outcomes preserve visible metrics", {
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args)
  altered <- args;future <- altered$rounds$r1$inputs$prematch_sp
  future$quote_at <- altered$rounds$r1$cutoff$cutoff_utc+1;future$sp_raw <- 100
  altered$rounds$r1$inputs$prematch_sp <- dplyr::bind_rows(altered$rounds$r1$inputs$prematch_sp,future)
  z <- do.call(BuildProbabilityBacktest,altered)
  expect_identical(x$cases[[1]]$decision$plan$evaluation$purchases,z$cases[[1]]$decision$plan$evaluation$purchases)
  expect_identical(x$cases[[1]]$decision$plan$selection,z$cases[[1]]$decision$plan$selection)
  expect_identical(x$cases[[1]]$decision$adapted$allocation,z$cases[[1]]$decision$adapted$allocation)
  obs <- BacktestObservation(args);obs$as_of <- args$rounds$r1$cutoff$cutoff_utc+30
  a <- SummarizeProbabilityBacktest(x,list(r1=obs))
  obs$match_results$outcome <- "L";obs$settlements$outcome <- "L";obs$settlements$settled_sp <- 999
  b <- SummarizeProbabilityBacktest(x,list(r1=obs))
  expect_identical(a$round_summary,b$round_summary)
  expect_identical(a$match_summary,b$match_summary)
  expect_identical(a$group_attributions,b$group_attributions)
})
test_that("depth participation does not blame masks and repeated fixture misses keep round IDs", {
  args <- BacktestFixture();args$strategies$bd$pattern <- c(3L,3L)
  x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  obs$match_results$outcome <- "L";obs$settlements$outcome <- "L"
  y <- SummarizeProbabilityBacktest(x,list(r1=obs));z <- SummarizeCoverageAttribution(y)
  expect_identical(z$round_causes$status,"DEPTH_MISS")
  expect_true(all(z$fixture_causes$structural_miss_groups==0))
  expect_true(all(z$fixture_causes$participating_depth_miss_groups==1))
  args <- BacktestFixture();args$rounds$r2 <- args$rounds$r1
  x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  obs$match_results$outcome[1] <- "L";obs$settlements$outcome[1] <- "L"
  z <- SummarizeCoverageAttribution(SummarizeProbabilityBacktest(x,list(r1=obs,r2=obs)))
  missed <- z$repeated_fixtures |> dplyr::filter(structural_miss_groups>0)
  expect_equal(nrow(missed),1L)
  expect_equal(missed$n_rounds,2L)
  expect_equal(missed$structural_miss_groups,2L)
  expect_equal(missed$rounds_with_structure_miss,2L)
})
test_that("shared winners remain covered elsewhere in round and fixture summaries", {
  args <- BacktestFixture();args$settings$issue_budget_cny <- 8;args$max_candidates <- NULL
  obs <- BacktestObservation(args)
  z <- SummarizeCoverageAttribution(SummarizeProbabilityBacktest(do.call(BuildProbabilityBacktest,args),list(r1=obs)))
  expect_true(any(z$round_causes$status=="COVERED_ELSEWHERE"))
  expect_true(any(z$fixture_causes$covered_elsewhere_groups>0))
  expect_false(any(z$fixture_causes$structural_miss_groups>0))
})
test_that("Top1 Top2 Top3 use resolved fixture denominators", {
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  obs$match_results$outcome <- c("D","L");obs$settlements$outcome <- c("D","L")
  y <- SummarizeProbabilityBacktest(x,list(r1=obs))
  r <- y$match_summary |> dplyr::filter(scope=="projected")
  expect_equal(r$hits,c(0L,1L,2L));expect_equal(r$hit_rate,c(0,.5,1))
  obs$match_results <- obs$match_results[-2,];obs$settlements <- obs$settlements[-2,]
  r <- SummarizeProbabilityBacktest(x,list(r1=obs))$match_summary |> dplyr::filter(scope=="projected")
  expect_equal(r$n_resolved,c(1L,1L,1L));expect_equal(r$n_pending,c(1L,1L,1L))
  expect_equal(r$hit_rate,c(0,1,1))
})
test_that("label zones, invalid empty-axis parameters and rebound decisions fail closed", {
  args <- BacktestFixture();obs <- BacktestObservation(args)
  bad <- obs;attr(bad$match_results$result_available_at,"tzone") <- NULL
  expect_error(.BacktestLabels(bad,args$rounds$r1$cutoff),"tz|timezone")
  args$rounds <- list();args$strategies$bd$pattern <- matrix(c(1,1))
  expect_error(do.call(BuildProbabilityBacktest,args),"plain")
  args <- BacktestFixture();x <- do.call(BuildProbabilityBacktest,args)
  x$cases[[1]]$arguments$strategy_id <- "foreign"
  bare <- x;bare$receipt <- NULL;x$receipt$output_hash <- rlang::hash(bare)
  expect_error(.ValidateProbabilityBacktest(x),"arguments")
})
test_that("unprojected DC fixtures are not pending outcomes in forecast denominators", {
  args <- BacktestFixture();args$strategies <- list(dc=list(base="dc"))
  args$rounds$r1$market_policy <- list(euro=default_euro(),totals=default_totals())
  args$rounds$r1$inputs$totals <- match_typed_empty("totals")
  x <- do.call(BuildProbabilityBacktest,args)
  y <- SummarizeProbabilityBacktest(x,list(r1=BacktestObservation(args)))
  expect_equal(y$match_summary$n_fixtures,rep(0L,9))
  expect_equal(y$match_summary$n_pending,rep(0L,9))
  expect_equal(nrow(y$fixture_results),0L)
})
test_that("equal probabilities rank W before D before L", {
  args <- BacktestFixture();args$rounds$r1$inputs$prematch_sp$sp_raw <- 3
  x <- do.call(BuildProbabilityBacktest,args);obs <- BacktestObservation(args)
  obs$match_results$outcome <- c("D","L");obs$settlements$outcome <- c("D","L")
  r <- SummarizeProbabilityBacktest(x,list(r1=obs))$match_summary |> dplyr::filter(scope=="projected")
  expect_equal(r$hits,c(0L,1L,2L))
})
