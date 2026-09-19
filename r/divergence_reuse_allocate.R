# Divergence-aware, label-free allocation for historical diagnosis.
# This module only ranks/funds an already frozen option pool; it never changes
# probabilities, reads settlement labels, or fits a model.

divergence_reuse_features <- function(pool, line_features, gap_mid = 0.05,
                                       gap_high = 0.10, degree_mid = 0.5,
                                       degree_high = 1) {
  stopifnot(is.list(pool), is.data.frame(line_features),
    all(c("issue", "slot", "provider_id", "degree") %in% names(line_features)),
    gap_mid >= 0, gap_high >= gap_mid, degree_mid >= 0,
    degree_high >= degree_mid)
  fx <- pool$fixtures
  rows <- lapply(seq_along(fx), function(i) {
    f <- fx[[i]]
    hit <- line_features[line_features$issue == f$issue &
      line_features$slot == f$slot & line_features$provider_id == f$provider_id, , drop = FALSE]
    stopifnot(nrow(hit) == 1)
    p <- sort(c(f$p_W, f$p_D, f$p_L), decreasing = TRUE)
    gap <- p[2] - p[3]
    degree <- abs(as.numeric(hit$degree[[1]]))
    category <- if (degree >= degree_high && gap >= gap_high) "HIGH" else
      if (degree >= degree_mid || gap >= gap_mid) "MEDIUM" else "LOW"
    tibble::tibble(issue = f$issue, slot = f$slot, provider_id = f$provider_id,
      fixture_index = i, degree = degree, top2_gap = gap, confidence = mean(c(degree / max(degree_high, 1), gap / max(gap_high, 1))),
      category = category)
  })
  dplyr::bind_rows(rows)
}

divergence_reuse_allocate <- function(pool, scenarios, evidence,
                                      cutoffs, budget_cny = 1024,
                                      unit_cny = 2, cap_high = 4,
                                      cap_medium = 2, cap_low = 1,
                                      third_min_expected_return = 0) {
  stopifnot(identical(pool$cutoffs, cutoffs), identical(scenarios$cutoffs, cutoffs),
    budget_cny > 0, budget_cny %% unit_cny == 0, unit_cny == 2,
    all(c("fixture_index", "confidence", "category") %in% names(evidence)))
  opts <- pool$options
  n <- length(opts); stopifnot(ncol(scenarios$hits) == n)
  caps <- c(HIGH = cap_high, MEDIUM = cap_medium, LOW = cap_low)
  stopifnot(all(caps >= 1), all(is.finite(caps)))
  cap_by_fixture <- caps[as.character(evidence$category)]
  group_score <- vapply(opts, function(o) {
    idx <- as.integer(o$fixtures)
    mean(evidence$confidence[match(idx, evidence$fixture_index)])
  }, numeric(1))
  expected <- vapply(opts, function(o) o$expected_gross, numeric(1))
  stake <- vapply(opts, function(o) o$stake, numeric(1))
  ids <- vapply(opts, function(o) as.character(o$sleeve_id), character(1))
  third_by_fixture <- vapply(pool$fixtures, function(f) {
    order(c(f$p_W, f$p_D, f$p_L), decreasing = TRUE)[3] - 1L
  }, integer(1))
  contains_third <- vapply(opts, function(o) {
    state <- as.integer(o$state_ids) - 1L
    digits <- t(vapply(state, function(s) (s %/% (3^(6:0))) %% 3L, integer(7)))
    any(digits[, as.integer(o$fixtures), drop = FALSE] ==
      matrix(third_by_fixture[as.integer(o$fixtures)], nrow = nrow(digits),
        ncol = length(o$fixtures), byrow = TRUE))
  }, logical(1))
  selected <- integer(); used <- integer(0); usage <- integer(nrow(evidence)); cash <- budget_cny
  actions <- list()
  repeat {
    cand <- which(!(seq_along(opts) %in% selected) & !(ids %in% used) & stake <= cash)
    cand <- cand[vapply(cand, function(j) {
      idx <- match(as.integer(opts[[j]]$fixtures), evidence$fixture_index)
      all(usage[idx] + 1 <= cap_by_fixture[idx])
    }, logical(1))]
    if (!length(cand)) break
    current <- if (length(selected)) rowSums(scenarios$hits[, selected, drop = FALSE]) > 0 else rep(FALSE, nrow(scenarios$hits))
    gain <- vapply(cand, function(j) mean(current | scenarios$hits[, j]) - mean(current), numeric(1))
    value <- expected[cand] / stake[cand]
    # A third option is admitted only when its incremental expected return
    # clears the caller's explicit diversification cost threshold.
    keep <- !contains_third[cand] | value >= third_min_expected_return
    cand <- cand[keep]; gain <- gain[keep]; value <- value[keep]
    if (!length(cand)) break
    ord <- order(-gain / stake[cand], -value, -group_score[cand], ids[cand])
    j <- cand[ord[1]]; idx <- match(as.integer(opts[[j]]$fixtures), evidence$fixture_index)
    selected <- c(selected, j); used <- c(used, ids[j]); usage[idx] <- usage[idx] + 1
    actions[[length(actions) + 1L]] <- tibble::tibble(step = length(selected), option = j,
      sleeve_id = ids[j], stake = stake[j], confidence = group_score[j],
      category = paste(sort(unique(evidence$category[idx])), collapse = "+"),
      marginal_hit = gain[ord[1]], cash_after = cash - stake[j])
    cash <- cash - stake[j]
  }
  list(selected = selected, metrics = n7_capital_evaluate(pool, selected, scenarios, cutoffs, budget_cny),
    actions = dplyr::bind_rows(actions), cash = cash, usage = usage,
    caps = caps, cutoffs = cutoffs)
}
