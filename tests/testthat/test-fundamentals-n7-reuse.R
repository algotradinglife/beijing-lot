source('../../r/python_bridge.R')
source('../../r/fundamentals_n7_reuse.R')

testthat::test_that('R parameter grid reproduces all 148 frozen plans and settles independently', {
  root <- normalizePath('../..');py <- Sys.getenv('FUNDAMENTALS_PYTHON')
  x <- jsonlite::fromJSON(gzfile('../fixtures/n7_reuse_interface.json.gz'),simplifyVector=TRUE)
  ctx <- prepare_n7_reuse(x$frame,x$cutoffs,py,root,7,1024,2,.65,41900,512,41901,1024)
  caps <- rbind(c(1,0),as.matrix(expand.grid(U=c(2,3,4,6,8,16),P=1:6)))
  for(d in 1:2) for(i in seq_len(nrow(caps))) for(replace in c(FALSE,TRUE)) {
    u <- caps[i,1];p <- caps[i,2]
    z <- plan_n7_reuse(ctx,x$cutoffs,d,u,p,py,root,replace_singles=replace)
    expected <- x$expected_seals[[paste0('D',d,'_U',u,'_P',p,'_',if(replace) 'SINGLE75' else 'BASE')]]
    testthat::expect_identical(z$receipt$plan_seal,expected)
    testthat::expect_s3_class(z$legs,'tbl_df');testthat::expect_s3_class(z$tickets,'tbl_df')
  }
  z <- plan_n7_reuse(ctx,x$cutoffs,2,16,6,py,root,replace_singles=TRUE)
  y <- settle_n7_reuse(z,x$audit,py,root)
  testthat::expect_identical(y$rule,c('BASE','SELECTED'))
  testthat::expect_true(all(y$stake+y$cash_cny==1024));testthat::expect_gt(y$gross[2],y$gross[1])
  # Manual independent one-ticket payout, with explicit identity join and one .65.
  leg <- dplyr::left_join(z$legs,x$audit,by=c('issue','slot','provider_id','handicap'),relationship='many-to-one')
  actual <- c(W='3',D='1',L='0')[leg$actual_direction]
  hit <- mapply(grepl,actual,leg$support,fixed=TRUE)
  gross <- 0
  for(g in unique(leg$group)) if(all(hit[leg$group==g])) gross <- gross+2*.65*prod(leg$spf_sp[leg$group==g])
  testthat::expect_equal(y$gross[2],gross)
  for(rule in c('GAP','MARKET','EITHER')) {
    z <- plan_n7_reuse(ctx,x$cutoffs,2,16,6,py,root,TRUE,.50,rule,.05,.15,.05)
    testthat::expect_equal(z$summary$stake_cny,1024)
    testthat::expect_equal(nrow(z$tickets),512)
    rt <- .n7_reuse_runtime(py,root)
    key <- names(jsonlite::fromJSON(z$bundle_json,simplifyVector=FALSE))[1]
    b <- rt$json$loads(z$bundle_json)$`__getitem__`(key)$`__getitem__`('plan')
    cuts <- reticulate::dict(convert=FALSE)
    for(s in names(x$cutoffs)) cuts$`__setitem__`(s,rt$temporal$Cutoff$decision_epoch(x$issue,x$cutoffs[[s]]))
    expected <- rt$support$replace_repeated_support(b,cutoffs=cuts,change_singles=TRUE,double_rule=rule,
      single_ceiling=.5,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
    testthat::expect_identical(z$receipt$plan_seal,reticulate::py_to_r(expected$`__getitem__`('seal')))
  }
  changed <- x$cutoffs;changed[[1]] <- '2009-01-01T00:00:00Z'
  testthat::expect_error(plan_n7_reuse(ctx,changed,2,2,4,py,root))
  for(d in list(0,3,NA,TRUE)) testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,d,2,4,py,root))
  for(u in list(0,-1,2.5,Inf,NA,TRUE)) testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,2,u,4,py,root))
  for(p in list(-1,7,1.5,NA,TRUE)) testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,2,2,p,py,root))
  testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,2,2,4,py,root,single_ceiling=TRUE))
  testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,2,2,4,py,root,double_rule='OTHER'))
  testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,2,2,4,py,root,max_gap=NA_real_))
  testthat::expect_error(plan_n7_reuse(ctx,x$cutoffs,2,2,4,py,root,single_ceiling=c(.5,.75),max_gap=numeric(0)))
  testthat::expect_error(prepare_n7_reuse(x$frame,x$cutoffs,py,root,7,1024,2,.65,c(41900,41901),numeric(0),41901,1024))
  bad <- ctx;bad$r_hashes[[1]] <- 'changed'
  testthat::expect_error(plan_n7_reuse(bad,x$cutoffs,2,2,4,py,root))
  bad <- ctx;bad$parameters$candidate_seed <- 123
  testthat::expect_error(plan_n7_reuse(bad,x$cutoffs,2,2,4,py,root))
  # Distinct replacement settings must never collapse into one policy key.
  one <- plan_n7_reuse(ctx,x$cutoffs,2,2,4,py,root,FALSE)
  two <- plan_n7_reuse(ctx,x$cutoffs,2,2,4,py,root,TRUE)
  testthat::expect_false(identical(names(jsonlite::fromJSON(one$bundle_json)),names(jsonlite::fromJSON(two$bundle_json))))
  same <- plan_n7_reuse(ctx,x$cutoffs,2L,2L,4L,py,root,FALSE)
  testthat::expect_identical(one$bundle_json,same$bundle_json)
  integer_ctx <- prepare_n7_reuse(x$frame,x$cutoffs,py,root,7L,1024L,2L,.65,41900L,512L,41901L,1024L)
  integer_plan <- plan_n7_reuse(integer_ctx,x$cutoffs,2,2,4,py,root,FALSE)
  testthat::expect_identical(one$bundle_json,integer_plan$bundle_json)
  testthat::expect_identical(ctx$metadata_seal,integer_ctx$metadata_seal)
  bad <- z;bad$bundle_json <- paste0(bad$bundle_json,' ')
  testthat::expect_error(settle_n7_reuse(bad,x$audit,py,root))
  bad <- z;bad$receipt$parameters$U <- 99
  testthat::expect_error(settle_n7_reuse(bad,x$audit,py,root))
  testthat::expect_error(settle_n7_reuse(z,x$audit[0,],py,root))
  testthat::expect_error(settle_n7_reuse(z,rbind(x$audit,x$audit[1,]),py,root))
  # No outcome fields may enter the preparation API; missing inputs fail closed.
  bad <- x$frame;bad$actual_direction <- 'W'
  testthat::expect_error(prepare_n7_reuse(bad,x$cutoffs,py,root,7,1024,2,.65,41900,512,41901,1024))
  bad <- x$frame;bad$p_W[1] <- NA_real_
  testthat::expect_error(prepare_n7_reuse(bad,x$cutoffs,py,root,7,1024,2,.65,41900,512,41901,1024))
  testthat::expect_error(prepare_n7_reuse(x$frame[0,],list(),py,root,7,1024,2,.65,41900,512,41901,1024))
  testthat::expect_error(.n7_reuse_runtime('/missing/python',root))
  # R/Python IDs remain strings, including leading zeros; slot types are integer.
  f <- x$frame;f$issue <- '001';f$provider_id <- paste0('00',f$provider_id)
  c2 <- prepare_n7_reuse(f,x$cutoffs,py,root,7,1024,2,.65,41900,128,41901,128)
  p2 <- plan_n7_reuse(c2,x$cutoffs,1,1,0,py,root)
  testthat::expect_true(all(p2$legs$issue=='001'));testthat::expect_true(all(startsWith(p2$legs$provider_id,'00')))
  testthat::expect_type(p2$legs$slot,'integer')
})
