#' Prepare template display tables from a frozen evaluation
#' @param evaluation Current selected or allocated evaluation with cutoff.
#' @param fixtures Frozen schedule tibble with unique fixture_key, slot, home_name,
#'   away_name, handicap, kickoff_at and pre-cutoff observed_at/source_url.
#' @param observation NULL or canonical match_results/settlements/as_of list.
#' @return List(groups,tickets,legs,options,depth,returns,receipt), with tibbles.
#'   depth includes theoretical support size and winner_depth: actual combination
#'   rank (including unbought combinations), zero for a mask miss, NA if unknown.
#'   Options are display unions only; exact tickets are the purchase authority.
#'   Times are formatted in Beijing time; unpublished actual SP remains NA.
#' @details Source chronology and fixture identities fail closed. No reranking,
#'   mask expansion, learning, network, writes, clock inference or mutation.
#' @export
BuildEvaluationBettingSheetView <- function(evaluation,fixtures,observation=NULL) {
  pool <- .parlay_ranked_validate_evaluation(evaluation)
  checkmate::assert_tibble(fixtures)
  if(!all(c("fixture_key","slot","home_name","away_name","handicap","kickoff_at","observed_at","source_url") %in% names(fixtures))) stop("catalog lacks required columns")
  checkmate::assert_character(fixtures$fixture_key,any.missing=FALSE,unique=TRUE,min.chars=1)
  checkmate::assert_integer(fixtures$slot,any.missing=FALSE,lower=1)
  checkmate::assert_integerish(fixtures$handicap,any.missing=FALSE)
  for(field in c("home_name","away_name","source_url"))checkmate::assert_character(fixtures[[field]],any.missing=FALSE,min.chars=1)
  for(field in c("kickoff_at","observed_at")) {
    checkmate::assert_posixct(fixtures[[field]],any.missing=FALSE)
    zone <- attr(fixtures[[field]],"tzone")
    if(any(!is.finite(as.numeric(fixtures[[field]]))) || length(zone)!=1L || !zone %in% c("UTC","Asia/Shanghai")) stop("catalog timestamps require finite explicit timezone")
  }
  if(any(fixtures$observed_at>=pool$cutoff$cutoff_utc)) stop("fixture catalog must be frozen before cutoff")
  if(any(!evaluation$plan$ticket_legs$fixture_id %in% fixtures$fixture_key)) stop("catalog missing purchased fixture")
  groups <- evaluation$group_selection |> dplyr::filter(.data$tickets>0L) |>
    dplyr::arrange(.data$group_id) |>
    dplyr::mutate(order=as.integer(dplyr::row_number()),actual_pattern=.data$actual_pattern,
      theoretical=as.double(.data$legal_space),new_ticket_count=.data$tickets,
      new_cost_cny=.data$spent_cny,cumulative_cost_cny=cumsum(.data$spent_cny))
  groups$cumulative_coverage <- vapply(seq_len(nrow(groups)),function(i) {
    owned <- evaluation$purchases |> dplyr::filter(.data$group_id %in% groups$group_id[seq_len(i)])
    return(.parlay_ranked_union_coverage(owned$ticket_id,evaluation$plan$ticket_legs,pool$probabilities))
  },numeric(1))
  tickets <- evaluation$purchases |>
    dplyr::left_join(dplyr::select(groups,group_id,order),by="group_id",relationship="many-to-one") |>
    dplyr::arrange(.data$order,.data$rank)
  catalog <- fixtures |> dplyr::transmute(fixture_id=fixture_key,slot,home_name,away_name,handicap,
    kickoff_beijing=format(kickoff_at,"%Y-%m-%d %H:%M:%S",tz="Asia/Shanghai"))
  legs <- evaluation$plan$ticket_legs |>
    dplyr::left_join(dplyr::select(evaluation$purchases,ticket_id,group_id),
      by="ticket_id",relationship="many-to-one") |>
    dplyr::left_join(dplyr::select(groups,group_id,order),by="group_id",relationship="many-to-one") |>
    dplyr::left_join(catalog,by="fixture_id",relationship="many-to-one")
  chosen <- legs |> dplyr::distinct(order,fixture_id,outcome) |> dplyr::mutate(selected=TRUE)
  options <- tidyr::crossing(legs |> dplyr::select(order,fixture_id,slot,home_name,away_name,handicap,kickoff_beijing) |>
    dplyr::distinct(),outcome=match_outcomes()) |>
    dplyr::left_join(pool$prematch_sp |> dplyr::select(fixture_id,outcome,sp_raw),
      by=c("fixture_id","outcome"),relationship="many-to-one") |>
    dplyr::left_join(chosen,by=c("order","fixture_id","outcome"),relationship="one-to-one") |>
    dplyr::mutate(selected=tidyr::replace_na(.data$selected,FALSE))
  results <- tibble::tibble(fixture_id=character(),actual_outcome=character(),settled_sp=double())
  returns <- NULL
  if(!is.null(observation)) {
    labels <- .BacktestLabels(observation,evaluation$cutoff)
    results <- labels$results |> dplyr::transmute(fixture_id,actual_outcome=outcome) |>
      dplyr::left_join(labels$actual |> dplyr::filter(.data$status=="settled") |>
        dplyr::select(fixture_id,settled_sp),by="fixture_id",relationship="one-to-one")
    returns <- parlay_settle_plan(evaluation$plan,labels$actual,labels$as_of)$ticket_returns
  }
  options <- options |> dplyr::left_join(results,by="fixture_id",relationship="many-to-one") |>
    dplyr::mutate(result=tidyr::replace_na(.data$outcome==.data$actual_outcome,FALSE))
  depth <- if(nrow(legs)) BettingSheetDepth(legs,dplyr::select(results,fixture_id,actual_outcome)) else tibble::tibble(
    order=integer(),total=integer(),observed=integer(),best_hits=integer(),viable_tickets=integer(),winning_tickets=integer(),group_status=character())
  canonical_results <- if(is.null(observation)) match_typed_empty("match_results") else labels$results
  combination_depth <- .BettingSheetCombinationDepth(evaluation,canonical_results,
    if(is.null(observation)) NULL else labels$as_of)
  depth <- depth |>
    dplyr::left_join(dplyr::select(groups,order,group_id),by="order",relationship="one-to-one") |>
    dplyr::left_join(combination_depth,by="group_id",relationship="one-to-one")
  out <- list(groups=groups,tickets=tickets,legs=legs,options=options,depth=depth,returns=returns)
  out$receipt <- list(cutoff=evaluation$cutoff,input_hash=rlang::hash(list(evaluation,fixtures,observation)),
    output_hash=rlang::hash(out),code_hash=.rank_outcome_code_hash("BuildEvaluationBettingSheetView"))
  return(out)
}

#' Render an exact betting sheet with the package's bundled Quarto template
#' @param view Display data from BuildEvaluationBettingSheetView or
#'   BuildBettingSheetView. Requires nonempty reconciled groups/tickets/legs/options.
#' @param output_file Explicit new HTML path; existing files are refused.
#' @param quarto Explicit path to an installed Quarto executable. No installation.
#' @param title Plain character sheet title; safely escaped by the template.
#' @return List(path,sha256,receipt), including input, template and implementation
#'   hashes. Generated HTML contains per-group selections, exact tickets, lossless
#'   duplex CSV downloads and single-ticket depth. Costs are CNY.
#' @details Renders in an isolated temporary directory; cleans on failure/success,
#'   never publishes, sends, places bets, or overwrites existing outputs. Uses
#'   installed R, dplyr, tidyr, htmltools, knitr and readr. No hidden workspace or
#'   repository sourcing. Quarto failures or embedded execution errors fail closed.
#' @export
RenderBettingSheet <- function(view,output_file,quarto,title="模拟下注单") {
  checkmate::assert_list(view)
  checkmate::assert_string(output_file,min.chars=1L)
  checkmate::assert_string(quarto,min.chars=1L)
  checkmate::assert_string(title,min.chars=1L)
  if(file.exists(output_file)) stop("refuse existing output_file")
  if(!file.exists(quarto) || file.access(quarto,1)!=0L) stop("quarto executable unavailable")
  for(n in c("groups","tickets","legs","options","depth")) checkmate::assert_tibble(view[[n]])
  if(!nrow(view$tickets) || !nrow(view$groups)) stop("betting sheet requires purchased tickets")
  if(!is.null(view$receipt$output_hash)) {
    bare <- view;bare$receipt <- NULL
    if(!identical(rlang::hash(bare),view$receipt$output_hash)) stop("view receipt mismatch")
  }
  counts <- view$tickets |> dplyr::group_by(.data$order) |>
    dplyr::summarise(n=dplyr::n(),cost=sum(.data$cost_cny),.groups="drop")
  check <- view$groups |> dplyr::left_join(counts,by="order",relationship="one-to-one")
  if(anyNA(check$n) || !identical(as.integer(check$n),as.integer(check$new_ticket_count)) ||
      !isTRUE(all.equal(check$cost,check$new_cost_cny)) || anyDuplicated(view$options[c("order","fixture_id","outcome")])) stop("sheet ledger mismatch")
  if(!identical(view$groups$order,seq_len(nrow(view$groups))) ||
      !setequal(view$tickets$order,view$groups$order) ||
      !isTRUE(all.equal(cumsum(check$cost),view$groups$cumulative_cost_cny))) stop("sheet group order mismatch")
  chosen <- view$legs |> dplyr::distinct(order,fixture_id,outcome)
  selected <- view$options |> dplyr::filter(.data$selected) |>
    dplyr::select(order,fixture_id,outcome)
  if(!identical(dplyr::arrange(chosen,.data$order,.data$fixture_id,.data$outcome),
      dplyr::arrange(selected,.data$order,.data$fixture_id,.data$outcome))) stop("sheet displayed selections mismatch")
  duplex <- CompressParlayTickets(view$tickets,view$legs)
  template <- system.file("quarto","betting_sheet.qmd",package="beidan",mustWork=TRUE)
  directory <- tempfile("beidan-sheet-");dir.create(directory)
  on.exit(unlink(directory,recursive=TRUE),add=TRUE)
  local <- file.path(directory,"sheet.qmd");file.copy(template,local)
  bundle <- file.path(directory,"bundle.rds");saveRDS(list(view=view,duplex=duplex,title=title),bundle)
  param <- file.path(directory,"params.yml")
  writeLines(paste0('bundle_path: "',gsub('\\\\','/',bundle),'"'),param)
  log <- file.path(directory,"render.log")
  status <- system2(quarto,c("render",shQuote(local),"--execute","--no-cache","--execute-params",shQuote(param)),stdout=log,stderr=log)
  html <- file.path(directory,"sheet.html")
  if(status!=0L || !file.exists(html)) stop("Quarto render failed: ",paste(readLines(log,warn=FALSE),collapse="\n"))
  bytes <- readLines(html,warn=FALSE)
  if(any(grepl('class="cell-output-error',bytes,fixed=TRUE))) stop("Quarto output contains execution error")
  if(!dir.exists(dirname(output_file))) stop("output parent directory must exist")
  if(!file.copy(html,output_file,overwrite=FALSE)) stop("failed to deliver betting sheet")
  return(list(path=normalizePath(output_file),sha256=digest::digest(file=output_file,algo="sha256"),
    receipt=list(input_hash=rlang::hash(view),title=title,
      template_sha256=digest::digest(file=template,algo="sha256"),
      code_hash=.rank_outcome_code_hash("RenderBettingSheet"),
      dependency_versions=as.list(vapply(c("htmltools","knitr","readr"),
        function(p)as.character(utils::packageVersion(p)),character(1))))))
}
