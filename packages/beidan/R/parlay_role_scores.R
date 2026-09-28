# Role round-robin baseline (#533), stage 1: role scoring.
#
# Implements export 1 of docs/strategy/role-round-robin-contract.md. A "role" is a
# leg position in a group, not a fixture: role 1 is the leg whose single most likely
# outcome is retained, role 2 retains the two most likely outcomes and role 3 keeps
# the whole triple. Every fixture in the admitted pool is scored under all three
# roles, so the same fixture can be the safest pick of one round and the riskiest of
# another. No scraping, persistence, fitting or betting happens here.

#' Deterministic ordering key for one fixture's three outcomes
#'
#' Internal.
#' @param probability Numeric vector of one fixture's three outcome probabilities in
#'   canonical `W`, `D`, `L` order.
#' @return Integer positions putting the highest probability first, with ties broken
#'   by the canonical `W`, `D`, `L` order rather than by label or input row order.
#' @details The tiebreaker is the POSITION in [match_outcomes()], not the label:
#'   `order(..., c("W", "D", "L"))` would sort D < L < W alphabetically. Ties compare
#'   a rounded probability so `rep(1/3, 3)` does not break a genuine three-way tie by
#'   floating-point noise.
#' @noRd
.parlay_role_triple_key <- function(probability) {
  order(-round(as.numeric(probability), 9), seq_along(match_outcomes()))
}

#' One fixture's definition under one role
#'
#' Internal.
#' @param probability Numeric vector of one fixture's three probabilities in canonical
#'   `W`, `D`, `L` order.
#' @param role Single integer 1, 2 or 3.
#' @return A list(allowed, score, retained). `allowed` is the kept outcomes in
#'   deterministic order (length equals the role); `score` is `p1`, `p1 + p2` or `p3`;
#'   `retained` is the kept mass `p1`, `p1 + p2` or `1`. Score and retained differ for
#'   role 3 by design.
#' @noRd
.parlay_role_definition <- function(probability, role) {
  triple <- as.numeric(probability)
  ranking <- .parlay_role_triple_key(triple)
  allowed <- match_outcomes()[ranking][seq_len(role)]
  score <- switch(as.character(role),
    "1" = triple[ranking][1L],
    "2" = sum(triple[ranking][1:2]),
    "3" = triple[ranking][3L])
  retained <- switch(as.character(role),
    "1" = triple[ranking][1L],
    "2" = sum(triple[ranking][1:2]),
    "3" = 1)
  list(allowed = allowed, score = score, retained = retained)
}

#' Score every admitted fixture under the three round-robin roles
#'
#' Turns the authoritative probability table into the deterministic ranking each
#' round of [parlay_construct_role_groups()] scans. A role is a leg position inside a
#' group: role 1 keeps one outcome, role 2 keeps two and role 3 keeps all three. Each
#' fixture is scored under all three roles, so no fixture is pre-classified into a
#' disjoint pool.
#'
#' @param probabilities Authoritative probability tibble with columns
#'   `fixture_id`, `outcome`, `probability`, exactly three W/D/L rows per fixture.
#'   Probabilities must be finite, nonnegative and sum to one per fixture; a negative
#'   value, a gap, a duplicate outcome or a foreign column set is an error.
#' @param cutoff Explicit cutoff object with a single UTC `cutoff_utc` and one
#'   `issue_id`; it is validated and carried through untouched.
#' @return A tibble with one row per (fixture, role):
#'   * `fixture_id` (character) -- preserved identifier, leading zeros kept;
#'   * `role` (integer) -- 1, 2 or 3;
#'   * `score` (double) -- the role's score: `p1`, `p1 + p2`, or `p3`;
#'   * `rank` (integer, one per role) -- 1 is the highest score in that role;
#'   * `retained_probability` (double) -- the probability mass the leg keeps:
#'     `p1`, `p1 + p2`, or `1` for role 3;
#'   * `allowed_outcomes` (list of character vectors) -- the kept W/D/L labels in
#'     deterministic order; a role-3 leg always keeps exactly `W`, `D`, `L`.
#'   Rows are ordered by role then rank. An empty `probabilities` table returns the
#'   typed-empty shape with the same columns and types.
#' @details Scoring is pure arithmetic over the supplied probabilities: no model is
#'   fitted and no historical label is read. Within a fixture the outcomes are ordered
#'   by probability descending with ties broken by the canonical `W`, `D`, `L` order,
#'   and rows for one role are ordered by score descending with ties broken by
#'   lexicographic `fixture_id`. Neither ordering consults any difficulty metric, so a
#'   fixture is never silently reclassified by uncertainty. The cutoff instant, the issue id, the
#'   input probability hash and the code identity are attached as attributes
#'   (`cutoff`, `issue_id`, `probability_hash`, `code_hash`); they are provenance
#'   labels and are re-derived by downstream stages rather than trusted alone.
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
#' probabilities <- tibble::tibble(
#'   fixture_id = rep(c("A", "B"), each = 3),
#'   outcome = rep(c("W", "D", "L"), 2),
#'   probability = c(0.6, 0.3, 0.1, 0.2, 0.5, 0.3))
#' parlay_role_scores(probabilities, cutoff)
#' @export
parlay_role_scores <- function(probabilities, cutoff) {
  match_require_cutoff(cutoff)
  prob <- match_validate_table(probabilities, "probabilities")
  metadata <- list(cutoff = cutoff, issue_id = as.character(cutoff$issue_id),
                   probability_hash = rlang::hash(prob),
                   code_hash = .parlay_role_code_hash())
  if (!nrow(prob)) {
    return(do.call(structure, c(list(.parlay_role_typed_empty("scores")), metadata)))
  }
  # Reuse the authoritative wide helper: it enforces exactly three W/D/L rows
  # per fixture, no gaps, nonnegative finite values and sum-to-one. Re-deriving those
  # checks here would let the role layer accept a table the rest of the pipeline
  # refuses.
  wide <- parlay_probability_wide(prob)
  fixture_ids <- sort(unique(as.character(wide$fixture_id)))
  rows <- list()
  for (role in 1:3) {
    scored <- lapply(fixture_ids, function(fixture_id) {
      triple <- as.numeric(wide[wide$fixture_id == fixture_id, match_outcomes()])
      definition <- .parlay_role_definition(triple, role)
      tibble::tibble(
        fixture_id = fixture_id,
        role = as.integer(role),
        score = as.numeric(definition$score),
        retained_probability = as.numeric(definition$retained),
        allowed_outcomes = list(definition$allowed))
    })
    block <- dplyr::bind_rows(scored)
    # Score descending, ties by fixture_id. The comparison is NUMERIC on `score`;
    # sorting the `allowed_outcomes` strings instead would order role-3 rows by W/D/L
    # labels rather than by p3, which is the regression the contract forbids.
    block <- block[order(-block$score, block$fixture_id), , drop = FALSE]
    block$rank <- seq_len(nrow(block))
    rows[[length(rows) + 1L]] <- block
  }
  out <- dplyr::bind_rows(rows)
  out <- tibble::as_tibble(out[, c("fixture_id", "role", "score", "rank",
                                   "retained_probability", "allowed_outcomes")])
  out$role <- as.integer(out$role)
  out$rank <- as.integer(out$rank)
  do.call(structure, c(list(out), metadata))
}
