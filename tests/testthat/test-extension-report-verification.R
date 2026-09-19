source(file.path('..','..','r/extension_report_verification.R'))
test_that('report requires complete passing replay receipt, including scalar counts',{
 a<-paste(rep('a',64),collapse='');b<-paste(rep('b',64),collapse='')
 x<-list(status='PASS',source_receipt_sha256=a,implementation_sha256=b,independent_official_settlement=TRUE,issues=50,policy_rows=300,future_history_invariance=50,base_replays=50,selective_replays=250)
 expect_true(extension_report_verification(x,a,b,50))
 for(n in names(x)){bad<-x;bad[[n]]<-NULL;expect_error(extension_report_verification(bad,a,b,50))}
 expect_error(extension_report_verification(list(independent_official_settlement=TRUE),a,b,50))
 x$issues<-c(50,50);expect_error(extension_report_verification(x,a,b,50))
})
