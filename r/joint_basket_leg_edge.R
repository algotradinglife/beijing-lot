# Per-leg decomposition of a ticket-level payout factor applied to N-leg baskets.
#
# The frozen audit applies the 0.65 payout factor ONCE per ticket. For an N-leg
# ticket that is equivalent to a per-leg factor of 0.65^(1/N), so a basket ROI
# converts to a per-leg gross edge e by e = ((1 + ROI) / payout_factor)^(1 / n).
# Break-even is e = (1 / payout_factor)^(1 / n).

# Gross multiplier implied by a realised return: (1 + roi) / payout_factor.
jb_leg_edge_gross <- function(roi, payout_factor = 0.65) {
  if (anyNA(roi)) stop('jb_leg_edge_gross: roi must be non-missing')
  if (length(payout_factor) != 1L || is.na(payout_factor) || payout_factor <= 0) {
    stop('jb_leg_edge_gross: payout_factor must be a single positive value')
  }
  if (any(roi <= -1)) stop('jb_leg_edge_gross: roi must be > -1')
  (1 + roi) / payout_factor
}

# Per-leg break-even gross edge for an n-leg ticket.
jb_leg_edge_breakeven <- function(n, payout_factor = 0.65) {
  if (length(n) != 1L || is.na(n) || n < 1L) stop('jb_leg_edge_breakeven: n must be >= 1')
  if (length(payout_factor) != 1L || is.na(payout_factor) || payout_factor <= 0) {
    stop('jb_leg_edge_breakeven: payout_factor must be a single positive value')
  }
  (1 / payout_factor)^(1 / n)
}

# Convert a realised basket return to its per-leg gross edge.
jb_leg_edge_from_roi <- function(roi, n, payout_factor = 0.65) {
  jb_leg_edge_gross(roi, payout_factor)^(1 / n)
}

# Margin of a per-leg edge over break-even, as a fraction.
jb_leg_edge_margin <- function(edge, n, payout_factor = 0.65) {
  be <- jb_leg_edge_breakeven(n, payout_factor)
  edge / be - 1
}

