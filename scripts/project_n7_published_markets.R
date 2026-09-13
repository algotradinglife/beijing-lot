# Thin research entry: accepted quote snapshot + bound published lottery handicap
# fields -> market-only projection inputs. No collection, cleaning or settlement.
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=6L) stop('Expected market_snapshot market_sha handicap_snapshot handicap_sha output repository_root')
if (file.exists(args[5])) stop('Output already exists')
for (pair in list(args[c(1,2)],args[c(3,4)]))
  if (!identical(digest::digest(file=pair[1],algo='sha256'),pair[2])) stop('Input hash mismatch')
root <- normalizePath(args[6],mustWork=TRUE)
modules <- c('probability_exploration.R','strength_market_scenario.R',
  'fundamentals_score_diagnostic.R','fundamentals_score_shape.R',
  'fundamentals_market_comparison.R','fundamentals_total_market.R','n7_market_projection.R')
for (name in modules) source(file.path(root,'r',name))
market <- jsonlite::fromJSON(gzfile(args[1]),simplifyVector=FALSE)
handicaps <- jsonlite::read_json(args[3],simplifyVector=FALSE)
if (!identical(handicaps$market_snapshot_sha256,args[2]) ||
    !identical(market$historical_admission,FALSE) || !identical(handicaps$historical_admission,FALSE))
  stop('Snapshot binding mismatch')
cuts <- list()
for (row in market$rows) {
  prior <- cuts[[row$issue]][[as.character(row$slot)]]
  if (!is.null(prior) && !identical(prior,row$cutoff_utc)) stop('Published cutoff conflict')
  cuts[[row$issue]][[as.character(row$slot)]] <- row$cutoff_utc
}
handicap_template <- tibble::tibble(issue=character(),slot=integer(),
  provider_id=character(),home_handicap=integer())
inputs <- n7_published_projection_inputs(market$rows,
  dplyr::bind_rows(handicap_template,handicaps$rows),cuts)
inputs$issue_order <- market$issue_order
inputs$publication_coverage <- market$coverage
inputs$source_hashes <- stats::setNames(as.list(args[c(2,4)]),args[c(1,3)])
code <- c(file.path('r',modules),'scripts/project_n7_published_markets.R')
inputs$implementation_hashes <- stats::setNames(lapply(file.path(root,code),
  function(p) digest::digest(file=p,algo='sha256')),code)
jsonlite::write_json(inputs,args[5],auto_unbox=TRUE,digits=17,na='null',null='null')
cat('Prepared research inputs:',nrow(inputs$fixtures),'fixtures;',nrow(inputs$exclusions),'excluded fixtures\n')
