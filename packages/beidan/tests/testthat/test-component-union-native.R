test_that("native weighted component agrees with frozen R mathematical oracle", {
 oracle <- readRDS(test_path("..","fixtures","component_union_oracle.rds"))
 set.seed(104L)
 exact <- logical(60); errors <- numeric(60)
 for(k in seq_len(60)) {
  n <- sample(2:6,1)
  fixtures <- sprintf("001:%02d",seq_len(n))
  p <- matrix(runif(n*3),nrow=n);p<-p/rowSums(p)
  events <- lapply(seq_len(sample(2:12,1)),function(j) {
   ids <- sort(sample(seq_len(n),sample(seq_len(n),1)))
   stats::setNames(sample(1:3,length(ids),replace=TRUE),fixtures[ids])
  })
  probability_of <- function(id,code) p[match(id,fixtures),code]
  before <- oracle(events,fixtures,probability_of,new.env(parent=emptyenv()))
  after <- .parlay_ranked_component_union(events,fixtures,probability_of)
  errors[k] <- abs(before-after);exact[k]<-identical(before,after)
  expect_equal(after,before,tolerance=1e-15)
  expect_equal(after,.parlay_ranked_component_union(rev(events),fixtures,probability_of),tolerance=1e-15)
 }
 expect_true(all(exact))
 expect_equal(max(errors),0)
})

test_that("kernel handles duplicate, nested, disjoint, empty and exclusive events", {
 ids <- c("001","002")
 p <- matrix(c(.4,.3,.3,.2,.5,.3),nrow=2,byrow=TRUE)
 f <- function(id,code)p[match(id,ids),code]
 expect_equal(.parlay_ranked_component_union(list(),ids,f),0)
 expect_equal(.parlay_ranked_component_union(list(c(`001`=1L),c(`001`=1L,`002`=2L)),ids,f),.4)
 expect_equal(.parlay_ranked_component_union(list(c(`001`=1L),c(`001`=1L)),ids,f),.4)
 expect_equal(.parlay_ranked_component_union(list(c(`001`=1L),c(`002`=2L)),ids,f),.7)
 expect_equal(.parlay_ranked_component_union(list(c(`001`=1L),c(`001`=2L)),ids,f),.7)
 expect_equal(ComponentUnionKernel(list(integer()),ids,p),1)
 expect_error(ComponentUnionKernel(list(c(`003`=1L)),ids,p),"assignment")
 expect_error(ComponentUnionKernel(list(c(`001`=1.5)),ids,p),"assignment")
 expect_error(ComponentUnionKernel(list(c(`001`=NA_real_)),ids,p),"assignment")
 expect_error(ComponentUnionKernel(list(c(`001`=1L,`001`=2L)),ids,p),"duplicate")
 expect_error(ComponentUnionKernel(list(1L),ids,p))
 expect_error(ComponentUnionKernel(list(),c("001","001"),p),"identifier")
 expect_error(ComponentUnionKernel(list(),c("001",NA_character_),p),"identifier")
 expect_error(ComponentUnionKernel(list(),ids,p[,1,drop=FALSE]),"dimensions")
 bad <- p;bad[1,1]<-Inf
 expect_error(ComponentUnionKernel(list(),ids,bad),"probability")
 bad <- p;bad[1,1]<-.8
 expect_error(ComponentUnionKernel(list(),ids,bad),"sum to one")
})

test_that("native identity binds compiled source and reproducible glue without pointers", {
 root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
 paths <- file.path(root,c("packages/beidan/src/component_union.cpp","packages/beidan/src/RcppExports.cpp","packages/beidan/src/Makevars"))
 names <- c("packages/beidan/src/component_union.cpp","packages/beidan/src/RcppExports.cpp","packages/beidan/src/Makevars")
 hashes <- vapply(paths,digest::digest,character(1),file=TRUE,algo="sha256");names(hashes)<-names
 expected <- digest::digest(hashes,algo="sha256")
 expect_identical(ComponentUnionKernelIdentity(),expected)
 expect_identical(.ParlayKernelSourceHash(),expected)
 expect_false(any(grepl("`_beidan",readLines(file.path(root,"packages/beidan/R/RcppExports.R")),fixed=TRUE)))
})

test_that("bounded dense components agree with R oracle without a full-table interface", {
 oracle <- readRDS(test_path("..","fixtures","component_union_oracle.rds"))
 for(n in c(10L,12L,15L,16L)) {
  fixtures <- sprintf("F%03d",seq_len(n))
  p <- matrix(rep(c(.4,.35,.25),n),nrow=n,byrow=TRUE)
  events <- list(stats::setNames(rep(1L,7),fixtures[1:7]),
   stats::setNames(rep(2L,7),fixtures[(n-6):n]),
   stats::setNames(c(1L,3L,2L),fixtures[c(2,5,n)]))
  f <- function(id,code)p[match(id,fixtures),code]
  before <- oracle(events,fixtures,f,new.env(parent=emptyenv()))
  after <- .parlay_ranked_component_union(events,fixtures,f)
  expect_equal(after,before,tolerance=1e-14)
 }
})

test_that("accepted near-unit mass preserves sparse missing-fixture semantics", {
 oracle <- readRDS(test_path("..","fixtures","component_union_oracle.rds"))
 ids <- sprintf("F%03d",1:10)
 p <- matrix(rep(c(.4,.35,.25),10),nrow=10,byrow=TRUE)
 p[1,1] <- p[1,1]+5e-10
 events <- list(stats::setNames(rep(1L,7),ids[1:7]),
                stats::setNames(rep(3L,7),ids[4:10]))
 f <- function(id,code)p[match(id,ids),code]
 expect_identical(.parlay_ranked_component_union(events,ids,f),
                  oracle(events,ids,f,new.env(parent=emptyenv())))
})
