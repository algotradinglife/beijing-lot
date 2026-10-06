#' Allocate surplus fixture categories to a fixed target structure
#'
#' Deterministic greedy allocation, without fitting or labels. For each deficit
#' role in order 3, 2, 1, move fixtures only from roles with surplus supply.
#' Minimize role distance, then maximize primary coverage gain, then fixture ID.
#' This minimizes the number of transfers, not a global portfolio objective.
#'
#' @param matches Validated fixture tibble with unique character fixture_id and
#'   numeric win/draw/lose probabilities. Extra source columns are not scored.
#' @param cutoff Explicit cutoff validated by match_require_cutoff.
#' @param pattern Nonempty plain numeric vector of whole roles 1:3.
#' @param single_threshold Fixed classifier threshold, default 0.50.
#' @param role_minimums Optional three-element whole nonnegative vector of
#'   required fixture counts for roles 1, 2 and 3, bound in the receipt.
#' @return List with cutoff, sorted integer pattern, threshold, source and
#'   implementation hashes, status and tibble ledger. Ledger is one row per
#'   fixture: native_role/allocated_role integers, coverage_before/after and gain
#'   probability units. Coverage sums original primary TopN probabilities.
#'   Insufficient fixtures leave all roles unchanged; empty input has a typed
#'   empty ledger. Invalid inputs error. No IO or input mutation.
#' @noRd
AdaptiveRoleAllocation <- function(matches, cutoff, pattern, single_threshold = 0.50, role_minimums = NULL) {
  match_require_cutoff(cutoff)
  if (!is.numeric(pattern) || is.object(pattern) || !is.null(dim(pattern)) ||
      !length(pattern) || anyNA(pattern) || any(!is.finite(pattern)) ||
      any(pattern != trunc(pattern)) || any(!pattern %in% 1:3)) {
    stop("pattern must be a nonempty plain numeric vector of whole roles 1:3", call. = FALSE)
  }
  if (!is.null(role_minimums) && (!is.numeric(role_minimums) || is.object(role_minimums) ||
      !is.null(dim(role_minimums)) || length(role_minimums) != 3L || anyNA(role_minimums) ||
      any(!is.finite(role_minimums)) || any(role_minimums < 0) ||
      any(role_minimums != trunc(role_minimums)))) {
    stop("role_minimums must be three nonnegative whole numbers", call. = FALSE)
  }
  native <- prepare_outcome_selections(matches, single_threshold)
  source <- matches[, c("fixture_id", "win", "draw", "lose"), drop = FALSE] |>
    dplyr::arrange(.data$fixture_id)
  # Strip carried receipts: source identity is the canonical required columns.
  source <- tibble::tibble(fixture_id = source$fixture_id, win = source$win,
                           draw = source$draw, lose = source$lose)
  first <- native[!duplicated(native$fixture_id), c("fixture_id", "base_role")]
  native_role <- first$base_role[match(source$fixture_id, first$fixture_id)]
  n <- nrow(source)
  coverages <- matrix(0, nrow = n, ncol = 3L)
  for (i in seq_len(n)) {
    p <- c(source$win[[i]], source$draw[[i]], source$lose[[i]])
    coverages[i, ] <- cumsum(p[order(-p, seq_along(p))])
  }
  allocated <- as.integer(native_role)
  demand <- tabulate(as.integer(pattern), nbins = 3L)
  if (!is.null(role_minimums)) demand <- pmax(demand, role_minimums)
  status <- if (n < sum(demand)) "insufficient_fixtures" else "allocated"
  if (status == "allocated") {
    counts <- tabulate(allocated, nbins = 3L)
    for (target in 3:1) {
      while (counts[[target]] < demand[[target]]) {
        eligible <- which(counts[allocated] > demand[allocated])
        if (!length(eligible)) stop("allocation has no surplus donor", call. = FALSE)
        gain <- coverages[eligible, target] -
          coverages[cbind(eligible, allocated[eligible])]
        choice <- eligible[order(abs(allocated[eligible] - target), -gain,
                                  source$fixture_id[eligible], method = "radix")[[1L]]]
        donor <- allocated[[choice]]
        allocated[[choice]] <- as.integer(target)
        counts[[donor]] <- counts[[donor]] - 1L
        counts[[target]] <- counts[[target]] + 1L
      }
    }
  }
  before <- as.double(coverages[cbind(seq_len(n), native_role)])
  after <- as.double(coverages[cbind(seq_len(n), allocated)])
  ledger <- tibble::tibble(fixture_id = source$fixture_id,
    native_role = as.integer(native_role), allocated_role = allocated,
    coverage_before = before, coverage_after = after, gain = after - before)
  return(list(cutoff = cutoff, cutoff_hash = .rank_outcome_cutoff_hash(cutoff),
    pattern = sort(as.integer(pattern), decreasing = TRUE),
    role_minimums = role_minimums, single_threshold = single_threshold, input_hash = rlang::hash(source),
    code_hash = .rank_outcome_code_hash("AdaptiveRoleAllocation"),
    status = status, ledger = ledger))
}
