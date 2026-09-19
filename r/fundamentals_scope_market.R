# Read an explicitly sealed full-scope market audit; no writes or collection.
# study/root/scope paths are explicit; expected_sha256 seals summary.json.
# Returns per-market fixture rows, per-fixture status pairs and per-issue counts.
# IDs remain character, cutoff is UTC POSIXct; missing/changed evidence fails.
read_scope_market_audit <- function(study, repository_root, implementation_root, scope_path, expected_sha256) {
  summary_path <- file.path(study, "summary.json")
  if (length(expected_sha256) != 1L || is.na(expected_sha256) ||
      !identical(digest::digest(file = summary_path, algo = "sha256"), expected_sha256))
    stop("Summary hash mismatch")
  x <- jsonlite::read_json(summary_path, simplifyVector = FALSE)
  if (!identical(x$historical_admission, FALSE) ||
      !identical(x$source_policy, "TITAN_PRIMARY_NOWSCORE_CROSSCHECK_FILL"))
    stop("Unexpected audit policy")
  for (field in c("source_hashes", "implementation_hashes", "output_hashes")) {
    hashes <- x[[field]]
    if (!length(hashes) || is.null(names(hashes))) stop("Missing evidence hashes")
    base <- switch(field, output_hashes=study,
                   implementation_hashes=implementation_root,
                   source_hashes=repository_root)
    for (name in names(hashes)) {
      target <- normalizePath(file.path(base, name), mustWork = TRUE)
      prefix <- paste0(normalizePath(base, mustWork = TRUE), "/")
      if (!startsWith(target, prefix)) stop("Evidence path outside root")
      if (!identical(digest::digest(file = target, algo = "sha256"), hashes[[name]]))
        stop("Evidence hash mismatch: ", name)
    }
  }
  scope_name <- substring(normalizePath(scope_path, mustWork = TRUE),
                          nchar(normalizePath(repository_root, mustWork = TRUE)) + 2L)
  if (is.null(x$source_hashes[[scope_name]]) ||
      !identical(digest::digest(file = scope_path, algo = "sha256"),
                 x$source_hashes[[scope_name]])) stop("Unbound scope input")
  scope <- jsonlite::read_json(scope_path, simplifyVector = TRUE)
  if (anyDuplicated(scope$issues) ||
      anyDuplicated(scope$fixtures[c("issue", "slot")]) ||
      !setequal(scope$issues, unique(scope$fixtures$issue)))
    stop("Invalid scope identities")
  rows <- purrr::map_dfr(x$rows, function(row) {
    tibble::tibble(issue = row$issue, slot = row$slot,
      provider_id = row$provider_id, market = row$market,
      status = row$status, cutoff_utc = row$cutoff_utc,
      prior_companies = row$prior_companies)
  })
  if (!nrow(rows) || !is.character(rows$issue) || !is.character(rows$provider_id) ||
      anyNA(rows) || anyDuplicated(rows[c("issue", "slot", "market")]) ||
      any(!rows$market %in% c("euro", "total")) ||
      any(rows$slot < 1 | rows$slot != as.integer(rows$slot)) ||
      any(rows$prior_companies < 0 | rows$prior_companies != as.integer(rows$prior_companies)))
    stop("Invalid market row contract")
  expected <- tidyr::crossing(tibble::as_tibble(scope$fixtures),
                              market = c("euro", "total")) |>
    dplyr::select(issue, slot, provider_id, market)
  keys <- c("issue", "slot", "provider_id", "market")
  if (anyDuplicated(expected[keys]) || nrow(rows) != nrow(expected) ||
      nrow(dplyr::anti_join(rows, expected, by = keys)) ||
      nrow(dplyr::anti_join(expected, rows, by = keys)))
    stop("Incomplete audit scope")
  if (!setequal(names(x$output_hashes), paste0(scope$issues, ".json")) ||
      length(x$issues) != length(scope$issues) ||
      x$fixture_market_rows != nrow(rows) || x$fixture_count != nrow(scope$fixtures))
    stop("Audit denominator mismatch")
  clocks <- dplyr::left_join(rows, tibble::as_tibble(scope$fixtures) |>
    dplyr::select(issue, slot, decision_ts), by = c("issue", "slot"))
  row_times <- readr::parse_datetime(clocks$cutoff_utc, locale = readr::locale(tz = "UTC"))
  scope_times <- readr::parse_datetime(clocks$decision_ts, locale = readr::locale(tz = "UTC"))
  if (anyNA(row_times) || anyNA(scope_times) ||
      nrow(readr::problems(row_times)) || nrow(readr::problems(scope_times)))
    stop("Invalid cutoff timestamp")
  if (any(row_times != scope_times)) stop("Scope cutoff mismatch")
  # A sealed summary must also agree with the sealed per-issue evidence.
  for (issue in scope$issues) {
    detail <- jsonlite::read_json(file.path(study, paste0(issue, ".json")),
                                 simplifyVector = FALSE)
    summary_rows <- Filter(function(row) identical(row$issue, issue), x$rows)
    fields <- names(rows)
    compact <- lapply(detail, function(row) row[fields])
    expected_compact <- lapply(summary_rows, function(row) row[fields])
    if (!identical(compact, expected_compact))
      stop("Summary/detail mismatch: ", issue)
  }
  if (any((rows$status == "QUOTES_PRIOR_DIAGNOSTIC") !=
          (rows$prior_companies > 0))) stop("Status/company count mismatch")
  issue_names <- vapply(x$issues, function(item) item$issue, character(1))
  if (anyDuplicated(issue_names) || !setequal(issue_names, scope$issues))
    stop("Summary issue identities mismatch")
  if (!is.character(x$generated_at) || length(x$generated_at) != 1L ||
      is.na(x$generated_at)) stop("Missing generation timestamp")
  generated <- readr::parse_datetime(x$generated_at, locale=readr::locale(tz="UTC"))
  if (is.na(generated) || nrow(readr::problems(generated)))
    stop("Invalid generation timestamp")
  rows$cutoff_utc <- row_times
  fixtures <- rows |> dplyr::select(dplyr::all_of(keys), status) |>
    tidyr::pivot_wider(names_from = market, values_from = status)
  by_issue <- rows |> dplyr::count(issue, market, status, name = "fixture_market_rows")
  availability <- fixtures |>
    dplyr::group_by(issue) |>
    dplyr::summarise(
      fixtures = dplyr::n(),
      euro_prior = sum(euro == "QUOTES_PRIOR_DIAGNOSTIC"),
      total_prior = sum(total == "QUOTES_PRIOR_DIAGNOSTIC"),
      both_prior = sum(euro == "QUOTES_PRIOR_DIAGNOSTIC" &
                         total == "QUOTES_PRIOR_DIAGNOSTIC"),
      .groups = "drop"
    )
  list(rows = rows, fixtures = fixtures, by_issue = by_issue,
       availability = availability,
       generated_at = x$generated_at, summary_sha256 = expected_sha256,
       historical_admission = FALSE)
}
