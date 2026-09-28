# Exposure caps for overlapping sleeves.
#
# Two independent caps govern how sleeves may share fixtures:
#   max_uses_per_fixture - how many sleeves may include the SAME fixture
#   max_pair_overlap     - how many fixtures any TWO sleeves may share
# The first bounds single-fixture exposure; the second bounds the correlation
# between sleeves, which is what makes `any_hit` rise without adding coverage.

# Per-fixture use counts over a sleeve list. `sleeves` is a list of integer
# fixture vectors. Returns a tibble with one row per fixture actually used.
jb_exposure_uses <- function(sleeves) {
  if (!is.list(sleeves)) stop('jb_exposure_uses: sleeves must be a list')
  if (any(vapply(sleeves, function(s) anyNA(s), logical(1)))) {
    stop('jb_exposure_uses: sleeve fixtures must be non-missing')
  }
  fx <- unlist(sleeves, use.names = FALSE)
  if (!length(fx)) {
    return(tibble::tibble(fixture = integer(0), uses = integer(0)))
  }
  tb <- table(fx)
  tibble::tibble(fixture = as.integer(names(tb)), uses = as.integer(tb)) |>
    dplyr::arrange(fixture)
}

# Maximum per-fixture use count across a sleeve list.
jb_exposure_max_uses <- function(sleeves) {
  u <- jb_exposure_uses(sleeves)
  if (!nrow(u)) return(0L)
  max(u$uses)
}

# Pairwise fixture overlap between every pair of sleeves.
# Returns a tibble of the pairs that share at least one fixture.
jb_exposure_pair_overlaps <- function(sleeves) {
  n <- length(sleeves)
  if (n < 2L) {
    return(tibble::tibble(i = integer(0), j = integer(0), overlap = integer(0)))
  }
  out <- list()
  for (i in seq_len(n - 1L)) {
    for (j in seq(i + 1L, n)) {
      ov <- length(intersect(sleeves[[i]], sleeves[[j]]))
      if (ov > 0L) out[[length(out) + 1L]] <- tibble::tibble(i = i, j = j, overlap = ov)
    }
  }
  if (!length(out)) return(tibble::tibble(i = integer(0), j = integer(0), overlap = integer(0)))
  dplyr::bind_rows(out)
}

# Maximum fixture overlap shared by any two sleeves.
jb_exposure_max_pair_overlap <- function(sleeves) {
  p <- jb_exposure_pair_overlaps(sleeves)
  if (!nrow(p)) return(0L)
  max(p$overlap)
}

# Do the sleeves satisfy both caps?
jb_exposure_within_caps <- function(sleeves, max_uses_per_fixture, max_pair_overlap) {
  if (length(max_uses_per_fixture) != 1L || is.na(max_uses_per_fixture) || max_uses_per_fixture < 1L) {
    stop('jb_exposure_within_caps: max_uses_per_fixture must be >= 1')
  }
  if (length(max_pair_overlap) != 1L || is.na(max_pair_overlap) || max_pair_overlap < 0L) {
    stop('jb_exposure_within_caps: max_pair_overlap must be >= 0')
  }
  jb_exposure_max_uses(sleeves) <= max_uses_per_fixture &&
    jb_exposure_max_pair_overlap(sleeves) <= max_pair_overlap
}

# Greedily add candidate sleeves while both caps hold. Candidates are taken in
# the order supplied, so callers rank them ex ante; this function never reads
# settlement. Returns the accepted subset as a list of fixture vectors plus a
# typed rejection reason for each candidate that did not fit.
jb_exposure_greedy_admit <- function(candidates, max_uses_per_fixture, max_pair_overlap) {
  if (!is.list(candidates)) stop('jb_exposure_greedy_admit: candidates must be a list')
  accepted <- list()
  reasons <- character(length(candidates))
  for (k in seq_along(candidates)) {
    cand <- candidates[[k]]
    if (anyNA(cand) || !length(cand)) {
      reasons[k] <- 'EMPTY_OR_MISSING'
      next
    }
    trial <- c(accepted, list(cand))
    if (jb_exposure_max_pair_overlap(trial) > max_pair_overlap) {
      reasons[k] <- 'PAIR_OVERLAP_EXCEEDED'
      next
    }
    if (jb_exposure_max_uses(trial) > max_uses_per_fixture) {
      reasons[k] <- 'FIXTURE_USES_EXCEEDED'
      next
    }
    accepted <- trial
    reasons[k] <- 'ADMITTED'
  }
  list(sleeves = accepted, reasons = reasons)
}

