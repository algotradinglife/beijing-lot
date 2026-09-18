source(file.path('..','..','r','handicap_line_gap.R'))
testthat::test_that('direction follows signed home line, ties are not forced',{
 d<-data.frame(net=0:2,probability=c(.2,.6,.2))
 a<-handicap_line_gap(d,0,1e-12);b<-handicap_line_gap(d,-2,1e-12)
 testthat::expect_equal(a$optimal_line,-1);testthat::expect_equal(a$signal,'W');testthat::expect_equal(a$q_W,.8)
 testthat::expect_equal(b$signal,'L');testthat::expect_equal(b$q_L,.8)
 testthat::expect_equal(handicap_line_gap(d,-1,1e-12)$signal,'NONE')
 t<-data.frame(net=0:1,probability=c(.5,.5));z<-handicap_line_gap(t,2,1e-12)
 testthat::expect_equal(z$ties,2);testthat::expect_equal(z$signal,'AMBIGUOUS');testthat::expect_equal(z$optimal_line,0)
 testthat::expect_equal(handicap_line_gap(data.frame(net=0,probability=1),0,1e-12)$q_D,1)
 testthat::expect_error(handicap_line_gap(rbind(d,d),0,1e-12));d$probability[1]<-.1
 testthat::expect_error(handicap_line_gap(d,0,1e-12))
})
