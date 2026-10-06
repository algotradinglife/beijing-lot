testthat::test_that("raw Beidan plan remains independent of euro/total availability and values", {
  fx <- epoch_fixture(2L)
  fx$inputs$prematch_sp <- tibble::tibble(fixture_id=rep(fx$inputs$fixtures$fixture_id,each=3L),
    outcome=rep(c("W","D","L"),2L),quote_at=fx$cutoff$cutoff_utc-60,
    sp_raw=rep(c(2,4,8),2L),source_url="fixture://raw-sp")
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 8
  settings$sp_threshold <- .Machine$double.xmax
  session_before <- parlay_settings()
  before <- fx$inputs
  a <- beidan::BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,max_candidates=2L)
  absent <- fx$inputs;absent$euro <- NULL;absent$totals <- NULL
  b <- beidan::BuildProbabilityPlan(absent,fx$cutoff,settings,4,max_candidates=2L)
  foreign <- fx$inputs;foreign$euro$odds_home <- 30;foreign$euro$odds_away <- 1.1
  foreign$totals$over_decimal <- 1.01
  c <- beidan::BuildProbabilityPlan(foreign,fx$cutoff,settings,4,max_candidates=2L)
  testthat::expect_identical(a$plan,b$plan)
  testthat::expect_identical(a$plan,c$plan)
  testthat::expect_identical(a$probability_base,"beidan")
  testthat::expect_identical(a$epoch$probability_base,a$probability_base)
  testthat::expect_identical(a$projected$probability_base,a$probability_base)
  testthat::expect_equal(a$projected$probabilities$probability[a$projected$probabilities$outcome=="W"],rep(4/7,2))
  testthat::expect_equal(a$adapted$allocation$ledger$allocated_role,c(2L,1L))
  testthat::expect_identical(a$status,"BET")
  testthat::expect_s3_class(a$selection,"tbl_df")
  testthat::expect_lte(sum(a$plan$evaluation$purchases$cost_cny),8)
  testthat::expect_true(all(a$selection$new_cost_cny<=4))
  testthat::expect_identical(fx$inputs,before)
  testthat::expect_identical(parlay_settings(),session_before)
})
testthat::test_that("DC and mixed admit only their declared market sources", {
  fx <- epoch_fixture(2L)
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 8
  policy <- list(euro=default_euro(),totals=default_totals())
  dc <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,base="dc",market_policy=policy,max_candidates=2L)
  mix <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,base="mixed",bd_weight=.75,market_policy=policy,max_candidates=2L)
  bd <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,max_candidates=2L)
  testthat::expect_identical(dc$epoch$probability_base,"dc")
  testthat::expect_identical(mix$epoch$probability_base,"mixed")
  testthat::expect_equal(mix$projected$probabilities,
    BlendMatchProbabilities(dc$projected$probabilities,bd$projected$probabilities,.75))
  for (x in list(dc,mix,bd)) {
    p <- .ParlayRiskPrepare(x$plan$evaluation,x$cutoff)$probabilities
    expected <- x$projected$probabilities |> dplyr::filter(fixture_id %in% p$fixture_id)
    testthat::expect_equal(.ParlayRiskCanonical(p,c("fixture_id","outcome")),
      .ParlayRiskCanonical(expected,c("fixture_id","outcome")))
  }
  missing <- fx$inputs;missing$euro <- match_typed_empty("euro");missing$totals <- match_typed_empty("totals")
  b <- BuildProbabilityPlan(missing,fx$cutoff,settings,4,max_candidates=2L)
  d <- BuildProbabilityPlan(missing,fx$cutoff,settings,4,base="dc",market_policy=policy,max_candidates=2L)
  testthat::expect_equal(nrow(b$epoch$fixtures),2L)
  testthat::expect_equal(nrow(d$epoch$fixtures),0L)
  testthat::expect_identical(d$status,"NO_BET")
  testthat::expect_true(all(grepl("euro",d$epoch$exclusions$reason)))
  testthat::expect_error(BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,base="dc"),"market_policy")
})
testthat::test_that("fixed target uses allocation and public coverage diagnoses depth without settlement SP", {
  fx <- epoch_fixture(2L)
  fx$inputs$prematch_sp <- tibble::tibble(fixture_id=rep(fx$inputs$fixtures$fixture_id,each=3L),
    outcome=rep(c("W","D","L"),2L),quote_at=fx$cutoff$cutoff_utc-60,
    sp_raw=rep(c(2,4,8),2L),source_url="fixture://raw-sp")
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 4
  x <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,pattern=c(3L,3L),max_candidates=2L)
  testthat::expect_identical(x$adapted$pattern,c(3L,3L))
  testthat::expect_identical(x$adapted$allocation$ledger$allocated_role,c(3L,3L))
  labels <- tibble::tibble(issue_id=fx$cutoff$issue_id,fixture_id=fx$inputs$fixtures$fixture_id,
    outcome="L",result_available_at=fx$cutoff$cutoff_utc+60,source_url="fixture://outcome")
  d <- beidan::ParlayCoverageAttribution(x$plan$evaluation,labels,fx$cutoff$cutoff_utc+120)
  testthat::expect_identical(d$groups$status,"DEPTH_MISS")
  testthat::expect_equal(d$groups$legal_space,9)
  testthat::expect_identical(d$groups$winner_rank,9L)
  testthat::expect_identical(d$groups$purchased_tickets,2L)
  testthat::expect_true(all(d$legs$admitted))
  testthat::expect_false("sp" %in% names(labels))
})
testthat::test_that("raw cutoff-bound plan supports independent exact replay and semantic cutoff identity", {
  fx <- epoch_fixture(2L)
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 8
  cutoff <- list(issue_id=fx$cutoff$issue_id,cutoff_utc=fx$cutoff$cutoff_utc)
  x <- BuildProbabilityPlan(fx$inputs,cutoff,settings,4,max_candidates=2L)
  snap <- x$receipt$input_snapshot
  replay <- do.call(BuildProbabilityPlan,c(snap[c("inputs","cutoff")],snap$parameters))
  testthat::expect_identical(replay,x)
  bare <- x;bare$receipt <- NULL
  testthat::expect_identical(x$receipt$output_hash,rlang::hash(bare))
  testthat::expect_identical(x$receipt$input_hash,rlang::hash(snap))
  testthat::expect_identical(x$receipt$parameters$base,"beidan")
  changed <- fx$cutoff;changed$issue_id <- "wrong"
  testthat::expect_error(BuildProbabilityPlan(fx$inputs,changed,settings,4),"cutoff")
})
testthat::test_that("post-cutoff source mutation cannot alter masks support or purchased tickets", {
  fx <- epoch_fixture(2L)
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 8
  x <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,max_candidates=2L)
  future <- fx$inputs$prematch_sp;future$quote_at <- fx$cutoff$cutoff_utc+1;future$sp_raw <- 100
  status <- fx$inputs$match_status[1,];status$status <- "cancelled"
  status$status_at <- fx$cutoff$cutoff_utc+1;status$available_at <- fx$cutoff$cutoff_utc+1
  changed <- fx$inputs
  changed$prematch_sp <- dplyr::bind_rows(changed$prematch_sp,future)
  changed$match_status <- dplyr::bind_rows(changed$match_status,status)
  y <- BuildProbabilityPlan(changed,fx$cutoff,settings,4,max_candidates=2L)
  testthat::expect_identical(x$projected$probabilities,y$projected$probabilities)
  testthat::expect_identical(x$ranked,y$ranked)
  testthat::expect_identical(x$adapted,y$adapted)
  testthat::expect_identical(x$pool,y$pool)
  testthat::expect_identical(x$plan,y$plan)
  testthat::expect_false(identical(x$receipt$cache_key,y$receipt$cache_key))
})
testthat::test_that("empty or unaffordable pools stay no-bet and invalid parameters fail", {
  fx <- epoch_fixture(2L)
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 8
  absent <- fx$inputs;absent$match_status <- match_typed_empty("match_status")
  e <- BuildProbabilityPlan(absent,fx$cutoff,settings,4,max_candidates=2L)
  testthat::expect_identical(e$status,"NO_BET")
  testthat::expect_s3_class(e$selection,"tbl_df")
  testthat::expect_equal(nrow(e$selection),0L)
  testthat::expect_type(e$filtered$matches$win,"double")
  testthat::expect_identical(e$adapted$allocation$status,"insufficient_fixtures")
  z <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,0,max_candidates=2L)
  testthat::expect_identical(z$status,"NO_BET")
  for(cap in list(NA_real_,Inf,-1,matrix(4),as.Date("1970-01-01"))) {
    testthat::expect_error(BuildProbabilityPlan(absent,fx$cutoff,settings,cap))
  }
  testthat::expect_error(BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,single_threshold=matrix(.45)))
  testthat::expect_error(BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,pattern=c(1L)))
  bad <- fx$inputs;bad$prematch_sp <- bad$prematch_sp[-1,]
  testthat::expect_error(BuildProbabilityPlan(bad,fx$cutoff,settings,4))
})

testthat::test_that("builder forwards the minimum SP policy and binds exact replay", {
  fx <- epoch_fixture(2L)
  fx$inputs$prematch_sp <- tibble::tibble(fixture_id=rep(fx$inputs$fixtures$fixture_id,each=3L),
    outcome=rep(c("W","D","L"),2L),quote_at=fx$cutoff$cutoff_utc-60,
    sp_raw=rep(c(1.9,4,8),2L),source_url="fixture://sp19")
  s <- parlay_constant_defaults(); s$n_legs <- 2L; s$issue_budget_cny <- 8
  x <- BuildProbabilityPlan(fx$inputs,fx$cutoff,s,4,top1_sp_threshold=1.9,max_candidates=2L)
  y <- BuildProbabilityPlan(fx$inputs,fx$cutoff,s,4,max_candidates=2L)
  expect_equal(nrow(x$filtered$matches),2)
  expect_equal(nrow(y$filtered$matches),0)
  expect_identical(x$receipt$parameters$top1_sp_threshold,1.9)
  expect_identical(x,do.call(BuildProbabilityPlan,c(list(inputs=fx$inputs,cutoff=fx$cutoff),x$receipt$parameters)))
})

testthat::test_that("plan derives role supply from budget and reuse and permits underspend", {
  fx <- epoch_fixture(6L)
  fx$inputs$prematch_sp <- tibble::tibble(fixture_id=rep(fx$inputs$fixtures$fixture_id,each=3L),
    outcome=rep(c("W","D","L"),6L),quote_at=fx$cutoff$cutoff_utc-60,
    sp_raw=rep(c(2,4,8),6L),source_url="fixture://raw-sp")
  settings <- parlay_constant_defaults();settings$n_legs <- 2L;settings$issue_budget_cny <- 16
  settings$sp_threshold <- .Machine$double.xmax
  x <- BuildProbabilityPlan(fx$inputs,fx$cutoff,settings,4,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L))
  expect_identical(x$adapted$allocation$role_minimums,c(3L,3L,0L))
  expect_identical(tabulate(x$adapted$allocation$ledger$allocated_role,3L),c(3L,3L,0L))
  counts <- x$plan$evaluation$plan$ticket_legs |>
    dplyr::left_join(x$plan$evaluation$purchases |> dplyr::select(ticket_id,group_id),
      by="ticket_id",relationship="many-to-one") |>
    dplyr::distinct(group_id,fixture_id) |> dplyr::count(fixture_id)
  expect_true(all(counts$n<=1L))
  expect_gt(x$plan$evaluation$summary$unspent_cny,0)
  expect_lte(x$plan$evaluation$summary$spent_cny,12)
})
