#' Build FM-1.6.0 symmetric margin-core targets
#' @param base List with normalized score-grid tibble and explicit cutoff.
#' @param review List decision (apply/retain), grid base_hash, ISO UTC cutoff_utc,
#'   nonempty reason and counterevidence; independent evidence, not ticket roles.
#' @param evidence_id Nonempty admitted evidence ID for all bins.
#' @param cutoff Explicit issue/time object identical to base and review;
#'   may be omitted to use the explicitly passed base$cutoff.
#' @param policy List max_radius (integer 0..2), threshold (0..1), coefficient
#'   (positive <=1), tie_tolerance (nonnegative), dual_gap (NULL or 0..1).
#'   FM16 retains 2/.1/.3/1e-12; dual_gap is an explicit expert policy.
#' @export
#' @return List judgement for adjust_score_margin_distribution(), branch,
#'   center, radius, core_margins, shell tibble, masses and identity binding.
#' @details Pure targets only: no fitting, fetching, writes or ticket handicap.
#' Review center_mode is single/dual/auto; dual uses adjacent top-two margins.
#' Explicit dual centers must be the unambiguous adjacent top pair. Auto requires
#' an explicit dual_gap (absolute probability difference); no default is learned.
#' Centers are frozen before weighting. Extend interval shells while
#' either side meets threshold; stop at first failed shell. Unresolved ties or explicit
#' retain decision preserve the original distribution. Missing support is zero.
#' Shared evidence admission and actual score reweighting use existing APIs.
BuildFmTailJudgement <- function(base, review, evidence_id, cutoff = base$cutoff, policy) {
  match_require_cutoff(cutoff)
  match_require_cutoff(base$cutoff)
  if (!identical(base$cutoff, cutoff)) stop("Base cutoff differs")
  if (any(c("handicap", "beidan_handicap", "roles") %in% names(base)) ||
      any(c("handicap", "beidan_handicap", "roles") %in% names(review))) {
    stop("Ticket roles or line cannot govern core selection")
  }
  g <- base$grid
  checkmate::assert_tibble(g, min.rows = 1L)
  checkmate::assert_names(names(g), identical.to = c("home_goals", "away_goals", "probability"))
  for (k in c("home_goals", "away_goals")) checkmate::assert_integerish(g[[k]], lower = 0, any.missing = FALSE)
  checkmate::assert_numeric(g$probability, lower = 0, upper = 1, finite = TRUE, any.missing = FALSE)
  if (anyDuplicated(g[c("home_goals", "away_goals")]) || abs(sum(g$probability) - 1) > 1e-12) stop("Unique normalized score grid required")
  checkmate::assert_list(review)
  checkmate::assert_choice(review$decision, c("apply", "retain"))
  for (k in c("base_hash", "cutoff_utc", "reason", "counterevidence")) checkmate::assert_character(review[[k]], len = 1L, min.chars = 1L, any.missing = FALSE)
  if (!identical(review$base_hash, .score_margin_hash(g))) stop("Review grid binding differs")
  if (!grepl("Z$", review$cutoff_utc)) stop("Review UTC cutoff required")
  rt <- suppressWarnings(lubridate::ymd_hms(review$cutoff_utc, tz = "UTC", quiet = TRUE))
  if (is.na(rt) || as.numeric(rt) != as.numeric(cutoff$cutoff_utc)) stop("Review cutoff differs")
  checkmate::assert_character(evidence_id, len = 1L, min.chars = 1L, any.missing = FALSE)
  checkmate::assert_list(policy)
  checkmate::assert_names(names(policy), identical.to = c("max_radius", "threshold", "coefficient", "tie_tolerance", "dual_gap"))
  checkmate::assert_int(policy$max_radius, lower = 0L, upper = 2L)
  checkmate::assert_number(policy$threshold, lower = 0, upper = 1, finite = TRUE)
  checkmate::assert_number(policy$coefficient, lower = .Machine$double.eps, upper = 1, finite = TRUE)
  checkmate::assert_number(policy$tie_tolerance, lower = 0, upper = 1e-6, finite = TRUE)
  checkmate::assert_choice(review$center_mode, c("single", "dual", "auto"))
  if (!is.null(policy$dual_gap)) checkmate::assert_number(policy$dual_gap, lower = 0, upper = 1, finite = TRUE)
  if (review$center_mode == "auto" && is.null(policy$dual_gap)) stop("Auto center requires explicit dual_gap")
  m <- g |> dplyr::mutate(margin = home_goals - away_goals) |>
    dplyr::group_by(margin) |> dplyr::summarise(probability = sum(probability), .groups = "drop") |>
    dplyr::arrange(dplyr::desc(probability), margin)
  modes <- m$margin[max(m$probability) - m$probability <= policy$tie_tolerance]
  centers <- if (length(modes) == 1L) as.integer(modes) else integer()
  pair <- integer(); gap <- NA_real_
  if (nrow(m) >= 2L) {
    top_pair <- m$margin[m$probability >= m$probability[2L] - policy$tie_tolerance]
    if (length(top_pair) == 2L && abs(diff(top_pair)) == 1L) {
      pair <- sort(as.integer(top_pair)); gap <- m$probability[1L] - m$probability[2L]
    }
  }
  if (review$center_mode == "dual") {
    checkmate::assert_integerish(review$centers, len = 2L, any.missing = FALSE)
    if (!length(pair) || !identical(sort(as.integer(review$centers)), pair)) stop("Dual centers require unambiguous adjacent top-two margins")
    centers <- pair
  } else if (review$center_mode == "auto" && length(pair) && gap <= policy$dual_gap + policy$tie_tolerance) {
    centers <- pair
  }
  center <- if (length(centers) == 1L) centers else NA_integer_
  radius <- NA_integer_; core <- integer()
  shells <- tibble::tibble(distance = integer(), left_probability = double(), right_probability = double(), accepted = logical())
  branch <- if (review$decision == "retain") "retained_review" else if (!length(centers)) "retained_mode_tie" else if (length(centers) == 2L) "dual_center_tail" else "single_center_tail"
  reason <- paste(review$reason, "Counterevidence:", review$counterevidence)
  bins <- tibble::tibble(bin_id = "retained", min_margin = -Inf, max_margin = Inf, target_mass = 1, evidence_id = evidence_id, reason = reason)
  normalizer <- 1; core_mass <- NA_real_; final_core_mass <- NA_real_
  if (branch %in% c("single_center_tail", "dual_center_tail")) {
    radius <- 0L
    for (distance in seq_len(policy$max_radius)) {
      left <- sum(m$probability[m$margin == min(centers) - distance])
      right <- sum(m$probability[m$margin == max(centers) + distance])
      accepted <- max(left, right) >= policy$threshold
      shells <- dplyr::bind_rows(shells, tibble::tibble(distance = distance, left_probability = left, right_probability = right, accepted = accepted))
      if (!accepted) break
      radius <- distance
    }
    core <- seq.int(min(centers) - radius, max(centers) + radius)
    core_mass <- sum(m$probability[m$margin %in% core])
    weighted <- m$probability * ifelse(m$margin %in% core, 1, policy$coefficient)
    normalizer <- sum(weighted)
    final_core_mass <- core_mass / normalizer
    full <- tibble::tibble(margin = seq.int(min(m$margin), max(m$margin))) |>
      dplyr::left_join(m, by = "margin", relationship = "one-to-one") |>
      dplyr::mutate(probability = dplyr::coalesce(probability, 0))
    bins <- full |> dplyr::transmute(bin_id = paste0("margin_", margin),
      min_margin = as.numeric(margin), max_margin = as.numeric(margin),
      target_mass = probability * ifelse(margin %in% core, 1, policy$coefficient) / normalizer,
      evidence_id = .env$evidence_id, reason = .env$reason)
    bins <- dplyr::bind_rows(bins, tibble::tibble(bin_id = c("lower_outer", "upper_outer"),
      min_margin = c(-Inf, max(full$margin) + 1), max_margin = c(min(full$margin) - 1, Inf),
      target_mass = 0, evidence_id = evidence_id, reason = reason)) |> dplyr::arrange(min_margin)
  }
  judgement <- list(model_id = "FM-1.6.0", rationale = paste(branch, reason), bins = bins)
  return(list(judgement = judgement, branch = branch, center = center, centers = centers, radius = radius,
    core_margins = core, shells = shells, core_mass = core_mass,
    final_core_mass = final_core_mass, normalizer = normalizer, policy = policy,
    binding_hash = .score_margin_hash(list(base_identity = .score_margin_hash(base),
      review = review, evidence_id = evidence_id, cutoff = cutoff, policy = policy,
      judgement = judgement, implementation = paste(deparse(BuildFmTailJudgement), collapse = "\n")))))
}
