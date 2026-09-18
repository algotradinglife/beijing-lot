for(n in c('n7_joint_sleeves','n7_sp_filter','top2_fresh_groups'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('exact union increments honor overlap and reject malformed groups', {
 m<-rep(.8,9);a<-list(1:7,2:8,3:9)
 testthat::expect_equal(top2_group_increment(a,list(),m),rep(.8^7,3))
 testthat::expect_equal(top2_group_increment(a,list(1:7),m),c(0,.8^7-.8^8,.8^7-.8^9))
 # Exhaustive independent Bernoulli worlds for an independent check.
 w<-as.matrix(expand.grid(rep(list(c(FALSE,TRUE)),9)));pr<-.8^rowSums(w)*.2^(9-rowSums(w))
 hit<-vapply(a,function(g)rowSums(w[,g,drop=FALSE])==7,logical(nrow(w)))
 testthat::expect_equal(top2_group_increment(a[3],a[1:2],m),sum(pr[hit[,3]&!hit[,1]&!hit[,2]]))
 testthat::expect_error(top2_group_increment(list(c(1,1)),list(),m))
 testthat::expect_error(top2_group_increment(a,list(),rep(NA_real_,9)))
})
testthat::test_that('fresh selection is cutoff bound, deterministic and settlement isolated', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-.5;f$p_D<-.3;f$p_L<-.2;f$q_W<-.5;f$q_D<-.3;f$q_L<-.2
 py<-Sys.getenv('RETICULATE_PYTHON')
 z<-top2_fresh_groups(f,e$cutoffs,py,7,1024,2,.65,1.3)
 testthat::expect_length(z$groups,1);testthat::expect_equal(z$probability,.8^7)
 testthat::expect_equal(z$union_probability$TOP2_DIVERSE,.8^7)
 testthat::expect_identical(z,top2_fresh_groups(f,e$cutoffs,py,7,1024,2,.65,1.3))
 lab<-f[c('issue','slot','provider_id','handicap')];lab$actual_direction<-'W';lab$spf_sp<-2
 s<-top2_fresh_settle(z,lab);testthat::expect_equal(s$gross,rep(2*.65*2^7,2));testthat::expect_equal(s$stake,c(256,256))
 lab$actual_direction<-'L';testthat::expect_equal(top2_fresh_settle(z,lab)$gross,c(0,0))
 testthat::expect_equal(top2_fresh_groups(f,e$cutoffs,py,7,1024,2,.65,3)$selected$TOP2_PROB,integer())
 testthat::expect_error(top2_fresh_settle(z,lab[-1,]));testthat::expect_error(top2_fresh_settle(z,rbind(lab,lab[1,])))
 bad<-z;bad$mass[1]<-.7;testthat::expect_error(top2_fresh_settle(bad,lab))
 testthat::expect_error(top2_fresh_groups(f,list(),py,7,1024,2,.65,1.3))
 bad<-f;bad$actual_direction<-'W';testthat::expect_error(top2_fresh_groups(bad,e$cutoffs,py,7,1024,2,.65,1.3))
 # Ten fixtures admit >4 unique groups and exact overlap-aware coverage.
 extra<-f[1:3,];extra$slot<-max(f$slot)+1:3;extra$provider_id<-paste0('extra',1:3)
 ff<-rbind(f,extra);cuts<-c(e$cutoffs,setNames(rep(e$cutoffs[1],3),as.character(extra$slot)))
 zz<-top2_fresh_groups(ff,cuts,py,7,1024,2,.65,1.3)
 testthat::expect_length(zz$selected$TOP2_PROB,4)
 testthat::expect_true(tail(zz$union_probability$TOP2_DIVERSE,1)>=tail(zz$union_probability$TOP2_PROB,1)-1e-12)
 testthat::expect_true(all(vapply(zz$groups,function(g)length(g)==7&&!anyDuplicated(g),logical(1))))
})
testthat::test_that('profit issues retain row-wise positives despite negative total net', {
 r<-tibble::tibble(issue=c('01','02'),policy='x',stake=c(10,10),gross=c(15,0),net=c(5,-10),hits=c(1,0),bought_groups=c(1,1))
 c<-tibble::tibble(policy='x',drawdown_cny=c(0,10))
 z<-top2_fresh_summary(r,c)
 testthat::expect_equal(z$profit_issues,1);testthat::expect_equal(z$net,-5);testthat::expect_equal(z$roi,-.25)
 testthat::expect_equal(z$max_drawdown,10)
 testthat::expect_error(top2_fresh_summary(rbind(r,r[1,]),c))
 testthat::expect_error(top2_fresh_summary(r,transform(c,policy='bad')))
 r$stake<-0;r$gross<-0;r$net<-0;r$hits<-0;r$bought_groups<-0
 testthat::expect_true(is.na(top2_fresh_summary(r,c)$roi))
})
