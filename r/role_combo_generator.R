# Generate balanced seven-fixture candidate structures before outcome ranking.
# `fixtures` is prediction-only and must contain one row per fixture.

generate_role_combinations <- function(fixtures, max_candidates = 5000L,
                                       seed = 1L) {
  stopifnot(is.data.frame(fixtures), all(c("fixture_id", "role") %in% names(fixtures)),
    !anyDuplicated(fixtures$fixture_id), all(fixtures$role %in% c("主力", "机会", "排除")),
    max_candidates >= 1, max_candidates == floor(max_candidates),
    seed >= 0, seed == floor(seed))
  main <- fixtures$fixture_id[fixtures$role == "主力"]
  opp <- fixtures$fixture_id[fixtures$role == "机会"]
  make <- function(n_main, n_opp, label) {
    if (length(main) < n_main || length(opp) < n_opp) return(list())
    a <- utils::combn(main, n_main, simplify = FALSE)
    b <- utils::combn(opp, n_opp, simplify = FALSE)
    out <- lapply(seq_along(a), function(i) {
      lapply(seq_along(b), function(j) {
        z <- c(a[[i]], b[[j]])
        data.frame(combo_id = paste0(label, "-", paste(sort(z), collapse = "_")),
          main_count = n_main, opportunity_count = n_opp,
          fixtures = paste(sort(z), collapse = ","), stringsAsFactors = FALSE)
      })
    })
    do.call(rbind, unlist(out, recursive = FALSE))
  }
  ans <- do.call(rbind, list(make(6L, 1L, "M6O1"), make(5L, 2L, "M5O2")))
  if (is.null(ans) || !nrow(ans)) return(data.frame(combo_id=character(), main_count=integer(), opportunity_count=integer(), fixtures=character()))
  ans <- ans[!duplicated(ans$combo_id), , drop = FALSE]
  if (nrow(ans) > max_candidates) {
    ans <- ans[sample.int(nrow(ans), max_candidates, replace = FALSE), , drop = FALSE]
  }
  ans[order(ans$main_count, ans$opportunity_count, ans$combo_id), , drop = FALSE]
}

attach_combo_metrics <- function(combos, metrics) {
  stopifnot(is.data.frame(combos), is.data.frame(metrics),
    "combo_id" %in% names(combos), "combo_id" %in% names(metrics),
    !anyDuplicated(metrics$combo_id))
  dplyr::left_join(combos, metrics, by = "combo_id", relationship = "one-to-one")
}
