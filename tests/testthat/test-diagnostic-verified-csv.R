source(file.path('..','..','r','diagnostic_verified_csv.R'))
testthat::test_that('settlement parsing uses verified bytes and explicit identifier types', {
 path<-tempfile();writeLines(c('issue,amount','001,2'),path)
 sha<-digest::digest(file=path,algo='sha256')
 x<-diagnostic_read_verified_csv(path,sha,readr::cols(issue='c',amount='d'))
 testthat::expect_identical(x$issue,'001');testthat::expect_equal(x$amount,2)
 # File replacement after a previous successful check must fail at consumption.
 writeLines(c('issue,amount','001,200'),path)
 testthat::expect_error(diagnostic_read_verified_csv(path,sha,readr::cols(issue='c',amount='d')))
 testthat::expect_error(diagnostic_read_verified_csv(path,'bad',readr::cols()))
 writeLines(c('issue,amount','001,not-a-number'),path)
 testthat::expect_error(suppressWarnings(diagnostic_read_verified_csv(path,
  digest::digest(file=path,algo='sha256'),readr::cols(issue='c',amount='d'))))
})
