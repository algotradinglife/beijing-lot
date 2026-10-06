test_that("batch enumeration preserves physical order and overlapping-candidate ownership", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-09-25",tz="UTC"))
  ids <- c("T:01","T:010","T:2","T:3")
  legs <- tibble::tibble(group_id="G",fixture_id=ids,leg_order=1:4)
  p <- tidyr::expand_grid(fixture_id=ids,outcome=c("W","D","L")) |>
    dplyr::mutate(probability=rep(c(.6,.3,.1),4))
  supports <- tidyr::expand_grid(candidate_id=c("G|wide","G|narrow"),
    fixture_id=ids,outcome=c("W","D","L")) |>
    dplyr::mutate(allowed=outcome!="L" &
      (candidate_id=="G|wide" | fixture_id==ids[1] | outcome=="W"),
      preference=as.integer(match(outcome,c("W","D","L"))))
  result <- parlay_enumerate_tickets(legs,p,cutoff,supports,4L)
  # Binary counting independently specifies first-leg-fastest enumeration.
  expected <- character(16);probability <- numeric(16)
  for(i in 0:15) {
    codes <- bitwAnd(bitwShiftR(i,0:3),1L)+1L
    expected[i+1L] <- parlay_physical_ticket_key(ids,codes)
    probability[i+1L] <- prod(c(.6,.3)[codes])
  }
  expect_identical(result$tickets$ticket_id,expected)
  expect_equal(result$tickets$probability,probability,tolerance=1e-15)
  expect_identical(result$ticket_legs$ticket_id,rep(expected,each=4))
  expect_identical(result$ticket_legs$fixture_id,rep(ids,times=16))
  expect_identical(result$candidate_tickets$candidate_id,
    c(rep("G|wide",16),rep("G|narrow",2)))
  expect_identical(tail(result$candidate_tickets$ticket_id,2),expected[1:2])
  expect_identical(result$tickets$group_id,rep("G",16))
  expect_true(all(is.na(result$tickets$sp_product_est)))
  expect_true(all(is.na(result$tickets$ev_net_est)))
  expect_identical(nrow(result$ticket_legs),64L)
  # A one-leg/one-ticket matrix must keep its dimensions at the R boundary.
  single_legs <- legs[1,]
  single_support <- supports |>
    dplyr::filter(candidate_id=="G|narrow",fixture_id==ids[1]) |>
    dplyr::mutate(allowed=outcome=="W")
  single <- parlay_enumerate_tickets(single_legs,p,cutoff,single_support,1L)
  expect_identical(single$tickets$ticket_id,paste0(ids[1],":1"))
  expect_identical(single$ticket_legs$outcome,"W")
  expect_equal(single$tickets$probability,.6)
})
