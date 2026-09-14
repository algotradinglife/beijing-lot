source('../../r/n7_selection_diagnostics.R')
testthat::test_that('overlap diagnostics distinguish genuine coverage from repeated fixtures',{
 rows<-tibble::tibble(issue='001',arm=c('shared','empty'),seed=1,groups=c(2,0),eval_union=c(.6,0))
 f<-tibble::tibble(issue='001',arm='shared',seed=1,sleeve_id=c('0','1'),coverage=c(.4,.4))
 m<-tibble::tibble(issue='001',sleeve_id=rep(c('0','1'),each=7),fixture_id=as.character(c(1:7,5:11)))
 z<-n7_selection_overlap(rows,f,m)
 testthat::expect_equal(z$unique_fixtures,c(11,0))
 testthat::expect_equal(z$max_fixture_reuse,c(2,0))
 testthat::expect_equal(z$max_pair_overlap,c(3,0))
 testthat::expect_equal(z$mean_pair_overlap,c(3,0))
 testthat::expect_equal(z$coverage_minus_union,c(.2,0))
 testthat::expect_error(n7_selection_overlap(rows,dplyr::bind_rows(f,f[1,]),m))
 testthat::expect_error(n7_selection_overlap(rows,f,m[-1,]))
 bad<-f;bad$arm<-'missing'
 testthat::expect_error(n7_selection_overlap(rows,bad,m))
 bad<-rows;bad$groups[1]<-1
 testthat::expect_error(n7_selection_overlap(bad,f,m))
 one<-n7_selection_overlap(dplyr::mutate(rows[1,],groups=1),f[1,],m)
 testthat::expect_equal(one$max_pair_overlap,0)
})

testthat::test_that('block profitable-issue counts precede net aggregation',{
 x<-tibble::tibble(issue=c('003','001','002','004'),arm='a',seed=1,
   stake=c(10,10,10,0),net=c(-5,10,20,0),hits=c(0,1,2,0))
 z<-n7_selection_blocks(x,c('001','002','003','004'),3)
 testthat::expect_equal(z$profit_issues,c(2L,0L))
 testthat::expect_equal(z$hit_issues,c(2L,0L))
 testthat::expect_equal(z$net,c(25,0))
 testthat::expect_equal(z$roi,c(25/30,NA_real_))
 testthat::expect_error(n7_selection_blocks(x,c('001','002'),3))
 testthat::expect_error(n7_selection_blocks(x,unique(x$issue),0))
 testthat::expect_error(n7_selection_blocks(dplyr::bind_rows(x,x[1,]),unique(x$issue),3))
})
