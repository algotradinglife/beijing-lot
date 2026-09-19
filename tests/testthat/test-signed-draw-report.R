testthat::test_that('signed draw report freezes predictions before evaluation labels', {
 s<-readLines(file.path('..','..','quarto','194_signed_draw_comparison.qmd'))
 testthat::expect_true(grep('^labels<-',s)>grep('saveRDS(z,',s,fixed=TRUE))
 testthat::expect_true(any(grepl("read_diagnostic_epoch_fixtures",s,fixed=TRUE)))
 testthat::expect_true(any(grepl("draw_refresh_prior_history_json",s,fixed=TRUE)))
 testthat::expect_true(any(grepl("edges<-c(-rev(edges[-1]),edges)",s,fixed=TRUE)))
})
