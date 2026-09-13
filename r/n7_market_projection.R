# Convert accepted market inputs to raw market score and handicap probabilities.
# fixtures: issue/provider_id character, slot integer, handicap integer,
# cutoff_utc character, odds_W/D/L mean decimal odds. total_quotes: matching
# issue/slot/provider_id plus company, line (goals), over_hk/under_hk.
# cutoffs: named issue -> named slot -> explicit cutoff string.
# Inputs contain only already selected, accepted pre-cutoff quotes; this function
# does not select, clean, fetch, fit history, or read settlement. Caller binds
# release hashes/availability evidence. Returns fixture tibble, named score grids,
# parameters and cutoffs. Missing/duplicate inputs fail; empty input is typed.
project_n7_market_inputs <- function(fixtures, total_quotes, cutoffs,
                                     total_bounds, tail_tolerance) {
  keys <- c('issue','slot','provider_id')
  fields <- c(keys,'handicap','cutoff_utc','odds_W','odds_D','odds_L')
  quote_fields <- c(keys,'company','line','over_hk','under_hk')
  if (!is.data.frame(fixtures) || !is.data.frame(total_quotes) ||
      !setequal(names(fixtures),fields) || !setequal(names(total_quotes),quote_fields) ||
      !is.character(fixtures$issue) || !is.character(fixtures$provider_id) ||
      !is.character(fixtures$cutoff_utc) || !is.character(total_quotes$issue) ||
      !is.character(total_quotes$provider_id) || anyNA(fixtures) || anyNA(total_quotes) ||
      anyDuplicated(fixtures[c('issue','slot')]) ||
      anyDuplicated(total_quotes[c(keys,'company')])) stop('Invalid market input schema or keys')
  numeric_fields <- c('slot','handicap','odds_W','odds_D','odds_L')
  if (!all(vapply(fixtures[numeric_fields],is.numeric,logical(1))) ||
      any(!is.finite(as.matrix(fixtures[numeric_fields]))) ||
      any(fixtures$slot<1 | fixtures$slot!=floor(fixtures$slot)) ||
      any(fixtures$handicap!=floor(fixtures$handicap)) ||
      any(as.matrix(fixtures[c('odds_W','odds_D','odds_L')])<=0) ||
      length(tail_tolerance)!=1L || !is.finite(tail_tolerance) ||
      tail_tolerance<=0 || tail_tolerance>=1 || length(total_bounds)!=2L ||
      any(!is.finite(total_bounds)) || total_bounds[1]<=0 || total_bounds[2]<=total_bounds[1])
    stop('Invalid market numerical parameters')
  if (!is.list(cutoffs) || !setequal(names(cutoffs),unique(fixtures$issue)) ||
      anyDuplicated(names(cutoffs))) stop('Explicit matching cutoffs required')
  for (issue in names(cutoffs)) {
    rows <- fixtures[fixtures$issue==issue,]
    expected <- stats::setNames(as.list(rows$cutoff_utc),as.character(rows$slot))
    actual <- cutoffs[[issue]]
    if (!is.list(actual) || anyDuplicated(names(actual)) ||
        !setequal(names(actual),names(expected)) || !identical(actual[names(expected)],expected))
      stop('Fixture cutoff mismatch')
  }
  if (nrow(dplyr::anti_join(total_quotes,fixtures,by=keys)) ||
      nrow(dplyr::anti_join(fixtures,total_quotes,by=keys))) stop('Missing or unmatched market quotes')
  result <- tibble::as_tibble(fixtures)
  for (column in c('q_W','q_D','q_L','lambda_home','lambda_away','market_residual'))
    result[[column]] <- rep(NA_real_,nrow(result))
  grids <- list()
  for (i in seq_len(nrow(fixtures))) {
    f <- fixtures[i,]
    quotes <- dplyr::semi_join(total_quotes,f,by=keys)
    constraint <- total_market_constraint(quotes,total_bounds)
    inverse <- 1/as.numeric(f[1,c('odds_W','odds_D','odds_L')])
    projection <- total_constrained_projection(constraint$lambda_total,inverse/sum(inverse),
                                               f$handicap,tail_tolerance)
    for (direction in c('W','D','L')) result[[paste0('q_',direction)]][i] <- projection$fields[[direction]]
    for (column in c('lambda_home','lambda_away','market_residual')) result[[column]][i] <- projection$fields[[column]]
    grids[[paste(f$issue,f$slot,sep='/')]] <- projection$grid
  }
  list(fixtures=result,grids=grids,cutoffs=cutoffs,historical_admission=FALSE,
       parameters=list(total_bounds=total_bounds,tail_tolerance=tail_tolerance,
                       method='EXISTING_OU_FIXED_MEAN_LEAST_SQUARES_1X2'))
}
