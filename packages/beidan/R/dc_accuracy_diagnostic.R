#' Describe ranks and probability scores on a paired fixture universe
#' @param probabilities Tibble with fixture_id, model, outcome (W/D/L), probability.
#'   One complete triple per fixture/model; all models use the same fixtures.
#' @param labels Tibble with unique fixture_id and actual_outcome (W/D/L).
#' @return List of fixture scores, overall scores, actual-outcome recall and
#'   predicted-outcome precision, marginal calibration and confusion tibbles.
#'   Probabilities are unitless; rates 0--1.
#' @details Pure historical description, no fitting or selection. Empty inputs,
#'   missing/invalid probabilities, mismatched universes and duplicate keys fail.
#'   Ties use W, D, L. Rank2/3 are exclusive; Top2/3 are cumulative coverage.
DcAccuracyDiagnostic <- function(probabilities, labels) {
  codes <- c("W", "D", "L")
  checkmate::assert_tibble(probabilities, min.rows = 1L)
  checkmate::assert_tibble(labels, min.rows = 1L)
  stopifnot(all(c("fixture_id", "model", "outcome", "probability") %in% names(probabilities)),
            all(c("fixture_id", "actual_outcome") %in% names(labels)))
  p <- probabilities |> dplyr::select(fixture_id, model, outcome, probability)
  y <- labels |> dplyr::select(fixture_id, actual_outcome)
  if (anyNA(p) || anyNA(y) || !is.numeric(p$probability) ||
      any(!is.finite(p$probability)) || any(p$probability < 0 | p$probability > 1) ||
      !is.character(p$fixture_id) || !is.character(y$fixture_id) ||
      any(!nzchar(p$fixture_id)) || any(!nzchar(p$model)) ||
      any(!p$outcome %in% codes) || any(!y$actual_outcome %in% codes) ||
      anyDuplicated(p[c("fixture_id", "model", "outcome")]) || anyDuplicated(y$fixture_id)) {
    stop("Invalid paired probability/label contract")
  }
  counts <- p |> dplyr::group_by(model, fixture_id) |>
    dplyr::summarise(n = dplyr::n(), mass = sum(probability), .groups = "drop")
  if (any(counts$n != 3L) || any(abs(counts$mass - 1) > 1e-8) ||
      nrow(counts) != dplyr::n_distinct(p$model) * nrow(y) ||
      !setequal(p$fixture_id, y$fixture_id)) stop("Incomplete paired universe")
  ranked <- p |> dplyr::mutate(tie = match(outcome, codes)) |>
    dplyr::arrange(model, fixture_id, dplyr::desc(probability), tie) |>
    dplyr::group_by(model, fixture_id) |>
    dplyr::mutate(rank = dplyr::row_number(), predicted_outcome = outcome[1L]) |>
    dplyr::ungroup() |>
    dplyr::left_join(y, by = "fixture_id", relationship = "many-to-one") |>
    dplyr::mutate(actual = as.double(outcome == actual_outcome))
  scores <- ranked |> dplyr::group_by(model, fixture_id) |>
    dplyr::summarise(actual_outcome = actual_outcome[1L],
      predicted_outcome = predicted_outcome[1L], actual_rank = rank[actual == 1],
      actual_probability = probability[actual == 1],
      brier = sum((probability - actual)^2),
      logloss = -log(probability[actual == 1]), .groups = "drop") |>
    dplyr::mutate(top1 = actual_rank == 1L, top2 = actual_rank <= 2L, top3 = actual_rank <= 3L)
  summary <- scores |> dplyr::group_by(model) |>
    dplyr::summarise(n = dplyr::n(), hits1 = sum(top1), hits2 = sum(top2),
      top1 = mean(top1), top2 = mean(top2), top3 = mean(top3),
      rank2 = mean(actual_rank == 2L), rank3 = mean(actual_rank == 3L),
      brier = mean(brier), logloss = mean(logloss), .groups = "drop")
  recall <- scores |> dplyr::group_by(model, actual_outcome) |>
    dplyr::summarise(n = dplyr::n(), hits1 = sum(top1), hits2 = sum(top2),
      top1 = mean(top1), top2 = mean(top2), top3 = mean(top3), .groups = "drop")
  precision <- scores |> dplyr::group_by(model, predicted_outcome) |>
    dplyr::summarise(n = dplyr::n(), hits = sum(top1), precision = mean(top1), .groups = "drop")
  calibration <- ranked |> dplyr::group_by(model, outcome) |>
    dplyr::summarise(n = dplyr::n(), predicted_mass = mean(probability),
      observed_mass = mean(actual), bias = predicted_mass - observed_mass, .groups = "drop")
  confusion <- scores |> dplyr::count(model, predicted_outcome, actual_outcome, name = "n")
  return(list(scores = scores, summary = summary, recall = recall, precision = precision,
    calibration = calibration, confusion = confusion))
}

#' Refit fixed rho scenarios from a frozen market epoch, without labels
#' @param epoch Explicit prepared epoch with bound cutoff and pre-cutoff quotes.
#' @param model_config Explicit rho, total_bounds and tail_tolerance configuration.
#' @param rhos Finite unique fixed scenario values; not selected from outcomes.
#' @return List of probability/fit tibbles and per-scenario exclusions, plus the
#'   explicit cutoff and input hash. No historical parameter choice is returned.
#' @details Reuses estimate_match_probabilities including chronology and status
#'   validation. Goal means are refitted for each rho. Empty/invalid grids fail;
#'   unequal successfully fitted fixture universes fail rather than bias scoring.
#'   No I/O, label access, caching or training occurs.
DcRhoScenarios <- function(epoch, model_config, rhos) {
  match_require_cutoff(epoch$cutoff)
  checkmate::assert_numeric(rhos, min.len = 1L, any.missing = FALSE, finite = TRUE, unique = TRUE)
  probabilities <- list()
  fits <- list()
  exclusions <- list()
  for (i in seq_along(rhos)) {
    config <- model_config
    config$rho <- rhos[i]
    projected <- estimate_match_probabilities(epoch, config)
    probabilities[[i]] <- projected$probabilities |>
      dplyr::mutate(model = paste0("rho=", rhos[i]), rho = rhos[i])
    fits[[i]] <- projected$fit |> dplyr::mutate(rho_scenario = rhos[i])
    exclusions[[i]] <- projected$exclusions
    if (i > 1L && !setequal(probabilities[[i]]$fixture_id, probabilities[[1L]]$fixture_id)) {
      stop("Rho scenarios have unequal fitted universes")
    }
  }
  if (!nrow(probabilities[[1L]])) stop("No fitted fixtures for rho scenarios")
  return(list(probabilities = dplyr::bind_rows(probabilities), fit = dplyr::bind_rows(fits),
    exclusions = exclusions, cutoff = epoch$cutoff,
    input_hash = rlang::hash(list(epoch, model_config, rhos))))
}
