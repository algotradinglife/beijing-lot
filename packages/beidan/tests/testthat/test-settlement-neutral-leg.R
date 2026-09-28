test_that("explicit all-option SP1 is neutral in parlays, never an inferred refund", {
  time <- as.POSIXct("2026-09-27 12:00:00", tz="UTC")
  labels <- tibble::tibble(issue_id="26098", fixture_id=c("26098:1","26098:2"),
    outcome=c("ALL","W"), settled_sp=c(1,3), label_available_at=time,
    status=c("all_options_one","settled"), source_url="https://example.test/source")
  plan <- list(issue_id="26098", constants=list(n_legs=2L,unit_cny=2,payout_factor=.65),
    funded=tibble::tibble(ticket_id=c("a","b","c"),group_id="g"),
    ticket_legs=tibble::tibble(ticket_id=rep(c("a","b","c"),each=2),
      fixture_id=rep(labels$fixture_id,3),outcome=c("W","W","D","W","L","L")))
  x <- parlay_settle_plan(plan,labels,time)
  expect_identical(x$ticket_returns$status,c("WON","WON","LOST"))
  expect_equal(x$ticket_returns$payout_cny,c(3.9,3.9,0))
  expect_equal(x$issue_returns$stake_cny,6)
  expect_equal(x$issue_returns$net_cny,1.8)
  expect_identical(parlay_settle_plan(plan,labels[1,],time)$ticket_returns$status,rep("PENDING",3))
  expect_identical(parlay_settle_plan(plan,labels,time-1)$ticket_returns$status,rep("PENDING",3))
  bad <- labels; bad$settled_sp[1] <- 2
  expect_error(parlay_settle_plan(plan,bad,time),"ALL and SP=1")
  bad <- labels; bad$outcome[1] <- "W"
  expect_error(parlay_settle_plan(plan,bad,time),"ALL and SP=1")
  bad <- labels; bad$status[1] <- "cancelled"
  expect_identical(parlay_settle_plan(plan,bad,time)$ticket_returns$status,rep("SPECIAL",3))
  all_void <- labels; all_void$status[] <- "all_options_one"; all_void$outcome[] <- "ALL"; all_void$settled_sp[] <- 1
  expect_identical(parlay_settle_plan(plan,all_void,time)$ticket_returns$status,rep("SPECIAL",3))
  single <- plan; single$constants$n_legs <- 1L; single$ticket_legs <- plan$ticket_legs[c(1,3,5),]
  expect_identical(parlay_settle_plan(single,labels,time)$ticket_returns$status,rep("SPECIAL",3))
})
