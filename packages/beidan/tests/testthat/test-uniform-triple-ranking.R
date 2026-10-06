test_that("uniform triple scoring preserves true valuation and replays", {
  e <- AllocationFixture(2L); before <- rlang::hash(e)
  p <- .parlay_ranked_validate_evaluation(e)
  s <- .PrepareRankedFunding(p,12)$spaces[[1]]
  b <- p$legs |> dplyr::filter(group_id==unique(p$legs$group_id)[1])
  u <- .UniformTripleRanking(s,b,p$probabilities)
  expect_identical(u$ranked$ticket_id,sort(s$ranked$ticket_id))
  expect_equal(dplyr::arrange(u$ranked,ticket_id)$probability,
               dplyr::arrange(s$ranked,ticket_id)$probability)
  a <- AllocateParlayBudget(e,20,group_budget_cny=12,triple_ranking="uniform")
  expect_silent(.parlay_ranked_validate_evaluation(a))
  expect_identical(rlang::hash(e),before)
  expect_equal(nrow(a$purchases),10L)
  expect_equal(dplyr::n_distinct(a$purchases$ticket_id),10L)
  expect_identical(a$portfolio$probabilities,e$portfolio$probabilities)
  expect_error(AllocateParlayBudget(e,8,triple_ranking="other"))
  expect_error(AllocateParlayBudget(e,8,triple_ranking=NULL))
  z <- AllocateParlayBudget(e,0,triple_ranking="uniform")
  expect_equal(nrow(z$purchases),0)
  expect_silent(.parlay_ranked_validate_evaluation(z))
  a$receipt$selection_policy$triple_ranking <- "beidan"
  expect_error(.parlay_ranked_validate_evaluation(a),"replay|binding")
})
test_that("only actual triples receive uniform weights, including zero mass", {
  e <- AllocationFixture(2L); p <- .parlay_ranked_validate_evaluation(e)
  s <- .PrepareRankedFunding(p,12)$spaces[[1]]
  b <- p$legs |> dplyr::filter(group_id==unique(p$legs$group_id)[1])
  b$n_outcomes[1] <- 2L
  pr <- p$probabilities
  pr$probability[pr$fixture_id==b$fixture_id[2]] <- c(0,0,1)
  u <- .UniformTripleRanking(s,b,pr)
  score <- s$tickets$ticket_legs |>
    dplyr::filter(fixture_id==b$fixture_id[1]) |>
    dplyr::left_join(pr,by=c("fixture_id","outcome"),relationship="many-to-one") |>
    dplyr::arrange(dplyr::desc(probability),ticket_id)
  expect_identical(u$ranked$ticket_id,score$ticket_id)
  expect_false(anyNA(u$ranked$probability))
  b$n_outcomes[] <- 2L
  expect_equal(.UniformTripleRanking(s,b,p$probabilities)$ranked,s$ranked)
})
