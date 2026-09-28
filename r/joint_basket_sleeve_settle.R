# Settle recorded sleeves against observed outcomes.
#
# A sleeve stores, for each of its 7 fixtures, the full 3^7 state space as a
# named probability and payout vector. The names are 7-digit base-3 strings in
# which digit 0 = W, 1 = D, 2 = L (verified against the fixture marginals).
# The sleeve buys `state_ids` (1-based indices INTO the full 3^7 ordering).
#
# Settlement gives one observed direction per (issue, slot). A sleeve hits when
# its observed tuple is among the bought states; the payout is then the sum of
# `state_payout` over the bought states that match - equivalently the payout of
# the single matching state, because one ticket maps to one state.

# Encode an observed outcome triple as the base-3 string used by state names.
# `dirs` is an integer vector of codes in the sleeve fixture order, 0=W 1=D 2=L.
jb_sleeve_tuple_name <- function(dirs) {
  if (anyNA(dirs)) stop('jb_sleeve_tuple_name: dirs must be non-missing')
  if (any(dirs < 0L | dirs > 2L)) stop('jb_sleeve_tuple_name: dirs must be 0, 1 or 2')
  paste0(dirs, collapse = '')
}

# Settle one sleeve. `dirs` is the observed direction per sleeve fixture.
# Returns the gross payout to the sleeve (0 when it misses).
jb_sleeve_settle <- function(sleeve, dirs) {
  if (anyNA(dirs)) return(0)
  name <- jb_sleeve_tuple_name(dirs)
  idx <- which(names(sleeve$state_probability) == name)
  if (!length(idx)) stop('jb_sleeve_settle: tuple not found in state space')
  if (!(idx %in% sleeve$state_ids)) return(0)
  sum(sleeve$state_payout[idx])
}

# Settle every sleeve of a plan. `settled` maps fixture slot -> direction code.
# Returns one typed row per sleeve. Sleeves with any unsettled fixture are
# reported as UNRESOLVED rather than silently treated as a loss.
jb_plan_settle <- function(plan_arm, fixture_slots, fixture_index, settled) {
  out <- list()
  for (s in plan_arm$options) {
    slots <- vapply(s$fixtures, function(i) fixture_slots[[i]], integer(1))
    dirs <- settled[as.character(slots)]
    status <- if (anyNA(dirs)) 'UNRESOLVED' else 'SETTLED'
    gross <- if (status == 'SETTLED') jb_sleeve_settle(s, as.integer(dirs)) else NA_real_
    out[[length(out) + 1L]] <- tibble::tibble(
      sleeve_id = s$sleeve_id, depth = s$depth, coverage = s$coverage,
      stake = s$stake, status = status, gross = gross,
      slots = paste(slots, collapse = ','))
  }
  if (!length(out)) {
    return(tibble::tibble(sleeve_id = integer(0), depth = numeric(0),
      coverage = numeric(0), stake = numeric(0), status = character(0),
      gross = numeric(0), slots = character(0)))
  }
  dplyr::bind_rows(out)
}

