# Independent oracle: enumerate fixture outcomes directly from actual bought legs.
testthat::test_that("joint risk agrees with direct physical-ticket enumeration", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::with_tz(lubridate::ymd_hms("2026-09-28 00:00:00",tz="Asia/Shanghai"),"UTC"))
  probabilities <- tibble::tibble(fixture_id=rep(c("26098:A","26098:B","26098:C"),each=3),
    outcome=rep(c("W","D","L"),3),probability=c(.6,.2,.2,.7,.15,.15,.8,.1,.1))
  quotes <- dplyr::mutate(dplyr::select(probabilities,fixture_id,outcome),
    quote_at=cutoff$cutoff_utc-60,sp_raw=2,source_url="fixture://independent")
  settings <- beidan::parlay_settings();settings$n_legs <- 2L
  pool <- IndependentRankedPool(probabilities,cutoff,settings,c(1L,1L),3L,sp=quotes)
  scenarios <- tibble::tibble(scenario_id="shared",pattern="p11",group_budget_cny=2,
    max_reuse=2L,max_overlap=1L)
  exploration <- beidan::parlay_explore_portfolios(list(p11=pool),scenarios)
  final <- exploration$results$shared$plan
  result <- beidan::parlay_compare_risk(exploration,method="exact")
  tickets <- final$purchases
  legs <- final$ticket_legs
  states <- tidyr::expand_grid(A=c("W","D","L"),B=c("W","D","L"),C=c("W","D","L"))
  weights <- payouts <- numeric(nrow(states))
  wins <- integer(nrow(states))
  for (i in seq_len(nrow(states))) {
    actual <- stats::setNames(as.character(states[i,]),c("26098:A","26098:B","26098:C"))
    weights[i] <- prod(probabilities$probability[match(paste(names(actual),actual),
      paste(probabilities$fixture_id,probabilities$outcome))])
    for (id in tickets$ticket_id) {
      ticket_legs <- legs[legs$ticket_id==id,]
      if (all(actual[ticket_legs$fixture_id]==ticket_legs$outcome)) {
        wins[i] <- wins[i]+1L
        payouts[i] <- payouts[i]+2*.65*2^nrow(ticket_legs)
      }
    }
  }
  full <- result$summary[which.max(result$summary$prefix_groups),]
  cost <- 2*nrow(tickets)
  testthat::expect_gt(full$prefix_groups,1L)
  testthat::expect_equal(full$cost_cny,cost)
  testthat::expect_equal(full$hit_probability,sum(weights[wins>0]),tolerance=1e-12)
  testthat::expect_equal(full$break_even_probability,sum(weights[payouts>=cost]),tolerance=1e-12)
  testthat::expect_equal(full$expected_net_cny,sum(weights*payouts)-cost,tolerance=1e-12)
  testthat::expect_equal(full$expected_winning_tickets,sum(weights*wins),tolerance=1e-12)
  testthat::expect_lte(full$hit_probability,full$expected_winning_tickets)
})

testthat::test_that("lab chunks execute end to end with explicit selection and no automatic champion", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  lines <- readLines(file.path(root,"quarto/parlay_combination_lab.qmd"))
  env <- new.env(parent=globalenv())
  env$cutoff <- list(issue_id="26098",cutoff_utc=lubridate::with_tz(lubridate::ymd_hms("2026-09-28 00:00:00",tz="Asia/Shanghai"),"UTC"))
  p <- tibble::tibble(fixture_id=rep(paste0("26098:",1:4),each=3),
    outcome=rep(c("W","D","L"),4),probability=c(.6,.3,.1,.7,.2,.1,.8,.15,.05,.5,.3,.2))
  env$source_result <- list(probabilities=p,constants=beidan::parlay_settings())
  env$source_result$constants$n_legs <- 2L
  env$decision_sp <- dplyr::mutate(dplyr::select(p,fixture_id,outcome),
    quote_at=env$cutoff$cutoff_utc-60,sp_raw=2,source_url="fixture://qmd")
  env$unit_cny <- 2;env$n_matches <- 4L
  env$settings <- env$source_result$constants
  env$patterns <- list(p11=c(1L,1L),p21=c(2L,1L))
  env$pattern_catalog <- tibble::tibble(pattern=c("p11","p21"),full_cover_units=c(1,2),full_cover_cny=c(2,4))
  env$group_budgets_cny <- c(2,4,8)
  labels <- c("role-rankings","role-candidates","exploration-scenarios","joint-risk",
    "budget-curves","budget-curves-zoom","fixed-depth","coverage-frontier","choose-scenario","refine-selected","selected-plan")
  for (label in labels) {
    start <- match(paste0("#| label: ",label),lines)
    finish <- which(seq_along(lines)>start & lines=="```")[[1]]
    expressions <- parse(text=lines[seq.int(start+1L,finish-1L)])
    invisible(utils::capture.output(eval(expressions,env)))
  }
  testthat::expect_gt(nrow(env$scenarios),0L)
  testthat::expect_true(all(env$exploration$summary$budget_unlimited))
  testthat::expect_false(env$selection_is_explicit)
  testthat::expect_null(env$role_evaluation)
  testthat::expect_true(all(env$frontier$hit_probability<=1))
  testthat::expect_true(all(env$depth_curve$retained_fraction<=1+1e-12))
  chosen <- env$budget_comparison |> dplyr::filter(cost_cny>0) |> dplyr::slice_head(n=1)
  env$params <- list(selected_scenario_id=chosen$scenario_id,selected_prefix_groups=chosen$prefix_groups)
  for (label in c("choose-scenario","refine-selected","selected-plan")) {
    start <- match(paste0("#| label: ",label),lines)
    finish <- which(seq_along(lines)>start & lines=="```")[[1]]
    invisible(utils::capture.output(eval(parse(text=lines[seq.int(start+1L,finish-1L)]),env)))
  }
  testthat::expect_true(env$role_evaluation$receipt$improve)
  testthat::expect_lte(max(env$refined_risk$summary$cost_cny),chosen$cost_cny)
})
