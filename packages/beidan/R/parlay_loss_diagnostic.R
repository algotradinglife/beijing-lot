# Issue #545 (26098 loss review): two label-free diagnostics over an already
# frozen decision. Both are pure: they read explicit frozen inputs, never fit,
# never read settlement, never advance a cutoff and never write anywhere.
#
#   .ParlayLossExposure(plan)                          -> fixture/outcome knockout stake
#   .ParlayLossMarketComparison(probabilities, sp, cutoff) -> model vs raw-SP ranking
#
# The point of putting these in the package (instead of the QMD) is that the
# boundary contracts and the chronology guard are the SAME ones the rest of the
# pipeline enforces, so a diagnostic can never quietly diverge from the ledger.

# --- shared diagnostics ------------------------------------------------------

#' Typed empty fixture/outcome knockout exposure
#'
#' @return Zero-row tibble with the exact schema returned by
#'   [.ParlayLossExposure()]; no side effects.
#' @noRd
.ParlayLossExposureEmpty <- function() {
  return(tibble::tibble(
    fixture_id = character(),
    outcome = character(),
    plan_stake_cny = double(),
    knockout_cny = double(),
    knockout_fraction = double(),
    surviving_cny = double()))
}

#' Directly-eliminated stake exposure of a frozen plan's actual purchases
#'
#' Internal, label-free diagnostic. For every admitted fixture and every Beidan handicap
#' W/D/L outcome it answers: if that outcome happens, how much of the plan's ACTUAL
#' purchased stake is already dead, because it sits on a physical ticket that
#' contains the fixture but selected a different outcome for it?
#'
#' Contract:
#' * `plan` is a frozen decision result as produced by [parlay_build_plan()] and
#'   accepted by [parlay_check_saved_result()]. That authoritative validator is
#'   the gate: identity, ledger reconciliation, history consistency and funded
#'   agreement are all re-checked here instead of being trusted from attributes.
#' * The fixture universe is the frozen `probabilities` table, so a fixture that
#'   is admitted but not bought is reported with zero exposure rather than
#'   silently dropped.
#' * Stakes are the actual `plan$plan$purchases$stake_cny` values, joined to the
#'   physical `ticket_legs` by `ticket_id`. A ticket contributes to `knockout_cny`
#'   for `(fixture, outcome)` exactly when it carries a leg on that fixture whose
#'   outcome differs; a ticket with no leg on the fixture is untouched and is part
#'   of `surviving_cny`. Because `ticket_legs` is keyed by `(ticket_id,
#'   fixture_id)`, a ticket can contribute at most once per `(fixture, outcome)`.
#' * `knockout_fraction` divides by the plan's TOTAL purchased stake (not by a
#'   per-fixture subtotal), so fractions across a column never add to one when a
#'   ticket covers several fixtures. `surviving_cny` is total minus knockout; it
#'   is explicitly NOT "wins" or "break-even".
#' * A plan with no purchases returns the typed empty table. Empty is a real
#'   answer here, not an error: an unfunded decision has no exposure to report.
#'
#' @param plan Frozen decision result. Must carry `plan`, `cutoff`, `history`,
#'   `funded`, `probabilities`, `built` and `ranked`, and must pass
#'   [parlay_check_saved_result()]. A bare frozen `plan` sub-list is not accepted.
#' @return A tibble with one row per `(fixture_id, outcome)` in fixture-major
#'   order and outcome order `W`, `D`, `L`:
#'   * `fixture_id` -- admitted fixture identifier, character;
#'   * `outcome` -- `W`, `D` or `L`;
#'   * `plan_stake_cny` -- total actual purchased stake in CNY, repeated per row;
#'   * `knockout_cny` -- purchased stake on tickets containing the fixture but
#'     selecting another outcome, in CNY;
#'   * `knockout_fraction` -- `knockout_cny / plan_stake_cny`, in `[0, 1]`;
#'   * `surviving_cny` -- `plan_stake_cny - knockout_cny`, in CNY.
#'   The zero-purchase case returns the same columns with zero rows.
#' @details Missing or duplicated ledger keys, a purchased ticket absent from the
#'   enumeration, a purchased ticket without legs, an illegal leg outcome, a
#'   ticket-leg fixture absent from the probabilities, and stakes that are not a
#'   positive whole number of frozen `unit_cny` units all fail closed. No
#'   settlement, fitting, cache, network or write is touched. This is a
#'   retrospective mechanism diagnostic: the fractions describe what the frozen
#'   plan already risked, not an expected return.
#' @noRd
.ParlayLossExposure <- function(plan) {
  # Authoritative frozen-result validation. Never re-implement it: the ledger,
  # history and funded reconciliation are exactly what makes the join below safe.
  parlay_check_saved_result(plan)
  settings <- plan$constants
  parlay_validate_settings(settings)
  if (!identical(settings, plan$plan$constants)) {
    stop(".ParlayLossExposure: frozen result and plan settings disagree")
  }
  probabilities <- match_validate_table(plan$probabilities, "probabilities",
    keys = c("fixture_id", "outcome"))
  match_check_character_id(probabilities$fixture_id, "fixture_id")
  if (anyNA(probabilities$outcome) ||
      any(!probabilities$outcome %in% match_outcomes())) {
    stop(".ParlayLossExposure: invalid probability outcomes")
  }
  if (is.object(probabilities$probability) ||
      !is.null(dim(probabilities$probability))) {
    stop(".ParlayLossExposure: probabilities must be plain numeric")
  }
  # Shared probability contract: exact W/D/L coverage per fixture and sum one.
  parlay_probability_wide(probabilities)

  tickets <- match_validate_table(plan$plan$tickets, "tickets", keys = "ticket_id")
  legs <- match_validate_table(plan$plan$ticket_legs, "ticket_legs",
    keys = c("ticket_id", "fixture_id"))
  purchases <- match_validate_table(plan$plan$purchases, "purchases",
    keys = "ticket_id")
  for (name in c("ticket_id", "group_id", "candidate_id")) {
    match_check_character_id(purchases[[name]], name)
  }
  # Same stake contract the frozen risk/prepare path enforces: real CNY, positive,
  # and a whole number of frozen unit_cny units.
  if (is.object(purchases$stake_cny) || !is.null(dim(purchases$stake_cny)) ||
      anyNA(purchases$stake_cny) || any(!is.finite(purchases$stake_cny)) ||
      any(purchases$stake_cny <= 0) ||
      any(abs(purchases$stake_cny / settings$unit_cny -
              round(purchases$stake_cny / settings$unit_cny)) > 1e-9)) {
    stop(".ParlayLossExposure: invalid purchased stake units")
  }
  if (!nrow(purchases)) return(.ParlayLossExposureEmpty())

  # Actual stakes join the physical ticket legs. A purchased ticket absent from
  # the enumeration, or with no legs at all, cannot be attributed to a fixture.
  if (anyNA(match(purchases$ticket_id, tickets$ticket_id))) {
    stop(".ParlayLossExposure: purchased physical ticket absent from frozen plan")
  }
  purchased_legs <- legs[legs$ticket_id %in% purchases$ticket_id, , drop = FALSE]
  if (!setequal(unique(purchased_legs$ticket_id), purchases$ticket_id)) {
    stop(".ParlayLossExposure: purchased ticket has no frozen legs")
  }
  if (anyNA(purchased_legs$outcome) ||
      any(!purchased_legs$outcome %in% match_outcomes())) {
    stop(".ParlayLossExposure: invalid ticket leg outcomes")
  }
  for (id in purchases$ticket_id) {
    one <- purchased_legs[purchased_legs$ticket_id == id, , drop = FALSE]
    if (nrow(one) != settings$n_legs || !identical(id,
        parlay_physical_ticket_key(one$fixture_id, match(one$outcome, match_outcomes())))) {
      stop(".ParlayLossExposure: physical ticket identity or leg count mismatch")
    }
    group <- purchases$group_id[match(id, purchases$ticket_id)]
    expected <- plan$plan$group_legs$fixture_id[plan$plan$group_legs$group_id == group]
    if (!setequal(one$fixture_id, expected)) stop(".ParlayLossExposure: ticket group fixture mismatch")
  }
  fixtures <- sort(unique(probabilities$fixture_id))
  if (any(!purchased_legs$fixture_id %in% fixtures)) {
    stop(".ParlayLossExposure: ticket leg fixture absent from probabilities")
  }

  joined <- dplyr::inner_join(
    purchased_legs[, c("ticket_id", "fixture_id", "outcome"), drop = FALSE],
    purchases[, c("ticket_id", "stake_cny"), drop = FALSE], by = "ticket_id", relationship = "many-to-one")
  total_stake <- sum(purchases$stake_cny)
  outcomes <- match_outcomes()
  grid <- tibble::tibble(
    fixture_id = rep(fixtures, each = length(outcomes)),
    outcome = rep(outcomes, times = length(fixtures)))
  # A ticket is knocked out for (fixture, outcome) when it carries that fixture
  # under any other outcome. Tickets without the fixture are not affected.
  knockout <- vapply(seq_len(nrow(grid)), function(i) {
    hit <- joined$fixture_id == grid$fixture_id[i] &
      joined$outcome != grid$outcome[i]
    sum(joined$stake_cny[hit])
  }, numeric(1))
  return(tibble::tibble(
    fixture_id = grid$fixture_id,
    outcome = grid$outcome,
    plan_stake_cny = total_stake,
    knockout_cny = knockout,
    knockout_fraction = knockout / total_stake,
    surviving_cny = total_stake - knockout))
}

#' Typed empty model-versus-SP ranking comparison
#'
#' @return Zero-row tibble with the exact schema returned by
#'   [.ParlayLossMarketComparison()]; no side effects.
#' @noRd
.ParlayLossMarketComparisonEmpty <- function() {
  return(tibble::tibble(
    fixture_id = character(),
    outcome = character(),
    model_probability = double(),
    model_rank = integer(),
    sp_raw = double(),
    sp_rank = integer(),
    disagreement = logical()))
}

#' Compare frozen W/D/L model probabilities with raw pre-match SP rankings
#'
#' Internal, label-free diagnostic. The model's own probability ordering and the
#' Beidan raw pre-match SP ordering are different signals; this table puts
#' them side by side per fixture and outcome without treating either as truth.
#'
#' Contract:
#' * `probabilities` is validated by [match_validate_table()] and
#'   [parlay_probability_wide()] (exact W/D/L rows, one probability per outcome,
#'   each fixture summing to one).
#' * `prematch_sp` is schema-validated by [match_validate_table()] and every
#'   `quote_at` must be present. The chosen quote is the LATEST one STRICTLY
#'   before `cutoff$cutoff_utc`, selected by the pipeline's authoritative
#'   [match_latest_quote_before()] primitive, which also refuses two different
#'   quotes at the selected latest `(fixture, outcome, instant)`. No private chronology code is
#'   introduced, and quotes at or after the cutoff are ignored, so the output is
#'   invariant to post-cutoff observations (this is verified by the tests).
#' * `model_rank` is 1 for the highest model probability; `sp_rank` is 1 for the
#'   LOWEST raw SP (shortest price = market favourite). Ties break
#'   deterministically `W`, then `D`, then `L`. A missing SP is `NA` and its
#'   `sp_rank` is `NA`; ranks of the remaining outcomes are computed among the
#'   outcomes that are present.
#' * `disagreement` is a fixture-level logical repeated on its three rows. It is
#'   `TRUE` when the fixture's model top-two outcome set is not the same set as
#'   the fixture's SP top-two outcome set, and `NA` whenever any of the fixture's
#'   three SP values is missing (an incomplete SP set cannot define a top two).
#'   It compares sets, so it is order- and tie-insensitive beyond the rank
#'   tie-break above.
#' * An empty probability table returns the typed empty table rather than an
#'   invented ranking.
#'
#' @param probabilities Authoritative W/D/L probability tibble with columns
#'   `fixture_id`, `outcome`, `probability`.
#' @param prematch_sp Pre-cutoff SP tibble (`fixture_id`, `outcome`, `quote_at`,
#'   `sp_raw`, `source_url`). Missing rows mean missing SP; a quote at or after
#'   `cutoff$cutoff_utc` is ignored, never selected.
#' @param cutoff Explicit shared decision cutoff (validated by
#'   [match_require_cutoff()]) with one UTC `cutoff_utc` and one `issue_id`.
#' @return A tibble with one row per `(fixture_id, outcome)`, ordered by
#'   `fixture_id` then `W`, `D`, `L`:
#'   * `fixture_id` -- character;
#'   * `outcome` -- `W`, `D` or `L`;
#'   * `model_probability` -- frozen model probability;
#'   * `model_rank` -- integer 1..3, descending probability;
#'   * `sp_raw` -- latest strictly pre-cutoff raw SP, or `NA`;
#'   * `sp_rank` -- integer rank, ascending raw SP, `NA` when `sp_raw` is `NA`;
#'   * `disagreement` -- fixture-level logical as described above.
#' @details This is a fixed-cutoff retrospective diagnostic. It never fits,
#'   values, settles, or writes, and it does not turn the SP reciprocal into a
#'   probability. The returned ranking is a descriptive alignment signal only.
#' @noRd
.ParlayLossMarketComparison <- function(probabilities, prematch_sp, cutoff) {
  match_require_cutoff(cutoff)
  probabilities <- match_validate_table(probabilities, "probabilities",
    keys = c("fixture_id", "outcome"))
  match_check_character_id(probabilities$fixture_id, "fixture_id")
  if (anyNA(probabilities$outcome) ||
      any(!probabilities$outcome %in% match_outcomes())) {
    stop(".ParlayLossMarketComparison: invalid probability outcomes")
  }
  if (is.object(probabilities$probability) ||
      !is.null(dim(probabilities$probability))) {
    stop(".ParlayLossMarketComparison: probabilities must be plain numeric")
  }
  parlay_probability_wide(probabilities)
  prematch_sp <- match_validate_table(prematch_sp, "prematch_sp")
  if (nrow(prematch_sp) && anyNA(prematch_sp$quote_at)) {
    stop(".ParlayLossMarketComparison: prematch_sp$quote_at must not be missing")
  }
  if (!nrow(probabilities)) return(.ParlayLossMarketComparisonEmpty())

  # Existing authoritative selection: latest quote strictly before the cutoff per
  # (fixture, outcome), refusing selected-latest-instant conflicts. Later quotes are dropped,
  # which is what makes the result invariant to post-cutoff observations.
  selected <- match_latest_quote_before(prematch_sp, cutoff$cutoff_utc, "sp_raw")

  long <- probabilities
  long$outcome_order <- match(long$outcome, match_outcomes())
  long <- long[order(long$fixture_id, long$outcome_order), , drop = FALSE]
  key_long <- paste(long$fixture_id, long$outcome, sep = "\r")
  key_sp <- paste(selected$fixture_id, selected$outcome, sep = "\r")
  long$sp_raw <- selected$sp_raw[match(key_long, key_sp)]
  long$model_probability <- as.double(long$probability)

  long <- long |>
    dplyr::group_by(fixture_id) |>
    dplyr::mutate(
      # Ties keep W before D before L because the group rows are already in
      # outcome order and ties.method = "first" preserves it.
      model_rank = as.integer(rank(-probability, ties.method = "first")),
      sp_rank = {
        ranks <- rep(NA_integer_, dplyr::n())
        present <- !is.na(sp_raw)
        if (any(present)) {
          ranks[present] <- as.integer(rank(sp_raw[present], ties.method = "first"))
        }
        ranks
      },
      disagreement = if (anyNA(sp_raw)) {
        NA
      } else {
        !setequal(outcome[order(model_rank)][seq_len(2L)],
                  outcome[order(sp_rank)][seq_len(2L)])
      }) |>
    dplyr::ungroup()

  return(tibble::as_tibble(long[, c("fixture_id", "outcome", "model_probability",
    "model_rank", "sp_raw", "sp_rank", "disagreement"), drop = FALSE]))
}
