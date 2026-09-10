for(p in c('eight_issue_holdout','fundamentals_retraining','fundamentals_expert_coverage','fundamentals_score_shape','fundamentals_score_diagnostic')) source(paste0('../../r/',p,'.R'))
testthat::test_that('holdout prediction and evaluation stay separated and immutable', {
 root <- normalizePath('../..');out <- tempfile('eight-holdout-');dir.create(out);dir.create(file.path(out,'market'));dir.create(file.path(out,'models'));dir.create(file.path(out,'models','100109'))
 cuts <- list('100109'=list('1'='2010-01-19T00:00:00Z'))
 f <- tibble::tibble(issue='100109',slot=1L,provider_id='a',home='H',away='A',handicap=0,x=1,baseline_draw=.2,baseline_cover=.3)
 g <- tibble::tibble(home_goals=c(0,1,0),away_goals=c(0,0,1),probability=c(.2,.5,.3),outcome=c('D','W','L'))
 e <- list(fixtures=dplyr::mutate(f,variant='raw',status='OK_DIAGNOSTIC',W=.5,D=.2,L=.3),grids=list('1/raw'=g),cutoffs=cuts[[1]])
 model <- list(experiments=list('100109'=e),scores=list(),coverage_choices=list(),provenance=list(),implementation_hashes=list(),parameters=list(),gates=list(),historical_admission=FALSE)
 model$provenance$expert_context <- list(input_file_hashes=list(),implementation_hashes=list(),expert_feature_sha256=digest::digest(f,algo='sha256'))
 model$seal <- digest::digest(model,algo='sha256')
 saveRDS(list(models=model,features=f,cutoffs=cuts),file.path(out,'new-inputs-internal.rds'))
 for(path in c('new-inventories.json','market/euro.json','market/total.json','models/100109/frozen-experts.pkl')) writeLines('fixture',file.path(out,path))
 jsonlite::write_json(list(test_issue='100109',receipt=list(draw=list(features=list('x'),target_issue='100109',cutoff_identity='DECISION_EPOCH_100109',cutoff_ts='2010-01-19T00:00:00+00:00'),high=list(features=list('x'),target_issue='100109',cutoff_identity='DECISION_EPOCH_100109',cutoff_ts='2010-01-19T00:00:00+00:00'))),file.path(out,'models/100109/frozen-experts.json'),auto_unbox=TRUE)
 control <- holdout_baseline_control(model,cuts)
 testthat::expect_equal(nrow(control$fixtures),1)
 testthat::expect_false(any(c('actual_home','actual_away') %in% names(control$fixtures)))
 testthat::expect_error(holdout_baseline_control(model,list()),'cutoff')
 bad <- model;bad$experiments[[1]]$grids[[1]]$probability[1] <- -1
 testthat::expect_error(holdout_baseline_control(bad,cuts),'grid')
 bad <- model;bad$experiments[[1]]$fixtures <- dplyr::bind_rows(e$fixtures,e$fixtures)
 testthat::expect_error(holdout_baseline_control(bad,cuts),'Duplicate')
 fn <- eight_holdout_predictions;scope <- new.env(parent=environment(fn));environment(fn) <- scope
 scope$ev_market_probabilities <- function(...) list(status=dplyr::mutate(f,status='READY',lambda_home=1.5,lambda_away=1),grids=list('100109/1'=g),cutoffs=cuts)
 scope$project_python_module <- function(name,...) {
  if(name=='src.temporal_learning') return(list(Cutoff=list(decision_epoch=function(...) list(identity='DECISION_EPOCH_100109',cutoff_ts=list(isoformat=function() '2010-01-19T00:00:00+00:00')))))
  list(predict_frozen_file=function(path,frame,cutoff,...) {
   testthat::expect_false(any(c('actual_home','actual_away','draw_target','cover_target') %in% names(frame)))
   result <- dplyr::transmute(frame,issue_code,slot,provider_id,draw_probability=.7,draw_signal='POSITIVE',high_probability=NA_real_,high_signal='NOT_APPLICABLE')
   list(to_dict=function(orient)lapply(seq_len(nrow(result)),function(i)as.list(result[i,])))
  })
 }
 frozen <- fn(out,'unused',root,cuts,.5)
 testthat::expect_true(file.exists(frozen$prediction_path))
 testthat::expect_identical(fn(out,'unused',root,cuts,.5)$prediction_sha256,frozen$prediction_sha256)
 testthat::expect_error(fn(out,'unused',root,cuts,.6),'Immutable')
 receipt_path <- file.path(out,'models/100109/frozen-experts.json')
 receipt_bytes <- readChar(receipt_path,file.info(receipt_path)$size,useBytes=TRUE)
 wrong <- jsonlite::read_json(receipt_path);wrong$test_issue <- '100108'
 jsonlite::write_json(wrong,receipt_path,auto_unbox=TRUE)
 testthat::expect_error(fn(out,'unused',root,cuts,.5),'target cutoff')
 writeChar(receipt_bytes,receipt_path,eos=NULL,useBytes=TRUE)
 ev <- eight_holdout_evaluation;env <- new.env(parent=environment(ev));environment(ev) <- env
 env$evaluate_issue_score_models <- function(...) {
  testthat::expect_true(file.exists(frozen$prediction_path))
  list(fixtures=dplyr::mutate(e$fixtures,actual_home=0L,actual_away=0L,scorable=TRUE))
 }
 result <- ev(frozen,list(),'unused',root)
 testthat::expect_equal(result$fixtures$main_hit,c(FALSE,TRUE))
 testthat::expect_equal(result$expert_rows$correct,c(TRUE,NA))
 env$evaluate_issue_score_models <- function(...) list(fixtures=dplyr::mutate(e$fixtures,actual_home=1L,actual_away=0L,scorable=TRUE))
 second <- ev(frozen,list(),'unused',root)
 testthat::expect_identical(result$prediction_sha256,second$prediction_sha256)
 testthat::expect_identical(fn(out,'unused',root,cuts,.5)$prediction_sha256,frozen$prediction_sha256)
 bad <- frozen;bad$snapshot$selected$fixtures$selected[1] <- 'D,L'
 testthat::expect_error(ev(bad,list(),'unused',root),'In-memory')
 prepared <- readRDS(file.path(out,'new-inputs-internal.rds'));prepared$features$x <- 5
 saveRDS(prepared,file.path(out,'new-inputs-internal.rds'))
 testthat::expect_error(fn(out,'unused',root,cuts,.5),'prepared inputs')
})

source('../../r/eight_issue_returns.R')
source('../../r/fundamentals_direct_score_returns.R')
source('../../r/python_bridge.R')
testthat::test_that('holdout returns freeze both score arms before audit and retain budget', {
 root <- normalizePath('../..');work <- tempfile('holdout-cash-');dir.create(work)
 cuts <- list('100109'=stats::setNames(as.list(rep('2010-01-19T00:00:00Z',7)),as.character(1:7)))
 legs <- tibble::tibble(issue='100109',slot=1:7,provider_id=as.character(1:7),home='H',away='A',handicap=0,selected='W,L',protect_home=1,protect_away=1,group=1,protection_stake=c(40,rep(36,6)))
 grids <- tidyr::crossing(slot=1:7,tibble::tibble(home_goals=c(1,1),away_goals=c(0,1),probability=c(.7,.3))) |> dplyr::mutate(issue='100109',provider_id=as.character(slot),scenario='retrained')
 pred <- list(selected=list(fixtures=dplyr::mutate(legs,scenario='retrained'),scores=grids,cutoffs=cuts),market=list())
 predpath <- file.path(work,'predictions.json');obspath <- file.path(work,'comparison.json')
 jsonlite::write_json(pred,predpath,auto_unbox=TRUE,dataframe='rows')
 jsonlite::write_json(list(fixtures=dplyr::mutate(legs,scenario='baseline',actual_home=1,actual_away=0),prediction_sha256=digest::digest(file=predpath,algo='sha256')),obspath,auto_unbox=TRUE,dataframe='rows')
 fn <- eight_holdout_returns;scope <- new.env(parent=environment(fn));environment(fn) <- scope
 scope$ev_candidate_factors <- function(...) tibble::tibble(marker=1)
 real_bridge <- project_python_module
 scope$project_python_module <- function(name,...) {
  if(name=='src.temporal_learning.provenance') return(list(implementation_closure=function(...) list()))
  real_bridge(name,...)
 }
 summary <- tibble::tibble(issue='100109',model='retrained',selection='coverage',status='PLANNED',actual_groups=1)
 scope$selection_comparison_plans <- function(...) list(plans=list('100109/retrained/coverage'=list(legs=legs)),summary=summary,prediction_sha256='synthetic-plan')
 scope$fundamentals_settlement_audit <- function(...) {
  testthat::expect_true(file.exists(file.path(work,'returns','score-plan.json')))
  list(fixtures=dplyr::mutate(dplyr::select(legs,issue,slot,provider_id,handicap),bf_option='1:0',bf_sp=10,status='READY'))
 }
 scope$settle_selection_comparison <- function(...) list(summary=tibble::tibble(issue='100109',model='retrained',selection='coverage',stake=512,main_gross=100),groups=tibble::tibble(),legs=legs)
 py <- Sys.getenv('FUNDAMENTALS_PYTHON',Sys.getenv('RETICULATE_PYTHON'))
 x <- fn(predpath,obspath,'unused',file.path(work,'returns'),cuts,py,root,7,6,2,256,.65)
 testthat::expect_equal(x$score_scenarios$stake,rep(512,3))
 testthat::expect_equal(x$score_scenarios$score_gross[match(c('protection','direct','mixed'),x$score_scenarios$strategy)],c(0,1664,832))
 testthat::expect_error(fn(predpath,obspath,'unused',file.path(work,'returns'),cuts,py,root,7,6,2,128,.65),'constants')
 testthat::expect_error(fn(predpath,obspath,'unused',file.path(work,'returns'),list(),py,root,7,6,2,256,.65),'cutoff')
 original_audit <- scope$fundamentals_settlement_audit
 scope$fundamentals_settlement_audit <- function(...) {
   a <- original_audit(...);a$fixtures$status[1] <- 'bf:MISSING_WINNING_SP';a$fixtures$bf_sp[1] <- NA_real_;a
 }
 summary$planned_stake <- 512
 scope$settle_selection_comparison <- function(predictions,...) {
   testthat::expect_length(predictions$plans,0)
   testthat::expect_equal(nrow(predictions$summary),0)
   list(summary=tibble::tibble(issue=character(),model=character(),selection=character(),stake=double(),main_gross=double(),gross=double(),net=double()),groups=tibble::tibble(),legs=tibble::tibble())
 }
 pending <- fn(predpath,obspath,'unused',file.path(work,'returns'),cuts,py,root,7,6,2,256,.65)
 testthat::expect_equal(pending$comparison$settlement_status,'PENDING_AUDIT')
 testthat::expect_equal(pending$comparison$stake,512)
 testthat::expect_true(is.na(pending$comparison$net))
 testthat::expect_equal(nrow(pending$score_scenarios),0)
 testthat::expect_equal(nrow(pending$pending_settlement),1)
 testthat::expect_equal(jsonlite::read_json(file.path(work,'returns','score-plan.json'),simplifyVector=TRUE)$ledger$slot, x$score_ledger$slot)
 scope$ev_candidate_factors <- function(...) tibble::tibble()
 scope$fundamentals_settlement_audit <- function(...) stop('Audit must not be read')
 empty <- fn(predpath,obspath,'unused',file.path(work,'empty'),cuts,py,root,7,6,2,256,.65)
 testthat::expect_equal(empty$comparison$status,'NO_MARKET_CANDIDATES')
 testthat::expect_equal(empty$comparison$stake,0)
 testthat::expect_equal(nrow(empty$pending_settlement),0)
})
