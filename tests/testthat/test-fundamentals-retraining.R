source('../../r/fundamentals_retraining.R')
source('../../r/fundamentals_expert_coverage.R')
source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_score_diagnostic.R')

testthat::test_that('market predictors and expert projection preserve identity and missing scope', {
 cuts <- list('100105'=list('1'='2010-01-12T15:01:00Z'))
 f <- tibble::tibble(issue='100105',slot=1L,provider_id='x',home='H',away='A',
                    handicap=0,baseline_draw=.2,baseline_cover=.3,scenario='baseline')
 g <- tibble::tibble(home_goals=c(0,1,0),away_goals=c(0,0,1),probability=c(.2,.5,.3),outcome=c('D','W','L'))
 market <- list(cutoffs=cuts,status=dplyr::mutate(f,status='READY',lambda_home=1.5,lambda_away=1),grids=list('100105/1'=g))
 x <- retraining_market_features(f,market,cuts)
 testthat::expect_equal(x$market_total,2.5)
 testthat::expect_equal(x$market_draw,.2)
 market$status$status <- 'MISSING'
 testthat::expect_true(is.na(retraining_market_features(f,market,cuts)$market_draw))
 testthat::expect_error(retraining_market_features(f,market,list()),'cutoff')
 control <- list(fixtures=f,scores=dplyr::mutate(g,issue=f$issue,slot=f$slot,provider_id='x',scenario='baseline'),cutoffs=cuts)
 s <- tibble::tibble(issue='100105',slot=1L,provider_id='x',draw_probability=.7,draw_signal='POSITIVE',high_probability=NA_real_,high_signal='NOT_APPLICABLE')
 y <- retraining_score_choices(control,s,cuts,.5)
 testthat::expect_equal(y$fixtures$selected,'D,W')
 testthat::expect_equal(sum(y$scores$probability[y$scores$outcome=='D']),.45)
 testthat::expect_equal(y$fixtures$protect_away,1L)
 s$draw_signal <- 'ABSTAIN'
 testthat::expect_equal(retraining_score_choices(control,s,cuts,.5)$fixtures$selected,'W,L')
 testthat::expect_error(retraining_score_choices(control,s[0,],cuts,.5),'signals')
 testthat::expect_error(retraining_score_choices(control,s,list(),.5),'cutoffs')
})

testthat::test_that('new-input preparation replays saved pages without reading target settlement', {
 root <- normalizePath('../..')
 for(p in c('python_bridge','probability_exploration','fundamentals_home_away','goal_distribution_experiment',
             'fundamentals_high_margin','fundamentals_three_issue_experts')) source(file.path(root,'r',paste0(p,'.R')))
 py <- Sys.getenv('FUNDAMENTALS_PYTHON'); bundle <- Sys.getenv('NEXT_ISSUE_FIXTURE')
 testthat::expect_true(nzchar(py) && file.exists(py))
 testthat::expect_true(nzchar(bundle) && file.exists(file.path(bundle,'context.json')))
 x <- retraining_new_inputs(file.path(bundle,'inventories.json'),file.path(bundle,'context.json'),py,root,file.path(bundle,'cache'))
 testthat::expect_true(nrow(x$features)>0)
 testthat::expect_false(any(c('actual_home','actual_away','draw_target','cover_target') %in% names(x$features)))
 projection <- project_python_module('src.context_projection',root,py,FALSE)
 compact_path <- tempfile(fileext='.json')
 projection$project_feature_context(file.path(bundle,'context.json'),compact_path)
 compact <- jsonlite::read_json(compact_path,simplifyVector=TRUE)
 original_context <- jsonlite::read_json(file.path(bundle,'context.json'),simplifyVector=TRUE)
 testthat::expect_identical(expert_feature_table(x$features,compact,x$cutoffs),
                           expert_feature_table(x$features,original_context,x$cutoffs))
 bad <- jsonlite::read_json(file.path(bundle,'context.json'));bad$cutoffs <- list()
 path <- tempfile(fileext='.json');jsonlite::write_json(bad,path,auto_unbox=TRUE)
  testthat::expect_error(retraining_new_inputs(file.path(bundle,'inventories.json'),path,py,root,NULL),'cutoffs')
 # A whole-scope call must preserve the previous per-issue feature values.
 ctx <- jsonlite::read_json(file.path(bundle,'context.json'))
 ctx$canonical_json <- NULL;ctx$seal <- NULL
 second <- ctx$rows
 for(i in seq_along(second)) second[[i]]$issue <- '100105'
 ctx$rows <- c(ctx$rows,second)
 second_receipts <- ctx$receipts
 for(i in seq_along(second_receipts)) second_receipts[[i]]$issue <- '100105'
 ctx$receipts <- c(ctx$receipts,second_receipts)
 ctx$cutoffs[['100105']] <- ctx$cutoffs[['100104']]
 encoded <- as.character(jsonlite::toJSON(ctx,auto_unbox=TRUE,digits=15,null='null'))
 ctx <- jsonlite::parse_json(encoded,simplifyVector=TRUE)
 ctx$canonical_json <- encoded
 ctx$seal <- digest::digest(encoded,algo='sha256',serialize=FALSE)
 first <- x$features;second <- first;second$issue <- '100105'
 together <- expert_feature_table(dplyr::bind_rows(first,second),ctx,ctx$cutoffs)
 separate <- dplyr::bind_rows(expert_feature_table(first,ctx,ctx$cutoffs),expert_feature_table(second,ctx,ctx$cutoffs))
 testthat::expect_identical(together,separate)
})

testthat::test_that('prepared raw and imported code changes fail before prediction', {
 root <- tempfile('provenance-');dir.create(root);dir.create(file.path(root,'src'))
 raw <- file.path(root,'page.json');writeLines('original',raw)
 code <- file.path(root,'src','parser.py');writeLines('# parser',code)
 model <- list(experiments=list(),scores=list(),coverage_choices=list(),
   provenance=list(list(input_file_hashes=stats::setNames(list(digest::digest(file=raw,algo='sha256')),raw),
     implementation_hashes=list('parser.py'=digest::digest(file=code,algo='sha256')))),
   implementation_hashes=list(),parameters=list(),gates=list(),historical_admission=FALSE)
 model$seal <- digest::digest(model,algo='sha256')
 testthat::expect_true(retraining_verify_provenance(model,root))
 writeLines('changed',raw)
 testthat::expect_error(retraining_verify_provenance(model,root),'source/implementation changed')
 writeLines('original',raw);writeLines('# changed',code)
 testthat::expect_error(retraining_verify_provenance(model,root),'source/implementation changed')
 model$parameters <- list(changed=TRUE)
 testthat::expect_error(retraining_verify_provenance(model,root),'seal changed')
})

testthat::test_that('comparison freezes choices before labels and replays exactly', {
 root <- normalizePath('../..');out <- tempfile('comparison-');dir.create(out);dir.create(file.path(out,'market'))
 cuts <- list('100101'=list('1'='2010-01-01T00:00:00Z'),
              '100104'=list('1'='2010-01-10T00:00:00Z'),'100105'=list('1'='2010-01-12T00:00:00Z'))
 f <- tibble::tibble(issue=names(cuts),slot=1L,provider_id=c('a','b','c'),home='H',away='A',
                    handicap=0,scenario='baseline',x=1,baseline_draw=.2,baseline_cover=.3)
 g <- tibble::tibble(home_goals=c(0,1,0),away_goals=c(0,0,1),probability=c(.2,.5,.3),outcome=c('D','W','L'))
 old <- f[1:2,];old$actual_home <- 1L;old$actual_away <- 0L
 for(i in 1:2) jsonlite::write_json(list(fixtures=old[i,]),file.path(out,paste0('old',i,'.json')),auto_unbox=TRUE,dataframe='rows')
 jsonlite::write_json(list(data=dplyr::mutate(old,issue_code=issue),features=list(draw='x',high='x')),
                     file.path(out,'training.json'),auto_unbox=TRUE,dataframe='rows')
 raw <- file.path(out,'raw.json');writeLines('raw',raw)
 e <- list(fixtures=dplyr::mutate(f[3,],variant='raw',status='OK_DIAGNOSTIC',W=.5,D=.2,L=.3),
           grids=list('1/raw'=g),cutoffs=cuts[['100105']])
 model <- list(experiments=list('100105'=e),scores=list(),coverage_choices=list(),
  provenance=list(list(input_file_hashes=stats::setNames(list(digest::digest(file=raw,algo='sha256')),raw),implementation_hashes=list())),
  implementation_hashes=list(),parameters=list(),gates=list(),historical_admission=FALSE)
 model$provenance$expert_context <- list(input_file_hashes=list(),implementation_hashes=list(),expert_feature_sha256=digest::digest(f[3,],algo='sha256'))
 model$seal <- digest::digest(model,algo='sha256')
 saveRDS(list(models=model,features=f[3,],cutoffs=cuts['100105']),file.path(out,'new-inputs-internal.rds'))
 jsonlite::write_json(list(list(issue='100105',cutoffs=cuts[['100105']])),file.path(out,'new-inventories.json'),auto_unbox=TRUE)
 for(path in c('frozen-experts.pkl','frozen-experts.json','market/euro.json','market/total.json')) writeLines('fixture',file.path(out,path))
 control <- list(fixtures=old,scores=dplyr::bind_rows(lapply(1:2,function(i)dplyr::mutate(g,issue=old$issue[i],slot=1L,provider_id=old$provider_id[i],scenario='baseline'))),cutoffs=cuts)
 market <- list(status=dplyr::mutate(f,status='READY',lambda_home=1.5,lambda_away=1),
                grids=stats::setNames(rep(list(g),3),paste(f$issue,1,sep='/')),cutoffs=cuts)
 fn <- retraining_comparison;scope <- new.env(parent=environment(fn));environment(fn) <- scope
 scope$ev_control_inputs <- function(...) control
 scope$ev_market_probabilities <- function(...) market
 scope$project_python_module <- function(name,...) {
   if(name=='src.temporal_learning') return(list(Cutoff=list(decision_epoch=function(...) list())))
   list(predict_frozen_file=function(path,frame,cutoff,...) {
     result <- dplyr::transmute(frame,issue_code,slot,provider_id,
       draw_probability=.7,draw_signal='POSITIVE',high_probability=NA_real_,high_signal='NOT_APPLICABLE')
     list(to_dict=function(orient)lapply(seq_len(nrow(result)),function(i)as.list(result[i,])))
   })
 }
 scope$evaluate_issue_score_models <- function(...) {
   testthat::expect_true(file.exists(file.path(out,'predictions.json')))
   list(fixtures=dplyr::mutate(e$fixtures,actual_home=0L,actual_away=0L,scorable=TRUE))
 }
 x <- fn(out,file.path(out,'old1.json'),file.path(out,'old2.json'),'unused',root,cuts,.5)
 testthat::expect_equal(nrow(x$summary),6L)
 testthat::expect_equal(x$fixtures$main_hit[x$fixtures$issue=='100105'],c(FALSE,TRUE))
 y <- fn(out,file.path(out,'old1.json'),file.path(out,'old2.json'),'unused',root,cuts,.5)
 testthat::expect_identical(x$receipt,y$receipt)
 testthat::expect_error(fn(out,file.path(out,'old1.json'),file.path(out,'old2.json'),'unused',root,cuts,.6),'Frozen predictions changed')
 prepared <- readRDS(file.path(out,'new-inputs-internal.rds'))
 altered <- prepared;altered$features$x[1] <- 99
 saveRDS(altered,file.path(out,'new-inputs-internal.rds'))
 testthat::expect_error(fn(out,file.path(out,'old1.json'),file.path(out,'old2.json'),'unused',root,cuts,.5),'expert features changed')
 saveRDS(prepared,file.path(out,'new-inputs-internal.rds'))
 writeLines('mutated',raw)
 testthat::expect_error(fn(out,file.path(out,'old1.json'),file.path(out,'old2.json'),'unused',root,cuts,.5),'source/implementation changed')
})
