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
testthat::test_that('half lines and non-draw conditioning have explicit contracts',{
 d<-data.frame(net=0:1,probability=c(.5,.5))
 testthat::expect_equal(handicap_line_gap(d,0,1e-12,.5)$optimal_line,-.5)
 testthat::expect_equal(handicap_line_gap(d,0,1e-12,.5,'conditional')$delta,.5)
 d<-data.frame(net=c(2,0,1),probability=c(.2,.45,.35))
 testthat::expect_equal(handicap_line_gap(d,0,1e-12,.5)$signal,'W')
 for(metric in c('unconditional','conditional'))for(step in c(1,.5)){
  hs<-seq(-3,1,by=step);w<-vapply(hs,function(h)sum(d$probability[d$net+h>0]),0.0);l<-vapply(hs,function(h)sum(d$probability[d$net+h<0]),0.0)
  obj<-abs(w-l);if(metric=='conditional')obj<-obj/(w+l)
  z<-handicap_line_gap(d,0,1e-12,step,metric)
  testthat::expect_equal(z$imbalance,min(obj));testthat::expect_true(z$optimal_line %in% hs[obj==min(obj)])
 }
 z<-handicap_line_gap(data.frame(net=0,probability=1),0,1e-12,.5,'conditional')
 testthat::expect_equal(z$signal,'AMBIGUOUS');testthat::expect_equal(z$optimal_line,-.5)
 testthat::expect_error(handicap_line_gap(d,0,1e-12,.25))
 testthat::expect_error(handicap_line_gap(d,0,1e-12,.5,'bad'))
})
testthat::test_that('CDF search reproduces direct sums on sparse signed supports',{
 set.seed(9243)
 for(i in 1:20){
  nets<-sort(sample(-6:6,5));mass<-runif(5);d<-data.frame(net=nets,probability=mass/sum(mass))
  for(step in c(1,.5))for(metric in c('unconditional','conditional')){
   hs<-seq(-max(nets)-1,-min(nets)+1,by=step)
   w<-vapply(hs,function(h)sum(d$probability[nets+h>0]),0.0);l<-vapply(hs,function(h)sum(d$probability[nets+h<0]),0.0)
   v<-abs(w-l);if(metric=='conditional')v<-v/(w+l)
   best<-hs[v<=min(v)+1e-12];expected<-best[order(abs(best),best)][1]
   z<-handicap_line_gap(d,-1,1e-12,step,metric)
   testthat::expect_equal(z$optimal_line,expected);testthat::expect_equal(z$ties,length(best));testthat::expect_equal(z$imbalance,min(v))
  }
 }
})
