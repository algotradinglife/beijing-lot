test_that('fundamental publication CLI rejects missing arguments before any collection', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  log <- tempfile();on.exit(unlink(log),add=TRUE)
  status <- system2(file.path(R.home('bin'),'Rscript'),
    shQuote(file.path(root,'r/global_dynamic_26105_base_publish_20261019.R')),
    stdout=log,stderr=log,env='R_PROFILE_USER=/dev/null')
  expect_equal(status,1L)
  expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Exactly ROOT OUTPUT ROSTER_JSON required',fixed=TRUE)
})

test_that('fundamental publication CLI refuses a partial roster before creating output', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
  roster <- file.path(work,'roster.json');jsonlite::write_json(list(data=list()),roster)
  out <- file.path(work,'not-created');log <- file.path(work,'error.log')
  status <- system2(file.path(R.home('bin'),'Rscript'),
    c(shQuote(file.path(root,'r/global_dynamic_26105_base_publish_20261019.R')),shQuote(root),shQuote(out),shQuote(roster)),
    stdout=log,stderr=log,env='R_PROFILE_USER=/dev/null')
  expect_equal(status,1L)
  expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Exact365-fixture26105 roster required',fixed=TRUE)
  expect_false(dir.exists(out))
})

test_that('fundamental publication refuses a missing source hash', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
  roster <- file.path(work,'roster.json')
  jsonlite::write_json(list(data=lapply(seq_len(365L),function(i) list(issue_id='26105',slot=i)),receipt=list()),roster,auto_unbox=TRUE)
  out <- file.path(work,'not-created');log <- file.path(work,'error.log')
  status <- system2(file.path(R.home('bin'),'Rscript'),
    c(shQuote(file.path(root,'r/global_dynamic_26105_base_publish_20261019.R')),shQuote(root),shQuote(out),shQuote(roster)),
    stdout=log,stderr=log,env='R_PROFILE_USER=/dev/null')
  expect_equal(status,1L)
  expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'sha256',fixed=TRUE)
  expect_false(dir.exists(out))
})

test_that('roster replacement during collection stops before validation or publication', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  withr::local_dir(root)
  work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
  roster <- file.path(work,'roster.json')
  jsonlite::write_json(list(data=lapply(seq_len(365L),function(i) list(issue_id='26105',slot=i)),receipt=list(sha256=paste(rep('a',64),collapse=''))),roster,auto_unbox=TRUE)
  context <- new.env(parent=globalenv())
  context$commandArgs <- function(...) c(root,file.path(work,'out'),roster)
  context$python_backend <- function(...) NULL
  testthat::local_mocked_bindings(import=function(module,...) {
    switch(module,
      'beidan_backend.unified_sources'=list(SourceClient=function() list()),
      'beidan_backend.source_issue_update'=list(collect_issue=function(client,issue,max_age,cache_only) {
        expect_identical(issue,'26105');expect_true(cache_only)
        writeLines('{}',roster);list()
      }),
      stop('Unexpected module'))
  },.package='reticulate')
  expect_error(sys.source(file.path(root,'r/global_dynamic_26105_base_publish_20261019.R'),envir=context),'Roster input changed during collection',fixed=TRUE)
  expect_false(file.exists(file.path(work,'out','publication.json')))
})
