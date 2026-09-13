source('../../r/probability_exploration.R')
source('../../r/strength_market_scenario.R')
source('../../r/fundamentals_score_diagnostic.R')
source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_market_comparison.R')
source('../../r/fundamentals_total_market.R')
source('../../r/n7_market_projection.R')

testthat::test_that('market-only projection equals existing projection without forms', {
  f <- tibble::tibble(issue='00101',slot=1L,provider_id='00123',handicap=-1L,
                     cutoff_utc='2010-01-01T00:00:00Z',odds_W=1.8,odds_D=3.5,odds_L=4)
  q <- tibble::tibble(issue='00101',slot=1L,provider_id='00123',company='A',
                     line=2.5,over_hk=.9,under_hk=.9)
  cuts <- list('00101'=list('1'=f$cutoff_utc))
  x <- project_n7_market_inputs(f,q,cuts,c(.1,16),1e-10)
  total <- total_market_constraint(q,c(.1,16))$lambda_total
  target <- 1/c(1.8,3.5,4);target <- target/sum(target)
  expected <- total_constrained_projection(total,target,-1,1e-10)
  testthat::expect_equal(x$grids[['00101/1']],expected$grid)
  testthat::expect_equal(as.numeric(x$fixtures[1,c('q_W','q_D','q_L')]),
                         unname(unlist(expected$fields[c('W','D','L')])))
  testthat::expect_identical(x$fixtures$provider_id,'00123')
  testthat::expect_false(x$historical_admission)
  testthat::expect_error(project_n7_market_inputs(f,q,list(),c(.1,16),1e-10),'cutoffs')
  testthat::expect_error(project_n7_market_inputs(f,q,list('00101'=list('1'='2011-01-01T00:00:00Z')),c(.1,16),1e-10),'cutoff mismatch')
  testthat::expect_error(project_n7_market_inputs(f,q[0,],cuts,c(.1,16),1e-10),'Missing')
  testthat::expect_error(project_n7_market_inputs(f,dplyr::bind_rows(q,q),cuts,c(.1,16),1e-10),'keys')
  testthat::expect_error(project_n7_market_inputs(dplyr::mutate(f,actual='W'),q,cuts,c(.1,16),1e-10),'schema')
  testthat::expect_error(project_n7_market_inputs(dplyr::mutate(f,odds_W=0),q,cuts,c(.1,16),1e-10),'numerical')
  empty <- project_n7_market_inputs(f[0,],q[0,],list(),c(.1,16),1e-10)
  testthat::expect_equal(nrow(empty$fixtures),0L)
  testthat::expect_type(empty$fixtures$q_D,'double')
})

testthat::test_that('published input adapter retains exclusions and source identity', {
  cut <- '2010-01-01T00:00:00Z'
  e <- list(issue='001',slot=1L,provider_id='002',market='euro',cutoff_utc=cut,
            status='QUOTES_PRIOR_DIAGNOSTIC',prior_companies=2L,
            rows=list(list(company='A',odds_W=2,odds_D=3,odds_L=4),
                      list(company='B',odds_W=3,odds_D=4,odds_L=5)))
  t <- list(issue='001',slot=1L,provider_id='002',market='total',cutoff_utc=cut,
            status='QUOTES_PRIOR_DIAGNOSTIC',prior_companies=1L,
            rows=list(list(company='A',line=2.5,over_hk=.9,under_hk=1)))
  h <- tibble::tibble(issue='001',slot=1L,provider_id='002',home_handicap=-1L)
  cuts <- list('001'=list('1'=cut))
  x <- n7_published_projection_inputs(list(e,t),h,cuts)
  testthat::expect_equal(x$fixtures$odds_W,2.5)
  testthat::expect_identical(x$cutoffs,cuts)
  testthat::expect_equal(nrow(x$total_quotes),1L)
  testthat::expect_equal(nrow(x$exclusions),0L)
  testthat::expect_equal(nrow(project_n7_market_inputs(x$fixtures,x$total_quotes,x$cutoffs,c(.1,16),1e-10)$fixtures),1L)
  bad <- t;bad$status <- 'NO_PRIOR_QUOTES';bad$rows <- list();bad$prior_companies <- 0L
  z <- n7_published_projection_inputs(list(e,bad),h,cuts)
  testthat::expect_equal(z$exclusions$total_status,'NO_PRIOR_QUOTES')
  testthat::expect_equal(nrow(z$fixtures),0L)
  testthat::expect_identical(z$input_cutoffs,cuts)
  testthat::expect_error(n7_published_projection_inputs(list(e,t),h[0,],cuts),'scope mismatch')
  testthat::expect_error(n7_published_projection_inputs(list(e,e,t),h,cuts),'two published')
  bad <- t;bad$provider_id <- '003'
  testthat::expect_error(n7_published_projection_inputs(list(e,bad),h,cuts),'identity/cutoff')
  bad <- t;bad$prior_companies <- 2L
  testthat::expect_error(n7_published_projection_inputs(list(e,bad),h,cuts),'company contract')
})

testthat::test_that('serialized empty arrays render through the projection entry', {
  root <- normalizePath('../..')
  input <- tempfile(fileext='.json'); output <- tempfile(fileext='.json')
  config <- file.path(root,'config/n7_next100_435.json')
  jsonlite::write_json(list(fixtures=list(),total_quotes=list(),cutoffs=list(),
    historical_admission=FALSE,implementation_hashes=list(),issue_order=list('00101'),
    exclusions=list(),publication_coverage=list(),source_hashes=list()),input,auto_unbox=TRUE)
  log <- system2(file.path(R.home('bin'),'Rscript'),c('--vanilla',
    shQuote(file.path(root,'scripts/run_n7_market_projection.R')),shQuote(input),
    digest::digest(file=input,algo='sha256'),shQuote(config),digest::digest(file=config,algo='sha256'),
    shQuote(output),shQuote(root)),stdout=TRUE,stderr=TRUE)
  testthat::expect_null(attr(log,'status'))
  testthat::expect_true(file.exists(output))
  if (file.exists(output)) {
    result <- jsonlite::read_json(output,simplifyVector=FALSE)
    testthat::expect_length(result$fixtures,0)
    testthat::expect_identical(result$issue_order,list('00101'))
    testthat::expect_false(result$historical_admission)
  }
})

testthat::test_that('unpublished batch keeps scope through the published entry', {
  root <- normalizePath('../..')
  market <- tempfile(fileext='.json.gz'); handicap <- tempfile(fileext='.json')
  output <- tempfile(fileext='.json')
  connection <- gzfile(market,'wt')
  writeLines(jsonlite::toJSON(list(rows=list(),issue_order=list('00101'),
    coverage=list(list(issue='00101',status='NOT_PUBLISHED',fixture_market_rows=0)),
    historical_admission=FALSE),auto_unbox=TRUE),connection)
  close(connection)
  market_sha <- digest::digest(file=market,algo='sha256')
  jsonlite::write_json(list(rows=list(),market_snapshot_sha256=market_sha,
    historical_admission=FALSE),handicap,auto_unbox=TRUE)
  log <- system2(file.path(R.home('bin'),'Rscript'),c('--vanilla',
    shQuote(file.path(root,'scripts/project_n7_published_markets.R')),shQuote(market),market_sha,
    shQuote(handicap),digest::digest(file=handicap,algo='sha256'),shQuote(output),shQuote(root)),
    stdout=TRUE,stderr=TRUE)
  testthat::expect_null(attr(log,'status'))
  testthat::expect_true(file.exists(output))
  if (file.exists(output)) {
    result <- jsonlite::read_json(output,simplifyVector=FALSE)
    testthat::expect_length(result$fixtures,0)
    testthat::expect_identical(result$issue_order,list('00101'))
    testthat::expect_identical(result$publication_coverage[[1]]$status,'NOT_PUBLISHED')
  }
})
