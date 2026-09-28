# Layered selection for an N=7 ticket: fixtures first, then leg depth, then combos.
#
# The owner's framing: a 7-fixture bundle mixes HIGH-certainty fixtures (which
# carry the joint probability and absorb the 0.65 fee) with LOW-certainty
# fixtures (which lift the parlay price). High-certainty legs need only their
# top-1 or top-2 outcome, because keeping top-1 already retains most of that
# leg's probability mass; truncating them collapses the combination space and
# concentrates the budget on the region most likely to actually occur.
#
# Three explicit layers, in order:
#   1. jt_pick_fixtures  -- h high-certainty + (7-h) low-certainty fixtures
#   2. jt_leg_shape      -- how many outcomes each leg keeps
#   3. jt_fund           -- rank the resulting combinations and spend the units
suppressMessages({library(dplyr); library(tibble); library(tidyr)})

# Layer 1: split an issue's fixtures into high- and low-certainty groups.
#
# `cert` is each fixture's largest model probability. A bundle takes `n_high`
# from the most certain end and 7 - n_high from the least certain end, so both
# roles are filled deliberately rather than by accident.
jt_pick_fixtures <- function(d, n_high, offset = 0L) {
  if (n_high < 0L || n_high > 7L) stop('jt_pick_fixtures: n_high must be in 0..7')
  if (nrow(d) < 7L) return(NULL)
  ord_hi <- order(-d$cert, d$slot)
  ord_lo <- order(d$cert, d$slot)
  n_low <- 7L - n_high
  hi <- d[ord_hi, , drop = FALSE]
  lo <- d[ord_lo, , drop = FALSE]
  # `offset` lets successive bundles take successive slices of each end
  hi_take <- hi[seq_len(min(nrow(hi), n_high + offset)), , drop = FALSE]
  hi_take <- hi_take[seq_len(n_high) + min(offset, max(0L, nrow(hi_take) - n_high)), , drop = FALSE]
  lo_take <- lo[seq_len(min(nrow(lo), n_low + offset)), , drop = FALSE]
  lo_take <- lo_take[seq_len(n_low) + min(offset, max(0L, nrow(lo_take) - n_low)), , drop = FALSE]
  out <- bind_rows(hi_take, lo_take)
  if (nrow(out) != 7L) return(NULL)
  out$role <- c(rep('high', nrow(hi_take)), rep('low', nrow(lo_take)))
  out
}

# Layer 2: how many outcomes each leg keeps.
#
# High-certainty legs are truncated to `hi_depth` (1 or 2); low-certainty legs
# keep all three so the price upside is not thrown away. Returns one integer per
# leg, in the row order of the bundle.
jt_leg_shape <- function(bundle, hi_depth = 1L, lo_depth = 3L) {
  if (!hi_depth %in% c(1L, 2L)) stop('jt_leg_shape: hi_depth must be 1 or 2')
  if (!lo_depth %in% c(1L, 2L, 3L)) stop('jt_leg_shape: lo_depth must be 1, 2 or 3')
  ifelse(bundle$role == 'high', hi_depth, lo_depth)
}

# Layer 3: enumerate the truncated space, rank it, and spend `units`.
#
# Unlike the full 3^7 space, the truncated space is small enough that every
# combination can receive at least one unit, so the budget is spent in full
# rather than truncated at a cut line. Ranking still follows `key`.
jt_fund <- function(bundle, shape, units, key = 'ev') {
  if (length(shape) != 7L) stop('jt_fund: shape must give 7 values')
  if (!key %in% c('ev', 'prob')) stop("jt_fund: key must be 'ev' or 'prob'")
  sup <- lapply(seq_len(7L), function(i) {
    sc <- stats::setNames(c(bundle$qW[[i]], bundle$qD[[i]], bundle$qL[[i]]), c('W','D','L'))
    unname(names(sort(sc, decreasing = TRUE))[seq_len(shape[i])])
  })
  idx <- expand.grid(rep(list(seq_len(3L)), 7L), KEEP.OUT.ATTRS = FALSE)
  cube <- vapply(seq_len(7L), function(i) c('W','D','L')[idx[[i]]], character(nrow(idx)))
  cube <- matrix(cube, nrow = nrow(idx))
  keep <- rep(TRUE, nrow(cube))
  for (i in seq_len(7L)) keep <- keep & (cube[, i] %in% sup[[i]])
  cube <- cube[keep, , drop = FALSE]
  # Coerce explicitly to a matrix: when the truncated space has a single row,
  # vapply returns a bare vector and the row-wise reductions below would fail.
  n_cube <- nrow(cube)
  q <- matrix(vapply(seq_len(7L), function(i) c(bundle$qW[[i]], bundle$qD[[i]], bundle$qL[[i]])[match(cube[,i], c('W','D','L'))], numeric(n_cube)), nrow = n_cube)
  sp <- matrix(vapply(seq_len(7L), function(i) c(bundle$spW[[i]], bundle$spD[[i]], bundle$spL[[i]])[match(cube[,i], c('W','D','L'))], numeric(n_cube)), nrow = n_cube)
  prob <- apply(q, 1, prod); price <- apply(sp, 1, prod)
  actual <- apply(cube, 1, function(r) all(r == bundle$dirn))
  tb <- tibble(combo = apply(cube, 1, paste0, collapse = ''),
               prob = prob, price = price, ev = prob*price*0.65, is_actual = actual) |>
    arrange(desc(.data[[key]]), .data$combo)
  n <- nrow(tb)
  per <- units %/% n; left <- units - per*n
  tb$units <- per; if (left > 0) tb$units[seq_len(left)] <- tb$units[seq_len(left)] + 1L
  tb <- tb |> filter(.data$units > 0)
  hit <- tb$is_actual
  list(funded = tb, n_space = n,
       stake_cny = sum(tb$units)*2,
       gross_cny = if (any(hit)) sum(tb$units[hit])*2*0.65*tb$price[hit] else 0,
       mass = sum(tb$prob), leg_mass = prod(vapply(seq_len(7L), function(i) {
         sc <- c(bundle$qW[[i]], bundle$qD[[i]], bundle$qL[[i]])
         sum(sort(sc, decreasing=TRUE)[seq_len(shape[i])]) }, numeric(1))))
}

