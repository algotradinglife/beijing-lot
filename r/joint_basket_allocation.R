# Ticket allocation analysis on a frozen 7-leg basket portfolio.
#
# Allocation moves the fixed per-issue ticket pool between the baskets of that
# same issue. It never changes which fixtures are played, so it is a pure
# within-issue stake transfer and its realised return can be measured against
# settlement without re-deriving the portfolio.
#
# Every function here is deterministic. `jb_alloc_*` build an allocation from
# EX-ANTE basket weights only. `jb_alloc_realised` is the measurement function:
# it takes settled outcomes, so it is an evaluation tool, never an input to
# selection.

# Allocation weights from a vector of ex-ante basket weights.
# `exponent` shapes the weight (0 = uniform). Negative or NA weights fail.
jb_alloc_weights <- function(weight, exponent = 1) {
  if (anyNA(weight) || any(weight < 0)) stop("jb_alloc_weights: weights must be non-negative and non-missing")
  if (length(exponent) != 1L || is.na(exponent)) stop("jb_alloc_weights: exponent must be a single non-missing value")
  if (exponent == 0) return(rep(1, length(weight)))
  weight^exponent
}

# Split `n_tickets` across `weight` proportionally, with integer tickets and an
# exact total. Largest-remainder: floor, then hand out the leftover to the
# largest fractional parts (ties broken by position).
jb_alloc_split <- function(weight, n_tickets) {
  if (anyNA(weight) || any(weight < 0)) stop("jb_alloc_split: weights must be non-negative and non-missing")
  if (length(n_tickets) != 1L || is.na(n_tickets) || n_tickets < 0) stop("jb_alloc_split: n_tickets must be a non-negative count")
  n_tickets <- as.integer(n_tickets)
  if (sum(weight) <= 0) {
    if (n_tickets == 0L) return(rep(0L, length(weight)))
    stop("jb_alloc_split: cannot split a positive ticket count over all-zero weights")
  }
  exact <- n_tickets * weight / sum(weight)
  base <- floor(exact)
  left <- n_tickets - sum(base)
  if (left > 0L) {
    ord <- order(-(exact - base), seq_along(exact))
    base[ord[seq_len(left)]] <- base[ord[seq_len(left)]] + 1L
  }
  as.integer(base)
}

# Allocate one issue's pool by ex-ante weight shape.
jb_alloc_by_mass <- function(mass, tickets_per_issue = 128L, exponent = 1) {
  jb_alloc_split(jb_alloc_weights(mass, exponent), tickets_per_issue)
}

# Realised gross of an allocation against settled outcomes.
# `unit_gross` is the per-2CNY-ticket payout, i.e. basket_total / (tickets * 2).
# Returns the realised return on stake.
jb_alloc_realised <- function(tickets, unit_gross, hit, unit_cny = 2) {
  if (length(tickets) != length(unit_gross) || length(tickets) != length(hit)) {
    stop("jb_alloc_realised: tickets, unit_gross and hit must have equal length")
  }
  if (anyNA(tickets) || anyNA(unit_gross) || anyNA(hit)) stop("jb_alloc_realised: missing input")
  stake <- tickets * unit_cny
  if (sum(stake) <= 0) stop("jb_alloc_realised: zero total stake")
  payout <- ifelse(hit, stake * unit_gross, 0)
  sum(payout) / sum(stake) - 1
}

# Per-2CNY-ticket payout implied by a basket-level settled gross.
jb_unit_gross <- function(basket_gross, tickets, unit_cny = 2) {
  if (anyNA(basket_gross) || anyNA(tickets)) stop("jb_unit_gross: missing input")
  if (any(tickets <= 0)) stop("jb_unit_gross: tickets must be positive")
  basket_gross / (tickets * unit_cny)
}

# Per-leg gross edge implied by an N-leg parlay return, at the frozen payout factor.
# ROI = (1 + e)^n * payout_factor - 1, so e = ((1 + roi) / payout_factor)^(1/n) - 1.
jb_implied_leg_edge <- function(roi, n_legs, payout_factor = 0.65) {
  if (any(is.na(roi)) || is.na(n_legs) || is.na(payout_factor)) stop("jb_implied_leg_edge: missing input")
  if (n_legs < 1) stop("jb_implied_leg_edge: n_legs must be >= 1")
  if (payout_factor <= 0) stop("jb_implied_leg_edge: payout_factor must be positive")
  ((1 + roi) / payout_factor)^(1 / n_legs) - 1
}

# Per-leg gross edge required to break even on an N-leg parlay.
jb_breakeven_leg_edge <- function(n_legs, payout_factor = 0.65) {
  if (n_legs < 1) stop("jb_breakeven_leg_edge: n_legs must be >= 1")
  if (payout_factor <= 0) stop("jb_breakeven_leg_edge: payout_factor must be positive")
  (1 / payout_factor)^(1 / n_legs) - 1
}
