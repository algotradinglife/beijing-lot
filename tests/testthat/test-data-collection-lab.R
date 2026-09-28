testthat::test_that("data lab skips the SP collector when there are no future fixtures", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  lines <- readLines(file.path(root,"quarto/data_collection_lab.qmd"),warn=FALSE)
  start <- which(lines=="#| label: data-lab-sp-settlements")
  end <- start+which(lines[(start+1L):length(lines)]=="```")[1L]
  code <- lines[(start+1L):(end-1L)]
  folder <- withr::local_tempdir()
  settlement_path <- file.path(folder,"settlements.rds")
  saveRDS(beidan::match_typed_empty("settlements"),settlement_path)
  context <- list2env(list(refresh_sp=TRUE,refresh_settlements=FALSE,
    schedule=tibble::tibble(kickoff_at=as.POSIXct("2000-01-01",tz="Asia/Shanghai")),
    run_dir=folder,backend=NULL,settlements_path=settlement_path,
    focus=tibble::tibble(fixture_key=character())),parent=globalenv())
  invisible(utils::capture.output(eval(parse(text=code),envir=context)))
  testthat::expect_identical(nrow(context$prematch_sp),0L)
  testthat::expect_identical(names(context$prematch_sp),names(beidan::match_typed_empty("prematch_sp")))
  testthat::expect_match(attr(context$prematch_sp,"diagnostics")$reason,"no_future_fixture")
  testthat::expect_true(file.exists(context$sp_path))
  testthat::expect_false(dir.exists(file.path(folder,"sp_raw")))
})
