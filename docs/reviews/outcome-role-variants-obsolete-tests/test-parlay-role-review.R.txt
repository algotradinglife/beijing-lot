# Independent regressions from Codex review, exercise public operations.
test_that("overlapping current groups deduplicate physical tickets and keep slot budgets", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("26098:1","26098:2"),each=3),
    outcome=rep(c("W","D","L"),2),probability=c(.5,.3,.2,.6,.3,.1))
  settings <- parlay_settings(); settings$n_legs <- 2L; settings$issue_budget_cny <- 6
  portfolio <- parlay_construct_role_groups(parlay_role_scores(p,cutoff),cutoff,settings,
    c(2L,1L),2L,probabilities=p)
  expect_equal(portfolio$pattern,c(2L,1L))
  expect_equal(dplyr::n_distinct(portfolio$groups$group_id),2L)
  # Force the two candidate slots onto the SAME physical package so the second is a
  # duplicate-only package under the current-group de-duplication.
  portfolio$role_legs$fixture_id <- c("26098:1", "26098:2", "26098:1", "26098:2")
  portfolio$role_legs <- beidan:::.parlay_role_refresh_masks(portfolio$role_legs,p)
  for (slot in 1:2) {
    idx <- portfolio$role_legs$group_slot == slot
    id <- paste0(paste(sort(portfolio$role_legs$fixture_id[idx]),collapse="+"),
                 "@",as.numeric(cutoff$cutoff_utc),":",slot)
    portfolio$role_legs$group_id[idx] <- id
    portfolio$groups$group_id[portfolio$groups$group_slot==slot] <- id
  }
  x <- parlay_evaluate_portfolio(portfolio,group_budget_cny=4,budget_cny=NULL,
    constraints=list(max_reuse=4L,max_overlap=2L),improve=FALSE)
  expect_equal(sum(x$selection$selected),1L)
  expect_true("duplicate_physical_tickets_only" %in% x$selection$reason)
  expect_equal(nrow(x$tickets),2L)
  expect_identical(nrow(x$tickets),dplyr::n_distinct(x$tickets$ticket_id))
  expect_equal(nrow(x$group_summary),1L)
  expect_equal(sum(x$group_summary$cost_cny),4)
})

test_that("receipt binds carried prices and search controls", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(paste0("26098:",1:3),each=3),
    outcome=rep(c("W","D","L"),3),probability=c(.8,.15,.05,.7,.2,.1,.6,.25,.15))
  settings <- parlay_settings();settings$n_legs<-2L;settings$issue_budget_cny<-4
  scores <- parlay_role_scores(p,cutoff)
  bad <- scores;bad$allowed_outcomes[[which(bad$role==1L)[1]]] <- "L"
  expect_error(parlay_construct_role_groups(bad,cutoff,settings,c(2L,1L),2L,probabilities=p),"masks")
  expect_error(parlay_construct_role_groups(scores[-1,],cutoff,settings,c(2L,1L),2L,probabilities=p),"exactly once")
  sp <- dplyr::mutate(dplyr::select(p,fixture_id,outcome),quote_at=cutoff$cutoff_utc-60,
    sp_raw=4,source_url="fixture")
  plan <- parlay_construct_role_groups(scores,cutoff,settings,c(2L,1L),2L,probabilities=p,
    prematch_sp=sp)
  x <- parlay_evaluate_portfolio(plan,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE,objective="ev")
  sp$sp_raw <- 5
  plan5 <- parlay_construct_role_groups(scores,cutoff,settings,c(2L,1L),2L,probabilities=p,
    prematch_sp=sp)
  y <- parlay_evaluate_portfolio(plan5,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE,objective="ev")
  expect_false(identical(x$receipt,y$receipt))
  expect_identical(x$receipt$prematch_sp_hash,plan$prematch_sp_hash)
  expect_identical(y$receipt$improve,FALSE)
  expect_true(is.list(y$receipt$improvement_policy))
  # A fixture with no pre-cutoff SP leaves EV unavailable and fails the EV objective.
  selected_sp <- dplyr::filter(sp,fixture_id != plan$role_legs$fixture_id[1])
  missing_plan <- parlay_construct_role_groups(scores,cutoff,settings,c(2L,1L),2L,
    probabilities=p,prematch_sp=selected_sp)
  expect_error(parlay_evaluate_portfolio(missing_plan,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L),objective="ev"),"ev")
  expect_error(parlay_evaluate_portfolio(plan,group_budget_cny=NA_real_,budget_cny=4,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE),"group_budget_cny")
})

test_that("every exchange addresses the selected repeated-role row across groups", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=paste0("26098:",1:4),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.7,.2,.1),4))
  settings <- parlay_settings();settings$n_legs<-2L;settings$issue_budget_cny<-8
  scores <- parlay_role_scores(p,cutoff)
  plan <- parlay_construct_role_groups(scores,cutoff,settings,c(2L,2L),2L,probabilities=p)
  moves <- .parlay_role_candidate_moves(plan,scores,2L)
  exchanges <- Filter(function(x) x$move=="group_exchange",moves)
  expect_length(exchanges,4L)
  for (move in exchanges) {
    expect_false(move$group_slot_a==move$group_slot_b)
    expect_equal(plan$role_legs$fixture_id[move$index_a],move$fixture_a)
    expect_equal(plan$role_legs$fixture_id[move$index_b],move$fixture_b)
    moved <- .parlay_role_apply_move(plan$role_legs,move)
    expect_equal(moved$fixture_id[move$index_a],move$fixture_b)
  }
})

test_that("cross-role exchanges improve the portfolio and leave an auditable trace", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(paste0("26098:",1:4),each=3),
    outcome=rep(c("W","D","L"),4),probability=c(.75,.24,.01,.65,.34,.01,.60,.25,.15,.55,.25,.20))
  settings <- parlay_settings();settings$n_legs<-2L;settings$issue_budget_cny<-9
  plan <- parlay_construct_role_groups(parlay_role_scores(p,cutoff),cutoff,settings,c(2L,1L),2L,probabilities=p)
  plan$role_legs$fixture_id <- c("26098:1","26098:4","26098:2","26098:3")
  plan$role_legs <- .parlay_role_refresh_masks(plan$role_legs,p)
  for (slot in 1:2) {
    idx <- plan$role_legs$group_slot==slot
    id <- paste0(paste(sort(plan$role_legs$fixture_id[idx]),collapse="+"),"@",as.numeric(cutoff$cutoff_utc),":",slot)
    plan$role_legs$group_id[idx] <- id
    plan$groups$group_id[plan$groups$group_slot==slot] <- id
  }
  x <- parlay_evaluate_portfolio(plan,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L))
  expect_gte(tail(x$metrics$expected_winning_tickets,1),1.21-1e-12)
  expect_equal(x$metrics$unspent_cny,c(1,1))
  expect_equal(x$diagnostics$unspent_cny,1)
  expect_true(all(!is.na(x$changes$old_fixture)))
  expect_true(all(!is.na(x$changes$new_fixture)))
  expect_true(all(x$changes$round_a %in% 1:2))
  sp <- dplyr::mutate(dplyr::select(p,fixture_id,outcome),quote_at=cutoff$cutoff_utc-60,
    sp_raw=12,source_url="fixture")
  plan_ev <- parlay_construct_role_groups(parlay_role_scores(p,cutoff),cutoff,settings,c(2L,1L),2L,probabilities=p,prematch_sp=sp)
  plan_ev$role_legs$fixture_id <- c("26098:1","26098:4","26098:2","26098:3")
  plan_ev$role_legs <- .parlay_role_refresh_masks(plan_ev$role_legs,p)
  for (slot in 1:2) {
    idx <- plan_ev$role_legs$group_slot==slot
    id <- paste0(paste(sort(plan_ev$role_legs$fixture_id[idx]),collapse="+"),"@",as.numeric(cutoff$cutoff_utc),":",slot)
    plan_ev$role_legs$group_id[idx] <- id
    plan_ev$groups$group_id[plan_ev$groups$group_slot==slot] <- id
  }
  ev <- parlay_evaluate_portfolio(plan_ev,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE,objective="ev")
  expect_equal(ev$tickets$objective_value,ev$tickets$ev_net_est)
  expect_equal(sum(ev$tickets$objective_value),tail(ev$metrics$ev_net_cny,1))
  empty_p <- match_typed_empty("probabilities")
  empty <- parlay_construct_role_groups(parlay_role_scores(empty_p,cutoff),cutoff,settings,
    c(2L,1L),2L,probabilities=empty_p)
  z <- parlay_evaluate_portfolio(empty,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L))
  expect_equal(z$metrics$unspent_cny,c(9,9))
  expect_equal(z$diagnostics$unspent_cny,9)
  two <- p[1:6,]
  incomplete <- parlay_construct_role_groups(parlay_role_scores(two,cutoff),cutoff,settings,
    c(3L,3L),2L,probabilities=two)
  expect_gt(nrow(incomplete$shortages),0L)
  expect_true(all(incomplete$shortages$group_id %in% incomplete$groups$group_id))
})


test_that("coordinated role and mask edits cannot expand a frozen structure", {
  cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=paste0("26098:",1:2),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.7,.2,.1),2))
  settings <- parlay_settings();settings$n_legs<-2L;settings$issue_budget_cny<-18
  plan <- parlay_construct_role_groups(parlay_role_scores(p,cutoff),cutoff,settings,c(1L,1L),2L,probabilities=p)
  plan$role_legs$role <- c(3L,3L)
  plan$role_legs$allowed_outcomes <- rep(list(c("W","D","L")),2)
  plan$role_legs$retained_probability <- c(1,1)
  expect_error(parlay_evaluate_portfolio(plan,group_budget_cny=4,budget_cny=settings$issue_budget_cny,constraints=list(max_reuse=1L,max_overlap=0L)),"frozen pattern")
})
