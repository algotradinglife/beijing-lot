source('../../r/joint_ticket_calibration.R')
testthat::test_that('ticket calibration preserves stakes and expected versus observed counts',{
 x<-tibble::tibble(issue=c('01','01','02'),policy='JOINT',sleeve_id=0,
 ticket_col_idx=1:3,prob=c(.001,.002,.004),hit=c(FALSE,TRUE,FALSE),
 gross=c(0,300,0),stake=2,stage=c('A','A','B'),payout_hat=c(100,200,500))
 z<-joint_ticket_calibration(x,c(0,.002,1))
 a<-dplyr::filter(z$bins,stage=='ALL')
 testthat::expect_equal(sum(a$expected_hits),.007)
 testthat::expect_equal(sum(a$actual_hits),1)
 testthat::expect_equal(sum(a$stake),6)
 testthat::expect_equal(sum(a$net),294)
 testthat::expect_error(joint_ticket_calibration(dplyr::bind_rows(x,x[1,]),c(0,1)))
 testthat::expect_error(joint_ticket_calibration(x,c(0,.1,.05,1)))
 x$prob[1]<-NA_real_;testthat::expect_error(joint_ticket_calibration(x,c(0,1)))
})
