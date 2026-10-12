#' Select the FM-1.6.0 native or joint-market score distribution
#' @param native Native base list: normalized grid tibble (home_goals,
#'   away_goals, probability), explicit cutoff, model_id, source_hashes,
#'   max_source_available_utc (POSIXct), intended_use. No ticket line or labels.
#' @param market Same base contract for joint euro/Asian/total projection,
#'   or NULL when unavailable. Ineligible market never supplies a fallback.
#' @param review List confidence (low/uncertain/adequate), market_sufficient,
#'   market_consistent (logical), reason, counterevidence, evidence_ids,
#'   cutoff_utc (ISO UTC Z), native_hash, market_hash (ABSENT if NULL),
#'   author and review_version (nonempty attribution).
#'   Confidence concerns evidence quality, not disagreement or win probability.
#' @param context Opaque shared temporal_learning adjustment evidence context.
#'   Bind fm_source_selection_inputs to hash(list(native,market,review,fixture,
#'   cutoff)), and fm_source_selection_code to this function's full signature/body hash.
#' @param fixture One-row tibble fixture_id, issue_id, home, away; no handicap.
#' @param cutoff Explicit issue_id/cutoff_utc object matching both inputs;
#'   may be omitted to use the explicitly passed native$cutoff.
#' @param repository_root Explicit backend root with project .venv and source.
#' @export
#' @return List base (selected score-grid base, no lambda blending),
#'   selected_source and cutoff/input/code/evidence-bound receipt. output_hash
#'   identifies the finalized returned base excluding only its self-reference
#'   source_hashes$selection_receipt; that field hashes the complete receipt.
#' @details No fitting, scraping, writes or default chronology. Low/uncertain
#'   native confidence plus sufficient consistent market selects market exactly;
#'   otherwise retain native. Eligible but missing market fails closed. Shared
#'   evidence validation/admission/replay is authoritative; no chronology proxy
#'   grants prospective eligibility. Empty/malformed/changed inputs are errors.
SelectFmProbabilitySource <- function(native, market, review, context, fixture, cutoff = native$cutoff, repository_root) {
  match_require_cutoff(cutoff)
  checkmate::assert_tibble(fixture, nrows = 1L)
  checkmate::assert_names(names(fixture), identical.to = c("fixture_id", "issue_id", "home", "away"))
  for (k in names(fixture)) checkmate::assert_character(fixture[[k]], len = 1L, min.chars = 1L, any.missing = FALSE)
  if (fixture$issue_id != cutoff$issue_id || !startsWith(fixture$fixture_id, paste0(fixture$issue_id, ":")) || fixture$home == fixture$away) stop("Fixture/cutoff differs")
  checkmate::assert_list(review)
  checkmate::assert_names(names(review), identical.to = c("confidence", "market_sufficient", "market_consistent", "reason", "counterevidence", "evidence_ids", "cutoff_utc", "native_hash", "market_hash", "author", "review_version"))
  checkmate::assert_choice(review$confidence, c("low", "uncertain", "adequate"))
  for (k in c("market_sufficient", "market_consistent")) checkmate::assert_flag(review[[k]])
  for (k in c("reason", "counterevidence", "cutoff_utc", "native_hash", "market_hash", "author", "review_version")) checkmate::assert_character(review[[k]], len = 1L, min.chars = 1L, any.missing = FALSE)
  checkmate::assert_character(review$evidence_ids, min.len = 1L, any.missing = FALSE, min.chars = 1L, unique = TRUE)
  if (!grepl("Z$", review$cutoff_utc)) stop("Review UTC cutoff required")
  rt <- suppressWarnings(lubridate::ymd_hms(review$cutoff_utc, tz = "UTC", quiet = TRUE))
  if (is.na(rt) || as.numeric(rt) != as.numeric(cutoff$cutoff_utc)) stop("Review cutoff differs")
  bases <- list(native = native)
  if (!is.null(market)) bases$market <- market
  for (b in bases) {
    checkmate::assert_list(b)
    checkmate::assert_names(names(b), identical.to = c("grid", "cutoff", "model_id", "source_hashes", "max_source_available_utc", "intended_use"))
    match_require_cutoff(b$cutoff)
    if (!identical(b$cutoff, cutoff)) stop("Base cutoff differs")
    checkmate::assert_character(b$model_id, len = 1L, min.chars = 1L, any.missing = FALSE)
    checkmate::assert_list(b$source_hashes, min.len = 1L, names = "unique")
    checkmate::assert_character(unlist(b$source_hashes, use.names = FALSE), any.missing = FALSE, min.chars = 1L)
    checkmate::assert_choice(b$intended_use, c("HISTORICAL_DIAGNOSTIC", "PROSPECTIVE_DECISION"))
    if (!inherits(b$max_source_available_utc, "POSIXct") || length(b$max_source_available_utc) != 1L || anyNA(b$max_source_available_utc) || !is.finite(as.numeric(b$max_source_available_utc)) || b$max_source_available_utc >= cutoff$cutoff_utc) stop("Prior base chronology required")
    g <- b$grid
    checkmate::assert_tibble(g, min.rows = 1L)
    checkmate::assert_names(names(g), identical.to = c("home_goals", "away_goals", "probability"))
    for (k in c("home_goals", "away_goals")) checkmate::assert_integerish(g[[k]], lower = 0L, any.missing = FALSE)
    checkmate::assert_numeric(g$probability, lower = 0, upper = 1, finite = TRUE, any.missing = FALSE)
    if (anyDuplicated(g[c("home_goals", "away_goals")]) || abs(sum(g$probability) - 1) > 1e-12) stop("Unique normalized grid required")
  }
  if (!is.null(market) && market$intended_use != native$intended_use) stop("Availability use differs")
  if (!identical(review$native_hash, .score_margin_hash(native)) || !identical(review$market_hash, if (is.null(market)) "ABSENT" else .score_margin_hash(market))) stop("Review input binding differs")
  use_market <- review$confidence %in% c("low", "uncertain") && review$market_sufficient && review$market_consistent
  if (review$market_sufficient && is.null(market)) stop("Sufficient market requires joint projection")
  reticulate::use_python(file.path(repository_root, ".venv/bin/python"), required = TRUE)
  sys <- reticulate::import("sys", convert = FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(sys$prefix)), normalizePath(file.path(repository_root, ".venv")))) stop("Project Python required")
  sys$path$insert(0L, file.path(repository_root, "packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.fundamental_probability", convert = FALSE)
  if (!inherits(context, "python.builtin.object")) stop("Opaque shared evidence context required")
  admitted <- reticulate::py_to_r(backend$export_adjustment_evidence_context(context, as.list(fixture), as.numeric(cutoff$cutoff_utc), native$intended_use, repository_root))
  hashes <- list(fm_source_selection_inputs = .score_margin_hash(list(native = native, market = market, review = review, fixture = fixture, cutoff = cutoff)), fm_source_selection_code = digest::digest(paste(deparse(SelectFmProbabilitySource), collapse = "\n"), algo = "sha256"), fm_source_selection_dependencies = .score_margin_code(repository_root))
  if (!identical(admitted$receipt$source_hashes[names(hashes)], hashes)) stop("Source selection input/code binding differs; rebuild context")
  evidence <- dplyr::bind_rows(admitted$evidence)
  if (!all(review$evidence_ids %in% evidence$evidence_id)) stop("Review evidence unavailable before cutoff")
  selected_source <- if (use_market) "market" else "native"
  selected <- bases[[selected_source]]
  selected$model_id <- paste0("FM-1.6.0_SOURCE_", toupper(selected_source))
  selected$source_hashes$selection_receipt <- NULL
  receipt <- list(model_id = "FM-1.6.0", cutoff = cutoff, fixture = as.list(fixture), selected_source = selected_source,
    rule = "LOW_OR_UNCERTAIN_AND_SUFFICIENT_AND_CONSISTENT_MARKET", review = review,
    input_hashes = hashes, source_context = admitted$receipt, selected_grid_hash = .score_margin_hash(selected$grid),
    output_hash = .score_margin_hash(selected), output_hash_scope = "BASE_EXCLUDING_SOURCE_HASHES_SELECTION_RECEIPT", cache_reuse = "NONE")
  selected$source_hashes$selection_receipt <- .score_margin_hash(receipt)
  return(list(base = selected, selected_source = selected_source, receipt = receipt))
}
