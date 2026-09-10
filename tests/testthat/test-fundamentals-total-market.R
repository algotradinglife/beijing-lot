source('../../r/probability_exploration.R')
source('../../r/strength_market_scenario.R')
source('../../r/fundamentals_score_diagnostic.R')
source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_market_comparison.R')
source('../../r/fundamentals_total_market.R')

test_that('Asian settlement handles half whole quarter lines and rejects invalids', {
  expect_equal(asian_total_probability(2.7,2.5),ppois(2,2.7,lower.tail=FALSE))
  w <- ppois(2,2.7,lower.tail=FALSE);l <- ppois(1,2.7)
  expect_equal(asian_total_probability(2.7,2),w/(w+l))
  expect_equal(asian_total_probability(2.7,2.25),w/(w+l+.5*dpois(2,2.7)))
  expect_equal(asian_total_probability(2.7,2.75),(ppois(3,2.7,lower.tail=FALSE)+.5*dpois(3,2.7))/
    (ppois(3,2.7,lower.tail=FALSE)+.5*dpois(3,2.7)+ppois(2,2.7)))
  expect_error(asian_total_probability(NA_real_,2.5),'Invalid')
  expect_error(asian_total_probability(2,2.1),'Invalid')
  expect_error(asian_total_probability(-1,2.5),'Invalid')
})

test_that('heterogeneous line inversion recovers total and fixed total fit', {
  lines <- c(2,2.25,2.5,2.75,3)
  prob <- vapply(lines,function(l)asian_total_probability(2.7,l),numeric(1))
  q <- tibble::tibble(company=letters[1:5],line=lines,over_hk=1/prob-1,under_hk=1/(1-prob)-1)
  x <- total_market_constraint(q,c(.1,16))
  expect_equal(x$lambda_total,2.7,tolerance=1e-8)
  expect_equal(x$companies$lambda_total,rep(2.7,5),tolerance=1e-8)
  expect_error(total_market_constraint(q[c(1,1),],c(.1,16)),'Invalid')
  expect_error(total_market_constraint(q[0,],c(.1,16)),'Invalid')
  expect_error(total_market_constraint(q,c(3,4)))
  p <- market_score_projection(c(1.8,.9),-1,1e-10)
  target <- unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])
  fit <- total_constrained_projection(2.7,target,-1,1e-10)
  expect_equal(fit$fields$lambda_home,1.8,tolerance=1e-7)
  expect_equal(fit$fields$lambda_home+fit$fields$lambda_away,2.7)
  expect_lt(fit$fields$market_residual,1e-7)
  expect_error(total_constrained_projection(2.7,c(.5,.5,.5),0,1e-10),'Invalid')
})

test_that('OU scenarios preserve total seal choices and refuse mutation', {
  project <- normalizePath('../..')
  p <- market_score_projection(c(1.8,.9),-1,1e-10)
  row <- dplyr::bind_cols(tibble::tibble(issue='001',slot=1L,provider_id='id',home='Home',away='Away',
    variant='raw',status='OK_DIAGNOSTIC',handicap=-1),tibble::as_tibble(p$fields))
  baseline <- row
  bp <- market_score_projection(c(1.2,1.5),-1,1e-10)
  for(field in names(bp$fields)) baseline[[field]] <- bp$fields[[field]]
  fixtures <- dplyr::bind_rows(dplyr::mutate(baseline,scenario='baseline'),dplyr::mutate(row,scenario='market'))
  cuts <- list('001'=list('1'='2010-01-01T00:00:00Z'))
  h <- list('r/probability_exploration.R'=digest::digest(file='../../r/probability_exploration.R',algo='sha256'))
  odds <- 1/unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])
  quote <- list(issue='001',slot=1L,odds_W=unname(odds[1]),odds_D=unname(odds[2]),odds_L=unname(odds[3]))
  market <- list(fixtures=fixtures,grids=list('001/1/baseline'=bp$grid,'001/1/market'=p$grid),
    choices=tibble::tibble(),receipt=list(cutoffs=cuts,source_model_seal='base',implementation_hashes=h,
      quote_inputs=list(seal='euro',rows=list(quote),implementation_hashes=h)))
  market$seal <- digest::digest(market,algo='sha256')
  target <- asian_total_probability(2.7,2.5)
  q <- list(issue='001',slot=1L,provider_id='id',company='A',line=2.5,
    over_hk=1/target-1,under_hk=1/(1-target)-1)
  totals <- list(cutoffs=cuts,euro_seal='euro',historical_admission=FALSE,capture_hashes=h,implementation_hashes=h,
    rows=list(list(issue='001',slot=1L,provider_id='id',status='OK_DIAGNOSTIC')),selected=list(q))
  totals$canonical_json <- as.character(jsonlite::toJSON(totals,auto_unbox=TRUE,digits=17,null='null'))
  totals$seal <- digest::digest(totals$canonical_json,algo='sha256',serialize=FALSE)
  args <- list(market=market,totals=totals,cutoffs=cuts,project_root=project,generated_at='2026-09-08T00:00:00Z',
    total_bounds=c(.1,16),correction_alpha=.1,residual_limit=.05,tail_tolerance=1e-10)
  x <- do.call(prepare_total_market_comparison,args)
  expect_equal(nrow(x$fixtures),4)
  expect_equal(x$fixtures$lambda_home+x$fixtures$lambda_away,rep(2.7,4))
  corrected <- dplyr::filter(x$fixtures,scenario=='ou_corrected10')
  uncorrected <- dplyr::filter(x$fixtures,scenario=='ou_market')
  expect_equal(corrected$lambda_home/2.7,.9*(uncorrected$lambda_home/2.7)+.1*(1.2/2.7),tolerance=1e-10)
  expect_lt(corrected$lambda_home,uncorrected$lambda_home)
  expect_identical(x,do.call(prepare_total_market_comparison,args))
  ev <- list(fixtures=dplyr::mutate(row,scorable=TRUE,actual_home=3L,actual_away=0L),seal='base')
  result <- evaluate_score_shape_scenarios(x,ev)
  expect_equal(nrow(result$summary),4)
  ev$fixtures$actual_home <- 0L
  invisible(evaluate_score_shape_scenarios(x,ev))
  expect_identical(x,do.call(prepare_total_market_comparison,args))
  bad <- args;bad$cutoffs <- list()
  expect_error(do.call(prepare_total_market_comparison,bad),'cutoffs')
  bad <- args;bad$totals$selected[[1]]$over_hk <- 99
  expect_error(do.call(prepare_total_market_comparison,bad),'mutated')
  bad <- args;bad$market$fixtures$lambda_home[1] <- 99
  expect_error(do.call(prepare_total_market_comparison,bad),'sealed')
  bad <- args;bad$residual_limit <- 1e-14
  expect_error(do.call(prepare_total_market_comparison,bad),'No common')
  bad <- args;bad$correction_alpha <- .3
  expect_error(do.call(prepare_total_market_comparison,bad),'Invalid')
})
