# Ex-ante coverage and set-selection geometry of a 7-leg joint basket.
#
# A basket enumerates 3^7 = 2187 outcome tuples. Buying a set S of tickets costs
# |S| * unit_cny regardless of WHICH tuples S contains, so the design question is
# purely: which set does a fixed budget buy?
#
# Every function here is deterministic and works from EX-ANTE quantities only:
# a per-leg probability matrix (rows = legs, columns = outcomes). Nothing here
# reads settlement, so nothing here can leak an outcome into a selection.
#
# SCOPE: this module establishes a SET-GEOMETRY fact only. For a fixed grid,
# the D largest tuple masses maximise covered mass among all D-element sets.
# It makes no statement about profit, payout, or calibration.
#
# Ranks are 1-based positions in the joint-probability ordering over the 3^n
# grid (rank 1 = most probable tuple).

# Validate a per-leg probability matrix against the module data contract.
jb_check_pv <- function(pv, caller) {
  pv <- as.matrix(pv)
  if (ncol(pv) != 3L) stop(caller, ": pv must have exactly 3 outcome columns")
  if (!nrow(pv)) stop(caller, ": pv must have at least one leg")
  if (!is.numeric(pv)) stop(caller, ": pv must be numeric")
  if (anyNA(pv)) stop(caller, ": pv must be non-missing")
  if (any(!is.finite(pv))) stop(caller, ": pv must be finite")
  if (any(pv < 0)) stop(caller, ": pv must be non-negative")
  if (any(abs(rowSums(pv) - 1) > 1e-8)) stop(caller, ": each leg must sum to 1")
  pv
}

# Validate a whole-number scalar count (ticket counts, widths, depths).
jb_check_count <- function(x, caller, what, lo = 0, hi = Inf) {
  if (length(x) != 1L || is.na(x) || !is.numeric(x)) stop(caller, ": ", what, " must be a single non-missing number")
  if (!is.finite(x)) stop(caller, ": ", what, " must be finite")
  if (abs(x - round(x)) > 1e-9) stop(caller, ": ", what, " must be a whole number")
  x <- as.integer(round(x))
  if (x < lo || x > hi) stop(caller, ": ", what, " must be between ", lo, " and ", hi)
  x
}

# Validate a probability grid: finite, non-negative, and summing to 1.
jb_check_grid <- function(grid, caller) {
  if (!is.numeric(grid)) stop(caller, ": grid must be numeric")
  if (!length(grid)) stop(caller, ": grid must be non-empty")
  if (anyNA(grid)) stop(caller, ": grid must be non-missing")
  if (any(!is.finite(grid))) stop(caller, ": grid must be finite")
  if (any(grid < 0)) stop(caller, ": grid must be non-negative")
  if (abs(sum(grid) - 1) > 1e-8) stop(caller, ": grid must sum to 1")
  invisible(TRUE)
}

# Joint probability of every tuple in the 3^n grid, first leg varying fastest.
# pv is legs x 3 and each row must be a distribution.
jb_grid_mass <- function(pv) {
  pv <- jb_check_pv(pv, "jb_grid_mass")
  n <- nrow(pv)
  grid <- array(1, dim = rep(3L, n))
  for (j in seq_len(n)) grid <- sweep(grid, j, pv[j, ], "*")
  as.numeric(grid)
}

# Descending order of the joint grid, stable so ties rank reproducibly.
jb_grid_order <- function(grid) {
  if (!is.numeric(grid)) stop("jb_grid_order: grid must be numeric")
  if (!length(grid)) stop("jb_grid_order: grid must be non-empty")
  if (anyNA(grid)) stop("jb_grid_order: grid must be non-missing")
  if (any(!is.finite(grid))) stop("jb_grid_order: grid must be finite")
  order(grid, decreasing = TRUE)
}

# Coverage of the D most probable tuples: the probability a settled tuple lies
# inside the top-D set. This is the ex-ante hit probability of a contiguous rule.
jb_coverage_at_depth <- function(grid, depth) {
  jb_check_grid(grid, "jb_coverage_at_depth")
  depth <- jb_check_count(depth, "jb_coverage_at_depth", "depth", lo = 0)
  if (depth == 0L) return(0)
  ord <- order(grid, decreasing = TRUE)
  sum(grid[ord[seq_len(min(depth, length(ord)))]])
}

# Rank of one tuple index (1-based position in the joint ordering).
jb_tuple_rank <- function(grid, index) {
  jb_check_grid(grid, "jb_tuple_rank")
  index <- jb_check_count(index, "jb_tuple_rank", "index", lo = 1, hi = length(grid))
  match(index, order(grid, decreasing = TRUE))
}

# Mean per-leg probability that the settled outcome lies among that leg top-width
# outcomes. Tests the per-leg reliability claim directly from the grid.
jb_leg_set_rate <- function(pv, width = 2L) {
  pv <- jb_check_pv(pv, "jb_leg_set_rate")
  width <- jb_check_count(width, "jb_leg_set_rate", "width", lo = 1, hi = 3)
  mean(apply(pv, 1, function(v) sum(sort(v, decreasing = TRUE)[seq_len(width)])))
}

# Coverage of a leg-constrained product set: every leg restricted to its own
# top-width outcomes. Its size is width^n, so it is comparable by cost to a
# contiguous rule buying the same number of tickets.
jb_legset_coverage <- function(pv, width = 2L) {
  pv <- jb_check_pv(pv, "jb_legset_coverage")
  width <- jb_check_count(width, "jb_legset_coverage", "width", lo = 1, hi = 3)
  prod(apply(pv, 1, function(v) sum(sort(v, decreasing = TRUE)[seq_len(width)])))
}

# Indices (into the grid from jb_grid_mass) of the leg-constrained product set:
# every leg restricted to its own top-width outcomes. Returns integer indices.
jb_legset_indices <- function(pv, width = 2L) {
  pv <- jb_check_pv(pv, "jb_legset_indices")
  width <- jb_check_count(width, "jb_legset_indices", "width", lo = 1, hi = 3)
  n <- nrow(pv)
  picks <- lapply(seq_len(n), function(j) order(-pv[j, ])[seq_len(width)])
  # grid index for a tuple is 1 + sum_j (outcome_j - 1) * 3^(j - 1)
  grid_idx <- expand.grid(lapply(picks, function(p) p - 1L))
  as.integer(1 + rowSums(sweep(as.matrix(grid_idx), 2, 3^(seq_len(n) - 1), "*")))
}

# Cost-equivalence comparison between contiguous and leg-constrained buying.
# A width-w product set over n legs costs w^n tickets. This function reports the
# coverage of BOTH sets computed on the SAME grid, and their difference.
jb_equal_cost_compare <- function(pv, width = 2L) {
  pv <- jb_check_pv(pv, "jb_equal_cost_compare")
  width <- jb_check_count(width, "jb_equal_cost_compare", "width", lo = 1, hi = 3)
  n <- nrow(pv)
  cost <- width^n
  grid <- jb_grid_mass(pv)
  leg_idx <- jb_legset_indices(pv, width)
  leg_cov <- sum(grid[leg_idx])
  cont_cov <- jb_coverage_at_depth(grid, cost)
  tibble::tibble(
    width = as.integer(width),
    n_legs = as.integer(n),
    cost_tickets = as.numeric(cost),
    legset_size = length(leg_idx),
    legset_coverage = leg_cov,
    contiguous_coverage = cont_cov,
    advantage = cont_cov - leg_cov)
}

# Admissibility of one bundle/settlement pairing, as a single testable decision.
# Returns NULL when the pairing is admissible, otherwise a short reason string.
#
# This is the delivery admission contract, extracted from the analysis so that
# automated tests exercise the SAME logic the document runs.
#   * both sides must carry a handicap column, with no missing values, and the
#     two must agree -- the handicap decides the settled direction, so a mismatch
#     silently inverts the outcome;
#   * slot/provider identity must be unique on both sides and match one-to-one;
#   * the per-leg probability matrix must satisfy the module probability contract.
jb_admit_pairing <- function(fx, lb, caller = "jb_admit_pairing") {
  need <- c("slot", "provider_id")
  if (!all(need %in% names(fx))) return("missing fixture identity columns")
  if (!all(need %in% names(lb))) return("missing label identity columns")
  if (!"handicap" %in% names(fx) || !"handicap" %in% names(lb)) return("missing handicap column")

  # Missing identity values must be rejected BEFORE building keys: paste() turns
  # NA into the literal "NA", so two different missing fixtures would otherwise
  # compare equal and be admitted as a matched pair.
  if (anyNA(fx$slot) || anyNA(fx$provider_id)) return("missing fixture identity value")
  if (anyNA(lb$slot) || anyNA(lb$provider_id)) return("missing label identity value")
  # An empty slot is as ambiguous as an empty provider_id: it would collide with
  # any other empty slot, so both key components are checked on both sides.
  if (any(!nzchar(as.character(fx$slot))) || any(!nzchar(as.character(lb$slot))) ||
      any(!nzchar(as.character(fx$provider_id))) || any(!nzchar(as.character(lb$provider_id)))) {
    return("empty identity value")
  }

  fx_key <- paste(fx$slot, fx$provider_id)
  lb_key <- paste(lb$slot, lb$provider_id)
  # Duplicate keys make the pairing ambiguous, so they are rejected before the
  # match. The fixture side is checked first, so a duplicated fixture key is
  # reported as such rather than surfacing later as an unmatched identity.
  if (anyDuplicated(fx_key)) return("duplicate fixture key")
  if (anyDuplicated(lb_key)) return("duplicate label key")

  idx <- match(fx_key, lb_key)
  if (anyNA(idx)) return("unmatched fixture identity")

  hx <- fx$handicap
  hl <- lb$handicap[idx]
  if (anyNA(hx) || anyNA(hl) || any(hx != hl)) return("handicap disagreement")

  if (!all(c("p_W", "p_D", "p_L") %in% names(fx))) return("missing probability columns")
  ok <- tryCatch({
    jb_check_pv(as.matrix(fx[, c("p_W", "p_D", "p_L"), drop = FALSE]), caller)
    TRUE
  }, error = function(e) FALSE)
  if (!ok) return("invalid probability matrix")

  NULL
}
