#' Describe confidence reliability of frozen three-outcome forecasts
#'
#' @param probabilities Tibble: fixture_id/model/outcome (W,D,L)/probability;
#'   a complete normalized triple for every fixture and model, same universe.
#' @param labels Tibble: unique fixture_id/actual_outcome (W,D,L).
#' @param breaks Strictly increasing numeric bin edges, covering [1/3,1].
#' @return List of tibbles: fixtures (one row per fixture/model), bins (including
#'   empty bins), summary (one row per model). Probability units are 0--1.
#' @details Pure post-hoc description: no fitting, calibration transformation,
#'   threshold selection or betting decisions. Calls DcAccuracyDiagnostic for
#'   authoritative W,D,L tie order and input contracts. Left-closed bins; last
#'   bin includes 1. Empty bins have n/hits=0, means NA. Degenerate correlations
#'   are NA. No confidence intervals or independence inference are produced.
#'   Missing/empty/invalid inputs fail; no side effects.
Top1Reliability <- function(probabilities, labels, breaks) {
  if (!is.numeric(breaks) || length(breaks) < 2L || anyNA(breaks) ||
      any(!is.finite(breaks)) || any(diff(breaks) <= 0) ||
      breaks[1] > 1/3 || breaks[1] < 0 || tail(breaks, 1) != 1) {
    stop("Invalid explicit confidence-bin edges")
  }
  diagnostic <- DcAccuracyDiagnostic(probabilities, labels)
  confidence <- probabilities |>
    dplyr::group_by(fixture_id, model) |>
    dplyr::summarise(p1 = max(probability),
      p12 = sum(sort(probability, decreasing = TRUE)[1:2]), .groups = "drop")
  fixtures <- diagnostic$scores |>
    dplyr::left_join(confidence, by = c("fixture_id", "model"), relationship = "one-to-one") |>
    dplyr::mutate(bin = as.integer(cut(p1, breaks = breaks,
      right = FALSE, include.lowest = TRUE)))
  stopifnot(!anyNA(fixtures$bin))
  counts <- fixtures |> dplyr::group_by(model, bin) |>
    dplyr::summarise(n = dplyr::n(), hits1 = sum(top1), hits2 = sum(top2),
      mean_p1 = mean(p1), hit_rate = mean(top1), mean_p12 = mean(p12),
      top2_rate = mean(top2), rank2_rate = mean(actual_rank == 2L),
      rank3_rate = mean(actual_rank == 3L), .groups = "drop")
  bins <- tidyr::expand_grid(model = unique(fixtures$model), bin = seq_len(length(breaks) - 1L)) |>
    dplyr::left_join(counts, by = c("model", "bin"), relationship = "one-to-one") |>
    dplyr::mutate(lower = breaks[bin], upper = breaks[bin + 1L],
      dplyr::across(c(n, hits1, hits2), ~tidyr::replace_na(.x, 0L)),
      calibration_gap = hit_rate - mean_p1,
      top2_calibration_gap = top2_rate - mean_p12)
  summary <- fixtures |> dplyr::group_by(model) |>
    dplyr::summarise(n = dplyr::n(), hits1 = sum(top1), hits2 = sum(top2),
      mean_p1 = mean(p1), hit_rate = mean(top1), mean_p12 = mean(p12),
      top2_rate = mean(top2), calibration_gap = mean(top1) - mean(p1),
      hit_confidence = if (any(top1)) mean(p1[top1]) else NA_real_,
      miss_confidence = if (any(!top1)) mean(p1[!top1]) else NA_real_,
      confidence_hit_correlation = if (stats::sd(p1) > 0 && dplyr::n_distinct(top1) == 2L)
        stats::cor(p1, as.double(top1)) else NA_real_, .groups = "drop")
  list(fixtures = fixtures, bins = bins, summary = summary)
}
