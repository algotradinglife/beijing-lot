source(file.path(rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION")),"r/parlay_loss_mask_experiment.R"))
testthat::test_that("fixed real snapshot SP mask experiment preserves money and inputs", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  x <- readRDS(file.path(root,"inputs/26098_walkthrough/three_plans_20260928/plans.rds"))
  original <- x$outputs[["3333222"]]
  before <- rlang::hash(original)
  e <- ParlayLossMaskExperiment(original,"sp_one_134")
  testthat::expect_identical(rlang::hash(original),before)
  testthat::expect_equal(sum(e$final$plan$purchases$stake_cny),512)
  testthat::expect_identical(e$final$probabilities,original$evaluated$final$probabilities)
  testthat::expect_identical(e$cutoff,original$evaluated$cutoff)
  gl <- e$final$plan$group_legs
  testthat::expect_setequal(unique(gl$group_id),unique(original$evaluated$final$plan$group_legs$group_id))
  legs <- e$final$plan$ticket_legs |>
    dplyr::inner_join(dplyr::select(e$final$plan$purchases,ticket_id,group_id),by="ticket_id") |>
    dplyr::filter(fixture_id=="26098:134")
  first <- sort(unique(legs$group_id))[1]
  testthat::expect_setequal(legs$outcome[legs$group_id==first],c("W","D"))
  testthat::expect_setequal(legs$outcome[legs$group_id!=first],c("W","L"))
  for (mode in c("sp_all","sp_one_134")) {
    z <- ParlayLossMaskExperiment(original,mode)
    testthat::expect_equal(nrow(z$final$plan$purchases),256)
    testthat::expect_true(z$receipt$diagnostic_only)
  }
  testthat::expect_error(ParlayLossMaskExperiment(original,"bad"))
  bad <- original; bad$evaluated$receipt$cutoff_hash <- NULL
  testthat::expect_error(ParlayLossMaskExperiment(bad,"sp_all"),"cutoff")
  bad <- original; bad$pool$probabilities$probability[1] <- .9
  testthat::expect_error(ParlayLossMaskExperiment(bad,"sp_all"),"binding")
})

testthat::test_that("all original final groups including improved groups are retained", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  x <- readRDS(file.path(root,"inputs/26098_walkthrough/three_plans_20260928/plans.rds"))
  for (pattern in c("3322221","3222221")) {
    o <- x$outputs[[pattern]]
    e <- ParlayLossMaskExperiment(o,"sp_all")
    testthat::expect_equal(sum(e$final$plan$purchases$stake_cny),
      sum(o$evaluated$final$plan$purchases$stake_cny))
    testthat::expect_setequal(unique(e$final$plan$purchases$group_id),
      unique(o$evaluated$final$plan$purchases$group_id))
  }
})

testthat::test_that("diversification covers every shared fixture without increasing cost", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  x <- readRDS(file.path(root,"inputs/26098_walkthrough/three_plans_20260928/plans.rds"))
  for (pattern in names(x$outputs)) {
    o <- x$outputs[[pattern]]
    e <- ParlayLossMaskExperiment(o,"diversify_shared")
    testthat::expect_equal(sum(e$final$plan$purchases$stake_cny),
      sum(o$evaluated$final$plan$purchases$stake_cny))
    gl <- e$final$plan$group_legs
    shared <- names(which(table(gl$fixture_id)>1))
    masks <- e$final$plan$supports
    for (fixture in shared) testthat::expect_setequal(
      masks$outcome[masks$fixture_id==fixture & masks$allowed],c("W","D","L"))
    testthat::expect_identical(e$final$probabilities,o$evaluated$final$probabilities)
  }
})
