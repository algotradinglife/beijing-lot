#' Project a diagnostic DC grid from one half-goal Asian and one total quote
#' @param asian One-row tibble company_id, fixture_id, quote_at UTC POSIXct,
#'   handicap signed home half-goal (not integer/quarter), home_decimal,
#'   away_decimal including stake. No Beidan line or score fields.
#' @param totals One-row tibble fixture_id, company_id, quote_at UTC POSIXct,
#'   line (quarter increments >=2.5), over_decimal, under_decimal.
#' @param policy Explicit list rho, total_bounds, lambda_floor,
#'   tail_tolerance, max_quote_age_hours. No learned or hidden defaults.
#' @param context Opaque shared adjustment evidence context. Source hashes bind
#'   partial_input to hash(list(asian,totals,policy,fixture,cutoff)), partial_code
#'   to the full function hash, direction_implementation to existing code identity,
#'   and partial_total_code to hash of full total_market_constraint and
#'   asian_total_probability definitions. Quote evidence IDs asian-COMPANY and
#'   totals-COMPANY bind exact canonical rows.
#' @param fixture One-row tibble fixture_id, issue_id, home, away; no ticket line.
#' @param cutoff Explicit issue/time cutoff, never current time.
#' @param repository_root Explicit pinned backend root/project interpreter.
#' @return List normalized score-grid tibble, parameter tibble, selected quotes,
#'   Asian target/model share and cutoff/input/dependency-bound diagnostic receipt.
#' @details Internal research API: not FM17 source admission. Uses existing total
#'   inversion and stats::uniroot. Half-goal AH has no pushes; ceil(handicap)
#'   projects its win event through the authoritative integer DC grid. Total>=2.5
#'   keeps DC low-cell corrections below the threshold with canceling total mass.
#'   Unsupported, empty, stale, unbound, infeasible or boundary solutions fail.
#'   No fitting to scores, fetching, writes, synthetic Euro input or lambda prior.
.ProjectHalfAsianTotalDc <- function(asian, totals, policy, context, fixture,
                                     cutoff, repository_root) {
  match_require_cutoff(cutoff)
  checkmate::assert_tibble(fixture, nrows = 1L)
  checkmate::assert_names(names(fixture), identical.to = c("fixture_id", "issue_id", "home", "away"))
  for (k in names(fixture)) checkmate::assert_character(fixture[[k]], len = 1L, any.missing = FALSE, min.chars = 1L)
  if (fixture$issue_id != cutoff$issue_id || !startsWith(fixture$fixture_id, paste0(cutoff$issue_id, ":")) || fixture$home == fixture$away) stop("Fixture cutoff differs")
  checkmate::assert_names(names(policy), identical.to = c("rho", "total_bounds", "lambda_floor", "tail_tolerance", "max_quote_age_hours"))
  dc_validate_rho(policy$rho)
  checkmate::assert_numeric(policy$total_bounds, len = 2L, lower = .Machine$double.eps, finite = TRUE, any.missing = FALSE)
  if (policy$total_bounds[2] <= policy$total_bounds[1]) stop("Increasing total bounds required")
  checkmate::assert_number(policy$lambda_floor, lower = .Machine$double.eps, finite = TRUE)
  checkmate::assert_number(policy$tail_tolerance, lower = .Machine$double.eps, upper = .009, finite = TRUE)
  checkmate::assert_number(policy$max_quote_age_hours, lower = 0, finite = TRUE)
  quotes <- list(asian = asian, totals = totals)
  for (kind in names(quotes)) {
    q <- quotes[[kind]]
    required <- if (kind == "asian") c("company_id", "fixture_id", "quote_at", "handicap", "home_decimal", "away_decimal") else c("fixture_id", "company_id", "quote_at", "line", "over_decimal", "under_decimal")
    checkmate::assert_tibble(q, nrows = 1L);checkmate::assert_names(names(q), identical.to = required)
    for (k in c("company_id", "fixture_id")) checkmate::assert_character(q[[k]], len = 1L, any.missing = FALSE, min.chars = 1L)
    if (!inherits(q$quote_at, "POSIXct") || anyNA(q$quote_at) || !is.finite(as.numeric(q$quote_at)) || q$fixture_id != fixture$fixture_id || q$quote_at >= cutoff$cutoff_utc || as.numeric(difftime(cutoff$cutoff_utc, q$quote_at, units = "hours")) > policy$max_quote_age_hours) stop("Prior matching fresh quote required")
    for (k in setdiff(required, c("company_id", "fixture_id", "quote_at"))) checkmate::assert_numeric(q[[k]], len = 1L, finite = TRUE, any.missing = FALSE)
    price <- if (kind == "asian") c(q$home_decimal, q$away_decimal) else c(q$over_decimal, q$under_decimal)
    if (any(price <= 1)) stop("Decimal prices must exceed one")
  }
  if (asian$handicap * 2 != round(asian$handicap * 2) || asian$handicap == round(asian$handicap)) stop("Half-goal Asian line required")
  if (totals$line < 2.5 || totals$line * 4 != round(totals$line * 4)) stop("Supported total line >=2.5 required")
  reticulate::use_python(file.path(repository_root, ".venv/bin/python"), required = TRUE)
  sys <- reticulate::import("sys", convert = FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(sys$prefix)), normalizePath(file.path(repository_root, ".venv")))) stop("Project Python required")
  sys$path$insert(0L, file.path(repository_root, "packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.fundamental_probability", convert = FALSE)
  if (!inherits(context, "python.builtin.object")) stop("Shared evidence context required")
  admitted <- reticulate::py_to_r(backend$export_adjustment_evidence_context(context, as.list(fixture), as.numeric(cutoff$cutoff_utc), "HISTORICAL_DIAGNOSTIC", repository_root))
  hashes <- list(partial_input = .score_margin_hash(list(asian = asian, totals = totals, policy = policy, fixture = fixture, cutoff = cutoff)), partial_code = digest::digest(paste(deparse(.ProjectHalfAsianTotalDc), collapse = "\n"), algo = "sha256"), direction_implementation = .score_margin_code(repository_root), partial_total_code = .score_margin_hash(lapply(list(total_market_constraint, asian_total_probability), function(f) paste(deparse(f), collapse = "\n"))))
  if (!identical(admitted$receipt$source_hashes[names(hashes)], hashes)) stop("Partial input/code binding differs; rebuild context")
  evidence <- dplyr::bind_rows(admitted$evidence)
  for (kind in names(quotes)) {
    q <- quotes[[kind]];bound <- dplyr::filter(evidence, evidence_id == paste0(kind, "-", q$company_id))
    if (nrow(bound) != 1L || bound$source_hash != .score_margin_hash(q)) stop("Selected quote evidence unavailable or differs")
  }
  total <- total_market_constraint(tibble::tibble(company = totals$company_id, line = totals$line, over_hk = totals$over_decimal - 1, under_hk = totals$under_decimal - 1), policy$total_bounds)$lambda_total
  target <- asian$away_decimal / (asian$home_decimal + asian$away_decimal)
  lower <- policy$lambda_floor;upper <- total - lower
  if (lower >= upper) stop("Feasible positive goal bounds required")
  # This domain callback has no historical selection or temporal machinery.
  difference <- function(home) unname(dixon_coles_score_grid(home, total - home, as.integer(ceiling(asian$handicap)), policy$tail_tolerance, policy$rho)$probability['W']) - target
  ends <- c(difference(lower), difference(upper))
  if (prod(ends) >= 0) stop("Interior Asian solution unavailable")
  home <- stats::uniroot(difference, c(lower, upper), tol = 1e-9)$root
  dc <- dixon_coles_score_grid(home, total - home, 0L, policy$tail_tolerance, policy$rho)
  grid <- tibble::as_tibble(dc$grid) |> dplyr::select(home_goals, away_goals, probability)
  parameters <- tibble::tibble(lambda_home = home, lambda_away = total - home, rho = policy$rho, total_mean = total)
  receipt <- list(model_id = "PARTIAL_HALF_AH_OU_DIAGNOSTIC", cutoff = cutoff, fixture = as.list(fixture), input_hashes = hashes, source_context = admitted$receipt, selected_parameters = parameters, policy = policy, asian_target = target, asian_model = target + difference(home), output_hash = .score_margin_hash(list(grid = grid, parameters = parameters)), cache_reuse = "NONE", intended_use = "HISTORICAL_DIAGNOSTIC")
  list(grid = grid, parameters = parameters, asian_target = target, asian_model = target + difference(home), asian = asian, totals = totals, receipt = receipt)
}
