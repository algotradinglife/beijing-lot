# PI arithmetic and boundary expectations for #537.
testthat::test_that("candidate generation is independent of all budget settings", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=sprintf("26098:%02d",1:18),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.6,.3,.1),18))
  settings <- beidan::parlay_settings();settings$n_legs<-7L;settings$issue_budget_cny<-128
  scores <- beidan::parlay_role_scores(p,cutoff)
  x <- beidan::parlay_construct_role_groups(scores,cutoff,settings,
    pattern=c(3L,2L,2L,2L,2L,2L,1L),n_candidates=8L,probabilities=p)
  settings$issue_budget_cny<-4096
  y <- beidan::parlay_construct_role_groups(scores,cutoff,settings,
    pattern=c(3L,2L,2L,2L,2L,2L,1L),n_candidates=8L,probabilities=p)
  testthat::expect_equal(x$role_legs,y$role_legs)
  testthat::expect_equal(x$groups,y$groups)
  testthat::expect_gt(nrow(x$groups),1L)
  legs <- x$role_legs
  testthat::expect_false(any(duplicated(legs[c("group_slot","fixture_id")])))
  testthat::expect_gt(max(table(legs$fixture_id)),1L)
  candidate_hash <- rlang::hash(x)
  altered <- x
  altered$probabilities$probability <- rep(c(.1,.3,.6),18)
  testthat::expect_error(beidan::parlay_evaluate_portfolio(altered,group_budget_cny=128,
    budget_cny=1024,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE),
    "probabilities")
  result <- beidan::parlay_evaluate_portfolio(x,
    group_budget_cny=128,budget_cny=1024,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)
  purchased_legs <- result$final$plan$group_legs |>
    dplyr::filter(group_id %in% result$final$funded$purchases$group_id)
  testthat::expect_lte(max(c(0L,table(purchased_legs$fixture_id))),1L)
  testthat::expect_lte(sum(result$final$funded$purchases$stake_cny),1024)
  testthat::expect_identical(rlang::hash(x),candidate_hash)
  testthat::expect_true(any(!result$selection$selected))
  relaxed <- beidan::parlay_evaluate_portfolio(x,
    group_budget_cny=128,budget_cny=1024,constraints=list(max_reuse=8L,max_overlap=7L),improve=FALSE)
  testthat::expect_equal(sum(relaxed$final$funded$purchases$stake_cny),nrow(x$groups)*128)
  testthat::expect_gt(sum(relaxed$final$funded$purchases$stake_cny),settings$unit_cny*64)

})

testthat::test_that("3222221 obeys exact purchase depths, support ceiling and whole-package affordability", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=sprintf("26098:%02d",1:7),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.6,.3,.1),7))
  settings <- beidan::parlay_settings();settings$n_legs<-7L
  # A single candidate isolates ticket depth from candidate choice.
  x <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,settings,
    pattern=c(3L,2L,2L,2L,2L,2L,1L),n_candidates=1L,probabilities=p)
  repeated <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,settings,
    pattern=c(3L,2L,2L,2L,2L,2L,1L),n_candidates=10L,probabilities=p)
  keys <- vapply(split(repeated$role_legs,repeated$role_legs$group_slot),
    function(g) paste(sort(paste(g$fixture_id,g$role)),collapse="|"),character(1))
  testthat::expect_false(anyDuplicated(keys)>0L)
  for (i in seq_along(c(128,160,192,300))) {
    cap <- c(128,160,192,300)[i]
    result <- beidan::parlay_evaluate_portfolio(x,
      group_budget_cny=cap,budget_cny=1000,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)
    testthat::expect_equal(nrow(result$final$funded$purchases),c(64,80,96,96)[i])
    testthat::expect_equal(sum(result$final$funded$purchases$stake_cny),c(128,160,192,192)[i])
    testthat::expect_equal(tail(result$metrics$unspent_cny,1),1000-c(128,160,192,192)[i])
    # Independently enumerate the fixed 3 x 2^5 x 1 support (no production enumerator).
    grid <- expand.grid(c(.6,.3,.1),c(.6,.3),c(.6,.3),c(.6,.3),c(.6,.3),c(.6,.3),.6)
    mass <- sort(apply(grid,1,prod),decreasing=TRUE)
    testthat::expect_equal(tail(result$metrics$expected_winning_tickets,1),sum(head(mass,c(64,80,96,96)[i])))
  }
  too_small <- beidan::parlay_evaluate_portfolio(x,
    group_budget_cny=192,budget_cny=191,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(too_small$final$funded$purchases),0L)
  testthat::expect_equal(tail(too_small$metrics$unspent_cny,1),191)
  fits <- beidan::parlay_evaluate_portfolio(x,
    group_budget_cny=300,budget_cny=192,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(fits$final$funded$purchases),96L)
})

testthat::test_that("selected result retains valid SP values and the current decision ledger", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=sprintf("26098:%02d",1:4),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.7,.2,.1),4))
  settings <- beidan::parlay_settings();settings$n_legs<-2L;settings$issue_budget_cny<-8
  x <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,settings,
    pattern=c(2L,1L),n_candidates=4L,probabilities=p)
  sp <- dplyr::mutate(dplyr::select(p,fixture_id,outcome),quote_at=cutoff$cutoff_utc-60,
    sp_raw=12,source_url="fixture")
  x <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,settings,
    pattern=c(2L,1L),n_candidates=4L,probabilities=p,prematch_sp=sp)
  first <- beidan::parlay_evaluate_portfolio(x,group_budget_cny=4,budget_cny=8,
    constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE,objective="ev")
  testthat::expect_gt(nrow(first$final$funded$purchases),0L)
  testthat::expect_true(all(is.finite(first$final$summary$tickets$ev_net)))
  testthat::expect_equal(first$final$summary$tickets$ev_net,
    first$final$summary$tickets$probability_mass*2*.65*4.5^2-2)
  testthat::expect_true(all(unique(first$final$funded$purchases$group_id) %in% names(first$final$history$fixture_sets)))
  testthat::expect_identical(first$final$prematch_sp, sp)
  testthat::expect_equal(first$final$history$purchases, first$final$funded$purchases)
})

testthat::test_that("changing purchase depth reranks candidate packages", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(paste0("26098:",LETTERS[1:4]),each=3),
    outcome=rep(c("W","D","L"),4),probability=c(.90,.06,.04,.55,.44,.01,.80,.10,.10,.50,.45,.05))
  settings <- beidan::parlay_settings();settings$n_legs<-2L
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,settings,
    pattern=c(2L,1L),n_candidates=4L,probabilities=p)
  shallow <- beidan::parlay_evaluate_portfolio(pool,
    group_budget_cny=2,budget_cny=2,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)
  deep <- beidan::parlay_evaluate_portfolio(pool,
    group_budget_cny=4,budget_cny=4,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)
  testthat::expect_equal(tail(shallow$metrics$expected_winning_tickets,1),.90*.80)
  testthat::expect_equal(tail(deep$metrics$expected_winning_tickets,1),(.55+.44)*.90)
  testthat::expect_setequal(shallow$final$plan$group_legs$fixture_id,c("26098:A","26098:C"))
  testthat::expect_setequal(deep$final$plan$group_legs$fixture_id,c("26098:A","26098:B"))
})

testthat::test_that("shared physical tickets are deduplicated before package affordability", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=c("26098:A","26098:B"),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.6,.3,.1),2))
  settings <- beidan::parlay_settings();settings$n_legs<-2L
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,settings,
    pattern=c(2L,1L),n_candidates=2L,probabilities=p)
  result <- beidan::parlay_evaluate_portfolio(pool,
    group_budget_cny=4,budget_cny=6,constraints=list(max_reuse=2L,max_overlap=2L),improve=FALSE)
  # Packages {WW,DW} and {WW,WD}; the second costs only two additional yuan.
  testthat::expect_equal(nrow(result$tickets),3L)
  testthat::expect_equal(sum(result$final$funded$purchases$stake_cny),6)
  testthat::expect_equal(sum(result$selection$selected),2L)
  testthat::expect_equal(sort(result$selection$package_cost_cny[result$selection$selected]),c(2,4))
  testthat::expect_equal(tail(result$metrics$expected_winning_tickets,1),.36+.18+.18)
  testthat::expect_false(anyDuplicated(result$tickets$ticket_id)>0L)
  testthat::expect_equal(nrow(result$final$funded$funded),3L)
  testthat::expect_equal(result$final$constants$issue_budget_cny,6)
  testthat::expect_equal(result$final$config$max_reuse,2L)
  testthat::expect_equal(result$final$config$max_overlap,2L)
  schedule <- tibble::tibble(fixture_key=c("26098:A","26098:B"),slot=1:2,
    home_name=c("A","B"),away_name=c("C","D"),handicap=0L,kickoff_at=cutoff$cutoff_utc+3600)
  sheet <- beidan::parlay_betting_sheet(result$final,schedule)
  testthat::expect_equal(sum(sheet$groups$cost_cny),6)
  testthat::expect_equal(sum(sheet$groups$funded_tickets),3L)
})
