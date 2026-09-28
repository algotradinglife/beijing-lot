testthat::test_that("betting sheet preserves exact truncated purchases and group amounts", {
  at <- lubridate::ymd_hms("2026-09-26 20:00:00",tz="Asia/Shanghai")
  fixtures <- tibble::tibble(issue_id="26098",fixture_id=c("26098:79","26098:120"),
    slot=c(79L,120L),provider_id=c("a","b"),kickoff_at=at+lubridate::dhours(8),
    handicap=c(-1L,0L),sale_state="open",source_url="fixture://test")
  projected <- list(cutoff=list(issue_id="26098",cutoff_utc=lubridate::with_tz(at,"UTC")),
    fixtures=fixtures,probabilities=tibble::tibble(fixture_id=rep(fixtures$fixture_id,each=3),
      outcome=rep(c("W","D","L"),2),probability=c(.65,.25,.10,.60,.30,.10)),
    prematch_sp=match_typed_empty("prematch_sp"),
    match_status=tibble::tibble(issue_id="26098",fixture_id=fixtures$fixture_id,
      status="scheduled",status_at=lubridate::with_tz(at-60,"UTC"),
      available_at=lubridate::with_tz(at-60,"UTC"),source_url="fixture://status"))
  cfg <- parlay_strategy_config(parlay_settings(n_legs=2L),patterns=list(p22=c(2L,2L)),spend_limit_cny=6)
  result <- parlay_build_plan(projected,cfg)
  schedule <- dplyr::transmute(fixtures,fixture_key=fixture_id,slot,
    home_name=c("甲<script>","乙"),away_name=c("丙","丁"),handicap,kickoff_at)
  sheet <- parlay_betting_sheet(result,schedule)
  testthat::expect_equal(nrow(sheet$groups),1L)
  testthat::expect_equal(nrow(sheet$tickets),3L)
  testthat::expect_equal(sum(sheet$tickets$cost_cny),6)
  testthat::expect_equal(sum(sheet$groups$cost_cny),6)
  testthat::expect_equal(nrow(sheet$ticket_legs),6L)
  testthat::expect_setequal(sheet$tickets$ticket_id,result$funded$purchases$ticket_id)
  testthat::expect_equal(sum(sheet$matches$selected),4L) # union is 4, but only 3 physical tickets
  testthat::expect_equal(dplyr::filter(sheet$matches,fixture_id=="26098:79")$probability,c(.65,.25,.10))
  testthat::expect_identical(lubridate::tz(sheet$matches$kickoff_at),"Asia/Shanghai")
  testthat::expect_identical(parlay_betting_sheet(result,schedule[2:1,]),sheet)
  testthat::expect_error(parlay_betting_sheet(result,schedule[1,]),"missing selected")
  testthat::expect_error(parlay_betting_sheet(result,dplyr::bind_rows(schedule,schedule)),"duplicat")
  testthat::expect_error(parlay_betting_sheet(result,schedule[,1:2]),"lacks")
  bad <- result; bad$funded$purchases$stake_cny[1] <- 20
  testthat::expect_error(parlay_betting_sheet(bad,schedule),"ledger mismatch")
  bad <- result; bad$plan$ticket_legs <- bad$plan$ticket_legs[-1,]
  testthat::expect_error(parlay_betting_sheet(bad,schedule),"reconcile")
  bad <- result
  bad$plan$ticket_legs <- dplyr::filter(bad$plan$ticket_legs, ticket_id != result$funded$purchases$ticket_id[1])
  testthat::expect_error(parlay_betting_sheet(bad,schedule),"reconcile")
  cfg$spend_limit_cny <- 0
  testthat::expect_error(parlay_betting_sheet(parlay_build_plan(projected,cfg),schedule),"selected tickets")
})
