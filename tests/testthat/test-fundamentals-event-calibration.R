source(file.path('..','..','r','fundamentals_event_calibration.R'))
testthat::test_that('event calibration uses all rows and rejects bad labels',{
 e <- tibble::tibble(issue='001',slot=1:2,provider_id=c('001','002'),model='baseline',event='ordinary_draw',probability=c(.2,.4))
 a <- tibble::tibble(issue='001',slot=1:2,provider_id=c('001','002'),status='READY',actual_home=c(1,3),actual_away=c(1,0),handicap=c(0,-1))
 s <- event_calibration(e,a)$summary
 testthat::expect_equal(s$n,2L);testthat::expect_equal(s$actual_percent,50)
 testthat::expect_equal(s$predicted_percent,30);testthat::expect_equal(s$error_pp,20)
 testthat::expect_equal(s$brier,.4)
 testthat::expect_error(event_calibration(e,a[-1,]))
 testthat::expect_error(event_calibration(dplyr::bind_rows(e,e[1,]),a))
 testthat::expect_error(event_calibration(dplyr::mutate(e,probability=2),a))
 testthat::expect_error(event_calibration(e,dplyr::mutate(a,status='PENDING')))
 testthat::expect_error(event_calibration(dplyr::mutate(e,event='giving_cover'),a))
})
testthat::test_that('all event labels follow score margin and handicap',{
 names<-c('ordinary_draw','handicap_draw','home_ge2','away_ge2','home_ge3','away_ge3','total_ge5','giving_cover')
 e<-tibble::tibble(issue='001',slot=1,provider_id='007',model='baseline',event=names,probability=.5)
 a<-tibble::tibble(issue='001',slot=1,provider_id='007',status='READY',actual_home=5,actual_away=1,handicap=-2)
 testthat::expect_equal(event_calibration(e,a)$observations$observed,c(FALSE,FALSE,TRUE,FALSE,TRUE,FALSE,TRUE,TRUE))
 a$actual_home<-0;a$actual_away<-3;a$handicap<-1
 testthat::expect_equal(event_calibration(e,a)$observations$observed,c(FALSE,FALSE,FALSE,TRUE,FALSE,TRUE,FALSE,TRUE))
 a$actual_home<-Inf
 testthat::expect_error(event_calibration(e,a))
})
