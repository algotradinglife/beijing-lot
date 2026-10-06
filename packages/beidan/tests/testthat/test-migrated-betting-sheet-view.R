testthat::test_that("depth uses a single purchased ticket and complete denominator", {
 legs <- tibble::tibble(order=1L,ticket_id=rep(c("001","002"),each=2),
  fixture_id=rep(c("A","B"),2),outcome=c("W","W","D","D"))
 empty <- tibble::tibble(fixture_id=character(),actual_outcome=character())
 pending <- BettingSheetDepth(legs,empty)
 testthat::expect_equal(pending$best_hits,0)
 testthat::expect_equal(pending$total,2)
 testthat::expect_true(is.na(pending$winning_tickets))
 actual <- tibble::tibble(fixture_id=c("A","B"),actual_outcome=c("W","D"))
 final <- BettingSheetDepth(legs,actual)
 testthat::expect_equal(final$best_hits,1)
 testthat::expect_equal(final$observed,2)
 testthat::expect_equal(final$winning_tickets,0L)
 partial <- BettingSheetDepth(legs,actual[1,])
 testthat::expect_equal(partial$observed,1)
 testthat::expect_equal(partial$total,2)
 testthat::expect_true(is.na(partial$winning_tickets))
 actual$actual_outcome <- c("W","W")
 testthat::expect_equal(BettingSheetDepth(legs,actual)$winning_tickets,1L)
 testthat::expect_error(BettingSheetDepth(legs,dplyr::bind_rows(actual,actual)))
 testthat::expect_error(BettingSheetDepth(dplyr::bind_rows(legs,legs[1,]),actual))
 testthat::expect_error(BettingSheetDepth(legs[-1,],actual))
 actual$actual_outcome[1] <- "bad"
 testthat::expect_error(BettingSheetDepth(legs,actual))
 testthat::expect_error(BettingSheetDepth(legs[0,],empty))
})

testthat::test_that("group counts use surviving purchased tickets rather than the option union", {
 legs <- tibble::tibble(order=rep(1:3,each=4),ticket_id=rep(sprintf("%03d",1:6),each=2),
  fixture_id=rep(c("A","B"),6),outcome=c("W","W","D","D","W","D","D","W","L","L","L","D"))
 empty <- tibble::tibble(fixture_id=character(),actual_outcome=character())
 testthat::expect_identical(BettingSheetDepth(legs,empty)$group_status,rep("PENDING",3))
 partial <- tibble::tibble(fixture_id="A",actual_outcome="W")
 result <- BettingSheetDepth(legs,partial)
 testthat::expect_identical(result$group_status,c("PENDING","PENDING","DEAD"))
 testthat::expect_identical(result$viable_tickets,c(1L,1L,0L))
 final <- dplyr::bind_rows(partial,tibble::tibble(fixture_id="B",actual_outcome="D"))
 result <- BettingSheetDepth(legs,final)
 testthat::expect_identical(result$group_status,c("DEAD","HIT","DEAD"))
 testthat::expect_identical(result$winning_tickets,c(0L,1L,0L))
 testthat::expect_equal(sum(result$group_status=="DEAD")+sum(result$group_status=="HIT")+
  sum(result$group_status=="PENDING"),3L)
 # Both observed outcomes appear in group 1's option union, but no purchased
 # ticket matches both: it must be dead, including before a third leg is known.
 extended <- dplyr::bind_rows(legs,tibble::tibble(order=rep(1:3,each=2),
  ticket_id=sprintf("%03d",1:6),fixture_id="C",outcome="W"))
 testthat::expect_identical(BettingSheetDepth(extended,final)$group_status,c("DEAD","PENDING","DEAD"))
})
test_that("migrated view uses portable frozen research inputs and authoritative settlement", {
  f <- ResearchSheetFixture();x <- BuildBettingSheetView(f$frozen,f$prepared,"3")
  expect_equal(x$groups$theoretical,c(3,3,3));expect_equal(nrow(x$tickets),3)
  expect_identical(x$tickets,f$frozen$tickets[["3"]])
  expect_equal(x$depth$observed,c(0,0,0));expect_null(x$returns)
  expect_true(all(x$options$sp_raw==3))
  o <- AllocationObservation(f$evaluation)
  o$match_results$outcome <- "W";o$settlements$outcome <- "W"
  attr(o$settlements,"match_results") <- o$match_results
  y <- BuildBettingSheetView(f$frozen,f$prepared,"3",o$settlements,o$as_of)
  expect_equal(y$depth$winning_tickets,c(1L,1L,1L))
  expect_equal(y$returns$payout_cny,rep(6.5,3))
  expect_equal(tail(y$budget_results$final_net_cny,1),13.5)
  expect_identical(y$tickets,x$tickets)
  changed <- f$prepared;changed$projected$prematch_sp$quote_at[1] <- changed$decision_at
  expect_error(BuildBettingSheetView(f$frozen,changed,"3"))
  expect_error(BuildBettingSheetView(f$frozen,f$prepared,"wrong"))
})

test_that("combination depth uses full theoretical support, beyond bought prefix", {
  e <- AllocationFixture();o <- AllocationObservation(e)
  x <- beidan:::.BettingSheetCombinationDepth(e,o$match_results,o$as_of)
  expect_equal(x$theoretical,rep(3,3))
  expect_identical(x$winner_depth,c(2L,2L,3L))
  expect_true(all(e$group_selection$tickets==1L))
  empty <- beidan:::.BettingSheetCombinationDepth(e,match_typed_empty("match_results"))
  expect_true(all(is.na(empty$winner_depth)))
  expect_equal(nrow(beidan:::.BettingSheetCombinationDepth(AllocateParlayBudget(e,0),o$match_results,o$as_of)),0)
  later <- o$match_results;later$result_available_at <- o$as_of+1
  expect_true(all(is.na(beidan:::.BettingSheetCombinationDepth(e,later,o$as_of)$winner_depth)))
  expect_error(beidan:::.BettingSheetCombinationDepth(e,o$match_results),"as_of")
  expect_error(beidan:::.BettingSheetCombinationDepth(e,dplyr::bind_rows(o$match_results,o$match_results),o$as_of),"unique")
  f <- ResearchSheetFixture();obs <- AllocationObservation(f$evaluation)
  attr(obs$settlements,"match_results") <- obs$match_results
  v <- BuildBettingSheetView(f$frozen,f$prepared,"3",obs$settlements,obs$as_of)
  expect_identical(v$depth$winner_depth,c(2L,2L,3L))
  expect_equal(v$depth$theoretical,rep(3,3))
  eval_view <- BuildEvaluationBettingSheetView(e,AllocationCatalog(e),o)
  expect_identical(eval_view$depth$winner_depth,c(2L,2L,3L))
})

test_that("known structural misses give zero even before remaining results", {
  e <- AllocationFixture();s <- e$portfolio$settings
  m <- tibble::tibble(fixture_id=c("A:001","A:002","A:003"),win=.44,draw=.4,lose=.16)
  ranked <- rank_outcome_selections(prepare_outcome_selections(m),e$cutoff)
  pool <- parlay_construct_role_groups(ranked,s,2L,max_candidates=3L,prematch_sp=e$portfolio$prematch_sp)
  selected <- parlay_select_groups(pool,objective="coverage",budget_cny=6,group_budget_cny=2)$evaluation
  o <- AllocationObservation(e);o$match_results <- o$match_results[1,,drop=FALSE];o$match_results$outcome <- "L"
  x <- beidan:::.BettingSheetCombinationDepth(selected,o$match_results,o$as_of)
  expect_equal(x$theoretical,rep(2,3))
  expect_equal(x$winner_depth[match(selected$portfolio$role_legs$group_id[selected$portfolio$role_legs$fixture_id=="A:001"],x$group_id)],0L)
  expect_true(any(is.na(x$winner_depth)))
})

test_that("actual combination rank follows frozen uniform ranking when requested", {
  e <- AllocationFixture(2L);a <- AllocateParlayBudget(e,6,"equal",group_budget_cny=2,triple_ranking="uniform")
  o <- AllocationObservation(e);o$match_results$outcome <- c("L","W","D")
  x <- beidan:::.BettingSheetCombinationDepth(a,o$match_results,o$as_of)
  id <- a$portfolio$role_legs |> dplyr::group_by(group_id) |>
    dplyr::summarise(pair=setequal(fixture_id,c("A:001","A:002")),.groups="drop") |>
    dplyr::filter(pair) |> dplyr::pull(group_id)
  expect_length(id,1L)
  expect_equal(x$theoretical[x$group_id==id],9)
  expect_identical(x$winner_depth[x$group_id==id],7L)
})
