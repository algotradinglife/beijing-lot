source(file.path("..","..","r","fundamentals_single_probability.R"))
testthat::test_that("fixed group minimum/joint probabilities reconcile with outcomes", {
 x<-tibble::tibble(issue="001",policy="P",component=0L,slot=1:7,
   support=c("3","3",rep("31",5)),actual_direction="W",
   p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2)
 z<-single_probability_diagnostics(x,c(0,.5,.6,1),c(0,.25,.4,1))
 testthat::expect_equal(z$groups$P_min,.6)
 testthat::expect_equal(z$groups$Q_joint,.25)
 testthat::expect_equal(z$groups$MIX_joint,.55^2)
 testthat::expect_true(z$groups$both_hit)
 testthat::expect_equal(sum(z$bins$groups),6)
 x$actual_direction[7]<-"L"
 z<-single_probability_diagnostics(x,c(0,.5,1),c(0,.3,1))
 testthat::expect_true(z$groups$both_hit)
 testthat::expect_false(z$groups$group_hit)
 x$actual_direction[1]<-"D"
 testthat::expect_false(single_probability_diagnostics(x,c(0,1),c(0,1))$groups$both_hit)
 testthat::expect_error(single_probability_diagnostics(x[0,],c(0,1),c(0,1)))
 testthat::expect_error(single_probability_diagnostics(dplyr::bind_rows(x,x[1,]),c(0,1),c(0,1)))
 testthat::expect_error(single_probability_diagnostics(x,c(.1,1),c(0,1)))
 x$p_W[1]<-NA_real_
 testthat::expect_error(single_probability_diagnostics(x,c(0,1),c(0,1)))
})

testthat::test_that("probability endpoints and malformed supports are checked", {
 x<-tibble::tibble(issue="001",policy="P",component=0L,slot=1:7,
   support=c("3","3",rep("31",5)),actual_direction="W",
   p_W=1,p_D=0,p_L=0,q_W=1,q_D=0,q_L=0)
 testthat::expect_equal(single_probability_diagnostics(x,c(0,.5,1),c(0,.5,1))$groups$Q_joint,1)
 bad<-x;bad$support[1]<-"31"
 testthat::expect_error(single_probability_diagnostics(bad,c(0,1),c(0,1)))
 bad<-x;bad$p_D[1]<-.1
 testthat::expect_error(single_probability_diagnostics(bad,c(0,1),c(0,1)))
 bad<-x;bad$actual_direction[1]<-"BAD"
 testthat::expect_error(single_probability_diagnostics(bad,c(0,1),c(0,1)))
})
