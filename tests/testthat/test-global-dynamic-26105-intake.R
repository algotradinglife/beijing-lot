test_that('26105 intake refuses missing arguments before SDK use', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 log <- tempfile();on.exit(unlink(log),add=TRUE)
 status <- system2(file.path(R.home('bin'),'Rscript'),shQuote(file.path(root,'r/global_dynamic_26105_intake_20261019.R')),stdout=log,stderr=log,env='R_PROFILE_USER=/dev/null')
 expect_equal(status,1L)
 expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Exactly ROOT BASE_PUBLICATION EURO_PUBLICATION ROSTER OUTPUT_TOKEN required',fixed=TRUE)
})
test_that('26105 intake refuses another issue before SDK use', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 work <- tempfile();dir.create(work);on.exit(unlink(work,recursive=TRUE),add=TRUE)
 base <- file.path(work,'base.json');euro <- file.path(work,'euro.json');roster <- file.path(work,'roster.json')
 jsonlite::write_json(list(publication=list(dataset='source_issue_26104')),base,auto_unbox=TRUE)
 jsonlite::write_json(list(publication=list(dataset='source_euro_issue_26105')),euro,auto_unbox=TRUE)
 jsonlite::write_json(list(data=list()),roster)
 log <- file.path(work,'error.log')
 status <- system2(file.path(R.home('bin'),'Rscript'),c(shQuote(file.path(root,'r/global_dynamic_26105_intake_20261019.R')),shQuote(root),shQuote(base),shQuote(euro),shQuote(roster),'hot:should-not-be-created'),stdout=log,stderr=log,env='R_PROFILE_USER=/dev/null')
 expect_equal(status,1L)
 expect_match(paste(readLines(log,warn=FALSE),collapse='\n'),'Exact26105 published dataset identities required',fixed=TRUE)
})


test_that('26105 roster projection accepts real structured unused kickoff dates', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 roster <- jsonlite::fromJSON(file.path(root,'tests/fixtures/global-dynamic-26105-intake-roster-excerpt.json'),simplifyVector=FALSE)
 expect_type(roster$data[[1]]$kickoff_date,'character')
 expect_type(roster$data[[2]]$kickoff_date,'list')
 projection <- NULL
 for(expression in parse(file.path(root,'r/global_dynamic_26105_intake_20261019.R'))) {
  if(is.call(expression) && identical(expression[[1]],as.name('<-')) && identical(expression[[2]],as.name('r'))) projection <- expression
 }
 expect_false(is.null(projection))
 context <- new.env(parent=globalenv());context$roster <- roster
 context$bind_rows <- dplyr::bind_rows;context$transmute <- dplyr::transmute;context$map <- purrr::map
 eval(projection,envir=context)
 expect_s3_class(context$r,'tbl_df')
 expect_identical(names(context$r),c('fixture_id','slot','league','handicap'))
 expect_equal(nrow(context$r),2L)
 expect_identical(context$r$fixture_id,vapply(roster$data,function(x) paste0(x$issue_id,':',x$slot),character(1)))
 expect_identical(context$r$league,vapply(roster$data,function(x) x$league,character(1)))
 expect_equal(context$r$handicap,vapply(roster$data,function(x) x$handicap,numeric(1)))
})


test_that('actual unresolved kickoff rows retain missing cutoffs in intake status', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 fixtures <- readr::read_csv(file.path(root,'tests/fixtures/global-dynamic-26105-unresolved-kickoffs.csv'),col_types=readr::cols(.default=readr::col_character(),kickoff_at=readr::col_datetime(),cutoff_utc=readr::col_datetime()))
 status_expression <- NULL
 for(expression in parse(file.path(root,'r/global_dynamic_26105_intake_20261019.R'))) {
  if(is.call(expression) && identical(expression[[1]],as.name('<-')) && identical(expression[[2]],as.name('fixtures')) && grepl('temporal_state',paste(deparse(expression),collapse=' '),fixed=TRUE))status_expression <- expression
 }
 expect_false(is.null(status_expression))
 context <- new.env(parent=globalenv());context$fixtures <- fixtures
 context$mutate <- dplyr::mutate;context$if_else <- dplyr::if_else
 eval(status_expression,envir=context)
 expect_identical(context$fixtures$fixture_id,fixtures$fixture_id)
 expect_true(all(is.na(context$fixtures$cutoff_utc)))
 expect_true(all(context$fixtures$temporal_state=='UNRESOLVED_KICKOFF'))
})
