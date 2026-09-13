# Explicit label-free score projection. Existing output cannot be overwritten.
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=6L) stop('Expected input input_sha config config_sha output repository_root')
if (file.exists(args[5])) stop('Output already exists')
for (pair in list(args[c(1,2)],args[c(3,4)]))
  if (!identical(digest::digest(file=pair[1],algo='sha256'),pair[2])) stop('Input hash mismatch')
root <- normalizePath(args[6],mustWork=TRUE)
modules <- c('probability_exploration.R','strength_market_scenario.R',
  'fundamentals_score_diagnostic.R','fundamentals_score_shape.R',
  'fundamentals_market_comparison.R','fundamentals_total_market.R','n7_market_projection.R')
for (name in modules) source(file.path(root,'r',name))
input <- jsonlite::read_json(args[1],simplifyVector=FALSE)
config <- jsonlite::read_json(args[3],simplifyVector=FALSE)
if (!identical(input$historical_admission,FALSE) || !identical(config$historical_admission,FALSE))
  stop('Diagnostic input contract required')
for (name in names(input$implementation_hashes))
  if (!identical(digest::digest(file=file.path(root,name),algo='sha256'),input$implementation_hashes[[name]]))
    stop('Prepared input implementation changed')
# Reuse the authoritative adapter's typed prototypes after JSON empty arrays.
empty <- n7_published_projection_inputs(list(),tibble::tibble(
  issue=character(),slot=integer(),provider_id=character(),home_handicap=integer()),list())
result <- project_n7_market_inputs(dplyr::bind_rows(empty$fixtures,input$fixtures),
  dplyr::bind_rows(empty$total_quotes,input$total_quotes),
  input$cutoffs,unlist(config$projection$total_bounds),config$projection$tail_tolerance)
result$issue_order <- input$issue_order
result$exclusions <- input$exclusions
result$publication_coverage <- input$publication_coverage
result$source_hashes <- c(input$source_hashes,stats::setNames(as.list(args[c(2,4)]),args[c(1,3)]))
code <- c(file.path('r',modules),'scripts/run_n7_market_projection.R')
result$implementation_hashes <- stats::setNames(lapply(file.path(root,code),
  function(p) digest::digest(file=p,algo='sha256')),code)
jsonlite::write_json(result,args[5],auto_unbox=TRUE,digits=17,na='null',null='null')
cat('Projected',nrow(result$fixtures),'fixtures with existing market algorithm\n')
