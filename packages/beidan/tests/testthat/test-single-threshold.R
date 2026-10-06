test_that("fixed single threshold preserves defaults and strict boundaries", {
  expect_identical(classify_outcomes(.46,.30,.24),classify_outcomes(.46,.30,.24,.50))
  expect_identical(attr(classify_outcomes(.46,.30,.24,.45),"base_role"),1L)
  expect_identical(classify_outcomes(.46,.30,.24,.45)[[1]],"win")
  expect_identical(attr(classify_outcomes(.45,.31,.24,.45),"base_role"),2L)
  expect_identical(attr(classify_outcomes(.34,.33,.33,.45),"base_role"),3L)
  for(t in list(NA_real_,Inf,0,.32,1.1,c(.45,.50),".45",TRUE)) {
    expect_error(classify_outcomes(.46,.30,.24,t))
    expect_error(prepare_outcome_selections(tibble::tibble(fixture_id=character(),win=double(),draw=double(),lose=double()),t))
  }
  m <- tibble::tibble(fixture_id="T:001",win=.46,draw=.30,lose=.24)
  expect_true(all(prepare_outcome_selections(m,.45)$base_role==1L))
  expect_true(all(prepare_outcome_selections(m)$base_role==2L))
})
test_that("ranking verifies threshold context and rejects posthoc mutation", {
 m <- tibble::tibble(fixture_id="T:001",win=.46,draw=.30,lose=.24)
 cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
 s <- prepare_outcome_selections(m,.45)
 r <- rank_outcome_selections(s,cutoff)
 expect_equal(attr(r,"single_threshold"),.45)
 expect_identical(attr(r,"input_snapshot"),s)
 attr(s,"single_threshold") <- .50
 expect_error(rank_outcome_selections(s,cutoff),"recomputed")
 attr(s,"single_threshold") <- NULL
 expect_error(rank_outcome_selections(s,cutoff),"missing single_threshold")
})

test_that("downstream receipt rejects changed or missing ranked threshold", {
 m <- tibble::tibble(fixture_id="T:001",win=.46,draw=.30,lose=.24)
 cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
 r <- rank_outcome_selections(prepare_outcome_selections(m,.45),cutoff)
 expect_silent(.parlay_ranked_validate_receipt(r))
 attr(r,"single_threshold") <- .50
 expect_error(.parlay_ranked_validate_receipt(r),"single_threshold")
 attr(r,"single_threshold") <- NULL
 expect_error(.parlay_ranked_validate_receipt(r),"single_threshold")
})
