#' Experimental top-three margin draw allocation (FM-1.8.0-alpha.1)
#' @param base Frozen selected BEFORE-tail artifact: grid tibble of home_goals,
#'   away_goals, probability; cutoff; source_hashes; max_source_available_utc;
#'   model_id; intended_use=HISTORICAL_DIAGNOSTIC. No prior alpha output accepted.
#' @param handicap Signed integer home handicap. Target margin is -handicap.
#' @param fixture One-row tibble fixture_id, issue_id, home, away.
#' @param cutoff Explicit issue_id and UTC cutoff_utc, identical to base$cutoff.
#' @param context Opaque shared temporal_learning evidence context, binding
#'   alpha_input=.score_margin_hash(list(base=base,handicap=handicap,
#'   fixture=fixture,cutoff=cutoff)), alpha_code=digest::digest(list(
#'   body(AlphaTop3Draw),body(.score_margin_hash),body(match_require_cutoff),
#'   body(match_check_character_id)),
#'   algo="sha256"). Shared context exporter verifies transitive implementation.
#' @param repository_root Explicit project root and .venv interpreter.
#' @return List grid, probabilities (W/D/L), margin table and cutoff-bound
#'   receipt. Reweighted grid is bound to this handicap, not a general DC fit.
#' @details Fixed diagnostic-only policy, no learning/selection of parameters.
#'   Rank draw atom among positive margin atoms; trigger competition rank <=2.
#'   Top-three boundary ties (absolute tolerance 1e-12) included in full. Fewer
#'   atoms use all. Non-trigger preserves grid exactly. W/L mass ratio and
#'   within-category score ratios preserved. Empty/invalid inputs, unsupported
#'   chronology/context/hash, or an already tail-adjusted grid fail closed.
#'   No fetching, database writes or automatic prospective admission.
AlphaTop3Draw <- function(base, handicap, fixture, cutoff, context, repository_root) {
  match_require_cutoff(cutoff); match_require_cutoff(base$cutoff)
  if (!identical(cutoff, base$cutoff)) stop("Cutoff differs; rebuild required")
  checkmate::assert_integerish(handicap, len = 1L, any.missing = FALSE)
  if (handicap != round(handicap)) stop("Exact integer handicap required")
  checkmate::assert_tibble(fixture, nrows = 1L)
  checkmate::assert_names(names(fixture), identical.to = c("fixture_id", "issue_id", "home", "away"))
  for (k in names(fixture)) checkmate::assert_character(fixture[[k]], len = 1L, any.missing = FALSE, min.chars = 1L)
  if (fixture$issue_id != cutoff$issue_id || !startsWith(fixture$fixture_id, paste0(cutoff$issue_id, ":")) || fixture$home == fixture$away) stop("Fixture/cutoff differs")
  if (!identical(base$intended_use, "HISTORICAL_DIAGNOSTIC")) stop("Alpha is diagnostic only")
  if (!is.null(base$receipt) || !is.null(base$projection_handicap) || !grepl("SOURCE_(NATIVE|MARKET)$", base$model_id)) stop("Selected BEFORE-tail source artifact required")
  checkmate::assert_list(base$source_hashes, min.len = 1L, names = "unique")
  checkmate::assert_character(unlist(base$source_hashes), any.missing = FALSE, min.chars = 1L)
  if (!inherits(base$max_source_available_utc, "POSIXct") || length(base$max_source_available_utc) != 1L || anyNA(base$max_source_available_utc) ||
      !is.finite(as.numeric(base$max_source_available_utc)) || base$max_source_available_utc >= cutoff$cutoff_utc) stop("Source chronology before cutoff required")
  grid <- base$grid
  checkmate::assert_tibble(grid, min.rows = 1L)
  checkmate::assert_names(names(grid), identical.to = c("home_goals", "away_goals", "probability"))
  for (k in c("home_goals", "away_goals")) {
    checkmate::assert_integerish(grid[[k]], lower = 0, any.missing = FALSE)
    if (any(grid[[k]] != round(grid[[k]]))) stop("Exact integer score support required")
  }
  checkmate::assert_numeric(grid$probability, lower = 0, upper = 1, finite = TRUE, any.missing = FALSE)
  if (anyDuplicated(grid[c("home_goals", "away_goals")]) || abs(sum(grid$probability) - 1) > 1e-12) stop("Unique normalized score grid required")
  input_hash <- .score_margin_hash(list(base = base, handicap = handicap, fixture = fixture, cutoff = cutoff))
  code_hash <- digest::digest(list(body(AlphaTop3Draw), body(.score_margin_hash), body(match_require_cutoff),
    body(match_check_character_id)), algo = "sha256")
  reticulate::use_python(file.path(repository_root, ".venv/bin/python"), required = TRUE)
  sys <- reticulate::import("sys", convert = FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(sys$prefix)), normalizePath(file.path(repository_root, ".venv")))) stop("Project Python required")
  sys$path$insert(0L, file.path(repository_root, "packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.fundamental_probability", convert = FALSE)
  if (!inherits(context, "python.builtin.object")) stop("Shared evidence context required")
  admitted <- reticulate::py_to_r(backend$export_adjustment_evidence_context(context, as.list(fixture),
    as.numeric(cutoff$cutoff_utc), "HISTORICAL_DIAGNOSTIC", repository_root))
  if (!identical(admitted$receipt$source_hashes$alpha_input, input_hash) ||
      !identical(admitted$receipt$source_hashes$alpha_code, code_hash)) stop("Alpha input/code binding differs")
  tolerance <- 1e-12
  margins <- grid |> dplyr::mutate(margin = as.integer(home_goals - away_goals)) |>
    dplyr::group_by(margin) |> dplyr::summarise(probability = sum(probability), .groups = "drop")
  positive <- margins |> dplyr::filter(probability > 0) |> dplyr::arrange(dplyr::desc(probability), margin)
  target <- -handicap
  atom <- sum(margins$probability[margins$margin == target])
  atom_rank <- if (atom > 0) as.integer(1L + sum(positive$probability > atom + tolerance)) else NA_integer_
  boundary <- positive$probability[min(3L, nrow(positive))]
  core <- positive |> dplyr::filter(probability >= boundary - tolerance)
  triggered <- !is.na(atom_rank) && atom_rank <= 2L
  category <- ifelse(grid$home_goals - grid$away_goals + handicap > 0, "W",
    ifelse(grid$home_goals - grid$away_goals + handicap == 0, "D", "L"))
  original <- vapply(c("W", "D", "L"), function(k) sum(grid$probability[category == k]), numeric(1))
  adjusted <- original
  if (triggered) {
    adjusted[["D"]] <- atom/sum(core$probability)
    sides <- original[["W"]] + original[["L"]]
    if (sides > 0) adjusted[c("W", "L")] <- (1 - adjusted[["D"]]) * original[c("W", "L")]/sides
    else adjusted[c("W", "L")] <- 0
    for (k in c("W", "D", "L")) {
      if (original[[k]] > 0) grid$probability[category == k] <- grid$probability[category == k] * adjusted[[k]]/original[[k]]
    }
  }
  observed <- vapply(c("W", "D", "L"), function(k) sum(grid$probability[category == k]), numeric(1))
  stopifnot(abs(sum(grid$probability) - 1) < 1e-12, max(abs(observed - adjusted)) < 1e-12)
  probabilities <- tibble::tibble(outcome = c("W", "D", "L"), probability = unname(observed))
  final_margins <- grid |> dplyr::mutate(margin = as.integer(home_goals - away_goals)) |>
    dplyr::group_by(margin) |> dplyr::summarise(probability = sum(probability), .groups = "drop")
  result <- list(grid = grid, probabilities = probabilities, margins = final_margins,
    before_margins = margins, cutoff = cutoff,
    projection_handicap = as.integer(handicap))
  result$receipt <- list(model_id = "FM-1.8.0-alpha.1", status = "EXPERIMENTAL_NOT_VALIDATED",
    intended_use = "HISTORICAL_DIAGNOSTIC", fixture_id = fixture$fixture_id,
    cutoff = list(issue_id = cutoff$issue_id,
      cutoff_utc = format(cutoff$cutoff_utc, "%Y-%m-%dT%H:%M:%OS6Z", tz = "UTC")), source_context = admitted$receipt,
    input_hash = input_hash, code_hash = code_hash,
    imported_helpers = list(hash = digest::digest(body(.score_margin_hash), algo = "sha256"),
      cutoff = digest::digest(body(match_require_cutoff), algo = "sha256"),
      character_id = digest::digest(body(match_check_character_id), algo = "sha256")),
    target_margin = target, projection_handicap = as.integer(handicap), triggered = triggered,
    draw_atom_rank = atom_rank, core_margins = core$margin, core_mass = sum(core$probability),
    original_probabilities = as.list(original), adjusted_probabilities = as.list(observed),
    boundary_tie_tolerance = tolerance, tail_compression = FALSE,
    output_hash = .score_margin_hash(result),
    cache_key = .score_margin_hash(list(cutoff = cutoff, input = input_hash, code = code_hash)), cache_reuse = "NONE")
  result
}
