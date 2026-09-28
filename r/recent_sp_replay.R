#' Recover contemporaneously observed SP from a frozen schedule response
#' @param source_path Path to the Sep26 frozen plan bundle, including schedule receipts.
#' @param backend Explicit project python_backend handle; no network is used.
#' @return List(quotes tibble, receipt, source result). Receipt binds source/raw/meta
#'   hashes, original observation and cutoff. Every model fixture must have W/D/L.
#' @details Reads original bytes and reuses the authoritative SP parser. Missing
#'   bytes, changed source hash, late observation, missing quotes or invalid frozen
#'   plans error. It never advances quote time, modifies the old plan, or writes.
RecentSpReplay <- function(source_path,backend) {
  checkmate::assert_file_exists(source_path)
  source <- readRDS(source_path)
  beidan:::parlay_check_saved_result(source$result)
  cutoff <- source$result$cutoff
  beidan:::match_require_cutoff(cutoff)
  paths <- attr(source$schedule,"written")
  meta <- jsonlite::read_json(paths$source_meta)
  raw_hash <- digest::digest(file=paths$nowscore_raw,algo="sha256")
  if (!identical(raw_hash,meta$raw_sha256$nowscore)) stop("raw source hash mismatch")
  observed <- lubridate::ymd_hms(meta$observed_at$nowscore,quiet=TRUE)
  if (length(observed)!=1L || is.na(observed) || observed>=cutoff$cutoff_utc)
    stop("observed SP is not before cutoff")
  if (!identical(meta$issue_id,cutoff$issue_id)) stop("source issue mismatch")
  schedule <- dplyr::filter(source$schedule,
    .data$fixture_key %in% source$result$probabilities$fixture_id)
  if (!setequal(schedule$fixture_key,source$result$probabilities$fixture_id))
    stop("model fixtures missing from source schedule")
  if (!inherits(backend,"python_backend")) stop("explicit python backend required")
  module <- reticulate::import_from_path("beidan_backend.prematch_sp",path=backend$root,convert=FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(module$`__file__`)),
      normalizePath(file.path(backend$root,"beidan_backend/prematch_sp.py")))) stop("wrong parser module")
  rows <- lapply(seq_len(nrow(schedule)),function(i) {
    row <- as.list(schedule[i,c("issue_id","slot","fixture_key","provider_id_nowscore","handicap","kickoff_at")])
    row$slot <- as.integer(row$slot)
    row$kickoff_at <- format(lubridate::with_tz(row$kickoff_at,"UTC"),"%Y-%m-%dT%H:%M:%SZ")
    return(row)
  })
  body <- readBin(paths$nowscore_raw,"raw",n=file.info(paths$nowscore_raw)$size)
  parsed <- reticulate::py_to_r(module$parse_prematch_sp(reticulate::r_to_py(body),
    rows,meta$observed_at$nowscore))
  quotes <- dplyr::bind_rows(parsed[[1]])
  if (length(parsed[[2]]) || nrow(quotes)!=3L*nrow(schedule)) stop("incomplete pre-cutoff SP")
  quotes$sp_raw <- as.double(quotes$sp_raw)
  quotes$quote_at <- lubridate::with_tz(lubridate::ymd_hms(quotes$quote_at,quiet=TRUE),"Asia/Shanghai")
  quotes <- beidan::match_validate_table(quotes,"prematch_sp",keys=c("fixture_id","outcome","quote_at"))
  receipt <- list(cutoff=cutoff,observed_at=observed,
    source_hash=digest::digest(file=source_path,algo="sha256"),
    raw_path=paths$nowscore_raw,raw_hash=raw_hash,
    meta_path=paths$source_meta,meta_hash=digest::digest(file=paths$source_meta,algo="sha256"),
    parser_hash=digest::digest(file=file.path(backend$root,"beidan_backend/prematch_sp.py"),algo="sha256"),
    quotes_hash=rlang::hash(quotes),offline=TRUE)
  return(list(quotes=quotes,receipt=receipt,source=source$result))
}

#' Build a new research source from recovered observations, preserving old cutoff
#' @param replay Valid result from RecentSpReplay; source quotes remain hash-bound.
#' @return An x-shaped source bundle for recent price experiments. This one-group
#'   carrier is newly built research, not the historical purchased plan.
#' @details Rebuilds with existing APIs; never edits old valuation receipts.
#'   Changed quotes or source cutoff fail; no I/O or settlement inputs.
RecentSpSource <- function(replay) {
  beidan:::parlay_check_saved_result(replay$source)
  if (!identical(replay$source$cutoff,replay$receipt$cutoff) ||
      !identical(rlang::hash(replay$quotes),replay$receipt$quotes_hash)) stop("replay binding mismatch")
  p <- replay$source$probabilities; cutoff <- replay$source$cutoff
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),
    cutoff,replay$source$constants,pattern=c(3L,3L,3L,3L,2L,2L,2L),n_candidates=1L,
    probabilities=p,prematch_sp=replay$quotes)
  evaluated <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=256,
    budget_cny=NULL,constraints=list(max_reuse=2L,max_overlap=2L),improve=FALSE)
  evaluated$receipt$recovered_source <- replay$receipt
  return(list(outputs=list(recovered=list(evaluated=evaluated,pool=pool))))
}
