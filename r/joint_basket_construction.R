# Joint-probability 7-leg basket construction.
#
# Outcome columns are ordered W, D, L and indexed 1, 2, 3 throughout.
# A ticket is one 7-tuple (one outcome per leg). A basket is a non-empty set of
# tickets that share the same 7 fixtures. Coverage of a portfolio of baskets on
# disjoint fixtures is exactly 1 - prod(1 - c_i), where c_i is the mass of the
# tickets bought in basket i: fixture outcomes are modelled independent and the
# baskets share no fixture, so the baskets are independent.
#
# Nothing here reads data or fits anything: every function is a deterministic
# map from its arguments. Selection and allocation use no historical outcome.

# Direction of a settled fixture under the frozen handicap line.
# actual_home/actual_away are goals; handicap is the North-Beidan line.
jb_outcome_index <- function(actual_home, actual_away, handicap) {
  if (length(actual_home) != length(actual_away) || length(actual_home) != length(handicap)) {
    stop("jb_outcome_index: actual_home, actual_away and handicap must have equal length")
  }
  if (anyNA(actual_home) || anyNA(actual_away) || anyNA(handicap)) {
    stop("jb_outcome_index: missing settled score or handicap")
  }
  net <- actual_home - actual_away + handicap
  ifelse(net > 0, 1L, ifelse(net == 0, 2L, 3L))
}

# Joint probability of every 3^n tuple of a basket, in the mixed-radix order
# defined by jb_tuple_index (leg i carries weight 3^(i-1)). This is the
# authoritative enumeration: every other function works from it.
jb_basket_joint_grid <- function(pv_mat) {
  pv_mat <- as.matrix(pv_mat)
  if (ncol(pv_mat) != 3L || nrow(pv_mat) < 1L) stop("jb_basket_joint_grid: expected n x 3 matrix")
  if (anyNA(pv_mat) || any(pv_mat < 0)) stop("jb_basket_joint_grid: probabilities must be finite and non-negative")
  if (any(abs(rowSums(pv_mat) - 1) > 1e-8)) stop("jb_basket_joint_grid: rows must sum to 1")
  v <- 1
  for (i in seq_len(nrow(pv_mat))) v <- as.vector(v %o% pv_mat[i, ])
  as.numeric(v)
}

# The same mass, sorted descending.
jb_basket_joint_probs <- function(pv_mat) {
  sort(jb_basket_joint_grid(pv_mat), decreasing = TRUE)
}

# Linear index (1-based) of one outcome tuple under the same mixed-radix order
# used by jb_basket_joint_probs: leg i carries weight 3^(i-1).
jb_tuple_index <- function(outcomes) {
  if (!length(outcomes)) stop("jb_tuple_index: outcomes must not be empty")
  if (anyNA(outcomes)) stop("jb_tuple_index: outcomes must not be missing")
  # Integer-valued, not merely in range: as.integer() truncates, so 1.9 would
  # silently become outcome 1 and invent a tuple that was never enumerated.
  if (any(outcomes != trunc(outcomes))) {
    stop("jb_tuple_index: outcomes must be whole numbers")
  }
  if (any(outcomes < 1L) || any(outcomes > 3L)) {
    stop("jb_tuple_index: outcomes must be 1..3")
  }
  1L + sum((as.integer(outcomes) - 1L) * 3L^(seq_along(outcomes) - 1L))
}

# Sum of the n largest elements, without fully sorting.
jb_top_mass <- function(v, n) {
  n <- min(as.integer(n), length(v))
  if (n < 1L) return(0)
  if (n >= length(v)) return(sum(v))
  # R's partial sort has no `decreasing` argument: partially sort the negated
  # values, which yields the n smallest of -v == the n largest of v.
  -sum(sort(-v, partial = n)[seq_len(n)])
}

# Greedily choose 7 distinct fixtures from `available` (indices into pv rows),
# each step adding the fixture that maximises the top-`n_ref` joint mass.
# `n_ref` is the within-basket reference ticket count; it is derived from the
# budget and the number of groups, never from an outcome.
jb_greedy_select_group <- function(pv, available, n_ref) {
  pv <- as.matrix(pv)
  available <- as.integer(available)
  if (length(available) < 7L) stop("jb_greedy_select_group: fewer than 7 available fixtures")
  if (anyDuplicated(available)) stop("jb_greedy_select_group: available must be unique")
  if (n_ref < 1L) stop("jb_greedy_select_group: n_ref must be positive")
  chosen <- integer(0)
  rest <- available
  for (slot in seq_len(7L)) {
    scores <- vapply(rest, function(cand) {
      jb_top_mass(jb_basket_joint_probs(pv[c(chosen, cand), , drop = FALSE]), n_ref)
    }, numeric(1))
    best <- rest[which.max(scores)]
    chosen <- c(chosen, best)
    rest <- setdiff(rest, best)
  }
  chosen
}

# Exact ticket allocation minimising sum_i log(1 - c_i) subject to
# sum_i n_i = n_tickets. The objective is additive in the baskets, so a DP over
# (basket, tickets used) is exact. Returns an integer vector of ticket counts.
jb_allocate_tickets <- function(prob_vectors, n_tickets) {
  if (!length(prob_vectors)) stop("jb_allocate_tickets: no baskets")
  n_tickets <- as.integer(n_tickets)
  if (is.na(n_tickets) || n_tickets < 0L) stop("jb_allocate_tickets: n_tickets must be non-negative")
  k <- length(prob_vectors)
  # A basket may be able to cover its whole tuple space, making 1 - c exactly 0.
  # Clamp so the log stays finite; the clamp only ever helps the basket that
  # achieves full cover, so the argmin is unchanged.
  neg <- lapply(prob_vectors, function(v) {
    n <- min(n_tickets, length(v))
    c(0, log1p(-pmin(cumsum(v[seq_len(n)]), 1 - 1e-15)))
  })
  dp <- matrix(Inf, k + 1L, n_tickets + 1L)
  choice <- matrix(NA_integer_, k + 1L, n_tickets + 1L)
  dp[1L, 1L] <- 0
  for (i in seq_len(k)) {
    for (t in 0:n_tickets) {
      if (!is.finite(dp[i, t + 1L])) next
      maxn <- min(n_tickets - t, length(neg[[i]]) - 1L)
      cand <- dp[i, t + 1L] + neg[[i]][seq_len(maxn + 1L)]
      idx <- (t + 0:maxn) + 1L
      better <- cand < dp[i + 1L, idx]
      dp[i + 1L, idx[better]] <- cand[better]
      choice[i + 1L, idx[better]] <- (0:maxn)[better]
    }
  }
  if (!is.finite(dp[k + 1L, n_tickets + 1L])) {
    stop("jb_allocate_tickets: no feasible allocation for ", n_tickets, " tickets")
  }
  # Trace the recorded decisions rather than re-deriving them from the values:
  # equality tests on the objective are not reliable near full cover.
  n <- integer(k)
  t <- n_tickets
  for (i in k:1L) {
    x <- choice[i + 1L, t + 1L]
    if (is.na(x)) stop("jb_allocate_tickets: backtrack failed at basket ", i)
    n[i] <- x
    t <- t - x
  }
  n
}

# Mass bought in each basket.
jb_basket_masses <- function(prob_vectors, allocation) {
  if (length(prob_vectors) != length(allocation)) stop("jb_basket_masses: length mismatch")
  vapply(seq_along(prob_vectors), function(i) {
    if (allocation[i] <= 0L) 0 else sum(prob_vectors[[i]][seq_len(allocation[i])])
  }, numeric(1))
}

# Model-expected probability that at least one basket contains the true tuple.
jb_expected_coverage <- function(prob_vectors, allocation) {
  c_i <- jb_basket_masses(prob_vectors, allocation)
  1 - prod(1 - c_i)
}

# Whether a basket's bought tickets contain the settled tuple.
#
# The bought tickets are the n_taken most likely tuples, so membership is tested
# against the ranks of the *unsorted* enumeration: order() on the already-sorted
# vector would return the identity permutation.
jb_basket_hit <- function(pv_group, outcomes, n_taken) {
  # The tuple index is meaningful only if it indexes the SAME enumeration the
  # grid produces. A shorter outcomes vector yields a valid index into a longer
  # grid and would report a hit for a tuple that was never enumerated.
  pv_group <- as.matrix(pv_group)
  if (length(outcomes) != nrow(pv_group)) {
    stop("jb_basket_hit: outcomes length (", length(outcomes),
         ") must equal basket legs (", nrow(pv_group), ")")
  }
  if (n_taken <= 0L) return(FALSE)
  grid <- jb_basket_joint_grid(pv_group)
  kept <- order(grid, decreasing = TRUE)[seq_len(min(n_taken, length(grid)))]
  jb_tuple_index(outcomes) %in% kept
}

# Build the whole portfolio for one issue.
#
# pv          n x 3 matrix of frozen per-fixture outcome probabilities
# budget_cny  total stake budget for the issue
# unit_cny    stake per ticket
#
# Groups are disjoint blocks of 7 fixtures. The number of groups is the largest
# the pool supports. The within-group reference ticket count is the budget's
# ticket count spread over those groups.
jb_construct_portfolio <- function(pv, budget_cny, unit_cny) {
  pv <- as.matrix(pv)
  n_fixtures <- nrow(pv)
  k_max <- n_fixtures %/% 7L
  if (k_max < 1L) stop("jb_construct_portfolio: pool has fewer than 7 fixtures")
  n_tickets <- as.integer(budget_cny %/% unit_cny)
  if (n_tickets < 1L) stop("jb_construct_portfolio: budget buys no ticket")
  n_ref <- max(1L, n_tickets %/% k_max)
  available <- seq_len(n_fixtures)
  groups <- vector("list", k_max)
  prob_vectors <- vector("list", k_max)
  for (g in seq_len(k_max)) {
    sel <- jb_greedy_select_group(pv, available, n_ref)
    groups[[g]] <- sel
    prob_vectors[[g]] <- jb_basket_joint_probs(pv[sel, , drop = FALSE])
    available <- setdiff(available, sel)
  }
  allocation <- jb_allocate_tickets(prob_vectors, n_tickets)
  list(
    groups = groups,
    prob_vectors = prob_vectors,
    allocation = allocation,
    masses = jb_basket_masses(prob_vectors, allocation),
    expected_coverage = jb_expected_coverage(prob_vectors, allocation),
    n_tickets = n_tickets,
    n_groups = k_max
  )
}

# Realised hit indicators, one per basket that was actually bought.
jb_realised_hits <- function(portfolio, pv, outcomes) {
  vapply(seq_along(portfolio$groups), function(g) {
    n <- portfolio$allocation[g]
    if (n <= 0L) return(NA)
    jb_basket_hit(pv[portfolio$groups[[g]], , drop = FALSE], outcomes[portfolio$groups[[g]]], n)
  }, logical(1))
}

# Rank of the settled tuple inside the per-leg Top2 restricted space.
#
# The restricted space contains 2^7 = 128 tuples, one per combination of each
# leg's two most likely outcomes. Returns NA (not an error) when any leg's
# settled outcome lies outside its Top2, because such a tuple is not in the
# restricted space at all.
#
# Do NOT rank by comparing the full-space mixed-radix index against the
# restricted-space ordering: those are different bases, and the comparison
# silently yields NA for every tuple whose full-space index exceeds 128. The
# settled tuple must first be located as a ROW of the restricted enumeration.
jb_restricted_rank <- function(pvg, top2, outcomes) {
  pvg <- as.matrix(pvg)
  if (!identical(dim(pvg), c(7L, 3L))) stop("jb_restricted_rank: pvg must be 7 x 3")
  if (anyNA(pvg) || any(pvg < 0)) stop("jb_restricted_rank: pvg must be non-negative and complete")
  if (any(rowSums(pvg) <= 0)) stop("jb_restricted_rank: every leg must carry probability mass")
  top2 <- as.matrix(top2)
  if (!identical(dim(top2), c(7L, 2L))) stop("jb_restricted_rank: top2 must be 7 x 2")
  if (anyNA(top2) || any(top2 < 1L) || any(top2 > 3L)) {
    stop("jb_restricted_rank: top2 must be outcome codes in 1..3")
  }
  if (any(vapply(seq_len(7), function(j) anyDuplicated(top2[j, ]) > 0L, logical(1)))) {
    stop("jb_restricted_rank: each leg's Top2 must be two distinct outcomes")
  }
  outcomes <- as.integer(outcomes)
  if (length(outcomes) != 7L || anyNA(outcomes) || any(outcomes < 1L | outcomes > 3L)) {
    stop("jb_restricted_rank: outcomes must be 7 values in 1..3")
  }
  if (!all(vapply(seq_len(7), function(j) outcomes[j] %in% top2[j, ], logical(1)))) {
    return(NA_integer_)
  }
  sub <- as.matrix(expand.grid(lapply(seq_len(7), function(j) top2[j, ])))
  row_index <- apply(sub, 1L, jb_tuple_index)
  prob <- apply(sub, 1L, function(o) prod(pvg[cbind(seq_len(7), o)]))
  row <- match(jb_tuple_index(outcomes), row_index)
  if (is.na(row)) stop("jb_restricted_rank: settled tuple absent from its own restricted space")
  match(row, order(prob, decreasing = TRUE))
}
