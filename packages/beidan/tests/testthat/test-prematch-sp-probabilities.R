cutoff <- list(issue_id="T",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
sp <- tibble::tibble(fixture_id="T:001",outcome=c("W","D","L"),
 quote_at=as.POSIXct("2026-10-03",tz="UTC"),sp_raw=c(2.5,2.6,2.7),source_url="fixture://frozen")
testthat::test_that("prematch SP normalization preserves identities and rejects unsafe evidence", {
 q <- PrematchSPProbabilities(sp,cutoff)
 testthat::expect_s3_class(q,"tbl_df")
 testthat::expect_equal(q$probability,(1/sp$sp_raw)/sum(1/sp$sp_raw))
 testthat::expect_equal(sum(q$probability),1)
 testthat::expect_identical(q$fixture_id,sp$fixture_id)
 testthat::expect_identical(q$outcome,sp$outcome)
 testthat::expect_error(PrematchSPProbabilities(sp,NULL))
 testthat::expect_error(PrematchSPProbabilities(sp[0,],cutoff))
 testthat::expect_error(PrematchSPProbabilities(sp[-1,],cutoff))
 testthat::expect_error(PrematchSPProbabilities(dplyr::bind_rows(sp,sp[1,]),cutoff))
 for(value in c(0,-1,Inf,NA_real_)) {
  bad <- sp;bad$sp_raw[1] <- value
  testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
 }
 bad <- sp;bad$quote_at[1] <- cutoff$cutoff_utc
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
 bad$quote_at[1] <- NA
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
 bad$quote_at[1] <- structure(-Inf,class=c("POSIXct","POSIXt"),tzone="UTC")
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
 bad <- sp;bad$sp_raw <- matrix(sp$sp_raw,ncol=1L)
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff),"plain")
 bad <- sp;bad$sp_raw <- as.Date(sp$sp_raw,origin="1970-01-01")
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff),"plain")
 bad <- sp;bad$fixture_id[1] <- NA_character_
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
 bad <- sp;bad$source_url[1] <- ""
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
 bad <- sp;bad$outcome[1] <- "X"
 testthat::expect_error(PrematchSPProbabilities(bad,cutoff))
})
