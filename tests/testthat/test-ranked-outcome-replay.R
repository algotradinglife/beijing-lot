root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
source(file.path(root,"r/ranked_outcome_replay.R"))
devtools::load_all(file.path(root,"packages/beidan"),quiet=TRUE)

# One fixture with two legal double variants makes the owned protection explicit.
ReplayCase <- function(group_budget_cny=NULL,prematch_sp=beidan::match_typed_empty("prematch_sp")) {
  settings <- beidan::parlay_settings()
  settings$n_legs <- 1L
  probabilities <- tibble::tibble(fixture_id="T:1",outcome=c("W","D","L"),
    probability=c(.45,.22,.33))
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-09-25",tz="UTC"))
  return(ReplayRankedOutcomes(probabilities,cutoff,settings,2L,prematch_sp,
    group_budget_cny,list(max_reuse=4L),list(max_overlap=1L)))
}

test_that("current replay freezes optional directions and never reads labels for selection", {
  replay <- ReplayCase()
  before <- rlang::hash(replay)
  labels <- tibble::tibble(issue_id="T",fixture_id="T:1",outcome="W",
    settled_sp=2,label_available_at=as.POSIXct("2026-09-26",tz="UTC"),
    status="settled",source_url="https://example.test/settlement")
  report <- DiagnoseRankedReplay(replay,labels,as.POSIXct("2026-09-27",tz="UTC"))
  expect_identical(rlang::hash(replay),before)
  expect_equal(nrow(replay$evaluation$purchases),3L)
  expect_equal(replay$evaluation$summary$spent_cny,6)
  expect_equal(sum(report$returns$ticket_returns$payout_cny),2*.65*2)
  expect_true(report$protection$draw_protected)
  expect_equal(report$protection$purchased_groups,2L)
  expect_true(report$protection$complementary_bought)
  expect_equal(report$protection$purchased_directions,2L)
  labels$outcome <- "D"
  changed <- DiagnoseRankedReplay(replay,labels,as.POSIXct("2026-09-27",tz="UTC"))
  expect_identical(rlang::hash(replay),before)
  expect_gt(nrow(changed$misses),0L)
  pending <- DiagnoseRankedReplay(replay,labels,as.POSIXct("2026-09-25",tz="UTC"))
  expect_true(all(pending$returns$ticket_returns$status=="PENDING"))
  expect_error(ReplayRankedOutcomes(replay$pool$probabilities,NULL,
    replay$pool$settings,2L,beidan::match_typed_empty("prematch_sp"),NULL,
    list(max_reuse=2L),list(max_overlap=1L)),"cutoff")
})

test_that("partial purchases do not imply all allowed protective outcomes were bought", {
  replay <- ReplayCase(group_budget_cny=2)
  report <- DiagnoseRankedReplay(replay,beidan::match_typed_empty("settlements"),
    as.POSIXct("2026-09-27",tz="UTC"))
  expect_equal(report$protection$admitted_directions,2L)
  expect_identical(report$protection$draw_protected,
    any(replay$evaluation$plan$ticket_legs$outcome=="D"))
  expect_false(report$protection$all_three_bought)
  expect_false(report$protection$complementary_bought)
  expect_equal(report$protection$purchased_directions,2L)
  expect_equal(dplyr::n_distinct(replay$evaluation$plan$ticket_legs$outcome),2L)
  expect_true("W" %in% replay$evaluation$plan$ticket_legs$outcome)
})

test_that("replay applies whole-fixture Top1 SP filtering and carries its receipt", {
  quote <- tibble::tibble(fixture_id="T:1",outcome="W",
    quote_at=as.POSIXct("2026-09-24",tz="UTC"),sp_raw=1.99,
    source_url="synthetic://SP")
  excluded <- ReplayCase(prematch_sp=quote)
  expect_identical(nrow(excluded$filtered$matches),0L)
  expect_equal(nrow(excluded$filtered$excluded),1L)
  expect_identical(nrow(excluded$selections),0L)
  expect_identical(nrow(excluded$evaluation$purchases),0L)
  expect_equal(excluded$evaluation$summary$spent_cny,0)
  quote$sp_raw <- 2
  retained <- ReplayCase(prematch_sp=quote)
  expect_equal(nrow(retained$filtered$matches),1L)
  expect_identical(attr(retained$ranked,"filter_receipt"),retained$filtered$receipt)
  missing <- ReplayCase()
  expect_true(missing$filtered$audit$missing_sp)
})

test_that("settlement refresh rejects changed original purchase or source bytes", {
  directory <- withr::local_tempdir()
  decision <- file.path(directory,"decision.rds")
  input <- file.path(directory,"input.rds")
  saveRDS(list(purchases="original"),decision)
  saveRDS(list(probability=.4),input)
  receipt <- list(decision_hash=digest::digest(decision,file=TRUE,algo="sha256"),
    input_sha256=digest::digest(input,file=TRUE,algo="sha256"))
  expect_true(VerifyRankedReplayReceipt(decision,input,receipt))
  expect_error(VerifyRankedReplayReceipt(decision,input,NULL),"Missing original")
  saveRDS(list(purchases="altered"),decision)
  expect_error(VerifyRankedReplayReceipt(decision,input,receipt),"hash mismatch")
  saveRDS(list(purchases="original"),decision)
  saveRDS(list(probability=.5),input)
  expect_error(VerifyRankedReplayReceipt(decision,input,receipt),"hash mismatch")
})
