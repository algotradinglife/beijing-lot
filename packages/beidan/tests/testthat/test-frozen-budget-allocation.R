test_that("equal and probability buy independent hand-ranked tickets at common cost", {
  e <- AllocationFixture();before <- e
  expect_equal(nrow(e$purchases),3)
  a <- AllocateParlayBudget(e,8,"equal");b <- AllocateParlayBudget(e,8,"probability")
  expect_equal(a$allocation$tickets,c(2L,1L,1L));expect_equal(b$allocation$tickets,c(1L,2L,1L))
  expect_equal(sum(a$purchases$probability),1.41);expect_equal(sum(b$purchases$probability),1.44)
  expect_equal(a$summary$actual_coverage,1-(1-.7)*(1-.37)*(1-.34))
  expect_equal(b$summary$actual_coverage,1-(1-.4)*(1-.7)*(1-.34))
  expect_equal(a$summary$spent_cny,8);expect_equal(b$summary$spent_cny,8)
  expect_identical(e,before)
  expect_identical(AllocateParlayBudget(e,8,"equal"),a)
  expect_identical(a$portfolio$role_legs,e$portfolio$role_legs)
  expect_silent(.parlay_ranked_validate_evaluation(a))
  o <- AllocationObservation(e)
  y <- SummarizeBudgetAllocations(list(equal=a,probability=b),o)
  expect_equal(y$summary$winning_tickets,c(1,1))
  expect_equal(y$summary$actual_payout_cny,c(6.5,6.5))
  expect_equal(y$summary$actual_net_cny,c(-1.5,-1.5))
  expect_equal(y$summary$frozen_sp_net_cny,c(-4.1,-4.1))
  expect_identical(do.call(SummarizeBudgetAllocations,y$receipt$input_snapshot),y)
  o$match_results$outcome[1] <- o$settlements$outcome[1] <- "L"
  y <- SummarizeBudgetAllocations(list(equal=a,probability=b),o)
  expect_equal(y$summary$winning_tickets,c(0,1))
  expect_equal(y$summary$actual_net_cny,c(-8,-1.5))
})
test_that("depth diagnostic separates support from depth and gives hindsight gaps", {
  e <- AllocationFixture();a <- AllocateParlayBudget(e,6)
  o <- AllocationObservation(e);x <- DiagnoseParlayDepth(a,o$match_results,o$as_of)
  expect_true(all(x$groups$status=="DEPTH_MISS"))
  expect_equal(x$groups$winner_rank,c(3L,2L,2L))
  expect_equal(x$groups$unbought_tickets_before_winner,c(2L,1L,1L))
  expect_equal(x$groups$best_hits,c(0,0,0));expect_equal(x$groups$observed,c(1,1,1))
  expect_true(all(x$groups$structural_misses==0L))
  o$match_results <- o$match_results[0,]
  expect_true(all(DiagnoseParlayDepth(a,o$match_results,o$as_of)$groups$status=="PENDING"))
  a <- AllocateParlayBudget(e,2)
  x <- DiagnoseParlayDepth(a,o$match_results,o$as_of)
  expect_equal(sum(x$groups$status=="NO_PURCHASE"),2)
})
test_that("caps rounding support exhaustion and empty decisions preserve schemas", {
  e <- AllocationFixture()
  a <- AllocateParlayBudget(e,7,"equal",2)
  expect_equal(a$allocation$tickets,c(1L,1L,1L));expect_equal(a$summary$unspent_cny,1)
  a <- AllocateParlayBudget(e,100,"probability")
  expect_equal(nrow(a$purchases),9);expect_equal(a$summary$spent_cny,18)
  expect_equal(a$summary$actual_coverage,1)
  zero <- AllocateParlayBudget(e,0)
  expect_equal(nrow(zero$purchases),0);expect_silent(.parlay_ranked_validate_evaluation(zero))
  expect_equal(nrow(zero$allocation),3)
  y <- SummarizeBudgetAllocations(list(zero=zero),AllocationObservation(e))
  expect_equal(y$summary$actual_net_cny,0);expect_true(is.na(y$summary$actual_roi))
  expect_identical(y$summary$status,"NO_BET")
  empty <- parlay_select_groups(e$portfolio,objective="coverage",budget_cny=0)$evaluation
  a <- AllocateParlayBudget(empty,10)
  expect_equal(nrow(a$allocation),0);expect_type(a$purchases$rank,"integer")
  expect_silent(.parlay_ranked_validate_evaluation(a))
})
test_that("overlapping groups deduplicate refill and preserve physical masks", {
  e <- AllocationFixture(2L)
  a <- AllocateParlayBudget(e,30,"equal");b <- AllocateParlayBudget(e,30,"probability")
  for(x in list(a,b)) {
    expect_false(anyDuplicated(x$purchases$ticket_id)>0)
    expect_equal(sum(x$purchases$cost_cny),30)
    expect_silent(.parlay_ranked_validate_evaluation(x))
    expect_true(all(x$purchases$group_id %in% e$purchases$group_id))
  }
  # Full support contains 27 unique physical tickets across the three fixture pairs.
  full <- AllocateParlayBudget(e,100)
  expect_equal(nrow(full$purchases),27)
})
test_that("invalid budgets identities cutoff and rebound ledgers fail closed", {
  e <- AllocationFixture();a <- AllocateParlayBudget(e,8)
  expect_error(AllocateParlayBudget(e,NULL),"finite")
  expect_error(AllocateParlayBudget(e,-1))
  expect_error(AllocateParlayBudget(e,matrix(8)))
  expect_error(AllocateParlayBudget(e,Inf))
  expect_error(AllocateParlayBudget(e,8,"wrong"))
  expect_error(AllocateParlayBudget(a,8),"original")
  bad <- a;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1
  expect_error(.parlay_ranked_validate_evaluation(bad),"cutoff")
  bad <- a;bad$receipt$selection_policy$source_hash <- "wrong"
  expect_error(.parlay_ranked_validate_evaluation(bad),"source")
  bad <- a;bad$receipt$selection_policy$method <- "probability"
  expect_error(.parlay_ranked_validate_evaluation(bad),"replay")
  expect_error(SummarizeBudgetAllocations(list(a=a,b=AllocateParlayBudget(e,10)),AllocationObservation(e)),"same")
  expect_error(SummarizeBudgetAllocations(list(),AllocationObservation(e)))
})
test_that("visible outcomes missing SP and future labels do not alter decisions", {
  e <- AllocationFixture();a <- AllocateParlayBudget(e,8,"probability");o <- AllocationObservation(e)
  o$settlements <- match_typed_empty("settlements")
  y <- SummarizeBudgetAllocations(list(a=a),o)
  expect_equal(y$summary$winning_tickets,1);expect_equal(y$summary$pending_prices,1)
  expect_true(is.na(y$summary$actual_net_cny));expect_equal(y$summary$frozen_sp_net_cny,-4.1)
  o$as_of <- e$cutoff$cutoff_utc+30
  x <- SummarizeBudgetAllocations(list(a=a),o)
  o$match_results$outcome <- "W"
  expect_identical(x$summary,SummarizeBudgetAllocations(list(a=a),o)$summary)
  expect_identical(a,AllocateParlayBudget(e,8,"probability"))
  # A newly observed quote after cutoff is never admitted to funding.
  original <- e$portfolio$prematch_sp
  later <- original;later$quote_at <- e$cutoff$cutoff_utc+1;later$sp_raw <- 100
  m <- tibble::tibble(fixture_id=c("A:001","A:002","A:003"),win=c(.4,.37,.34),draw=c(.3,.33,.33),lose=c(.3,.3,.33))
  expect_error(parlay_construct_role_groups(rank_outcome_selections(prepare_outcome_selections(m),e$cutoff),
    e$portfolio$settings,3L,max_candidates=3L,prematch_sp=dplyr::bind_rows(original,later)),"strictly before")
})
test_that("missing frozen prices do not hide confirmed outcome wins or fabricate cash", {
  e <- AllocationFixture();p <- e$portfolio
  c <- e$cutoff
  m <- tibble::tibble(fixture_id=c("A:001","A:002","A:003"),win=c(.4,.37,.34),draw=c(.3,.33,.33),lose=c(.3,.3,.33))
  p <- parlay_construct_role_groups(rank_outcome_selections(prepare_outcome_selections(m),c),
    p$settings,3L,max_candidates=3L,prematch_sp=match_typed_empty("prematch_sp"))
  e <- parlay_select_groups(p,objective="coverage",budget_cny=20,group_budget_cny=2)$evaluation
  a <- AllocateParlayBudget(e,8,"probability");o <- AllocationObservation(e)
  y <- SummarizeBudgetAllocations(list(a=a),o)
  expect_equal(y$summary$winning_tickets,1)
  expect_equal(y$summary$actual_net_cny,-1.5)
  expect_true(is.na(y$summary$frozen_sp_net_cny))
  o$settlements <- match_typed_empty("settlements")
  y <- SummarizeBudgetAllocations(list(a=a),o)
  expect_equal(y$summary$pending_prices,1)
  expect_true(is.na(y$summary$actual_net_cny))
  bad <- a;bad$allocation$tickets[1] <- 200L
  expect_error(.parlay_ranked_validate_evaluation(bad),"summary")
})
test_that("special settlements never infer a refund and future outcomes remain pending", {
  e <- AllocationFixture();a <- AllocateParlayBudget(e,8);o <- AllocationObservation(e)
  o$settlements$status[1] <- "cancelled";o$settlements$outcome[1] <- "ALL"
  o$match_results <- o$match_results[-1,]
  y <- SummarizeBudgetAllocations(list(a=a),o)
  expect_identical(y$summary$status,"SPECIAL")
  expect_true(is.na(y$summary$actual_net_cny))
  o <- AllocationObservation(e);o$as_of <- e$cutoff$cutoff_utc+30
  y <- SummarizeBudgetAllocations(list(a=a),o)
  expect_equal(y$summary$pending_results,4)
  expect_true(is.na(y$summary$frozen_sp_net_cny))
})
