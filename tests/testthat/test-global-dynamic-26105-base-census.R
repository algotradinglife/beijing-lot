test_that('26105 census converts null columns and empty resources using declared schemas', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
  backend <- reticulate::import('beidan_backend.source_issue_update',convert=FALSE)
  expressions <- as.list(parse(file=file.path(root,'r/global_dynamic_26105_base_census_20261018.R')))
  conversion <- Filter(function(e) is.call(e) && identical(e[[1]],as.name('<-')) &&
    is.symbol(e[[2]]) && as.character(e[[2]]) %in% c('schemas','status','resources'),expressions)
  expect_length(conversion,3L)
  row <- reticulate::dict(issue='26105',slot=1L,fixture_id='26105:1',state='CACHE_MISS',
    conflicts=0L,gaps=1L,missing_fields=0L,error_type=NULL)
  context <- new.env(parent=globalenv());context$backend <- backend
  context$result <- reticulate::dict(tables=reticulate::dict(status=list(row),resources=list()))
  for(expression in conversion) eval(expression,envir=context)
  expect_s3_class(context$status,'tbl_df');expect_s3_class(context$resources,'tbl_df')
  expect_identical(context$status$error_type,NA_character_)
  expect_identical(context$status$slot,1L)
  expect_identical(context$status$fixture_id,'26105:1')
  expect_identical(names(context$resources),names(context$schemas$resources))
  expect_identical(context$resources$error_type,character())
  expect_identical(context$resources$fixture_id,character())
  expect_identical(nrow(context$resources),0L)
})
