# Synthetic entry-point regression: a sealed purchase list must match selection.
testthat::test_that('independent replay rejects divergent purchased options', {
  root <- normalizePath('../..')
  work <- tempfile('purchase-replay-')
  dir.create(work)
  on.exit(unlink(work, recursive = TRUE), add = TRUE)
  fixtures <- rep(list(list(p_W=1/3,p_D=1/3,p_L=1/3,
                           q_W=1/3,q_D=1/3,q_L=1/3)),7)
  option <- list(fixtures=1:7,state_ids=1L,depth=1L,coverage=1/2187,
                 expected_gross=1.3,stake=2,sleeve_id=1)
  pool <- list(fixtures=fixtures,options=list(option),opening_options=1L,
               purchase_parameters=list(policy='PROB',gap_threshold=.05),mode='BREADTH')
  plan <- list(fixtures=fixtures,seed=1L,worlds=4L,
               policies=data.frame(id='JOINT',u=Inf,money=Inf,ordering='OPEN_FIRST'),
               arms=list(JOINT=list(pool=pool,fit=list(selected=1L),options=list(option))))
  for (corrupt in c(FALSE,TRUE)) {
    candidate <- plan
    if (corrupt) candidate$arms$JOINT$options[[1]]$state_ids <- 2L
    candidate$seal <- digest::digest(candidate,algo='sha256')
    saveRDS(candidate,file.path(work,'plan.rds'))
    receipt <- list(scope=list('100101'),bindings=list('100101'=list(file='plan.rds',
      sha256=digest::digest(file=file.path(work,'plan.rds'),algo='sha256'))))
    jsonlite::write_json(receipt,file.path(work,'plans-receipt.json'),auto_unbox=TRUE)
    hash <- digest::digest(file=file.path(work,'plans-receipt.json'),algo='sha256')
    output <- file.path(work,if(corrupt)'invalid.json' else 'valid.json')
    log <- file.path(work,'run.log')
    status <- system2(file.path(R.home('bin'),'Rscript'),
      shQuote(c(file.path(root,'scripts/check_n7_purchase_replay.R'),work,hash,output)),
      stdout=log,stderr=log)
    if(corrupt) {
      testthat::expect_true(status!=0L)
      testthat::expect_false(file.exists(output))
    } else {
      testthat::expect_equal(status,0L,info=paste(readLines(log),collapse='\n'))
      testthat::expect_identical(jsonlite::fromJSON(output)$status,'PASS')
    }
  }
})
