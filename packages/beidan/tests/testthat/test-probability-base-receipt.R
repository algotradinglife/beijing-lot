testthat::test_that("selected projections replay and reject altered decision artifacts", {
  fx <- epoch_fixture(2L)
  epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,
    list(euro=default_euro(),totals=default_totals()),probability_base="beidan")
  x <- SelectProbabilityBase(epoch)
  testthat::expect_true(.ValidateProbabilityBaseProjection(x))
  testthat::expect_identical(parlay_projection_context(x)$cutoff,x$cutoff)
  testthat::expect_identical(x$probability_base,"beidan")
  bare <- x;bare$probability_base_receipt <- NULL
  testthat::expect_identical(x$probability_base_receipt$output_hash,rlang::hash(bare))
  testthat::expect_identical(x$probability_base_receipt$input_hash,rlang::hash(epoch))
  testthat::expect_lt(x$probability_base_receipt$maximum_admitted_quote_or_status_at,epoch$cutoff$cutoff_utc)
  bad <- x;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1
  testthat::expect_error(parlay_projection_context(bad),"receipt")
  bad <- x;bad$cutoff$issue_id <- "wrong"
  testthat::expect_error(parlay_projection_context(bad),"receipt")
  bad <- x;bad$probability_base <- "dc"
  testthat::expect_error(parlay_projection_context(bad),"receipt")
  bad <- x;bad$probabilities$probability[1] <- .01
  testthat::expect_error(parlay_projection_context(bad),"output")
  bad <- x;bad$probability_base_receipt$implementation_hash <- "stale"
  testthat::expect_error(parlay_projection_context(bad),"implementation")
  bad <- x;bad$probability_base_receipt$input_snapshot$prematch_sp$sp_raw[1] <- 3
  testthat::expect_error(parlay_projection_context(bad),"source")
  bad <- x;bad$probability_base_receipt <- NULL
  testthat::expect_error(parlay_projection_context(bad),"required")
  bad <- x;bad$probability_base_receipt$cache_key <- "stale"
  testthat::expect_error(parlay_projection_context(bad),"replay")
  policy <- list(euro=default_euro(),totals=default_totals())
  dc <- SelectProbabilityBase(prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,policy,probability_base="dc"),"dc")
  mixed <- SelectProbabilityBase(prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,policy,probability_base="mixed"),"mixed",.75)
  testthat::expect_true(.ValidateProbabilityBaseProjection(dc))
  testthat::expect_true(.ValidateProbabilityBaseProjection(mixed))
  testthat::expect_false(identical(x$probability_base_receipt$cache_key,mixed$probability_base_receipt$cache_key))
  e2 <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc+1,probability_base="beidan")
  y <- SelectProbabilityBase(e2)
  testthat::expect_false(identical(x$probability_base_receipt$cache_key,y$probability_base_receipt$cache_key))
})

testthat::test_that("post-cutoff status cannot alter probability or support choices", {
  fx <- epoch_fixture(8L)
  epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,
    list(euro=default_euro(),totals=default_totals()),probability_base="beidan")
  x <- SelectProbabilityBase(epoch)
  later <- fx$inputs$match_status[1,]
  later$status <- "cancelled";later$status_at <- epoch$cutoff$cutoff_utc+1
  later$available_at <- epoch$cutoff$cutoff_utc+1
  changed <- fx$inputs;changed$match_status <- dplyr::bind_rows(changed$match_status,later)
  y <- SelectProbabilityBase(prepare_match_inputs(changed,fx$cutoff$cutoff_utc,probability_base="beidan"))
  testthat::expect_identical(x$probabilities,y$probabilities)
  testthat::expect_identical(x$fixtures,y$fixtures)
  mx <- tidyr::pivot_wider(x$probabilities,names_from=outcome,values_from=probability) |>
    dplyr::rename(win=W,draw=D,lose=L)
  my <- tidyr::pivot_wider(y$probabilities,names_from=outcome,values_from=probability) |>
    dplyr::rename(win=W,draw=D,lose=L)
  rx <- rank_outcome_selections(prepare_outcome_selections(mx,.45),x$cutoff)
  ry <- rank_outcome_selections(prepare_outcome_selections(my,.45),y$cutoff)
  testthat::expect_identical(rx,ry)
  ax <- AdaptOutcomeSelections(rx,7L);ay <- AdaptOutcomeSelections(ry,7L)
  testthat::expect_identical(ax,ay)
  settings <- parlay_constant_defaults(); settings$n_legs <- 7L; settings$issue_budget_cny <- 2048
  px <- parlay_construct_role_groups(ax$ranked,settings,ax$pattern,max_candidates=2L,prematch_sp=x$prematch_sp)
  py <- parlay_construct_role_groups(ay$ranked,settings,ay$pattern,max_candidates=2L,prematch_sp=y$prematch_sp)
  testthat::expect_identical(px,py)
  testthat::expect_gt(nrow(px$groups),0L)
  sx <- parlay_select_groups(px,objective="coverage",budget_cny=256,group_budget_cny=256,
    min_group_ev_cny=NULL,reuse_policy=list(max_reuse=NULL),overlap_policy=list(max_overlap=NULL))
  sy <- parlay_select_groups(py,objective="coverage",budget_cny=256,group_budget_cny=256,
    min_group_ev_cny=NULL,reuse_policy=list(max_reuse=NULL),overlap_policy=list(max_overlap=NULL))
  testthat::expect_identical(sx$selection,sy$selection)
  testthat::expect_identical(sx$evaluation$purchases,sy$evaluation$purchases)
})
