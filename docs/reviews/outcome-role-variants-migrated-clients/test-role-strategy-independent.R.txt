# PI-owned numerical acceptance. Separate from implementation-owned helper tests.
testthat::test_that("role scores equal the approved arithmetic, not entropy", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 11:52:04",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("26098:A","26098:B","26098:C"),each=3),
    outcome=rep(c("W","D","L"),3),probability=c(.90,.07,.03,.49,.48,.03,.35,.34,.31))
  scores <- beidan::parlay_role_scores(p,cutoff)
  testthat::expect_s3_class(scores,"tbl_df")
  testthat::expect_equal(nrow(scores),9L)
  for (role in 1:3) {
    rows <- dplyr::filter(scores,.data$role==!!role) |> dplyr::arrange(fixture_id)
    expected <- switch(role,c(.9,.49,.35),c(.97,.97,.69),c(.03,.03,.31))
    mass <- switch(role,c(.9,.49,.35),c(.97,.97,.69),rep(1,3))
    testthat::expect_equal(rows$score,expected)
    testthat::expect_equal(rows$retained_probability,mass)
    testthat::expect_equal(lengths(rows$allowed_outcomes),rep(role,3))
  }
  triples <- dplyr::filter(scores,role==3L) |> dplyr::arrange(rank)
  testthat::expect_identical(triples$fixture_id[1],"26098:C")
  shuffled <- beidan::parlay_role_scores(p[c(9,1,5,3,7,2,8,4,6),],cutoff)
  testthat::expect_equal(lapply(dplyr::arrange(scores,role,fixture_id),identity),
    lapply(dplyr::arrange(shuffled,role,fixture_id),identity))
})

testthat::test_that("snake rounds build all groups together and improve the whole portfolio", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 11:52:04",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(paste0("26098:",1:4),each=3),
    outcome=rep(c("W","D","L"),4),
    probability=c(.50,.49,.01,.70,.28,.02,.85,.10,.05,.80,.15,.05))
  settings <- beidan::parlay_settings()
  settings$n_legs <- 2L;settings$issue_budget_cny <- 8;settings$unit_cny <- 2
  scores <- beidan::parlay_role_scores(p,cutoff)
  portfolio <- beidan::parlay_construct_role_groups(scores,cutoff,settings,
    pattern=c(2L,1L),n_candidates=2L,probabilities=p)
  portfolio$role_legs$fixture_id <- c("26098:1","26098:4","26098:2","26098:3")
  portfolio$role_legs <- beidan:::.parlay_role_refresh_masks(portfolio$role_legs,p)
  for (slot in 1:2) {
    idx <- portfolio$role_legs$group_slot==slot
    id <- paste0(paste(sort(portfolio$role_legs$fixture_id[idx]),collapse="+"),"@",as.numeric(cutoff$cutoff_utc),":",slot)
    portfolio$role_legs$group_id[idx] <- id
    portfolio$groups$group_id[portfolio$groups$group_slot==slot] <- id
  }
  selected <- dplyr::arrange(portfolio$role_legs,round,group_slot)
  testthat::expect_identical(selected$fixture_id,c("26098:1","26098:2","26098:4","26098:3"))
  testthat::expect_equal(selected$role,c(2L,2L,1L,1L))
  original <- rlang::hash(portfolio)
  empty_sp <- beidan:::match_typed_empty("prematch_sp")
  baseline <- beidan::parlay_evaluate_portfolio(portfolio, group_budget_cny = 4, budget_cny = 8,
    constraints = list(max_reuse = 1L, max_overlap = 0L),improve=FALSE)
  testthat::expect_equal(sum(baseline$final$summary$tickets$probability_mass),1.625)
  testthat::expect_equal(sum(baseline$final$funded$purchases$stake_cny),8)
  testthat::expect_equal(nrow(baseline$changes),0L)
  improved <- beidan::parlay_evaluate_portfolio(portfolio, group_budget_cny = 4, budget_cny = 8,
    constraints = list(max_reuse = 1L, max_overlap = 0L),
    improvement_policy=list(max_passes=2L,rank_window=3L,max_evaluations=60L))
  testthat::expect_gte(sum(improved$final$summary$tickets$probability_mass),1.6255-1e-12)
  testthat::expect_gt(nrow(improved$changes),0L)
  legs <- dplyr::distinct(improved$final$plan$group_legs,group_id,fixture_id)
  testthat::expect_equal(max(table(legs$fixture_id)),1L)
  testthat::expect_identical(rlang::hash(portfolio),original)
  testthat::expect_equal(sum(improved$final$funded$purchases$stake_cny),8)
  testthat::expect_identical(sort(names(improved)),sort(names(baseline)))
})

testthat::test_that("seven global rounds use3 then2 and alternate all four group turns", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 11:52:04",tz="UTC"))
  p <- tidyr::expand_grid(fixture_id=paste0("26098:",1:28),outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.7,.2,.1),28))
  settings <- beidan::parlay_settings()
  settings$n_legs <- 7L;settings$issue_budget_cny <- 1024;settings$unit_cny <- 2
  x <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),
    cutoff,settings,pattern=c(3L,3L,3L,3L,2L,2L,2L),n_candidates=4L,probabilities=p)
  chosen <- dplyr::filter(x$trace,action=="selected")
  testthat::expect_equal(chosen$round,rep(1:7,each=4))
  testthat::expect_equal(chosen$group_slot,c(1:4,4:1,1:4,4:1,1:4,4:1,1:4))
  testthat::expect_equal(chosen$role,rep(c(3L,3L,3L,3L,2L,2L,2L),each=4))
  testthat::expect_equal(dplyr::n_distinct(chosen$fixture_id),28L)
  testthat::expect_equal(nrow(x$shortages),0L)
  testthat::expect_true(all(x$groups$complete))
  settings$issue_budget_cny <- 1023
  reduced <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),
    cutoff,settings,pattern=c(3L,3L,3L,3L,2L,2L,2L),n_candidates=4L,probabilities=p)
  testthat::expect_equal(reduced$role_legs,x$role_legs)
})


testthat::test_that("equal outcomes follow W D L rather than alphabetic order", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 11:52:04",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep("26098:1",3),outcome=c("L","D","W"),probability=rep(1/3,3))
  scores <- beidan::parlay_role_scores(p,cutoff)
  testthat::expect_identical(scores$allowed_outcomes[[which(scores$role==1L)]],"W")
  testthat::expect_identical(scores$allowed_outcomes[[which(scores$role==2L)]],c("W","D"))
})
