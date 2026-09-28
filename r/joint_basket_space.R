# Rank the complete 3^7 outcome space of a 7-leg ticket.
#
# For one bundle of seven fixtures, every one of the 3^7 = 2187 outcome
# combinations has a joint model probability P(c) = prod_i q_i(o_i) and a
# joint parlay price SP(c) = prod_i SP_i(o_i). Ranking by the two together
# gives the expected return of a single 2-CNY unit placed on that combination:
#
#     EV(c) = P(c) * SP(c) * 0.65
#
# This is the quantity a budget of 1024 CNY (512 units) has to spend. With
# fewer units than combinations, only the top of the ranking can be funded and
# the tail is skipped outright -- which is exactly how dropping a leg's second
# or third outcome appears on the probability curve.
suppressMessages({library(dplyr); library(tibble); library(tidyr)})

# Enumerate the full outcome space of one 7-fixture bundle.
#
# `bundle` must carry, per leg, the model probabilities qW/qD/qL, the prices
# spW/spD/spL, and the realised direction `dirn`. Returns one row per outcome
# combination with its joint probability, joint price, expected return, and
# whether it is the combination that actually occurred.
jc_full_space <- function(bundle) {
  if (nrow(bundle) != 7L) stop('jc_full_space: a bundle must have exactly 7 legs')
  needed <- c('qW','qD','qL','spW','spD','spL','dirn')
  missing <- setdiff(needed, names(bundle))
  if (length(missing)) stop('jc_full_space: missing columns: ', paste(missing, collapse=', '))
  # one square grid per leg, then the Cartesian product across the seven legs
  per_leg <- lapply(seq_len(7L), function(i) {
    tibble(
      leg = i,
      outcome = c('W', 'D', 'L'),
      q = c(bundle$qW[[i]], bundle$qD[[i]], bundle$qL[[i]]),
      sp = c(bundle$spW[[i]], bundle$spD[[i]], bundle$spL[[i]]))
  })
  grid <- expand.grid(leg = seq_len(7L), outcome = c('W', 'D', 'L'),
                      KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
  grid$q <- do.call(c, lapply(per_leg, function(x) x$q))
  grid$sp <- do.call(c, lapply(per_leg, function(x) x$sp))
  # reshape to one row per combination: 2187 rows x 7 outcome columns
  idx <- expand.grid(rep(list(seq_len(3L)), 7L), KEEP.OUT.ATTRS = FALSE)
  qmat <- vapply(seq_len(7L), function(i) per_leg[[i]]$q[idx[[i]]], numeric(nrow(idx)))
  spmat <- vapply(seq_len(7L), function(i) per_leg[[i]]$sp[idx[[i]]], numeric(nrow(idx)))
  code <- vapply(seq_len(7L), function(i) c('W','D','L')[idx[[i]]], character(nrow(idx)))
  code <- matrix(code, nrow = nrow(idx), ncol = 7L)
  prob <- apply(qmat, 1, prod)
  price <- apply(spmat, 1, prod)
  is_actual <- apply(code, 1, function(r) all(r == bundle$dirn))
  tibble(
    combo = apply(code, 1, paste0, collapse = ''),
    prob = prob,
    price = price,
    ev = prob * price * 0.65,
    is_actual = is_actual)
}

