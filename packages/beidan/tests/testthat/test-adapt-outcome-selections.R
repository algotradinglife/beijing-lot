test_that("adaptive selections fill deficits while preserving probability mass", {
  m <- tibble::tibble(fixture_id = sprintf("T:%03d", 1:10),
    win = c(.46,.47,.48,.49,.51,.52,.44,.43,.34,.35),
    draw = c(.34,.32,.31,.30,.29,.28,.33,.34,.33,.33),
    lose = c(.20,.21,.21,.21,.20,.20,.23,.23,.33,.32))
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  r <- rank_outcome_selections(prepare_outcome_selections(m,.45),cutoff)
  before <- r
  x <- AdaptOutcomeSelections(r,7L)
  expect_identical(x$pattern,c(3L,3L,2L,2L,2L,2L,1L))
  moves <- x$allocation$ledger |> dplyr::filter(native_role != allocated_role)
  expect_identical(moves$fixture_id,c("T:001","T:002"))
  expect_true(all(moves$native_role==1L & moves$allocated_role==2L))
  expect_equal(moves$gain,c(.34,.32))
  expect_identical(r,before)
  expect_silent(.parlay_ranked_validate_receipt(x$ranked))
  expect_equal(as.data.frame(dplyr::distinct(x$ranked,fixture_id,win,draw,lose) |> dplyr::arrange(fixture_id)),as.data.frame(m),ignore_attr=TRUE)
  expect_true(all(x$ranked$n_outcomes[x$ranked$fixture_id %in% moves$fixture_id]==2L))
  settings <- parlay_constant_defaults()
  settings$n_legs <- 7L; settings$issue_budget_cny <- 2048
  settings$unit_cny <- 2; settings$payout_factor <- .65
  old <- parlay_construct_role_groups(r,settings,x$pattern,max_candidates=1L)
  new <- parlay_construct_role_groups(x$ranked,settings,x$pattern,max_candidates=1L)
  expect_equal(nrow(old$groups),0L)
  expect_equal(nrow(new$groups),1L)
  expect_equal(dplyr::n_distinct(new$role_legs$fixture_id),7L)
  bad <- x$ranked;attr(bad,"role_allocation") <- NULL
  expect_error(.parlay_ranked_validate_receipt(bad),"role_allocation")
  bad <- x$ranked; attr(bad,"cutoff")$cutoff_utc <- cutoff$cutoff_utc+1
  expect_error(.parlay_ranked_validate_receipt(bad),"cutoff")
  s <- attr(x$ranked,"input_snapshot");attr(s,"role_allocation")$ledger$allocated_role[1] <- 1L
  expect_error(rank_outcome_selections(s,cutoff),"role_allocation")
  expect_error(rank_outcome_selections(attr(x$ranked,"input_snapshot"),
   list(issue_id="T",cutoff_utc=cutoff$cutoff_utc+1)),"cutoff")
  expect_error(AdaptOutcomeSelections(x$ranked,7L),"original unallocated")
  expect_error(AdaptOutcomeSelections(r,7L,2L),"n_legs")
  expect_error(AdaptOutcomeSelections(r,0L))
})
test_that("adaptive masks support narrowing and DC protection on changed roles", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id="T:001",win=.34,draw=.33,lose=.33)
  r <- rank_outcome_selections(prepare_outcome_selections(m),cutoff)
  x <- AdaptOutcomeSelections(r,1L,1L)
  expect_identical(x$ranked$outcomes,list("win"))
  expect_identical(x$ranked$base_role,1L)
  expect_equal(x$ranked$coverage_probability,.34)
  expect_equal(x$allocation$ledger$gain,-.66)
  dc <- tibble::tibble(fixture_id="T:001",outcome=c("W","D","L"),probability=c(.2,.5,.3))
  r <- rank_outcome_selections(prepare_outcome_selections(m,dc_protection=dc),cutoff)
  x <- AdaptOutcomeSelections(r,1L,1L)
  expect_identical(x$ranked$outcomes,list(c("win","draw"),"win"))
  expect_equal(sort(x$ranked$coverage_probability),c(.34,.67))
})
test_that("adaptive handles empty and insufficient fixture pools", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id=character(),win=double(),draw=double(),lose=double())
  r <- rank_outcome_selections(prepare_outcome_selections(m),cutoff)
  x <- AdaptOutcomeSelections(r,7L)
  expect_identical(x$allocation$status,"insufficient_fixtures")
  expect_equal(nrow(x$ranked),0L)
  expect_silent(.parlay_ranked_validate_receipt(x$ranked))
})

test_that("allocation-only retiming fails even without a filter receipt", {
  m <- tibble::tibble(fixture_id="T:001",win=.6,draw=.3,lose=.1)
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  a <- AdaptiveRoleAllocation(m,cutoff,2L)
  a$cutoff$cutoff_utc <- cutoff$cutoff_utc+1
  expect_error(prepare_outcome_selections(m,role_allocation=a),"cutoff binding")
  a <- AdaptiveRoleAllocation(m,cutoff,2L);a$cutoff$issue_id <- "OTHER"
  expect_error(prepare_outcome_selections(m,role_allocation=a),"cutoff binding")
  a <- AdaptiveRoleAllocation(m,cutoff,2L);a$cutoff_hash <- NULL
  expect_error(prepare_outcome_selections(m,role_allocation=a),"cutoff binding")
  a <- AdaptiveRoleAllocation(m,cutoff,2L);a$code_hash <- "changed"
  expect_error(prepare_outcome_selections(m,role_allocation=a),"implementation")
  a <- AdaptiveRoleAllocation(m,cutoff,2L);m$win <- .59;m$draw <- .31
  expect_error(prepare_outcome_selections(m,role_allocation=a),"source")
})

test_that("adapter binds reuse-aware supply and validates planning scalars", {
  m <- tibble::tibble(fixture_id=sprintf("T:%02d",1:35),win=c(rep(.6,10),rep(.44,23),rep(.34,2)),
    draw=c(rep(.3,10),rep(.36,23),rep(.33,2)),lose=c(rep(.1,10),rep(.2,23),rep(.33,2)))
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  r <- rank_outcome_selections(prepare_outcome_selections(m,.45),cutoff)
  x <- AdaptOutcomeSelections(r,7L,requested_groups=8L,max_reuse=2L)
  expect_identical(x$allocation$role_minimums,c(4L,16L,8L))
  expect_identical(tabulate(x$allocation$ledger$allocated_role,3L),c(10L,17L,8L))
  expect_silent(.parlay_ranked_validate_receipt(x$ranked))
  for(value in list(0L,-1L,1.5,NA_real_,Inf,TRUE)) {
    expect_error(AdaptOutcomeSelections(r,7L,requested_groups=value))
    expect_error(AdaptOutcomeSelections(r,7L,max_reuse=value))
  }
})
