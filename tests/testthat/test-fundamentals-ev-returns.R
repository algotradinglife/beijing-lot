for(p in c('python_bridge','fundamentals_returns','fundamentals_ev_returns')) source(paste0('../../r/',p,'.R'))

testthat::test_that('market factors and seven selection never need actual SP', {
 py <- Sys.getenv('FUNDAMENTALS_PYTHON');root <- normalizePath('../..')
 cuts <- list(i=as.list(stats::setNames(rep('2010-01-10T00:00:00Z',8),1:8)))
 fixtures <- tidyr::expand_grid(slot=1:8,scenario=c('baseline','both_half')) |>
   dplyr::mutate(issue='i',provider_id=as.character(slot),home='H',away='A',handicap=0,selected='W,L',protect_home=0,protect_away=0)
 g <- tibble::tibble(home_goals=c(0,1,0),away_goals=c(0,0,1),probability=c(.2,.5,.3),outcome=c('D','W','L'))
 scores <- dplyr::cross_join(dplyr::select(fixtures,issue,slot,provider_id,scenario),g)
 control <- list(fixtures=fixtures,scores=scores,cutoffs=cuts,source_hashes=list(test='fixture'))
 market <- list(grids=stats::setNames(rep(list(g),8),paste('i',1:8,sep='/')),cutoffs=cuts,receipt=list(test='fixture'))
 f <- ev_candidate_factors(control,market,py,root)
 testthat::expect_equal(f$main_factor,rep(2,16))
 testthat::expect_equal(f$protection_factor,rep(1,16))
 testthat::expect_equal(f$protection_sp_proxy,rep(5,16))
 path <- tempfile(fileext='.json');p <- ev_seven_plans(f,control,market,py,root,path)
 testthat::expect_equal(p$summary$expected_roi,rep(-.35,2),tolerance=1e-10)
 testthat::expect_equal(p$plans[['i/baseline']]$legs$slot,1:7)
 testthat::expect_identical(ev_seven_plans(f,control,market,py,root,path)$prediction_sha256,p$prediction_sha256)
 audit <- tibble::tibble(issue='i',slot=1:8,provider_id=as.character(1:8),handicap=0,status='READY',spf_sp=2,bf_sp=10,actual_direction='W',bf_option='1:0')
 settled <- ev_settle_plans(p,audit,py,root)
 testthat::expect_equal(settled$summary$main_gross,rep(6*.65*2^7,2))
 audit$spf_sp <- 20
 different <- ev_settle_plans(p,audit,py,root)
 testthat::expect_identical(different$prediction_sha256,settled$prediction_sha256)
 testthat::expect_gt(different$summary$main_gross[1],settled$summary$main_gross[1])
 f$main_factor[1] <- 9
 testthat::expect_error(ev_seven_plans(f,control,market,py,root,path),'Frozen')
 small <- ev_seven_plans(dplyr::filter(f,slot<=6),control,market,py,root,tempfile())
 testthat::expect_true(all(small$summary$status=='FEWER_THAN_SEVEN_MARKET_MATCHES'))
 testthat::expect_equal(nrow(ev_settle_plans(small,audit,py,root)$summary),0L)
 bad <- p;bad$implementation$r[[1]] <- 'bad'
 testthat::expect_error(ev_settle_plans(bad,audit,py,root),'implementation changed')
 market$grids[['i/1']]$probability[1] <- 0
 testthat::expect_error(ev_candidate_factors(control,market,py,root),'Normalized')
})

testthat::test_that('control columns and sealed market inversion enforce their contracts', {
 root <- normalizePath('../..');py <- Sys.getenv('FUNDAMENTALS_PYTHON');out <- tempfile();dir.create(out)
 status <- system2(py,c(file.path(root,'scripts/prepare_ev_returns_fixture.py'),'--output',out))
 testthat::expect_equal(status,0L)
 for(p in c('probability_exploration','fundamentals_market_comparison','fundamentals_total_market')) source(file.path(root,'r',paste0(p,'.R')))
 inv <- jsonlite::read_json(file.path(out,'inventories.json'))
 cuts <- stats::setNames(lapply(inv,`[[`,'cutoffs'),vapply(inv,`[[`,character(1),'issue'))
 control <- ev_control_inputs(file.path(out,'previous.json'),file.path(out,'next.json'),cuts)
 testthat::expect_equal(nrow(control$fixtures),4L)
 testthat::expect_false(any(c('actual_home','actual_away','spf_sp') %in% names(control$fixtures)))
 testthat::expect_error(ev_control_inputs(file.path(out,'previous.json'),file.path(out,'next.json'),list()),'cutoff')
 market <- ev_market_probabilities(file.path(out,'euro.json'),file.path(out,'total.json'),control$fixtures,cuts,root,1e-10)
 testthat::expect_true(all(market$status$status=='READY'))
 testthat::expect_equal(unname(vapply(market$grids,function(g)sum(g$probability),numeric(1))),rep(1,2))
 e <- jsonlite::read_json(file.path(out,'euro.json'));e$seal <- 'bad';jsonlite::write_json(e,file.path(out,'euro.json'),auto_unbox=TRUE)
 testthat::expect_error(ev_market_probabilities(file.path(out,'euro.json'),file.path(out,'total.json'),control$fixtures,cuts,root,1e-10),'seal')
})


testthat::test_that('empty sealed quote arrays retain an unavailable denominator', {
 root <- normalizePath('../..');out <- tempfile();dir.create(out)
 cuts <- list(i=list('1'='2010-01-01T00:00:00Z'))
 payloads <- list(euro=list(rows=list(),implementation_hashes=list()),total=list(rows=list(),cutoffs=cuts,capture_hashes=list(),implementation_hashes=list()))
 for(n in names(payloads)) {
   if(n=='total') payloads[[n]]$euro_seal <- seal
   canonical <- as.character(jsonlite::toJSON(payloads[[n]],auto_unbox=TRUE))
   seal <- digest::digest(canonical,algo='sha256',serialize=FALSE)
   jsonlite::write_json(list(canonical_json=canonical,seal=seal),file.path(out,paste0(n,'.json')),auto_unbox=TRUE)
 }
 fixtures <- tibble::tibble(issue='i',slot=1L,provider_id='1',handicap=0)
 result <- ev_market_probabilities(file.path(out,'euro.json'),file.path(out,'total.json'),fixtures,cuts,root,1e-10)
 testthat::expect_equal(result$status$status,'MARKET_UNAVAILABLE')
 testthat::expect_length(result$grids,0L)
})
