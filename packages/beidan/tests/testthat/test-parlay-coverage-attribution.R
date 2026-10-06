#' Build one double-mask group with only its Top1 ticket purchased
#' @return Frozen synthetic evaluation; no IO.
CoverageFixture <- function() {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id="T:001",win=.45,draw=.35,lose=.20)
  ranked <- rank_outcome_selections(prepare_outcome_selections(m),cutoff)
  sp <- tibble::tibble(fixture_id="T:001",outcome=c("W","D","L"),
    quote_at=cutoff$cutoff_utc-60,sp_raw=c(3,3,3),source_url="fixture://coverage")
  settings <- parlay_constant_defaults(); settings$n_legs <- 1L; settings$issue_budget_cny <- 2
  settings$unit_cny <- 2; settings$payout_factor <- .65
  pool <- parlay_construct_role_groups(ranked,settings,2L,max_candidates=1L,prematch_sp=sp)
  return(parlay_select_groups(pool,objective="coverage",budget_cny=2,group_budget_cny=2,
    reuse_policy=list(max_reuse=NULL),overlap_policy=list(max_overlap=NULL))$evaluation)
}
test_that("coverage separates structural misses depth misses and hits without SP", {
  e <- CoverageFixture();c <- e$cutoff
  m <- tibble::tibble(issue_id="T",fixture_id="T:001",outcome="W",
    result_available_at=c$cutoff_utc+60,source_url="fixture://final-score")
  before <- e
  x <- ParlayCoverageAttribution(e,m,c$cutoff_utc+120)
  expect_identical(x$groups$status,"HIT")
  expect_identical(x$groups$winner_rank,1L)
  expect_equal(x$groups$legal_space,2)
  expect_equal(x$groups$purchased_tickets,1L)
  expect_identical(e,before)
  m$outcome <- "D";x <- ParlayCoverageAttribution(e,m,c$cutoff_utc+120)
  expect_identical(x$groups$status,"DEPTH_MISS")
  expect_identical(x$groups$winner_rank,2L)
  expect_true(x$groups$depth_blocked)
  m$outcome <- "L";x <- ParlayCoverageAttribution(e,m,c$cutoff_utc+120)
  expect_identical(x$groups$status,"STRUCTURE_MISS")
  expect_identical(x$groups$structural_misses,1L)
  expect_true(is.na(x$groups$winner_rank))
  expect_false(x$legs$admitted)
})
test_that("coverage rejects malformed chronology and keeps unknowns pending", {
  e <- CoverageFixture();c <- e$cutoff
  m <- tibble::tibble(issue_id="T",fixture_id="T:001",outcome="D",
    result_available_at=c$cutoff_utc+60,source_url="fixture://final-score")
  x <- ParlayCoverageAttribution(e,m,c$cutoff_utc+30)
  expect_identical(x$groups$status,"PENDING")
  expect_identical(x$groups$unknown_legs,1L)
  expect_identical(x$receipt$excluded_future_labels,1L)
  expect_identical(ParlayCoverageAttribution(e,m[0,],c$cutoff_utc+120)$groups$status,"PENDING")
  expect_error(ParlayCoverageAttribution(e,dplyr::bind_rows(m,m),c$cutoff_utc+120))
  bad <- m;bad$result_available_at <- c$cutoff_utc
  expect_error(ParlayCoverageAttribution(e,bad,c$cutoff_utc+120),"after cutoff")
  bad <- m;bad$result_available_at <- NA
  expect_error(ParlayCoverageAttribution(e,bad,c$cutoff_utc+120))
  bad <- m;bad$issue_id <- "OTHER"
  expect_error(ParlayCoverageAttribution(e,bad,c$cutoff_utc+120),"issue")
  expect_error(ParlayCoverageAttribution(e,m,c$cutoff_utc),"as_of")
  expect_error(ParlayCoverageAttribution(e,m,Sys.Date()),"as_of")
  bad <- e;bad$cutoff$cutoff_utc <- c$cutoff_utc+1
  expect_error(ParlayCoverageAttribution(bad,m,c$cutoff_utc+120))
})
test_that("coverage empty purchases keep typed tables", {
  e <- CoverageFixture();c <- e$cutoff
  empty <- parlay_select_groups(e$portfolio,objective="coverage",budget_cny=0,group_budget_cny=2,
    reuse_policy=list(max_reuse=NULL),overlap_policy=list(max_overlap=NULL))$evaluation
  m <- match_typed_empty("match_results")
  x <- ParlayCoverageAttribution(empty,m,c$cutoff_utc+120)
  expect_s3_class(x$groups,"tbl_df")
  expect_s3_class(x$legs,"tbl_df")
  expect_equal(nrow(x$groups),0L)
  expect_equal(nrow(x$legs),0L)
  expect_type(x$groups$winner_rank,"integer")
  expect_type(x$groups$depth_blocked,"logical")
  expect_true(is.na(x$receipt$max_result_available_at))
})

test_that("overlapping purchased masks credit a physical winner to its owning group", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id=c("T:001","T:002"),win=.60,draw=.25,lose=.15)
  ranked <- rank_outcome_selections(prepare_outcome_selections(m),cutoff)
  sp <- tidyr::expand_grid(fixture_id=m$fixture_id,outcome=c("W","D","L")) |>
    dplyr::mutate(quote_at=cutoff$cutoff_utc-60,sp_raw=3,source_url="fixture://coverage")
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 8
  pool <- parlay_construct_role_groups(ranked,settings,c(1L,1L),max_candidates=NULL,prematch_sp=sp)
  evaluation <- parlay_select_groups(pool,objective="coverage",budget_cny=8,group_budget_cny=2,
    reuse_policy=list(max_reuse=NULL),overlap_policy=list(max_overlap=NULL))$evaluation
  labels <- tibble::tibble(issue_id="T",fixture_id=m$fixture_id,outcome="W",
    result_available_at=cutoff$cutoff_utc+60,source_url="fixture://score")
  x <- beidan::ParlayCoverageAttribution(evaluation,labels,cutoff$cutoff_utc+120)
  expect_gt(nrow(x$groups),1L)
  expect_equal(sum(x$groups$status=="HIT"),1L)
  elsewhere <- x$groups |> dplyr::filter(status=="COVERED_ELSEWHERE")
  expect_gt(nrow(elsewhere),0L)
  expect_true(all(elsewhere$winner_owned_elsewhere))
  expect_false(any(elsewhere$purchased_winner))
  expect_true(all(elsewhere$structural_misses==0L & elsewhere$unknown_legs==0L))
  expect_true(all(is.finite(elsewhere$winner_rank)))
})

test_that("known mask misses outrank pending legs while blocked depth stays diagnostic", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id=c("T:001","T:002"),win=.45,draw=.35,lose=.20)
  ranked <- rank_outcome_selections(prepare_outcome_selections(m),cutoff)
  sp <- tidyr::expand_grid(fixture_id=m$fixture_id,outcome=c("W","D","L")) |>
    dplyr::mutate(quote_at=cutoff$cutoff_utc-60,sp_raw=3,source_url="fixture://coverage")
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 2
  pool <- parlay_construct_role_groups(ranked,settings,c(2L,2L),max_candidates=1L,prematch_sp=sp)
  evaluation <- parlay_select_groups(pool,objective="coverage",budget_cny=2,group_budget_cny=2,
    reuse_policy=list(max_reuse=NULL),overlap_policy=list(max_overlap=NULL))$evaluation
  labels <- tibble::tibble(issue_id="T",fixture_id="T:001",outcome="L",
    result_available_at=cutoff$cutoff_utc+60,source_url="fixture://score")
  x <- beidan::ParlayCoverageAttribution(evaluation,labels,cutoff$cutoff_utc+120)
  expect_identical(x$groups$status,"STRUCTURE_MISS")
  expect_identical(x$groups$structural_misses,1L)
  expect_identical(x$groups$unknown_legs,1L)
  expect_true(x$groups$depth_blocked)
  labels$outcome <- "D"
  x <- beidan::ParlayCoverageAttribution(evaluation,labels,cutoff$cutoff_utc+120)
  expect_identical(x$groups$status,"PENDING")
  expect_identical(x$groups$structural_misses,0L)
  expect_identical(x$groups$unknown_legs,1L)
  expect_true(x$groups$depth_blocked)
  expect_true(is.na(x$groups$winner_rank))
  labels$outcome <- "W"
  x <- beidan::ParlayCoverageAttribution(evaluation,labels,cutoff$cutoff_utc+120)
  expect_identical(x$groups$status,"PENDING")
  expect_false(x$groups$depth_blocked)
})
