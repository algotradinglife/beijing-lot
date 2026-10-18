test_that('26105 settlement and evaluation refuse another issue or missing arguments', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 for(name in c('global_dynamic_26105_settlement_20261019.R','global_dynamic_26105_evaluate_20261019.R')) {
  context <- new.env(parent=globalenv());context$commandArgs <- function(...) character()
  expect_error(sys.source(file.path(root,'r',name),envir=context),'length(args)',fixed=TRUE)
  context$commandArgs <- function(...) c(root,'26104')
  expect_error(sys.source(file.path(root,'r',name),envir=context),'args[2]',fixed=TRUE)
 }
})
test_that('actual whole issue guard refuses pending statuses and permits terminal observations', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 for(name in c('global_dynamic_26105_settlement_20261019.R','global_dynamic_26105_evaluate_20261019.R')) {
  nodes <- as.list(parse(file=file.path(root,'r',name)))
  guard <- Filter(function(node) is.call(node)&&identical(node[[1]],as.name('if'))&&grepl('Whole26105 terminal status',paste(deparse(node),collapse=' '),fixed=TRUE),nodes)[[1]]
  context <- new.env(parent=baseenv())
  context$observed <- list(events=tibble::tibble(status=c('完场','未开')))
  context$roster <- context$observed$events
  expect_error(eval(guard,context),'Whole26105 terminal status',fixed=TRUE)
  context$observed$events$status <- c('完场','取消');context$roster <- context$observed$events
  expect_silent(eval(guard,context))
 }
})

test_that('actual issue-scope guards reject a substituted slot', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 for(name in c('global_dynamic_26105_settlement_20261019.R','global_dynamic_26105_evaluate_20261019.R')) {
  nodes <- as.list(parse(file=file.path(root,'r',name)))
  guard <- Filter(function(node) is.call(node)&&identical(node[[1]],as.name('stopifnot'))&&grepl('setequal(',paste(deparse(node),collapse=' '),fixed=TRUE),nodes)[[1]]
  context <- new.env(parent=baseenv())
  context$roster <- tibble::tibble(issue_id=rep('26105',365L),slot=seq_len(365L))
  context$observed <- list(events=context$roster,receipt=list(network_attempts=0L))
  expect_silent(eval(guard,context))
  context$roster$slot[365L] <- 366L;context$observed$events <- context$roster
  expect_error(eval(guard,context),'setequal',fixed=TRUE)
 }
})
test_that('actual settlement manifest guard refuses changed or missing hashes', {
 root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
 nodes <- as.list(parse(file=file.path(root,'r/global_dynamic_26105_evaluate_20261019.R')))
 guard <- Filter(function(node) is.call(node)&&identical(node[[1]],as.name('if'))&&grepl('Frozen settlement manifest binding mismatch',paste(deparse(node),collapse=' '),fixed=TRUE),nodes)[[1]]
 context <- new.env(parent=baseenv());context$settlement_sha <- paste(rep('a',64),collapse='');context$sr <- list(sha256=paste(rep('b',64),collapse=''))
 context$settlement_manifest <- list(sha256=context$settlement_sha,source_selection_sha256=context$sr$sha256)
 expect_silent(eval(guard,context))
 context$settlement_manifest$sha256 <- 'changed'
 expect_error(eval(guard,context),'Frozen settlement manifest binding mismatch',fixed=TRUE)
 context$settlement_manifest$sha256 <- NULL
 expect_error(eval(guard,context),'Frozen settlement manifest binding mismatch',fixed=TRUE)
 context$settlement_manifest$sha256 <- context$settlement_sha;context$settlement_manifest$source_selection_sha256 <- 'other selection'
 expect_error(eval(guard,context),'Frozen settlement manifest binding mismatch',fixed=TRUE)
})
