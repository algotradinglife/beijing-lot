# Construct an N=7 (7串1) fixture portfolio: which fixtures, how many outcomes
# to cover per fixture, and which tickets to fund.
#
# Why: under the market-implied probabilities, p_bd,i(o) * SP_i(o) = 1/booksum_i
# holds for every outcome o of fixture i. The reciprocal booksum is a per-fixture
# quantity, so a fixed seven-fixture group funded on any outcomes has expected
# return 0.65 * prod_i (1/booksum_i), and ranking by market probability is inverse
# to ranking by payout. Coverage (the chance the winning ticket is inside the
# funded set) is the property a construction rule can move most; payout
# distribution and variance move too.
#
# That derivation is scoped to MARKET probabilities. This module ranks fixtures
# and scores tickets with whatever probability matrix the caller supplies, which
# in the delivery is a Dixon-Coles model rather than the market. Inverse ordering
# under market probabilities does not carry over to model probabilities, so the
# model-ranked construction is not covered by the argument above. A funded group of F tickets is the F
# highest-probability combinations of the full 3^7 outcome grid, so its coverage
# is the mass of that top-F set. That set is a down-set in the product lattice:
# a union of coverage boxes, not one box, so the per-leg coverage counts it
# implies are emergent rather than chosen and the coverage pattern only fixes
# F = prod_i k_i. Payout distribution and variance also change with the choice
# of fixtures, so coverage is not the only quantity a rule moves.
#
# The expected return 0.65 * 0.998138^7 = 0.6416 is an APPROXIMATION. Per
# fixture the identity gives 1/booksum_i, and the reciprocal booksums observed
# in this data range over roughly 0.991054..0.999956, so the exact fixed-group
# expectation is 0.65 * prod_i (1/booksum_i). The constant is used only as a
# benchmark, never as an exact claim.
#
# The maximiser of prod_i q_i(k_i) over all fixtures and all k_i with
# prod k_i <= F equals, in 7 of 8 test issues, the simple rule "take the seven
# fixtures with the smallest third-outcome probability and cover two outcomes
# each". 128 = 2^7 is the only all-two budget, so a banker/upside mix requires a
# different budget tier (108 = 3^3 * 2^2, 96 = 3 * 2^5, ...).
#
# No I/O, no history lookup, no hidden state.

# Number of legs in one ticket.
N7_LEGS <- 7L

# Payout per 2-CNY unit, as a multiple of the winning ticket's SP product.
N7_PAYOUT_FACTOR <- 0.65

# Number of outcome combinations on the full grid.
N7_COMBINATIONS <- 3L^N7_LEGS

# Validate one whole-number argument before it is used as a count or an index.
n7_check_count <- function(value, what, upper = N7_COMBINATIONS, lower = 1L) {
  if (length(value) != 1L || !is.numeric(value) || is.na(value) ||
      !is.finite(value) || value != trunc(value) || value < lower ||
      value > upper) {
    stop(sprintf('%s must be one whole number in %d..%d', what, lower, upper))
  }
  as.integer(value)
}

# Every coverage pattern reachable with N7_LEGS legs each covered 1..3 times,
# ordered by descending ticket count. A pattern fixes only the group's ticket
# count, prod_i k_i; the funded set is then the top that many combinations of
# the canonical grid.
n7_coverage_patterns <- function(max_tickets = 512L) {
  max_tickets <- n7_check_count(max_tickets, 'n7_coverage_patterns: max_tickets',
    upper = N7_COMBINATIONS)
  grid <- as.matrix(expand.grid(rep(list(1:3), N7_LEGS), KEEP.OUT.ATTRS = FALSE))
  counts <- apply(grid, 1L, prod)
  keep <- counts <= max_tickets
  grid <- grid[keep, , drop = FALSE]
  counts <- counts[keep]
  out <- lapply(order(counts, decreasing = TRUE), function(i) as.integer(grid[i, ]))
  out
}

# Ticket count of one coverage pattern.
n7_pattern_tickets <- function(pattern) {
  if (length(pattern) != N7_LEGS || anyNA(pattern) ||
      any(!pattern %in% 1:3)) {
    stop('n7_pattern_tickets: pattern must be 7 values in 1..3')
  }
  as.integer(prod(pattern))
}

# All 3^7 outcome combinations, one row per ticket, leg i in column i.
# Row r encodes outcome grid[r, i] for leg i, and the row index is
# 1 + sum_i (outcome_i - 1) * 3^(i-1).
n7_combo_grid <- function() {
  as.matrix(expand.grid(rep(list(1:3), N7_LEGS), KEEP.OUT.ATTRS = FALSE))
}

# Row index of one outcome vector in the n7_combo_grid() ordering.
n7_combo_index <- function(outcomes) {
  if (length(outcomes) != N7_LEGS || anyNA(outcomes) ||
      any(!outcomes %in% 1:3)) {
    stop('n7_combo_index: outcomes must be 7 values in 1..3')
  }
  1L + sum((as.integer(outcomes) - 1L) * 3L^(0:(N7_LEGS - 1L)))
}

# Validate a fixture probability matrix: one row per fixture, three columns,
# every row a finite probability vector summing to 1.
n7_check_probabilities <- function(p) {
  p <- as.matrix(p)
  if (ncol(p) != 3L || nrow(p) < 1L) {
    stop('n7_check_probabilities: p must be a matrix with 3 columns')
  }
  if (anyNA(p) || any(!is.finite(p)) || any(p < 0) || any(p > 1)) {
    stop('n7_check_probabilities: p must be finite probabilities in [0, 1]')
  }
  if (any(abs(rowSums(p) - 1) > 1e-6)) {
    stop('n7_check_probabilities: every row of p must sum to 1')
  }
  p
}

# Coverage of each leg when k outcomes are covered: the summed probability of
# the k most likely outcomes. Returns a 3 x nrow(p) matrix, row k = q_i(k).
n7_leg_coverage <- function(p) {
  p <- n7_check_probabilities(p)
  q <- vapply(seq_len(nrow(p)),
    function(i) cumsum(sort(p[i, ], decreasing = TRUE)), numeric(3L))
  matrix(q, nrow = 3L)
}

# Rank fixtures by their two-outcome coverage q_i(2) descending. Ties fall back
# to the fixture index so the ordering is deterministic. This is the selection
# rule: it is deliberately independent of any price level.
n7_rank_fixtures <- function(p) {
  q <- n7_leg_coverage(p)
  order(-q[2L, ], seq_len(nrow(p)))
}

# How many distinct outcomes a funded group actually covers on each leg. The
# top-F combinations of the product lattice form a down-set, so this is read off
# the funded set rather than imposed on it. Reported for diagnosis only; it does
# not drive ticket selection, and it is a count of outcomes, not the size of the
# smallest coverage box (the outcome codes are not probability ranks).
n7_emergent_coverage <- function(selected) {
  selected <- n7_check_selection(selected)
  grid <- n7_combo_grid()
  vapply(seq_len(N7_LEGS),
    function(leg) length(unique(grid[selected, leg])), integer(1))
}

# Validate a set of funded grid rows.
n7_check_selection <- function(selected) {
  if (!is.numeric(selected) || length(selected) < 1L || anyNA(selected) ||
      any(!is.finite(selected)) || any(selected != trunc(selected)) ||
      anyDuplicated(selected) || any(selected < 1L) ||
      any(selected > N7_COMBINATIONS)) {
    stop('selected must be distinct whole-number grid rows in range')
  }
  as.integer(selected)
}

# Split a ticket budget into groups. The base pattern repeats while it fits and
# the remainder is filled with the largest feasible pattern, so the budget is
# used exactly whenever the remainder is itself a reachable ticket count.
n7_fill_budget <- function(budget_tickets, base_pattern) {
  budget_tickets <- n7_check_count(budget_tickets,
    'n7_fill_budget: budget_tickets')
  base_tickets <- n7_pattern_tickets(base_pattern)
  patterns <- list()
  remaining <- budget_tickets
  while (remaining >= base_tickets) {
    patterns[[length(patterns) + 1L]] <- as.integer(base_pattern)
    remaining <- remaining - base_tickets
  }
  while (remaining > 0L) {
    feasible <- n7_coverage_patterns(max_tickets = remaining)
    if (length(feasible) == 0L) break
    take <- feasible[[1L]]
    patterns[[length(patterns) + 1L]] <- take
    remaining <- remaining - n7_pattern_tickets(take)
  }
  patterns
}

# Fund the F highest-probability combinations of the full 3^7 grid for one
# group. Returns the funded combo row indices in descending probability order.
# The grid is always the canonical n7_combo_grid(), so no caller can pass a
# reordered or corrupted grid that would break settlement indexing. Selecting
# over the whole grid rather than inside a coverage box is at least as good in
# probability mass: a box of F tickets is another F-element subset of the same
# grid, so the top-F set is maximal and equality is possible.
n7_select_tickets <- function(p_group, tickets, blocked = NULL) {
  p_group <- n7_check_probabilities(p_group)
  if (nrow(p_group) != N7_LEGS) {
    stop('n7_select_tickets: p_group must have exactly 7 rows')
  }
  if (is.null(blocked)) blocked <- matrix(FALSE, N7_LEGS, 3L)
  blocked <- n7_check_blocked(blocked)
  if (nrow(blocked) != nrow(p_group)) {
    stop('n7_select_tickets: blocked must have one row per fixture in p_group')
  }
  grid <- n7_combo_grid()
  allowed <- rep(TRUE, nrow(grid))
  for (leg in seq_len(N7_LEGS)) {
    allowed <- allowed & !blocked[leg, grid[, leg]]
  }
  candidates <- which(allowed)
  tickets <- n7_check_count(tickets, 'n7_select_tickets: tickets',
    upper = length(candidates))
  log_p <- rep(0, nrow(grid))
  for (leg in seq_len(N7_LEGS)) {
    log_p <- log_p + log(p_group[leg, grid[, leg]])
  }
  candidates[order(log_p[candidates], decreasing = TRUE)][seq_len(tickets)]
}

# Expected payout of one funded group per 2-CNY unit, as a multiple of the
# supplied product of reciprocal booksums. Under market probabilities every
# funded outcome of leg i carries the same p_bd * SP product, so the expectation
# depends on prod_i k_i and on prod_i (1/booksum_i) but not on which funded
# outcomes were chosen. The product is still fixture-dependent, so fixture choice
# does change the expectation when the reciprocal booksums differ.
n7_group_expected_payout <- function(counts, sp_probability_product) {
  if (length(sp_probability_product) != 1L || is.na(sp_probability_product) ||
      !is.finite(sp_probability_product) || sp_probability_product <= 0) {
    stop('n7_group_expected_payout: sp_probability_product must be one positive value')
  }
  N7_PAYOUT_FACTOR * n7_pattern_tickets(counts) * sp_probability_product
}

# Verify the ticket identity p_bd(c) * SP(c) = 1 / booksum on every outcome of
# every fixture. Returns the per-fixture reciprocal booksum with the spread of
# the within-fixture residuals, so a caller can assert the market is internally
# consistent before ranking on it.
n7_ticket_identity <- function(p_bd, sp) {
  p_bd <- n7_check_probabilities(p_bd)
  sp <- as.matrix(sp)
  if (!identical(dim(sp), dim(p_bd))) {
    stop('n7_ticket_identity: sp must have the same shape as p_bd')
  }
  if (anyNA(sp) || any(!is.finite(sp)) || any(sp <= 1)) {
    stop('n7_ticket_identity: sp must be finite decimal prices above 1')
  }
  products <- p_bd * sp
  residuals <- apply(products, 1L, function(row) diff(range(row)))
  list(reciprocal_booksum = rowMeans(products), residual_spread = residuals)
}

# Bootstrap the portfolio return by resampling whole issues. The unit of
# resampling is the issue, not the group: groups inside one issue share a fixture
# pool, and the sixth group of an issue costs less than the other five, so
# averaging per-group returns would not estimate the reported portfolio return.
# Each replicate recomputes total payout over total cost, which is the same
# statistic the headline return reports.
#
# Side effect: none. The RNG seed is set to `seed` for the draws and the
# caller's previous RNG state is restored on exit.
# Returns the point estimate, the percentile interval, and the fraction of
# replicates above `threshold` (a resampling exceedance frequency, not a
# probability that the true return exceeds it).
n7_bootstrap_return <- function(per_issue, reps = 6000L, seed = 1L,
                                threshold = 1, level = 0.95) {
  if (!is.data.frame(per_issue) ||
      !all(c('成本', '派彩') %in% names(per_issue)) || nrow(per_issue) < 2L) {
    stop('n7_bootstrap_return: per_issue must have 成本 and 派彩 and at least 2 rows')
  }
  if (!is.numeric(per_issue$成本) || !is.numeric(per_issue$派彩) ||
      anyNA(per_issue$成本) || anyNA(per_issue$派彩) ||
      any(!is.finite(per_issue$成本)) || any(!is.finite(per_issue$派彩)) ||
      any(per_issue$成本 <= 0) || any(per_issue$派彩 < 0)) {
    stop(paste('n7_bootstrap_return: 成本 must be finite and positive and',
      '派彩 finite and non-negative'))
  }
  if (!is.finite(sum(per_issue$成本)) || !is.finite(sum(per_issue$派彩))) {
    stop('n7_bootstrap_return: the cost and payout totals must be finite')
  }
  reps <- n7_check_count(reps, 'n7_bootstrap_return: reps', upper = 1e7)
  seed <- n7_check_count(seed, 'n7_bootstrap_return: seed', upper = .Machine$integer.max)
  if (length(threshold) != 1L || is.na(threshold) || !is.finite(threshold)) {
    stop('n7_bootstrap_return: threshold must be one finite value')
  }
  if (length(level) != 1L || is.na(level) || level <= 0 || level >= 1) {
    stop('n7_bootstrap_return: level must be one value strictly inside (0, 1)')
  }
  had_seed <- exists('.Random.seed', envir = globalenv(), inherits = FALSE)
  old_seed <- if (had_seed) get('.Random.seed', envir = globalenv(), inherits = FALSE)
  on.exit({
    if (had_seed) {
      assign('.Random.seed', old_seed, envir = globalenv())
    } else if (exists('.Random.seed', envir = globalenv(), inherits = FALSE)) {
      rm('.Random.seed', envir = globalenv())
    }
  }, add = TRUE)
  set.seed(seed)
  n <- nrow(per_issue)
  draws <- vapply(seq_len(reps), function(i) {
    idx <- sample.int(n, n, replace = TRUE)
    sum(per_issue$派彩[idx]) / sum(per_issue$成本[idx])
  }, numeric(1L))
  alpha <- (1 - level) / 2
  list(
    estimate = sum(per_issue$派彩) / sum(per_issue$成本),
    lower = unname(quantile(draws, alpha)),
    upper = unname(quantile(draws, 1 - alpha)),
    exceedance = mean(draws > threshold),
    reps = reps,
    seed = seed
  )
}


# Distribute fixtures across groups so the groups are as equally strong as
# possible, allowing reuse under two caps. Sequential blocks of seven make the
# first group strong and the last group weak whenever the pool is shallow.
#
# This is a HEURISTIC, not a proven optimum: it repeatedly gives the currently
# weakest group the best available fixture, and retries with a wider choice
# among near-best fixtures when a dead end is hit. A local swap can still
# reduce the spread further, so the result is not the minimum-spread
# assignment and must not be reported as one.
#
# `max_uses` caps how many groups may share one fixture. `max_overlap` caps how
# many fixtures any two groups may share, which bounds how correlated the
# groups are. Both caps are required: without them the greedy would put the
# seven strongest fixtures in every group and the groups would be identical.
#
# Returns a list of `n_groups` integer vectors of length `legs` (fixture rows).
# Raises an error when the greedy fails within `attempts`; that error states it
# is a heuristic failure, not a proof that no assignment exists.
# Side effect: none. The caller RNG state is restored on exit.
n7_balance_groups <- function(p, n_groups, legs = N7_LEGS,
                              max_uses = 3L, max_overlap = 3L,
                              attempts = 64L, seed = 1L) {
  p <- n7_check_probabilities(p)
  n_groups <- n7_check_count(n_groups, "n7_balance_groups: n_groups", upper = 64L)
  legs <- n7_check_count(legs, "n7_balance_groups: legs", upper = N7_LEGS)
  max_uses <- n7_check_count(max_uses, "n7_balance_groups: max_uses", upper = 64L)
  max_overlap <- n7_check_count(max_overlap, "n7_balance_groups: max_overlap",
    upper = N7_LEGS, lower = 0L)
  attempts <- n7_check_count(attempts, "n7_balance_groups: attempts", upper = 10000L)
  seed <- n7_check_count(seed, "n7_balance_groups: seed",
    upper = .Machine$integer.max)
  n <- nrow(p)
  if (n < legs) {
    stop("n7_balance_groups: fewer fixtures than legs in a group")
  }
  if (n * max_uses < n_groups * legs) {
    stop("n7_balance_groups: max_uses is too small to fill every group")
  }
  q <- n7_leg_coverage(p)
  w <- log(q[2L, ])
  greedy <- function(widen) {
    groups <- replicate(n_groups, integer(0L), simplify = FALSE)
    mass <- rep(0, n_groups)
    uses <- integer(n)
    for (round in seq_len(legs)) {
      for (g in order(mass, seq_len(n_groups))) {
        taken <- groups[[g]]
        ok <- which(uses < max_uses & !(seq_len(n) %in% taken))
        if (length(ok) > 0L) {
          ok <- ok[vapply(ok, function(i) {
            all(vapply(seq_len(n_groups), function(h) {
              if (h == g) return(TRUE)
              length(intersect(c(taken, i), groups[[h]])) <= max_overlap
            }, logical(1L)))
          }, logical(1L))]
        }
        if (length(ok) == 0L) return(NULL)
        ranked <- ok[order(w[ok], decreasing = TRUE)]
        # The pure greedy can walk into a dead end that a different early choice
        # avoids, so later attempts widen the choice among near-best fixtures.
        pick <- if (widen <= 1L) ranked[1L]
          else ranked[sample.int(min(widen, length(ranked)), 1L)]
        groups[[g]] <- c(taken, pick)
        mass[g] <- mass[g] + w[pick]
        uses[pick] <- uses[pick] + 1L
      }
    }
    groups
  }
  had_seed <- exists(".Random.seed", envir = globalenv(), inherits = FALSE)
  old_seed <- if (had_seed) get(".Random.seed", envir = globalenv(), inherits = FALSE)
  on.exit({
    if (had_seed) {
      assign(".Random.seed", old_seed, envir = globalenv())
    } else if (exists(".Random.seed", envir = globalenv(), inherits = FALSE)) {
      rm(".Random.seed", envir = globalenv())
    }
  }, add = TRUE)
  set.seed(seed)
  for (attempt in seq_len(attempts)) {
    result <- greedy(widen = min(3L, attempt))
    if (!is.null(result)) return(result)
  }
  stop(sprintf(paste("n7_balance_groups: the greedy failed to complete an",
    "assignment in %d attempts. This is a heuristic failure, not a proof that",
    "no assignment exists under these caps."), attempts))
}

# Coverage mass of one group under a probability matrix and a funded ticket set.
n7_group_mass <- function(p_group, selected) {
  p_group <- n7_check_probabilities(p_group)
  if (nrow(p_group) != N7_LEGS) {
    stop("n7_group_mass: p_group must have exactly 7 rows")
  }
  selected <- n7_check_selection(selected)
  grid <- n7_combo_grid()
  log_p <- vapply(seq_len(N7_LEGS),
    function(leg) log(p_group[leg, grid[selected, leg]]), numeric(length(selected)))
  if (length(selected) == 1L) log_p <- matrix(log_p, nrow = 1L)
  sum(exp(rowSums(log_p)))
}


# Split a ticket budget across groups so the groups end up with similar coverage
# mass, instead of giving every group the same pattern. A group whose fixtures
# are intrinsically weaker needs more tickets to reach the same coverage, so
# equal patterns do not produce equal groups. Greedy: start every group at the
# smallest pattern, then repeatedly upgrade the currently weakest group by the
# smallest affordable step. Returns the pattern chosen for each group.
n7_allocate_balanced <- function(p_groups, budget_tickets) {
  if (!is.list(p_groups) || length(p_groups) < 1L) {
    stop("n7_allocate_balanced: p_groups must be a non-empty list")
  }
  budget_tickets <- n7_check_count(budget_tickets,
    "n7_allocate_balanced: budget_tickets")
  # Validate every group up front, including the zero-upgrade path where the
  # loop body never runs.
  p_groups <- lapply(p_groups, function(pg) {
    pg <- n7_check_probabilities(pg)
    if (nrow(pg) != N7_LEGS) {
      stop("n7_allocate_balanced: every group must have exactly 7 rows")
    }
    pg
  })
  ng <- length(p_groups)
  if (ng > budget_tickets) {
    stop("n7_allocate_balanced: budget cannot give every group a ticket")
  }
  patterns <- n7_coverage_patterns(budget_tickets)
  sizes <- vapply(patterns, n7_pattern_tickets, integer(1))
  mass_at <- function(g, size) {
    pat <- patterns[[match(size, sizes)]]
    n7_group_mass(p_groups[[g]], n7_select_tickets(p_groups[[g]], size))
  }
  chosen <- rep(sizes[length(sizes)], ng)
  remaining <- budget_tickets - ng
  repeat {
    if (remaining <= 0L) break
    mass <- vapply(seq_len(ng), function(g) mass_at(g, chosen[g]), numeric(1L))
    # Walk groups weakest-first, but keep looking past a group that cannot afford
    # its next step: another group may still be able to spend the remainder.
    upgraded <- FALSE
    for (g in order(mass, seq_len(ng))) {
      step <- sizes[sizes > chosen[g] & (sizes - chosen[g]) <= remaining]
      if (length(step) > 0L) {
        next_size <- min(step)
        remaining <- remaining - (next_size - chosen[g])
        chosen[g] <- next_size
        upgraded <- TRUE
        break
      }
    }
    if (!upgraded) break
  }
  list(
    patterns = lapply(seq_len(ng), function(g) patterns[[match(chosen[g], sizes)]]),
    allocated = sum(chosen),
    unspent = budget_tickets - sum(chosen),
    reason = if (sum(chosen) == budget_tickets) 'budget_exhausted' else 'no_affordable_step'
  )
}


# Validate a blocked-cell mask: TRUE means that outcome of that fixture cannot be
# bet, so every combination containing it is removed before ranking. The mask is
# per (fixture, outcome) cell, not per fixture: 北单 can leave a single outcome
# unpriced while the other two are on sale.
n7_check_blocked <- function(blocked) {
  if (!is.logical(blocked) || !is.matrix(blocked) || ncol(blocked) != 3L ||
      nrow(blocked) < 1L || anyNA(blocked)) {
    stop("blocked must be a logical matrix with 3 outcome columns, no missing")
  }
  blocked
}

# How many of the 3^7 combinations of a seven-leg group survive the blocked
# mask. The mask must describe exactly the seven legs of one group.
n7_available_combos <- function(blocked) {
  blocked <- n7_check_blocked(blocked)
  if (nrow(blocked) != N7_LEGS) {
    stop(sprintf("n7_available_combos: blocked must have %d rows", N7_LEGS))
  }
  as.integer(prod(3L - rowSums(blocked)))
}

# Derive the blocked mask from an SP matrix: an outcome is blocked when its price
# is missing, non-positive, non-finite, or so large it cannot be a real quote.
n7_blocked_from_sp <- function(sp, max_sp = 1e4) {
  if (length(max_sp) != 1L || !is.numeric(max_sp) || is.na(max_sp) ||
      !is.finite(max_sp) || max_sp <= 0) {
    stop("n7_blocked_from_sp: max_sp must be one finite positive number")
  }
  sp <- as.matrix(sp)
  if (ncol(sp) != 3L || nrow(sp) < 1L) {
    stop("n7_blocked_from_sp: sp must be a matrix with 3 outcome columns")
  }
  if (!is.numeric(sp)) stop("n7_blocked_from_sp: sp must be numeric")
  blocked <- is.na(sp) | !is.finite(sp) | sp <= 0 | sp > max_sp
  dimnames(blocked) <- NULL
  blocked
}


# Summarise a settled portfolio of groups into the metrics a construction rule is
# judged on. `bt` has one row per group with columns 期次, 组, 成本, 中 (logical),
# 派彩. The headline return is total payout over total cost, not a mean of
# per-group ratios, because groups within an issue can cost different amounts.
n7_portfolio_summary <- function(bt) {
  required <- c("期次", "组", "成本", "中", "派彩")
  if (!is.data.frame(bt) || !all(required %in% names(bt)) || nrow(bt) < 1L) {
    stop("n7_portfolio_summary: bt needs 期次, 组, 成本, 中, 派彩 and at least 1 row")
  }
  if (!is.numeric(bt$成本) || !is.numeric(bt$派彩) || !is.logical(bt$中) ||
      anyNA(bt$成本) || anyNA(bt$派彩) || anyNA(bt$中) ||
      any(!is.finite(bt$成本)) || any(!is.finite(bt$派彩)) ||
      any(bt$成本 <= 0) || any(bt$派彩 < 0)) {
    stop("n7_portfolio_summary: 成本 positive and finite, 派彩 finite and non-negative, 中 logical")
  }
  issues <- unique(bt$期次)
  hit_issues <- unique(bt$期次[bt$中])
  tibble::tibble(
    期数 = length(issues),
    组数 = nrow(bt),
    成本 = sum(bt$成本),
    回收 = sum(bt$派彩),
    回报率 = sum(bt$派彩) / sum(bt$成本),
    至少中一组期数 = length(hit_issues),
    中组 = sum(bt$中),
    中奖率 = mean(bt$中)
  )
}

# Admit only fixtures whose model probability is consistent with the market to
# within `max_edge`. A fixture whose best model outcome is priced at many times
# its market probability is a fitting failure, not an opportunity, and would
# otherwise dominate any rule that ranks on model probability times price.
n7_admit_fixtures <- function(p_model, sp, max_edge = 2) {
  p_model <- n7_check_probabilities(p_model)
  sp <- as.matrix(sp)
  if (!identical(dim(sp), dim(p_model))) {
    stop('n7_admit_fixtures: sp must have the same shape as p_model')
  }
  if (anyNA(sp) || any(!is.finite(sp)) || any(sp <= 1)) {
    stop('n7_admit_fixtures: sp must be finite decimal prices above 1')
  }
  if (length(max_edge) != 1L || is.na(max_edge) || !is.finite(max_edge) || max_edge <= 0) {
    stop('n7_admit_fixtures: max_edge must be one positive value')
  }
  apply(p_model * sp, 1L, max) <= max_edge
}