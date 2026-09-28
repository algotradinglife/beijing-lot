# Two-layer N=7 ticket engine under a fixed per-issue budget.
#
# LAYER 1 picks WHICH fixtures form each 7-leg bundle. LAYER 2 picks WHICH
# outcome combinations inside a bundle receive units. They are separate
# decisions and must not be conflated: a bundle is a set of seven fixtures,
# and its 3^7 outcome combinations are ranked only after the fixtures are set.
#
# Budget contract: an issue receives `issue_units` units of 2 CNY each. Those
# units are split across `n_bundles` bundles, then inside each bundle across the
# ranked combinations. Nothing is staked outside this budget.
suppressMessages({library(dplyr); library(tibble); library(tidyr)})
source('r/joint_basket_space.R')

# LAYER 1 -- partition an issue's fixtures into `n_bundles` disjoint 7-leg bundles.
#
# `d` is the analysable fixture table for ONE issue; `score` ranks fixtures for
# admission. Higher score is admitted first. Returns a table carrying a `bundle`
# column, or NULL when the issue cannot supply 7 * n_bundles distinct fixtures.
jb_bundles <- function(d, n_bundles, score) {
  if (length(n_bundles) != 1L || is.na(n_bundles) || n_bundles < 1L) {
    stop('jb_bundles: n_bundles must be a positive integer')
  }
  if (length(score) != nrow(d) || anyNA(score)) {
    stop('jb_bundles: score must give one finite value per fixture')
  }
  need <- 7L * n_bundles
  if (nrow(d) < need) return(NULL)
  ord <- order(-score, d$slot)
  picked <- d[ord[seq_len(need)], , drop = FALSE]
  picked$bundle <- rep(seq_len(n_bundles), each = 7L)
  picked
}

# LAYER 2 -- fund the top of a bundle's ranked combination space.
#
# Every one of the 3^7 combinations gets P(c) and SP(c) from jc_full_space. The
# ranking key is `key`; `floor_ev` optionally removes combinations whose
# expected return is below a stated floor BEFORE ranking, which is how a leg's
# second or third outcome gets excluded on the probability curve. Units are
# assigned one per combination from the top down, so a bundle with `units`
# units funds exactly its top `units` combinations, one unit each.
jb_fund_bundle <- function(bundle, units, key = 'ev', floor_ev = -Inf) {
  if (length(units) != 1L || is.na(units) || units < 1L) {
    stop('jb_fund_bundle: units must be a positive integer')
  }
  if (!key %in% c('ev', 'prob')) stop("jb_fund_bundle: key must be 'ev' or 'prob'")
  space <- jc_full_space(bundle)
  if (!is.finite(floor_ev)) floor_ev <- -Inf
  space <- space |> filter(.data$ev >= floor_ev)
  if (!nrow(space)) {
    return(list(funded = space[0, , drop = FALSE], units_used = 0L,
                stake_cny = 0, gross_cny = 0, n_combos_space = 0L))
  }
  ranked <- space |> arrange(desc(.data[[key]]), .data$combo)
  take <- min(units, nrow(ranked))
  funded <- ranked[seq_len(take), , drop = FALSE]
  funded$units <- 1L
  hit <- funded$is_actual
  gross <- if (any(hit)) sum(funded$units[hit]) * 2 * 0.65 * funded$price[hit] else 0
  list(funded = funded, units_used = take,
       stake_cny = take * 2, gross_cny = sum(gross), n_combos_space = nrow(space))
}

# Settle one whole issue: split the budget, run both layers, reconcile the stake.
jb_settle_issue <- function(d, n_bundles, issue_units, score, key = 'ev',
                            floor_ev = -Inf) {
  picked <- jb_bundles(d, n_bundles, score)
  if (is.null(picked)) return(NULL)
  per_bundle <- issue_units %/% n_bundles
  if (per_bundle < 1L) return(NULL)
  rows <- list()
  for (b in seq_len(n_bundles)) {
    one <- picked |> filter(.data$bundle == b)
    f <- jb_fund_bundle(one, per_bundle, key = key, floor_ev = floor_ev)
    rows[[length(rows) + 1L]] <- tibble(
      bundle = b, units = f$units_used, stake_cny = f$stake_cny,
      gross_cny = f$gross_cny, n_space = f$n_combos_space,
      coverage = if (nrow(f$funded)) sum(f$funded$prob) else 0)
  }
  res <- bind_rows(rows)
  res$issue_units <- issue_units
  res
}

