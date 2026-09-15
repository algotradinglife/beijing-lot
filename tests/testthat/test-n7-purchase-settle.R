source(file.path('..','..','r','n7_purchase_settle.R'))
testthat::test_that('frozen canonical tickets settle once and reject changed identity', {
 f<-lapply(1:7,function(k)list(slot=k,provider_id=as.character(k),handicap=0))
 o<-list(sleeve_id=1,fixtures=1:7,state_ids=1L,stake=2,coverage=.1,expected_gross=3)
 p<-list(issue='001',fixtures=f,arms=list(A=list(options=list(o))))
 p$seal<-digest::digest(p,algo='sha256')
 l<-tibble::tibble(issue='001',slot=1:7,provider_id=as.character(1:7),handicap=0,actual_direction='W',spf_sp=2)
 x<-n7_purchase_settle(p,l,2,.65)
 testthat::expect_equal(x$gross,2*.65*2^7)
 l$actual_direction[1]<-'D';testthat::expect_equal(n7_purchase_settle(p,l,2,.65)$gross,0)
 l$provider_id[1]<-'bad';testthat::expect_error(n7_purchase_settle(p,l,2,.65))
 p$issue<-'002';testthat::expect_error(n7_purchase_settle(p,l,2,.65))
})

testthat::test_that('mixed outcomes and permuted fixture membership settle physical tickets', {
 f<-lapply(1:7,function(k)list(slot=k,provider_id=as.character(k),handicap=0))
 indices<-c(7L,1L,4L,2L,6L,3L,5L)
 directions<-c('L','W','D','L','D','W','L')
 enumeration<-as.matrix(expand.grid(rep(list(c('W','D','L')),7)))[,7:1]
 matching<-which(apply(enumeration,1,function(row)identical(unname(row),directions[indices])))
 testthat::expect_length(matching,1)
 o<-list(sleeve_id=1,fixtures=indices,state_ids=matching,stake=6,coverage=.1,expected_gross=3)
 p<-list(issue='001',fixtures=f,arms=list(A=list(options=list(o)),EMPTY=list(options=list())))
 p$seal<-digest::digest(p,algo='sha256')
 l<-tibble::tibble(issue='001',slot=1:7,provider_id=as.character(1:7),handicap=0,
  actual_direction=directions,spf_sp=c(1.5,2,3,4,5,6,7))
 l<-l[c(3,7,1,4,6,2,5),]
 x<-n7_purchase_settle(p,l,2,.65)
 testthat::expect_equal(nrow(x),1L)
 testthat::expect_true(x$hit)
 testthat::expect_equal(x$gross,3*2*.65*prod(l$spf_sp))
 testthat::expect_equal(x$stake,6)
})

 testthat::test_that('settlement constants reject non-scalar or non-numeric values', {
 p<-list(arms=list());p$seal<-digest::digest(p,algo='sha256')
 l<-tibble::tibble(issue=character(),slot=integer(),provider_id=character(),handicap=double(),actual_direction=character(),spf_sp=double())
 for(x in list(numeric(),c(2,2),NA_real_,Inf,'2'))
  testthat::expect_error(n7_purchase_settle(p,l,x,.65))
 for(x in list(numeric(),c(.65,.65),NA_real_,Inf,'0.65'))
  testthat::expect_error(n7_purchase_settle(p,l,2,x))
 testthat::expect_equal(nrow(n7_purchase_settle(p,l,2,.65)),0L)
 })
