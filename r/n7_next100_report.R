# Validate fixed diagnostic inputs and retain unavailable periods. Inputs are
# decoded prediction/config lists with explicit original issue order. Probabilities
# are fractions; no fitting, file I/O or mutation. Returns typed probabilities and
# one coverage row per requested issue. Invalid scope, keys or masses stop.
n7_next100_inputs <- function(pred, cfg) {
  stopifnot(identical(pred$historical_admission,FALSE),
    identical(cfg$historical_admission,FALSE),
    length(pred$issue_order)==cfg$scope$issue_count,!anyDuplicated(pred$issue_order),
    pred$issue_order[1]==cfg$scope$first,tail(pred$issue_order,1)==cfg$scope$last)
  probabilities <- if(length(pred$rows)) tibble::as_tibble(pred$rows) else
    tibble::tibble(issue=character(),slot=integer(),provider_id=character(),handicap=double(),
      q_W=double(),q_D=double(),q_L=double(),new_W=double(),new_D=double(),
      new_L=double(),version=character())
  required <- c('issue','slot','provider_id','handicap','q_W','q_D','q_L',
                'new_W','new_D','new_L','version')
  stopifnot(all(required %in% names(probabilities)),
    !anyNA(probabilities[required]),
    !anyDuplicated(probabilities[c('issue','slot','provider_id')]),
    all(probabilities$issue %in% pred$issue_order),
    all(probabilities$version==cfg$model$version))
  for (cols in list(c('q_W','q_D','q_L'),c('new_W','new_D','new_L'))) {
    stopifnot(all(vapply(probabilities[cols],is.numeric,logical(1))))
    p <- as.matrix(probabilities[cols])
    stopifnot(all(is.finite(p)),all(p>=0 & p<=1),
              all(abs(rowSums(p)-1)<1e-10))
  }
  coverage <- tibble::as_tibble(pred$publication_coverage)
  stopifnot(!anyDuplicated(coverage$issue),setequal(coverage$issue,pred$issue_order))
  periods <- tibble::tibble(issue=pred$issue_order,order=seq_along(pred$issue_order)) |>
    dplyr::left_join(coverage,by='issue',relationship='one-to-one') |>
    dplyr::left_join(dplyr::count(probabilities,issue,name='projected_fixtures'),
                     by='issue',relationship='one-to-one') |>
    dplyr::mutate(projected_fixtures=tidyr::replace_na(projected_fixtures,0L),
                  excluded_fixtures=fixture_market_rows/2-projected_fixtures)
  stopifnot(!anyNA(periods$status),!anyNA(periods$fixture_market_rows),
    all(periods$fixture_market_rows%%2==0),all(periods$excluded_fixtures>=0))
  list(probabilities=probabilities,periods=periods)
}
