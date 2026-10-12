#' Build probability-ranked net-margin core targets for research
#' @param base List containing a normalized score-grid tibble and explicit cutoff.
#' @param review List grid base_hash, ISO-Z cutoff_utc, reason, counterevidence.
#' @param evidence_id Nonempty identity admitted by the shared adjustment context.
#' @param policy List coverage (0,1), coefficient (0,1], tie_tolerance (0,1e-8].
#' @param cutoff Explicit cutoff matching base and review; defaults to base cutoff.
#' @return List complete integer-partition judgement, probability-ranked margin
#'   tibble, core margins, masses, normalizer, policy and implementation binding.
#' @details Pure target construction: no fitting, labels, writes or ticket lines.
#'   Include the first rank crossing coverage strictly; numerical comparisons use
#'   tie_tolerance, capped below half the remaining distance to one. Include all
#'   bins tied to the boundary probability, so ties cannot arbitrarily select a
#'   side. The core may be disconnected. Core weight one, exterior coefficient;
#'   preserve all score support and within-margin conditional score proportions
#'   through adjust_score_margin_distribution(). Invalid inputs fail closed.
.BuildFmMassCoreJudgement <- function(base, review, evidence_id, policy,
                                      cutoff = base$cutoff) {
  match_require_cutoff(cutoff)
  match_require_cutoff(base$cutoff)
  if (!identical(base$cutoff, cutoff)) stop("Base cutoff differs")
  if (any(c("handicap", "roles", "beidan_handicap") %in% c(names(base), names(review)))) {
    stop("Ticket roles or line cannot govern mass core")
  }
  checkmate::assert_names(names(policy), identical.to = c("coverage", "coefficient", "tie_tolerance"))
  checkmate::assert_number(policy$coverage, lower = .Machine$double.eps, upper = 1 - .Machine$double.eps)
  checkmate::assert_number(policy$coefficient, lower = .Machine$double.eps, upper = 1)
  checkmate::assert_number(policy$tie_tolerance, lower = .Machine$double.eps, upper = 1e-8)
  checkmate::assert_character(evidence_id, len = 1L, min.chars = 1L, any.missing = FALSE)
  for (key in c("base_hash", "cutoff_utc", "reason", "counterevidence")) {
    checkmate::assert_character(review[[key]], len = 1L, min.chars = 1L, any.missing = FALSE)
  }
  if (!grepl("Z$", review$cutoff_utc)) stop("Review UTC required")
  ts <- suppressWarnings(lubridate::ymd_hms(review$cutoff_utc, tz = "UTC", quiet = TRUE))
  if (is.na(ts) || as.numeric(ts) != as.numeric(cutoff$cutoff_utc)) stop("Review cutoff differs")
  grid <- base$grid
  checkmate::assert_tibble(grid, min.rows = 1L)
  checkmate::assert_names(names(grid), identical.to = c("home_goals", "away_goals", "probability"))
  for (key in c("home_goals", "away_goals")) {
    checkmate::assert_integerish(grid[[key]], lower = 0, any.missing = FALSE)
  }
  checkmate::assert_numeric(grid$probability, lower = 0, upper = 1, finite = TRUE, any.missing = FALSE)
  if (anyDuplicated(grid[c("home_goals", "away_goals")]) || abs(sum(grid$probability) - 1) > 1e-12) {
    stop("Unique normalized score grid required")
  }
  if (!identical(review$base_hash, .score_margin_hash(grid))) stop("Review grid binding differs")
  ranked <- grid |> dplyr::mutate(margin = home_goals - away_goals) |>
    dplyr::group_by(margin) |> dplyr::summarise(probability = sum(probability), .groups = "drop") |>
    dplyr::arrange(dplyr::desc(probability), margin) |>
    dplyr::mutate(cumulative = cumsum(probability))
  epsilon <- min(policy$tie_tolerance, (1 - policy$coverage) / 2)
  boundary <- which(ranked$cumulative > policy$coverage + epsilon)[1L]
  if (is.na(boundary)) stop("No strictly crossing mass boundary")
  boundary_probability <- ranked$probability[boundary]
  ranked$core <- ranked$probability >= boundary_probability - policy$tie_tolerance
  core <- sort(as.integer(ranked$margin[ranked$core]))
  core_mass <- sum(ranked$probability[ranked$core])
  normalizer <- sum(ranked$probability * ifelse(ranked$core, 1, policy$coefficient))
  full <- tibble::tibble(margin = seq.int(min(ranked$margin), max(ranked$margin))) |>
    dplyr::left_join(ranked |> dplyr::select(margin, probability), by = "margin", relationship = "one-to-one") |>
    dplyr::mutate(probability = dplyr::coalesce(probability, 0))
  reason <- paste(review$reason, "Counterevidence:", review$counterevidence)
  bins <- full |> dplyr::transmute(bin_id = paste0("margin_", margin),
    min_margin = as.numeric(margin), max_margin = as.numeric(margin),
    target_mass = probability * ifelse(margin %in% core, 1, policy$coefficient) / normalizer,
    evidence_id = .env$evidence_id, reason = .env$reason)
  bins <- dplyr::bind_rows(bins, tibble::tibble(bin_id = c("lower_outer", "upper_outer"),
    min_margin = c(-Inf, max(full$margin) + 1), max_margin = c(min(full$margin) - 1, Inf),
    target_mass = 0, evidence_id = evidence_id, reason = reason)) |> dplyr::arrange(min_margin)
  judgement <- list(model_id = "MASS_CORE_DIAGNOSTIC", rationale = reason, bins = bins)
  return(list(judgement = judgement, ranked_margins = ranked, boundary_rank = boundary,
    core_margins = core, core_mass = core_mass, final_core_mass = core_mass / normalizer,
    normalizer = normalizer, policy = policy,
    binding_hash = .score_margin_hash(list(base = base, review = review, cutoff = cutoff,
      evidence_id = evidence_id, policy = policy, judgement = judgement,
      implementation = paste(deparse(.BuildFmMassCoreJudgement), collapse = "\n")))))
}
