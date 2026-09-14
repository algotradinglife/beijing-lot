source(file.path('..','..','r','strategy_diagnostic_probabilities.R'))
testthat::test_that('multiclass scores, ties, zero probabilities and contracts are explicit',{
 x<-tibble::tibble(issue=rep(c('001','002'),each=3),slot=1L,provider_id='01',model='m',
   segment=rep(c('old','new'),each=3),outcome=rep(c('W','D','L'),2),
   actual_outcome=rep(c('D','L'),each=3),probability=c(.5,.5,0,1,0,0))
 z<-strategy_probability_diagnostics(x,'segment',c('W','D','L'),c(0,.5,1))
 testthat::expect_equal(z$scores$brier,c(.5,2))
 testthat::expect_equal(z$scores$log_loss,c(-log(.5),Inf))
 testthat::expect_equal(z$scores$top1,c(FALSE,FALSE))
 testthat::expect_equal(z$scores$top2,c(TRUE,FALSE))
 testthat::expect_equal(sum(z$calibration$fixtures),6L)
 testthat::expect_equal(z$scores$issue,c('001','002'))
 testthat::expect_error(strategy_probability_diagnostics(x[-1,],'segment',c('W','D','L'),c(0,1)))
 bad<-x;bad$probability[1]<-.7
 testthat::expect_error(strategy_probability_diagnostics(bad,'segment',c('W','D','L'),c(0,1)))
 bad<-dplyr::bind_rows(x,dplyr::mutate(x,model='m2',actual_outcome='W'))
 testthat::expect_error(strategy_probability_diagnostics(bad,'segment',c('W','D','L'),c(0,1)))
 bad<-dplyr::bind_rows(x,dplyr::mutate(x[1:3,],model='m2'))
 testthat::expect_error(strategy_probability_diagnostics(bad,'segment',c('W','D','L'),c(0,1)))
 for(col in c('probability','actual_outcome','segment')) {
  bad<-x;bad[[col]][1]<-NA
  testthat::expect_error(strategy_probability_diagnostics(bad,'segment',c('W','D','L'),c(0,1)))
 }
 testthat::expect_error(strategy_probability_diagnostics(x[0,],'segment',c('W','D','L'),c(0,1)))
 testthat::expect_error(strategy_probability_diagnostics(x,'segment',c('W','D','L'),c(.1,1)))
 testthat::expect_equal(nrow(strategy_probability_diagnostics(x,character(),c('W','D','L'),c(0,1))$summary),1L)
})
testthat::test_that('composition and within effects reconcile and unsupported cells fail',{
 x<-tibble::tibble(segment=c(rep('old',4),rep('new',4)),
  stratum=c('A','B','B','B','A','A','A','B'),value=c(1,0,0,0,1,1,1,0))
 z<-strategy_composition_diagnostics(x,'old','new')
 testthat::expect_equal(z$summary$change,.5)
 testthat::expect_equal(z$summary$composition,.5)
 testthat::expect_equal(z$summary$within,0)
 x$value[x$segment=='new' & x$stratum=='A']<-0
 z<-strategy_composition_diagnostics(x,'old','new')
 testthat::expect_equal(z$summary$change,-.25)
 testthat::expect_equal(z$summary$within,-.75)
 testthat::expect_equal(sum(z$cells$composition+z$cells$within),z$summary$change)
 testthat::expect_equal(sum(z$ledger$n),8L)
 testthat::expect_error(strategy_composition_diagnostics(x[x$stratum!='B' | x$segment!='new',],'old','new'))
 testthat::expect_error(strategy_composition_diagnostics(x,'old','absent'))
 testthat::expect_error(strategy_composition_diagnostics(x,'old','old'))
 x$value[1]<-NA
 testthat::expect_error(strategy_composition_diagnostics(x,'old','new'))
 testthat::expect_error(strategy_composition_diagnostics(x[0,],'old','new'))
})

testthat::test_that('required receipt files cannot escape verification',{
 d<-tempfile();dir.create(d);on.exit(unlink(d,recursive=TRUE))
 writeLines('fixture',file.path(d,'x.csv'))
 h<-list('x.csv'=digest::digest(file=file.path(d,'x.csv'),algo='sha256'))
 testthat::expect_true(strategy_verify_diagnostic_inputs(d,h,'x.csv'))
 testthat::expect_error(strategy_verify_diagnostic_inputs(d,h,'missing.csv'))
 for(v in list(NULL,NA_character_,character(),c(h[[1]],h[[1]]),'bad'))
   testthat::expect_error(strategy_verify_diagnostic_inputs(d,list('x.csv'=v),'x.csv'))
 writeLines('mutated',file.path(d,'x.csv'))
 testthat::expect_error(strategy_verify_diagnostic_inputs(d,h,'x.csv'))
 testthat::expect_error(strategy_verify_diagnostic_inputs(d,h,character()))
 testthat::expect_error(strategy_verify_diagnostic_inputs(d,c(h,h),'x.csv'))
})
