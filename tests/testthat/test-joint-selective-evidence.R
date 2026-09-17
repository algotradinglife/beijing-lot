source(file.path('..','..','r','joint_selective_evidence.R'))
test_that('same issue and sleeve IDs cannot hide a different membership source', {
 s<-list(issue='01',sha256=strrep('a',64));j<-s
 b<-list(issue='01',sleeves=list(list(id=1,fixture_indices=list(0,1))))
 expect_equal(joint_selective_members(s,j,b)$fixture,c('0','1'))
 j$sha256<-strrep('b',64);b$sleeves[[1]]$fixture_indices<-list(4,5)
 expect_error(joint_selective_members(s,j,b))
 j<-s;b$issue<-'02';expect_error(joint_selective_members(s,j,b))
})
test_that('incremental concentration keeps all period contributions', {
 x<-data.frame(issue=letters[1:5],policy='p',extra_stake=2,extra_net=c(10,-5,8,-4,1))
 a<-joint_selective_concentration(x)
 expect_equal(a$total_extra_net,10);expect_equal(a$marginal_roi,1)
 expect_equal(a$positive_issues,3);expect_equal(a$negative_issues,2)
 expect_equal(a$without_top1,0);expect_equal(a$without_top3,-9)
 x$extra_net<-0;x$extra_stake<-0;expect_true(is.na(joint_selective_concentration(x)$marginal_roi))
 expect_equal(nrow(joint_selective_concentration(x[FALSE,])),0)
 x$issue[2]<-x$issue[1];expect_error(joint_selective_concentration(x))
})
