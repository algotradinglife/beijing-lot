source('../../r/joint_payout_mix_diagnostics.R')
testthat::test_that('mixed diagnostics separate rescued issues from foregone return',{
 x<-tibble::tibble(issue=rep(c('01','02'),2),policy=rep(c('REF','MIX'),each=2),
  stake=c(100,100,90,90),gross=c(0,300,150,0),net=c(-100,200,60,-90),hits=c(0,1,1,0))
 m<-tibble::tibble(issue=c('01','02'),stage=c('BEFORE','AFTER'))
 z<-joint_payout_mix_diagnostics(x,m,'REF')
 a<-z$summary |> dplyr::filter(policy=='MIX',stage=='ALL')
 testthat::expect_equal(a$delta_net,-130)
 testthat::expect_equal(a$delta_stake,-20)
 testthat::expect_equal(a$rescued,1L);testthat::expect_equal(a$lost,1L)
 testthat::expect_equal(a$improved,1L);testthat::expect_equal(a$worse,1L)
 testthat::expect_equal(a$unchanged,0L)
 testthat::expect_equal(z$summary$unchanged[z$summary$policy=='REF' & z$summary$stage=='ALL'],2L)
 testthat::expect_error(joint_payout_mix_diagnostics(x[-1,],m,'REF'))
 testthat::expect_error(joint_payout_mix_diagnostics(dplyr::bind_rows(x,x[1,]),m,'REF'))
 bad<-x;bad$net[1]<-0
 testthat::expect_error(joint_payout_mix_diagnostics(bad,m,'REF'))
 bad<-x;bad$gross[1]<-NA_real_
 testthat::expect_error(joint_payout_mix_diagnostics(bad,m,'REF'))
})
