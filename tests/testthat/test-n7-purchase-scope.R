source(file.path('..','..','r','n7_purchase_scope.R'))
testthat::test_that('scope validation rejects missing bindings and malformed issue entries', {
 cfg<-jsonlite::fromJSON(file.path('..','..','config','top2_outside_validation.json'))
 hash<-cfg$catalog_sha256
 testthat::expect_length(n7_purchase_scope(cfg,hash),484)
 for(value in list(NULL,NA_character_,'',rep(hash,2),'bad')) {
  bad<-cfg;bad$catalog_sha256<-value
  testthat::expect_error(n7_purchase_scope(bad,hash))
 }
 for(value in list(c('001',NA_character_),list('001',NULL),c('001','001'),
                   c('001',''),c('001','x'),c(1,2),character())) {
  bad<-cfg;bad$issues<-value
  testthat::expect_error(n7_purchase_scope(bad,hash))
 }
 bad<-cfg;bad$excluded_drawdown_issues<-list('001',NULL)
 testthat::expect_error(n7_purchase_scope(bad,hash))
 for(value in list(NULL,NA_real_,c(1024,1024),2048)) {
  bad<-cfg;bad$budget_cny<-value
  testthat::expect_error(n7_purchase_scope(bad,hash))
 }
 cfg$issues<-c('002','001');cfg$excluded_drawdown_issues<-list()
 testthat::expect_identical(n7_purchase_scope(cfg,hash),c('001','002'))
 testthat::expect_error(n7_purchase_scope(cfg,paste(rep('a',64),collapse='')))
})
