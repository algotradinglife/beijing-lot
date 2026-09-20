# Convert accepted market inputs to raw market score and handicap probabilities.
# fixtures: issue/provider_id character, slot integer, handicap integer,
# cutoff_utc character, odds_W/D/L mean decimal odds. total_quotes: matching
# issue/slot/provider_id plus company, line (goals), over_hk/under_hk.
# cutoffs: named issue -> named slot -> explicit cutoff string.
# Inputs contain only already selected, accepted pre-cutoff quotes; this function
# does not select, clean, fetch, fit history, or read settlement. Caller binds
# release hashes/availability evidence. Returns fixture tibble, named score grids,
# parameters and cutoffs. Missing/duplicate inputs fail; empty input is typed.
# rho is the frozen Dixon-Coles dependence parameter supplied by the caller; it is
# recorded in parameters so the receipt binds the caliber actually used.
project_n7_market_inputs <- function(fixtures, total_quotes, cutoffs,
                                     total_bounds, tail_tolerance, rho) {
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
  dc_validate_rho(rho)
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
                                               f$handicap,tail_tolerance,rho)
    for (direction in c('W','D','L')) result[[paste0('q_',direction)]][i] <- projection$fields[[direction]]
    for (column in c('lambda_home','lambda_away','market_residual')) result[[column]][i] <- projection$fields[[column]]
    grids[[paste(f$issue,f$slot,sep='/')]] <- projection$grid
  }
  list(fixtures=result,grids=grids,cutoffs=cutoffs,historical_admission=FALSE,
       parameters=list(total_bounds=total_bounds,tail_tolerance=tail_tolerance,
                       low_score_dependence_rho=rho,
                       method='EXISTING_OU_FIXED_MEAN_LEAST_SQUARES_1X2_DIXON_COLES'))
}

# Adapt verified published market rows and lottery handicaps, without cleaning.
# market_rows is a list of per-market records from read_n7_published_markets;
# handicaps is a tibble with issue/slot/provider_id/home_handicap. cutoffs is
# the explicit issue -> slot map from that release. Keep every non-ready fixture
# in exclusions with both source statuses. Returns typed projection inputs,
# narrowed ready cutoffs and the full input cutoffs. No writes or label access.
n7_published_projection_inputs <- function(market_rows, handicaps, cutoffs) {
  fixture_template <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),
    handicap=integer(),cutoff_utc=character(),odds_W=double(),odds_D=double(),odds_L=double())
  quote_template <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),
    company=character(),line=double(),over_hk=double(),under_hk=double())
  exclusion_template <- tibble::tibble(issue=character(),slot=integer(),provider_id=character(),
    euro_status=character(),total_status=character())
  if (!is.list(market_rows) || !is.data.frame(handicaps) ||
      !all(c('issue','slot','provider_id','home_handicap') %in% names(handicaps)) ||
      !is.character(handicaps$issue) || !is.character(handicaps$provider_id) ||
      anyNA(handicaps[c('issue','slot','provider_id','home_handicap')]) ||
      anyDuplicated(handicaps[c('issue','slot')])) stop('Invalid published handicap identities')
  group_keys <- vapply(market_rows,function(r) paste(r$issue,r$slot,sep='/'),character(1))
  if (!setequal(unique(group_keys),paste(handicaps$issue,handicaps$slot,sep='/')))
    stop('Published market/handicap scope mismatch')
  fixtures <- quotes <- exclusions <- list()
  ready_cutoffs <- list()
  for (group in split(market_rows,group_keys)) {
    if (length(group)!=2L || !setequal(vapply(group,`[[`,character(1),'market'),c('euro','total')))
      stop('Exactly two published markets required')
    e <- group[[which(vapply(group,`[[`,character(1),'market')=='euro')]]
    t <- group[[which(vapply(group,`[[`,character(1),'market')=='total')]]
    h <- handicaps[handicaps$issue==e$issue & handicaps$slot==e$slot,]
    cut <- cutoffs[[e$issue]][[as.character(e$slot)]]
    if (nrow(h)!=1L || !identical(e$provider_id,t$provider_id) ||
        !identical(h$provider_id,e$provider_id) || is.null(cut) ||
        !identical(e$cutoff_utc,cut) || !identical(t$cutoff_utc,cut)) stop('Published identity/cutoff mismatch')
    if (e$status!='QUOTES_PRIOR_DIAGNOSTIC' || t$status!='QUOTES_PRIOR_DIAGNOSTIC') {
      exclusions[[length(exclusions)+1L]] <- tibble::tibble(issue=e$issue,slot=as.integer(e$slot),
        provider_id=e$provider_id,euro_status=e$status,total_status=t$status)
      next
    }
    eq <- dplyr::bind_rows(e$rows); tq <- dplyr::bind_rows(t$rows)
    if (!nrow(eq) || !nrow(tq) || nrow(eq)!=e$prior_companies || nrow(tq)!=t$prior_companies ||
        anyDuplicated(eq$company) || anyDuplicated(tq$company)) stop('Published company contract mismatch')
    fixtures[[length(fixtures)+1L]] <- tibble::tibble(issue=e$issue,slot=as.integer(e$slot),
      provider_id=e$provider_id,handicap=h$home_handicap,cutoff_utc=cut,
      odds_W=mean(eq$odds_W),odds_D=mean(eq$odds_D),odds_L=mean(eq$odds_L))
    quotes[[length(quotes)+1L]] <- dplyr::mutate(tq,issue=e$issue,slot=as.integer(e$slot),provider_id=e$provider_id) |>
      dplyr::select(dplyr::all_of(names(quote_template)))
    ready_cutoffs[[e$issue]][[as.character(e$slot)]] <- cut
  }
  list(fixtures=dplyr::bind_rows(fixture_template,fixtures),
       total_quotes=dplyr::bind_rows(quote_template,quotes),
       exclusions=dplyr::bind_rows(exclusion_template,exclusions),
       cutoffs=ready_cutoffs,input_cutoffs=cutoffs,historical_admission=FALSE)
}
