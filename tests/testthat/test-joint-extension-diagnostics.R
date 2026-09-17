source(file.path('..','..','r/joint_extension_diagnostics.R'))
test_that('extension preserves bankroll seam and distinguishes local drawdown',{
 x<-tibble::tibble(issue=c('01','02','03','04'),policy='A',period=1:4,stake=10,gross=c(30,0,0,12),hits=c(1,0,0,1)) |> dplyr::mutate(net=gross-stake)
 z<-joint_extension_diagnostics(x,2,100)
 expect_equal(z$curves$bankroll,c(120,110,100,102))
 expect_equal(z$curves$drawdown,c(0,10,20,18))
 q<-z$summary[z$summary$cohort=='NEW50',]
 expect_equal(q$local_max_drawdown,10);expect_equal(q$full_curve_drawdown,20)
 expect_equal(z$summary$longest_no_hit[z$summary$cohort=='ALL834'],2)
 expect_error(joint_extension_diagnostics(dplyr::bind_rows(x,x[1,]),2,100))
 x$net[1]<-0;expect_error(joint_extension_diagnostics(x,2,100))
})
