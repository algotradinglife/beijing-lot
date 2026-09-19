source(file.path('..','..','r','joint_rotation_diagnostics.R'))
test_that('diagnostics derive spend and first/second copies from sealed rows', {
 x<-tibble::tibble(issue='001',policy=c('EXPAND','EXPAND','EXPAND_PROB','ROTATE'),ticket_id=c('a','b','a','a'),sleeve_id=c(0L,1L,0L,0L),copies=c(1L,2L,1L,0L),base_copies=c(1L,0L,1L,1L))
 z<-joint_rotation_diagnostics(x,'001',3,2187,2)
 expect_equal(z$target_stake,c(6,0));expect_equal(z$comparator_stake,c(2,0))
 expect_equal(z$new_combinations,c(1,0));expect_equal(z$extra_copies,c(1,0));expect_equal(z$removed,c(0,1));expect_equal(z$new_groups,c(1L,0L))
 expect_equal(joint_rotation_diagnostics(x[FALSE,],'001',0,2187,2)$target_stake,c(0,0))
 expect_error(joint_rotation_diagnostics(x,'002',3,2187,2))
})
