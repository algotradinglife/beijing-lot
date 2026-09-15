source('../../r/n7_winner_changes.R')

testthat::test_that('winner changes reconcile retained added and lost payouts', {
 x<-tibble::tribble(~issue,~policy,~ticket_key,~gross_cny,
  '01','A','same',100,'01','B','same',100,
  '01','A','lost',50,'01','B','added',70,'02','B','only',20)
 z<-n7_winner_changes(x,c('01','02','03'),'A','B')
 testthat::expect_equal(z$issues$retained,c(1,0,0))
 testthat::expect_equal(z$issues$added,c(1,1,0))
 testthat::expect_equal(z$issues$lost,c(1,0,0))
 testthat::expect_equal(z$issues$gross_change,c(20,20,0))
 testthat::expect_setequal(z$tickets$change,c('ADDED','LOST','RETAINED'))
})
testthat::test_that('empty winners preserve the issue denominator', {
 x<-tibble::tibble(issue=character(),policy=character(),ticket_key=character(),gross_cny=numeric())
 z<-n7_winner_changes(x,c('001','002'),'A','B')
 testthat::expect_identical(z$issues$issue,c('001','002'))
 testthat::expect_equal(z$issues$gross_change,c(0,0))
 testthat::expect_equal(nrow(z$tickets),0)
})
testthat::test_that('equal payouts never imply identical tickets', {
 x<-tibble::tibble(issue=c('01','01'),policy=c('A','B'),ticket_key=c('fixture1:W','fixture2:W'),gross_cny=c(100,100))
 z<-n7_winner_changes(x,'01','A','B')
 testthat::expect_equal(z$issues$retained,0)
 testthat::expect_equal(z$issues$added,1)
 testthat::expect_equal(z$issues$lost,1)
 testthat::expect_equal(z$issues$gross_change,0)
})
testthat::test_that('ambiguous identities and inconsistent settlement fail', {
 x<-tibble::tibble(issue=c('01','01'),policy=c('A','B'),ticket_key=c('same','same'),gross_cny=c(10,11))
 testthat::expect_error(n7_winner_changes(x,'01','A','B'))
 x$gross_cny<-c(10,10)
 testthat::expect_error(n7_winner_changes(dplyr::bind_rows(x,x[1,]),'01','A','B'))
 testthat::expect_error(n7_winner_changes(x,'02','A','B'))
 testthat::expect_error(n7_winner_changes(x,c('01','01'),'A','B'))
 testthat::expect_error(n7_winner_changes(x,'01','A','A'))
 x$gross_cny[1]<-NA_real_
 testthat::expect_error(n7_winner_changes(x,'01','A','B'))
 x$gross_cny[1]<-0
 testthat::expect_error(n7_winner_changes(x,'01','A','B'))
})
