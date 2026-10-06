test_that("allocation implements all six transfers with original primary probabilities", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  probabilities <- list(c(.6,.3,.1),c(.45,.35,.2),c(.34,.33,.33))
  for (from in 1:3) for (to in setdiff(1:3,from)) {
    p <- probabilities[[from]]
    m <- tibble::tibble(fixture_id="T:001",win=p[1],draw=p[2],lose=p[3])
    a <- AdaptiveRoleAllocation(m,cutoff,as.integer(to))
    expect_identical(a$ledger$native_role,as.integer(from))
    expect_identical(a$ledger$allocated_role,as.integer(to))
    expect_equal(a$ledger$coverage_after,sum(p[seq_len(to)]))
    expect_equal(a$ledger$gain,sum(p[seq_len(to)])-sum(p[seq_len(from)]))
  }
})
test_that("allocation is minimal deterministic and never drains demanded categories", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id=c("T:B","T:A","T:C"),
    win=c(.6,.6,.45),draw=c(.3,.3,.35),lose=c(.1,.1,.2))
  a <- AdaptiveRoleAllocation(m,cutoff,c(2L,2L,1L))
  expect_identical(a$ledger$allocated_role,c(2L,1L,2L))
  expect_identical(a,AdaptiveRoleAllocation(m[3:1,],cutoff,c(1L,2L,2L)))
  expect_identical(m$fixture_id,c("T:B","T:A","T:C"))
  b <- AdaptiveRoleAllocation(m,cutoff,c(2L,1L,1L))
  expect_identical(b$ledger$native_role,b$ledger$allocated_role)
  changed <- m;changed$draw[1] <- .31;changed$lose[1] <- .09
  expect_false(identical(a$input_hash,AdaptiveRoleAllocation(changed,cutoff,c(2L,2L,1L))$input_hash))
  attr(m,"unrelated") <- "provenance"
  expect_identical(a,AdaptiveRoleAllocation(m,cutoff,c(2L,2L,1L)))
})
test_that("allocation validates boundaries and reports typed shortages", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id="T:001",win=.6,draw=.3,lose=.1)
  a <- AdaptiveRoleAllocation(m,cutoff,c(2L,2L))
  expect_identical(a$status,"insufficient_fixtures")
  expect_identical(a$ledger$allocated_role,a$ledger$native_role)
  e <- AdaptiveRoleAllocation(m[0,],cutoff,2L)
  expect_s3_class(e$ledger,"tbl_df")
  expect_equal(nrow(e$ledger),0L)
  expect_identical(vapply(e$ledger,typeof,character(1)),c(fixture_id="character",
    native_role="integer",allocated_role="integer",coverage_before="double",
    coverage_after="double",gain="double"))
  for (pattern in list(integer(),0L,4L,1.5,NA_real_,Inf,"2",TRUE,
                       matrix(2),as.Date("2026-10-04"))) {
    expect_error(AdaptiveRoleAllocation(m,cutoff,pattern))
  }
  for (id in c("",NA_character_)) {
    bad <- m;bad$fixture_id <- id
    expect_error(AdaptiveRoleAllocation(bad,cutoff,2L))
  }
  expect_error(AdaptiveRoleAllocation(dplyr::bind_rows(m,m),cutoff,2L))
  for (value in c(NA_real_,Inf,-.1,.7)) {
    bad <- m;bad$win <- value
    expect_error(AdaptiveRoleAllocation(bad,cutoff,c(2L,2L)))
  }
  expect_error(AdaptiveRoleAllocation(m,NULL,2L))
  expect_error(AdaptiveRoleAllocation(m,cutoff,2L,NA_real_))
})

test_that("reuse supply promotes surplus doubles before singles without changing probabilities", {
  cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id=sprintf("T:%02d",1:35),
    win=c(rep(.6,10),rep(.44,23),rep(.34,2)),
    draw=c(rep(.3,10),rep(.36,23),rep(.33,2)),
    lose=c(rep(.1,10),rep(.2,23),rep(.33,2)))
  a <- AdaptiveRoleAllocation(m,cutoff,c(3L,3L,2L,2L,2L,2L,1L),.45,c(4L,16L,8L))
  expect_identical(tabulate(a$ledger$allocated_role,3L),c(10L,17L,8L))
  changed <- a$ledger[a$ledger$native_role!=a$ledger$allocated_role,]
  expect_equal(nrow(changed),6L)
  expect_true(all(changed$native_role==2L & changed$allocated_role==3L))
  expect_equal(changed$coverage_after,rep(1,6))
  expect_equal(changed$gain,rep(.2,6))
  selections <- prepare_outcome_selections(m,.45,role_allocation=a)
  expect_equal(selections$win,m$win[match(selections$fixture_id,m$fixture_id)])
  bad <- a; bad$role_minimums <- c(4L,16L,7L)
  expect_error(prepare_outcome_selections(m,.45,role_allocation=bad))
  expect_identical(AdaptiveRoleAllocation(m,cutoff,3L,.45,c(40L,0L,0L))$status,"insufficient_fixtures")
  for (minimum in list(c(1,2),c(1,2,NA),c(1,-1,2),c(1,2,1.5),matrix(1,1,3)))
    expect_error(AdaptiveRoleAllocation(m,cutoff,3L,.45,minimum),"role_minimums")
})
