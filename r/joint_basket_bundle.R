# Multi-bundle N=7 ticket construction and settlement under an explicit budget.
#
# Three independent degrees of freedom, all inside a fixed per-issue stake:
#   1. how many 7-fixture bundles the issue funds
#   2. how many units each bundle receives
#   3. how many outcomes each leg covers, and WHICH ones
#
# A ticket is (bundle, outcome tuple). The bundle's basic combinations are the
# Cartesian product of its legs' support sets. Units are spread across those
# combinations. Settlement pays every combination whose tuple equals the real
# result, once, at the product of the winning leg SPs.
suppressMessages({library(dplyr); library(tibble); library(tidyr)})

# Split an issue's analysable fixtures into disjoint 7-fixture bundles.
# `order_key` decides which bundles exist; every fixture is used at most once.
jc_bundles_disjoint <- function(d, n_bundles) {
  if (n_bundles < 1L) stop('jc_bundles_disjoint: n_bundles must be positive')
  usable <- d |> arrange(desc(.data$rank_key), .data$slot)
  need <- 7L * n_bundles
  if (nrow(usable) < need) return(NULL)
  usable <- usable[seq_len(need), ]
  usable$bundle <- rep(seq_len(n_bundles), each = 7L)
  usable
}

# Support set for one leg: the top-m outcomes by q, with m in 1..3.
jc_leg_support <- function(qW, qD, qL, m) {
  q <- c(W = qW, D = qD, L = qL)
  if (length(m) != 1L || is.na(m) || m < 1L || m > 3L) stop('jc_leg_support: m must be 1, 2 or 3')
  names(sort(q, decreasing = TRUE))[seq_len(m)]
}

# Settle one bundle: enumerate its basic combinations, spread `units` over them,
# and pay the ones that match the realised direction vector.
jc_settle_bundle <- function(bundle, m_top, units, sp_cols = c('spW','spD','spL')) {
  if (nrow(bundle) != 7L) stop('jc_settle_bundle: a bundle must have exactly 7 legs')
  if (units < 1L) stop('jc_settle_bundle: units must be a positive integer')
  supports <- lapply(seq_len(7L), function(i) {
    jc_leg_support(bundle$qW[i], bundle$qD[i], bundle$qL[i], m_top[i])
  })
  combos <- expand.grid(supports, KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
  n_combo <- nrow(combos)
  per <- units %/% n_combo
  if (per < 1L) return(list(combos = combos, n_combo = n_combo, units_each = 0L,
                            stake_cny = 0, gross_cny = 0, hit_combos = 0L))
  base <- rep(per, n_combo)
  leftover <- units - per * n_combo
  if (leftover > 0L) base[seq_len(leftover)] <- base[seq_len(leftover)] + 1L
  # a combination wins if every leg's chosen outcome equals the realised one
  win <- rep(TRUE, n_combo)
  for (i in seq_len(7L)) {
    win <- win & (combos[[i]] == bundle$dirn[i])
  }
  n_win <- sum(win)
  sp_prod <- if (n_win > 0L) prod(bundle$sp_pick) else NA_real_
  gross <- if (n_win > 0L) sum(base[win]) * 2 * 0.65 * sp_prod else 0
  list(combos = combos, n_combo = n_combo, units_each = per,
       stake_cny = sum(base) * 2, gross_cny = gross, hit_combos = n_win)
}

# Plain-English contract for the analysable fixture table this module consumes.
jc_required_columns <- function() {
  c('issue','slot','qW','qD','qL','spW','spD','spL','dirn','eW','eD','eL','e_pick','sp_pick')
}
# Validate the fixture table once at the boundary; fail closed on any gap.
jc_validate_fixtures <- function(d) {
  missing <- setdiff(jc_required_columns(), names(d))
  if (length(missing)) stop('jc_validate_fixtures: missing columns: ', paste(missing, collapse = ', '))
  if (anyNA(d$dirn) || any(!d$dirn %in% c('W','D','L'))) stop('jc_validate_fixtures: dirn must be W/D/L')
  d
}
# Choose one leg's outcome set by probability order, then optionally extend the
# pick beyond the model's own top choice using the third outcome.
#
# `m_top` gives the number of outcomes to cover on each leg. `rule` picks the
# ranking basis: 'prob' ranks by model probability, 'edge' ranks by e = q * SP.
# Returned outcome codes are the bare letters W/D/L. Source columns may carry
# leftover names from an earlier named-vector sort, so every score is rebuilt
# as a freshly named numeric of length three before ranking.
jc_support_from_prob <- function(bundle, m_top, rule) {
  if (!is.character(rule) || length(rule) != 1L || !rule %in% c('prob', 'edge')) {
    stop("jc_support_from_prob: rule must be 'prob' or 'edge'")
  }
  if (length(m_top) != 7L || any(is.na(m_top)) || any(m_top < 1L) || any(m_top > 3L)) {
    stop('jc_support_from_prob: m_top must give 7 values in 1..3')
  }
  lapply(seq_len(7L), function(i) {
    if (rule == 'prob') {
      raw <- c(bundle$qW[[i]], bundle$qD[[i]], bundle$qL[[i]])
    } else {
      raw <- c(bundle$eW[[i]], bundle$eD[[i]], bundle$eL[[i]])
    }
    score <- stats::setNames(as.numeric(raw), c('W', 'D', 'L'))
    unname(names(sort(score, decreasing = TRUE))[seq_len(m_top[i])])
  })
}

