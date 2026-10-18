#' Rank handicap tickets by their strongest retained margin scenario
#' @param decision List with explicit cutoff, margins tibble (fixture_id, margin,
#'   handicap, probability), legs tibble (group_slot, fixture_id), and receipt.
#'   Receipt binds cutoff, input_hash, source_hashes and max_source_available_utc.
#' @param depth Positive integer number of margin bins per fixture, or Inf.
#' @return Tickets and retained bins, with input/code/cutoff receipt. Score is
#'   unnormalized scenario mass, never ticket probability. No labels, learning,
#'   network or storage IO. Ties use margin ascending then ticket ID ascending.
#' @noRd
RankFirstMarginTickets <- function(decision, depth) {
  match_require_cutoff(decision$cutoff)
  receipt <- decision$receipt
  if (!identical(receipt$cutoff,decision$cutoff) ||
      !identical(receipt$input_hash,rlang::hash(list(margins=decision$margins,legs=decision$legs))) ||
      !length(receipt$source_hashes) ||
      !all(grepl('^[a-f0-9]{64}$',unlist(receipt$source_hashes))) ||
      !inherits(receipt$max_source_available_utc,'POSIXct') ||
      length(receipt$max_source_available_utc)!=1L || is.na(receipt$max_source_available_utc) ||
      receipt$max_source_available_utc>=decision$cutoff$cutoff_utc) stop('invalid cutoff/input receipt')
  if (!is.numeric(depth) || length(depth)!=1L || is.na(depth) || depth<1 ||
      (is.finite(depth) && depth!=as.integer(depth))) stop('invalid support depth')
  m <- decision$margins;legs <- decision$legs
  if (!tibble::is_tibble(m) || !all(c('fixture_id','margin','handicap','probability') %in% names(m)) ||
      !tibble::is_tibble(legs) || !all(c('group_slot','fixture_id') %in% names(legs)) ||
      !nrow(m) || !nrow(legs) || anyNA(m) || anyNA(legs) ||
      !is.character(m$fixture_id) || !is.character(legs$fixture_id) ||
      any(!nzchar(m$fixture_id)) || any(!nzchar(legs$fixture_id)) ||
      anyDuplicated(m[c('fixture_id','margin')]) || anyDuplicated(legs) ||
      !all(is.finite(m$margin) & m$margin==trunc(m$margin)) ||
      !all(is.finite(m$handicap) & m$handicap==trunc(m$handicap)) ||
      !all(is.finite(m$probability) & m$probability>=0) ||
      !setequal(m$fixture_id,legs$fixture_id)) stop('invalid margin/legs contract')
  totals <- m |> dplyr::group_by(fixture_id) |>
    dplyr::summarise(total=sum(probability),lines=dplyr::n_distinct(handicap),.groups='drop')
  if (any(abs(totals$total-1)>1e-9) || any(totals$lines!=1L) ||
      any(dplyr::count(legs,group_slot)$n!=7L)) stop('normalized margins and seven-leg groups required')
  retained <- m |> dplyr::group_by(fixture_id) |>
    dplyr::arrange(dplyr::desc(probability),margin,.by_group=TRUE) |>
    dplyr::mutate(margin_rank=dplyr::row_number()) |>
    dplyr::filter(margin_rank<=depth,probability>0) |> dplyr::ungroup() |>
    dplyr::mutate(outcome=dplyr::case_when(margin+handicap>0~'W',margin+handicap==0~'D',TRUE~'L'))
  categories <- retained |> dplyr::group_by(fixture_id,outcome) |>
    dplyr::summarise(peak=max(probability),retained_mass=sum(probability),.groups='drop')
  blocks <- list()
  for (g in sort(unique(legs$group_slot))) {
    ids <- sort(legs$fixture_id[legs$group_slot==g],method='radix')
    choices <- lapply(ids,function(id) categories$outcome[categories$fixture_id==id])
    names(choices) <- ids
    space <- tidyr::expand_grid(!!!choices)
    log_score <- log_mass <- rep(0,nrow(space));tokens <- vector('list',7L)
    for (j in seq_along(ids)) {
      q <- categories[categories$fixture_id==ids[j],]
      ix <- match(space[[j]],q$outcome)
      log_score <- log_score+log(q$peak[ix]);log_mass <- log_mass+log(q$retained_mass[ix])
      tokens[[j]] <- paste0(ids[j],':',match(space[[j]],c('W','D','L')))
    }
    block <- tibble::tibble(group_slot=g,ticket_id=do.call(paste,c(tokens,sep='|')),
      log_scenario_score=log_score,scenario_score=exp(log_score),retained_ticket_mass=exp(log_mass)) |>
      dplyr::arrange(dplyr::desc(log_scenario_score),ticket_id) |>
      dplyr::mutate(rank=dplyr::row_number())
    blocks[[as.character(g)]] <- block
  }
  list(tickets=dplyr::bind_rows(blocks),retained=retained,categories=categories,
    receipt=list(cutoff=decision$cutoff,input_receipt=receipt,depth=depth,
      implementation_hash=.rank_outcome_code_hash(roots='RankFirstMarginTickets'),
      score_kind='MAXIMUM_SCENARIO_MASS',normalized=FALSE))
}
