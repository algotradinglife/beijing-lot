test_that('26105 native CLI rejects missing mode or an unknown mode before SDK use', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 path <- file.path(root,'r/global_dynamic_26105_native_20261019.R')
 context <- new.env(parent=globalenv())
 context$commandArgs <- function(...) character()
 expect_error(sys.source(path,envir=context),'length(args)',fixed=TRUE)
 context$commandArgs <- function(...) c(root,root,'unsupported')
 expect_error(sys.source(path,envir=context),'args[3]',fixed=TRUE)
})
test_that('26105 native CLI rejects invalid shard plans before SDK use', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 path <- file.path(root,'r/global_dynamic_26105_native_20261019.R')
 context <- new.env(parent=globalenv())
 context$commandArgs <- function(...) c(root,root,'fit','1','4')
 expect_error(sys.source(path,envir=context),'shards == 3L',fixed=TRUE)
 context$commandArgs <- function(...) c(root,root,'fit','0','3')
 expect_error(sys.source(path,envir=context),'shard >= 1L',fixed=TRUE)
})

test_that('native input receipt and immutable assembly guards stop before fitting', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 withr::local_dir(root)
 work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
 input <- file.path(work,'inputs.json');metadata <- file.path(work,'metadata.json');inventory <- file.path(work,'inventory.json');receipt <- file.path(work,'intake-receipt.json')
 jsonlite::write_json(list(source_versions=list(),input_bindings=list()),input)
 writeLines('{}',metadata);writeLines('{}',inventory)
 jsonlite::write_json(list(input_sha256='incorrect'),receipt,auto_unbox=TRUE)
 context <- new.env(parent=globalenv());context$commandArgs <- function(...) c(root,root,'assemble');context$python_backend <- function(...) NULL
 testthat::local_mocked_bindings(import=function(module,...) {
  if(module=='beidan_backend.catalog.paths')return(list(location=function(token,...) {
   if(grepl('history-metadata',token,fixed=TRUE))metadata else if(grepl('channel-inventory',token,fixed=TRUE))inventory else work
  }))
  list()
 },py_str=function(x) x,.package='reticulate')
 path <- file.path(root,'r/global_dynamic_26105_native_20261019.R')
 expect_error(sys.source(path,envir=context),'Intake receipt input hash mismatch',fixed=TRUE)
 expect_false(dir.exists(file.path(work,'native-fit-shards')))
 jsonlite::write_json(list(input_sha256=digest::digest(file=input,algo='sha256'),source_versions=list(),input_bindings=list()),receipt,auto_unbox=TRUE)
 writeLines('existing frozen artifact',file.path(work,'fixtures.csv'))
 expect_error(sys.source(path,envir=context),'Immutable assembled output exists',fixed=TRUE)
 expect_identical(readLines(file.path(work,'fixtures.csv')),'existing frozen artifact')
 unlink(file.path(work,'fixtures.csv'))
 context$readBin <- function(con,...) {
  bytes <- base::readBin(con,...)
  if(identical(con,input))writeLines('{}',input)
  bytes
 }
 expect_error(sys.source(path,envir=context),'Native source changed during intake',fixed=TRUE)
 expect_false(dir.exists(file.path(work,'native-fit-shards')))
})

test_that('native rejects a changed decision cutoff even when input receipt was regenerated', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 withr::local_dir(root)
 work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
 input <- file.path(work,'inputs.json');metadata <- file.path(work,'metadata.json');inventory <- file.path(work,'inventory.json');receipt <- file.path(work,'intake-receipt.json')
 writeLines('{}',inventory)
 fixtures <- lapply(seq_len(365L),function(i) list(fixture_id=paste0('26105:',i),kickoff_at='2026-10-16T09:00:00Z',cutoff_utc='2026-10-15T10:00:00Z',handicap=0L))
 jsonlite::write_json(list(issue_id='26105',fixtures=fixtures,source_versions=list(),input_bindings=list()),input,auto_unbox=TRUE)
 jsonlite::write_json(list(issue_id='26105',inventory_sha256=digest::digest(file=inventory,algo='sha256'),network_attempts=0L,packets=lapply(seq_len(365L),function(i) list(fixture_id=paste0('26105:',i)))),metadata,auto_unbox=TRUE)
 jsonlite::write_json(list(input_sha256=digest::digest(file=input,algo='sha256'),source_versions=list(),input_bindings=list()),receipt,auto_unbox=TRUE)
 context <- new.env(parent=globalenv());context$commandArgs <- function(...) c(root,root,'fit','1','3');context$python_backend <- function(...) NULL
 testthat::local_mocked_bindings(import=function(module,...) {
  if(module=='beidan_backend.catalog.paths')return(list(location=function(token,...) {
   if(grepl('history-metadata',token,fixed=TRUE))metadata else if(grepl('channel-inventory',token,fixed=TRUE))inventory else work
  }))
  list()
 },py_str=function(x) x,.package='reticulate')
 expect_error(sys.source(file.path(root,'r/global_dynamic_26105_native_20261019.R'),envir=context),'all(fixtures$cutoff_utc',fixed=TRUE)
 expect_false(dir.exists(file.path(work,'native-fit-shards')))
})

test_that('native fails closed on missing future IDs and incomplete metadata identity', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 withr::local_dir(root)
 work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
 input <- file.path(work,'inputs.json');metadata <- file.path(work,'metadata.json');inventory <- file.path(work,'inventory.json');receipt <- file.path(work,'intake-receipt.json');future <- file.path(work,'future.json')
 writeLines('{}',inventory)
 fixtures <- lapply(seq_len(365L),function(i) list(fixture_id=paste0('26105:',i),provider_id=as.character(i),home_id='10',away_id='20',kickoff_at='2026-10-16T09:00:00Z',cutoff_utc='2026-10-15T09:00:00Z',handicap=0L))
 jsonlite::write_json(list(issue_id='26105',fixtures=fixtures,source_versions=list(),input_bindings=list()),input,auto_unbox=TRUE)
 packets <- lapply(seq_len(365L),function(i) list(fixture_id=paste0('26105:',i),receipt=list(sha256=paste(rep('a',64),collapse=''),url='https://example.test/analysis'),result=list(identity=list(provider_id=as.character(i),home_id='10'))))
 jsonlite::write_json(list(issue_id='26105',inventory_sha256=digest::digest(file=inventory,algo='sha256'),network_attempts=0L,packets=packets),metadata,auto_unbox=TRUE)
 jsonlite::write_json(list(input_sha256=digest::digest(file=input,algo='sha256'),source_versions=list(),input_bindings=list()),receipt,auto_unbox=TRUE)
 jsonlite::write_json(list(coverage_state='VERIFIED_ROSTER',target_issue='26105',following_issue='26106',has_verified_future_roster=TRUE,result=list(data=list(list(issue_id='26106')))),future,auto_unbox=TRUE)
 context <- new.env(parent=globalenv());context$commandArgs <- function(...) c(root,root,'fit','1','3');context$python_backend <- function(...) NULL
 testthat::local_mocked_bindings(import=function(module,...) {
  if(module=='beidan_backend.catalog.paths')return(list(location=function(token,...) {
   if(grepl('history-metadata',token,fixed=TRUE))metadata else if(grepl('channel-inventory',token,fixed=TRUE))inventory else if(grepl('26106-probe',token,fixed=TRUE))future else work
  }))
  list()
 },py_str=function(x) x,.package='reticulate')
 path <- file.path(root,'r/global_dynamic_26105_native_20261019.R')
 expect_error(sys.source(path,envir=context),'Future roster requires issue_id and native_id',fixed=TRUE)
 jsonlite::write_json(list(coverage_state='VERIFIED_ROSTER',target_issue='26105',following_issue='26106',has_verified_future_roster=TRUE,result=list(data=list(list(issue_id='26106',native_id='')))),future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),'future$native_id',fixed=TRUE)
 jsonlite::write_json(list(coverage_state='VERIFIED_ROSTER',target_issue='26105',following_issue='26106',has_verified_future_roster=TRUE,result=list(data=list(list(issue_id='26106',native_id='900001')))),future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),'away_id',fixed=TRUE)

 failure <- file.path(work,'failure.json');failure_log <- file.path(work,'failure.log')
 jsonlite::write_json(list(exit_status=1L),failure,auto_unbox=TRUE);writeLines('beidan_backend.transport.FetchError: fetching https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&all=1&issueNum=26106 failed after 1 attempt(s): HTTP Error 500: Internal Server Error',failure_log)
 observation <- list(receipt_path=as.character(fs::path_rel(failure,start=root)),receipt_sha256=digest::digest(file=failure,algo='sha256'),log_path=as.character(fs::path_rel(failure_log,start=root)),log_sha256=digest::digest(file=failure_log,algo='sha256'))
 packet <- list(coverage_state='REQUEST_FAILED',target_issue='26105',following_issue='26106',has_verified_future_roster=FALSE,result=list(data=list()),observations=list(observation))
 jsonlite::write_json(packet,future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),'away_id',fixed=TRUE)
 expect_identical(context$future_scope$state,'REQUEST_FAILED')
 expect_equal(context$future_scope$known_future_fixtures,0L)
 expect_setequal(context$excluded,as.character(seq_len(365L)))
 writeLines('tampered failure observation',failure_log)
 expect_error(sys.source(path,envir=context),'observation$log_sha256',fixed=TRUE)
 missing_data <- packet;missing_data$result <- list()
 jsonlite::write_json(missing_data,future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),"data",fixed=TRUE)
 writeLines('{}',failure);writeLines('HTTP Error 500: unrelated earlier request',failure_log)
 packet$observations[[1]]$receipt_sha256 <- digest::digest(file=failure,algo='sha256')
 packet$observations[[1]]$log_sha256 <- digest::digest(file=failure_log,algo='sha256')
 jsonlite::write_json(packet,future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),'failure$exit_status',fixed=TRUE)
 jsonlite::write_json(list(exit_status=1L),failure,auto_unbox=TRUE)
 packet$observations[[1]]$receipt_sha256 <- digest::digest(file=failure,algo='sha256')
 jsonlite::write_json(packet,future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),'Expected terminal26106 HTTP500 failure',fixed=TRUE)
 writeLines(c('HTTP Error 500','ValueError: different terminal failure'),failure_log)
 packet$observations[[1]]$log_sha256 <- digest::digest(file=failure_log,algo='sha256')
 jsonlite::write_json(packet,future,auto_unbox=TRUE)
 expect_error(sys.source(path,envir=context),'Expected terminal26106 HTTP500 failure',fixed=TRUE)

 expect_false(dir.exists(file.path(work,'native-fit-shards')))
})


test_that('unresolved real kickoff rows cannot enter native cutoff construction', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 missing <- readr::read_csv(file.path(root,'tests/fixtures/global-dynamic-26105-unresolved-kickoffs.csv'),col_types=readr::cols(.default=readr::col_character(),cutoff_utc=readr::col_datetime()))
 expect_equal(nrow(missing),8L);expect_true(all(is.na(missing$cutoff_utc)))
 guard <- NULL
 for(top in parse(file.path(root,'r/global_dynamic_26105_native_20261019.R'))) {
  if(!is.call(top) || !identical(top[[1]],as.name('if')) || !grepl('target_ids',paste(deparse(top),collapse=' '),fixed=TRUE))next
  for(statement in as.list(top[[3]])[-1L]) {
   if(!is.call(statement) || !identical(statement[[1]],as.name('for')))next
   for(candidate in as.list(statement[[4]])[-1L]) {
    if(is.call(candidate) && identical(candidate[[1]],as.name('if')) && grepl('explicit cutoff unavailable',paste(deparse(candidate),collapse=' '),fixed=TRUE))guard <- candidate
   }
  }
 }
 expect_false(is.null(guard))
 for(i in seq_len(nrow(missing))) {
  context <- new.env(parent=globalenv());context$f <- missing[i,];context$id <- missing$fixture_id[i]
  context$row <- tibble::tibble(fixture_id=context$id,state='UNESTIMATED',reason='initial')
  context$status <- list();context$fit_called <- FALSE
  loop <- substitute(for(dummy in 1L) {GUARD;fit_called <- TRUE},list(GUARD=guard))
  eval(loop,envir=context)
  expect_false(context$fit_called)
  expect_identical(context$status[[context$id]]$state,'UNESTIMATED')
  expect_identical(context$status[[context$id]]$reason,'Unresolved source kickoff; explicit cutoff unavailable')
 }
})


test_that('native sparse errors remain observable when metadata shadows identity', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 candidate_expression <- NULL
 for(top in parse(file.path(root,'r/global_dynamic_26105_native_20261019.R'))) {
  if(!is.call(top) || !identical(top[[1]],as.name('if')) || !grepl('target_ids',paste(deparse(top),collapse=' '),fixed=TRUE))next
  for(statement in as.list(top[[3]])[-1L]) {
   if(!is.call(statement) || !identical(statement[[1]],as.name('for')))next
   for(candidate in as.list(statement[[4]])[-1L]) {
    if(is.call(candidate) && identical(candidate[[1]],as.name('<-')) && identical(candidate[[2]],as.name('candidate')))candidate_expression <- candidate
   }
  }
 }
 expect_false(is.null(candidate_expression))
 context <- new.env(parent=globalenv());context$identity <- list(provider_id='123')
 context$backend <- list(prepare_reviewed_opponent_goals=function(...)stop('Sparse target competition/venue support',call.=FALSE))
 context$domain <- context$fixture <- context$epoch <- context$bindings <- context$policy <- list()
 context$excluded <- character();context$implementation_root <- root
 eval(candidate_expression,envir=context)
 expect_s3_class(context$candidate,'error')
 expect_identical(conditionMessage(context$candidate),'Sparse target competition/venue support')
})


test_that('malformed paired timestamp strings never become unresolved clocks', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 context <- new.env(parent=globalenv());context$as_tibble <- tibble::as_tibble;context$mutate <- dplyr::mutate
 context$input_bytes <- charToRaw(jsonlite::toJSON(list(fixtures=list(list(fixture_id='26105:167',kickoff_at='2026-02-30T10:00:00Z',cutoff_utc='2026-02-29T10:00:00Z',handicap=0L))),auto_unbox=TRUE))
 guard <- NULL
 for(expression in parse(file.path(root,'r/global_dynamic_26105_native_20261019.R'))) {
  if(is.call(expression) && identical(expression[[1]],as.name('<-')) && (identical(expression[[2]],as.name('raw_fixtures'))||identical(expression[[2]],as.name('fixtures'))))eval(expression,envir=context)
  if(is.call(expression) && identical(expression[[1]],as.name('if')) && grepl('Invalid source kickoff or cutoff timestamp',paste(deparse(expression),collapse=' '),fixed=TRUE))guard <- expression
 }
 expect_false(is.null(guard))
 expect_error(eval(guard,envir=context),'Invalid source kickoff or cutoff timestamp',fixed=TRUE)
})
