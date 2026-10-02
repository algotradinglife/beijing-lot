#' Build a real two-fixture saved plan for depth diagnostics.
#' @param quotes Logical; include pre-match SP of two for every outcome.
#' @param budget Finite per-group CNY spending.
#' @param tie Logical; make the two legal tickets equiprobable.
#' @param issue_budget Unused issue spending setting, CNY.
#' @return Saved final plan with two legal tickets and no external side effects.
fixed_depth_plan <- function(quotes = TRUE, budget = 2, tie = FALSE, issue_budget = 1024) {
  cutoff <- list(issue_id = "26098", cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
  probabilities <- tibble::tibble(fixture_id = rep(c("26098:1", "26098:2"), each = 3),
    outcome = rep(c("W", "D", "L"), 2), probability = c(.5, .4, .1, .7, .2, .1))
  if (tie) probabilities$probability[1:3] <- c(.45, .45, .1)
  sp <- if (quotes) dplyr::mutate(dplyr::select(probabilities, fixture_id, outcome),
    quote_at = cutoff$cutoff_utc - 60, sp_raw = 2, source_url = "test") else
    match_typed_empty("prematch_sp")
  settings <- parlay_settings(); settings$n_legs <- 2L
  settings$issue_budget_cny <- issue_budget
  matches <- tidyr::pivot_wider(probabilities, names_from = outcome, values_from = probability) |>
    dplyr::rename(win = W, draw = D, lose = L)
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
  pool <- parlay_construct_role_groups(ranked, settings, c(2L, 1L),
    max_candidates = 1L, prematch_sp = sp)
  return(parlay_evaluate_portfolio(pool, group_budget_cny=budget, budget_cny=NULL,
    reuse_policy=list(max_reuse=2L), overlap_policy=list(max_overlap=2L), improve = FALSE))
}

test_that("fixed depth curves match frozen prefixes, unit floors and saturation", {
  plan <- fixed_depth_plan()
  before <- rlang::hash(plan)
  caps <- c(0, 1, 2, 3, 4, 100)
  x <- parlay_fixed_depth_curve(list(p21 = plan), caps)
  # Constructor assigns the widest mask to fixture 1: .6+.3, fixture 2: .7.
  expect_equal(x$support_size, rep(2L, 6))
  expect_equal(x$structure_probability, rep(.63, 6))
  expect_equal(x$purchased_tickets, c(0L, 0L, 1L, 1L, 2L, 2L))
  expect_equal(x$cost_cny, c(0, 0, 2, 2, 4, 4))
  expect_equal(x$coverage_probability, c(0, 0, .35, .35, .63, .63))
  expect_equal(x$retained_fraction, c(0, 0, 5/9, 5/9, 1, 1))
  expect_equal(x$expected_net_cny, c(0, 0, -.18, -.18, -.724, -.724))
  expect_identical(x$group_budget_cny, caps)
  expect_identical(rlang::hash(plan), before)
})

test_that("missing selected EV stays unknown but zero depth is zero", {
  x <- parlay_fixed_depth_curve(list(p = fixed_depth_plan(FALSE)), c(0, 2, 4))
  expect_equal(x$expected_net_cny[1], 0)
  expect_true(all(is.na(x$expected_net_cny[-1])))
  expect_equal(x$coverage_probability, c(0, .35, .63))
})

test_that("current evaluation bindings reject source, plan and ledger mutations", {
  plan <- fixed_depth_plan()
  for (field in c("portfolio", "plan", "purchases", "receipt")) {
    bad <- plan; bad[[field]] <- NULL
    expect_error(parlay_fixed_depth_curve(list(p=bad),2))
  }
  bad <- plan; bad$portfolio$probabilities$probability[1] <- .1
  expect_error(parlay_fixed_depth_curve(list(p=bad),2))
  bad <- plan; bad$plan$purchases$stake_cny[1] <- 4
  expect_error(parlay_fixed_depth_curve(list(p=bad),2),"binding")
  bad <- plan; bad$final$role_legs$allowed_outcomes[[1]] <- "W"
  expect_error(parlay_fixed_depth_curve(list(p=bad),2),"binding")
  expect_error(parlay_fixed_depth_curve(list(p=plan,other=fixed_depth_plan(FALSE)),2),"share")
})

test_that("empty caps, empty lists and unpurchased plans keep typed schema", {
  plan <- fixed_depth_plan()
  a <- parlay_fixed_depth_curve(list(),numeric())
  b <- parlay_fixed_depth_curve(list(p=plan),numeric())
  c <- parlay_fixed_depth_curve(list(p=fixed_depth_plan(budget=0)),2)
  expect_identical(a,b); expect_identical(a,c)
  expect_error(parlay_fixed_depth_curve(list(p=plan),-1))
  expect_error(parlay_fixed_depth_curve(list(p=plan),NA_real_))
  expect_error(parlay_fixed_depth_curve(list(p=plan),matrix(2)))
})

test_that("independent masks reject a manually rebound illegal final selection", {
  plan <- fixed_depth_plan()
  plan$final$role_legs$allowed_outcomes[[1]] <- "W"
  plan$receipt$final_role_legs_hash <- rlang::hash(plan$final$role_legs)
  expect_error(parlay_fixed_depth_curve(list(p=plan),2),"mask|outcome|selection")
})

test_that("probability sum tolerance survives one and multiple full-triple legs", {
  for (n in 1:2) {
    cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
    matches <- tibble::tibble(fixture_id=paste0("F",seq_len(n)),
      win=.4,draw=.3,lose=.3000000005)
    ranked <- rank_outcome_selections(prepare_outcome_selections(matches),cutoff)
    settings <- parlay_constant_defaults();settings$n_legs <- as.integer(n)
    pool <- parlay_construct_role_groups(ranked,settings,rep(3L,n),max_candidates=1L)
    result <- parlay_evaluate_portfolio(pool,group_budget_cny=NULL,
      reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
    curve <- parlay_fixed_depth_curve(list(p=result),2*3^n)
    expect_equal(curve$support_size,as.integer(3^n))
    expect_equal(curve$structure_probability,(1.0000000005)^n,tolerance=1e-12)
    expect_equal(curve$coverage_probability,(1.0000000005)^n,tolerance=1e-12)
    expect_identical(result$portfolio$probabilities$probability,
      rep(c(.4,.3,.3000000005),n))
  }
})

test_that("fixed depth independently refuses manually rebound purchase values", {
  plan <- fixed_depth_plan()
  for (field in c("probability","sp_product_est","ev_net_est")) {
    bad <- plan;bad$purchases[[field]][1] <- 999
    bad$receipt$final_purchase_hash <- rlang::hash(bad$purchases)
    expect_error(parlay_fixed_depth_curve(list(p=bad),2),"probability|valuation")
  }
})


test_that("funding and frozen issue stay independently bound after hash rebinding", {
  plan <- fixed_depth_plan()
  mutations <- list(
    function(p) {p$plan$funded <- dplyr::bind_rows(p$plan$funded,p$plan$funded);p},
    function(p) {p$plan$funded$group_id[1] <- "wrong";p},
    function(p) {p$plan$funded$stake_cny[1] <- 4;p},
    function(p) {p$plan$issue_id <- "26099";p},
    function(p) {p$receipt$issue_id <- "26099";p},
    function(p) {p$plan$purchases$issue_id[1] <- "26099";p},
    function(p) {p$plan$purchases$epoch_at[1] <- p$cutoff$cutoff_utc+60;p})
  for (mutate in mutations) {
    bad <- mutate(plan);bad$receipt$plan_hash <- rlang::hash(bad$plan)
    expect_error(parlay_fixed_depth_curve(list(p=bad),2),"funding|issue|cutoff")
    expect_error(parlay_compare_risk(list(results=list(p=bad),cutoff=bad$cutoff,
      summary=tibble::tibble(scenario_id="p"))),
      "funding|issue|cutoff")
  }
})

test_that("fixed depth compares explicit funding alternatives despite unused issue budgets", {
  a <- fixed_depth_plan(issue_budget=1024)
  b <- fixed_depth_plan(issue_budget=2048)
  curves <- parlay_fixed_depth_curve(list(a=a,b=b),c(2,4))
  expect_equal(curves$coverage_probability,c(.35,.63,.35,.63))
  expect_equal(curves$cost_cny,c(2,4,2,4))
})

test_that("physical ticket identities cannot be aliased by rebinding receipts", {
  bad <- fixed_depth_plan()
  id <- bad$purchases$ticket_id[1]
  bad$purchases$ticket_id[1] <- "alias"
  for (table in c("funded","purchases","ticket_legs")) {
    bad$plan[[table]]$ticket_id[bad$plan[[table]]$ticket_id==id] <- "alias"
  }
  bad$receipt$final_purchase_hash <- rlang::hash(bad$purchases)
  bad$receipt$plan_hash <- rlang::hash(bad$plan)
  expect_error(parlay_fixed_depth_curve(list(p=bad),2),"physical ticket identity")
})
