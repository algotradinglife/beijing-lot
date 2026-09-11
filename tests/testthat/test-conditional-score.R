testthat::test_that("conditional report verifies bytes and preserves issue identifiers", {
  source(testthat::test_path("..", "..", "r", "conditional_score_report.R"))
  directory <- tempfile();dir.create(directory)
  on.exit(unlink(directory, recursive=TRUE), add=TRUE)
  files <- list(
    observations="issue,slot,provider_id,method\n001,1,0002,BASELINE\n",
    returns="issue,method,selection\n001,BASELINE,FIXED\n",
    training="issue,method\n001,GLOBAL\n",
    exclusions="issue,reason\n000,INSUFFICIENT\n",
    summary="method,score_logloss\nBASELINE,2.9\n")
  hashes <- list()
  for (name in names(files)) {
    path <- file.path(directory, paste0(name, ".csv"))
    writeLines(files[[name]],path)
    hashes[[paste0(name,".csv")]] <- digest::digest(file=path,algo="sha256")
  }
  jsonlite::write_json(list(historical_admission=FALSE,files=hashes),
                      file.path(directory,"receipt.json"),auto_unbox=TRUE)
  x <- suppressWarnings(read_conditional_score_report(directory))
  testthat::expect_s3_class(x$observations, "tbl_df")
  testthat::expect_identical(x$observations$issue, "001")
  testthat::expect_identical(x$observations$provider_id, "0002")
  writeLines("changed",file.path(directory,"summary.csv"))
  testthat::expect_error(read_conditional_score_report(directory),"Changed report artifact")
})

testthat::test_that("conditional summary uses aggregate stake weighted ROI", {
  source(testthat::test_path("..", "..", "r", "conditional_score_report.R"))
  observations <- tibble::tibble(issue=c("01","02"),slot=1L,method="BASELINE",
    conflict="AGREE",score_logloss=3,wdl_logloss=1,score_brier=.9,wdl_brier=.6,
    top1=c(TRUE,FALSE),top2=TRUE,p_D=.3,draw_actual=c(TRUE,FALSE),
    large_probability=.1,large_actual=FALSE,btts_probability=.5,btts_actual=TRUE,
    conditional_total_error=c(1,-1),conditional_total_logloss=1,
    conditional_total_brier=.5,actual_margin=0)
  returns <- tibble::tibble(issue=c("01","02"),method="BASELINE",selection="FIXED",
    stake=c(100,200),gross=c(200,100),net=c(100,-100),drawdown_cny=c(0,100))
  x <- summarise_conditional_score(observations,returns)
  testthat::expect_equal(x$money$roi_percent,0)
  testthat::expect_equal(x$probability$top1_percent,50)
  testthat::expect_equal(x$probability$draw_bias_pp,-20)
  testthat::expect_equal(x$money$maximum_drawdown_cny,100)
  testthat::expect_error(summarise_conditional_score(dplyr::bind_rows(observations,observations),returns),"Duplicate")
})
