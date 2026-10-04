# Post-settlement diagnosis: one call from a frozen evaluation plus its
# settlements to the realised returns and the per-leg coverage verdict.
#
# The two questions a settled decision has to answer are separate and this file
# keeps them separate:
#   * the LEDGER question -- what did the plan actually cost and return, settled
#     against labels that were visible at an explicit observation time;
#   * the COVERAGE question -- for every purchased leg, did the variant it bought
#     even admit the outcome that happened?
#
# A group whose legs all admit the realised outcomes should have won; a group with
# an unadmitted leg could not have won no matter how the tickets fell. Reporting
# the two together is what makes a miss attributable: a budget failure shows up as
# an unfunded ticket, a structural failure shows up as an unadmitted leg.

#' Typed-empty per-leg coverage verdict
#'
#' Internal. Keeps the full column set and types so an empty verdict binds with a
#' populated one and "no legs" stays distinguishable from "the wrong shape".
#' @return Zero-row tibble.
#' @noRd
.ParlayCoverageEmpty <- function() {
  return(tibble::tibble(
    group_id = character(), group_slot = integer(), leg_order = integer(),
    fixture_id = character(), selection_id = integer(), base_role = integer(),
    n_outcomes = integer(), allowed_outcomes = character(),
    actual_outcome = character(), admitted = logical(), reason = character()))
}

#' Typed-empty group outcome split
#'
#' Internal. One row per purchased group classifying it as won, missed by
#' structure or missed with every leg admitted.
#' @return Zero-row tibble.
#' @noRd
.ParlayGroupOutcomeEmpty <- function() {
  return(tibble::tibble(
    group_id = character(), group_slot = integer(), legs = integer(),
    unadmitted_legs = integer(), stake_cny = double(), payout_cny = double(),
    net_cny = double(), status = character()))
}

#' Diagnose a settled decision's returns and per-leg coverage in one call
#'
#' Settles the frozen `evaluation` against `settlements` as of `as_of`, then joins
#' every purchased leg back to the pool's authoritative mask to say whether the
#' variant that was bought admitted the realised outcome. Both halves are returned
#' so a miss can be attributed: a group that lost with every leg admitted is a leg
#' outcome that could not have been foreseen, while a group that lost because a
#' leg never admitted the realised outcome is a structural shortfall in the
#' candidate that was selected.
#'
#' `as_of` governs which labels may be consumed and is never defaulted to the clock:
#' a label whose `label_available_at` is later than `as_of` is invisible, so the
#' diagnosis cannot leak a result the decision could not have seen.
#' @param evaluation Frozen evaluation from [parlay_select_groups()] (its inner
#'   `evaluation`), carrying the `plan`, `purchases` and settled `summary`.
#' @param pool The candidate pool the evaluation was selected from. Its
#'   `role_legs` supplies the authoritative `allowed_outcomes` mask per leg.
#' @param settlements Validated settlement tibble (issue_id, fixture_id, outcome,
#'   settled_sp, label_available_at, status, source_url). Only rows visible at
#'   `as_of` are consumed.
#' @param as_of Single UTC `POSIXct` instant at which labels are observed.
#' @return Named list:
#'   * `issue_returns`, `group_returns`, `ticket_returns` -- the settled ledgers
#'     exactly as [parlay_settle_plan()] returns them;
#'   * `coverage` -- one row per purchased leg with the bought mask, the realised
#'     outcome and a logical `admitted`;
#'   * `group_outcomes` -- one row per purchased group with its leg count, its
#'     unadmitted-leg count, settled stake/payout and a `status` of `won`,
#'     `missed_structure` (at least one leg never admitted the realised outcome) or
#'     `missed_admitted` (every leg admitted it, yet the group still lost);
#'   * `summary` -- one-row tibble of stake, payout, net, ROI and the leg/group
#'     tallies.
#' @section Errors:
#' A missing `plan`/`purchases` block, a `pool` without `role_legs`, a fixture the
#' pool does not carry, an unknown realised outcome, or a leg whose pool mask is
#' absent all fail closed rather than reporting a partial diagnosis.
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
#' matches <- tibble::tibble(
#'   fixture_id = c("A", "B"), win = c(0.45, 0.40), draw = c(0.30, 0.30),
#'   lose = c(0.25, 0.30))
#' ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
#' settings <- parlay_settings()
#' settings$n_legs <- 2L
#' pool <- parlay_construct_role_groups(ranked, settings, pattern = c(3L, 2L),
#'                                      max_candidates = 2L)
#' evaluation <- parlay_select_groups(pool, objective = "coverage",
#'   budget_cny = NULL, group_budget_cny = 4,
#'   reuse_policy = list(max_reuse = NULL),
#'   overlap_policy = list(max_overlap = NULL))$evaluation
#' settlements <- tibble::tibble(
#'   issue_id = "26098", fixture_id = c("A", "B"), outcome = c("W", "D"),
#'   settled_sp = c(2.5, 3.1),
#'   label_available_at = as.POSIXct("2026-09-26 14:00:00", tz = "UTC"),
#'   status = "settled", source_url = "https://example.test/s")
#' parlay_diagnose_settlement(evaluation, pool, settlements,
#'   as_of = as.POSIXct("2026-09-26 15:00:00", tz = "UTC"))$summary
#' @export
parlay_diagnose_settlement <- function(evaluation, pool, settlements, as_of) {
  if (!is.list(evaluation) || is.null(evaluation$plan) ||
      is.null(evaluation$purchases)) {
    stop("parlay_diagnose_settlement: evaluation must carry a frozen plan and ",
         "purchases; pass the evaluation returned by parlay_select_groups()")
  }
  if (!is.list(pool) || is.null(pool$role_legs)) {
    stop("parlay_diagnose_settlement: pool must carry role_legs masks")
  }
  if (!inherits(as_of, "POSIXct") || is.null(as_of) ||
      !identical(attr(as_of, "tzone"), "UTC")) {
    stop("parlay_diagnose_settlement: as_of must be a UTC POSIXct instant")
  }
  match_validate_table(settlements, "settlements")

  settled <- parlay_settle_plan(evaluation$plan, settlements, as_of)

  plan <- evaluation$plan
  purchases <- evaluation$purchases
  role_legs <- pool$role_legs
  group_legs <- plan$group_legs
  ticket_legs <- plan$ticket_legs

  # Only labels actually visible at as_of may be used. `parlay_settle_plan` applies
  # the same rule internally; repeating the filter here keeps the legality check in
  # this function's own hands rather than inheriting it by accident.
  visible <- settlements[!is.na(settlements$label_available_at) &
                           settlements$label_available_at <= as_of, , drop = FALSE]
  # One realised outcome per fixture. A fixture carries exactly one result, so a
  # conflicting second label is a broken input rather than a row to pick from.
  realised <- visible[visible$status == "settled", , drop = FALSE]
  if (anyDuplicated(realised$fixture_id)) {
    duplicated_ids <- unique(realised$fixture_id[duplicated(realised$fixture_id)])
    stop("parlay_diagnose_settlement: fixture(s) carry more than one settled ",
         "outcome: ", paste(utils::head(duplicated_ids, 5L), collapse = ", "))
  }
  outcome_of <- stats::setNames(as.character(realised$outcome), realised$fixture_id)
  unknown <- setdiff(unique(outcome_of), match_outcomes())
  if (length(unknown) > 0L) {
    stop("parlay_diagnose_settlement: unknown realised outcome(s): ",
         paste(utils::head(unknown, 5L), collapse = ", "))
  }

  # One verdict per GROUP LEG, not per ticket: a group's 128 tickets all share the
  # same legs, so expanding per purchase row would repeat the same verdict 128
  # times and inflate every tally.
  purchased_groups <- unique(as.character(purchases$group_id))
  if (length(purchased_groups) == 0L) {
    coverage <- .ParlayCoverageEmpty()
  } else {
    coverage <- lapply(purchased_groups, function(group_id) {
      legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
      lapply(seq_len(nrow(legs)), function(j) {
        fixture_id <- as.character(legs$fixture_id[j])
        mask_index <- which(role_legs$group_id == group_id &
                              role_legs$fixture_id == fixture_id)
        if (length(mask_index) == 0L) {
          stop("parlay_diagnose_settlement: pool carries no mask for group ",
               group_id, " fixture ", fixture_id)
        }
        mask <- as.character(role_legs$allowed_outcomes[[mask_index[1]]])
        if (!fixture_id %in% names(outcome_of)) {
          return(tibble::tibble(group_id = group_id,
            group_slot = as.integer(role_legs$group_slot[mask_index[1]]),
            leg_order = as.integer(legs$leg_order[j]), fixture_id = fixture_id,
            selection_id = as.integer(role_legs$selection_id[mask_index[1]]),
            base_role = as.integer(role_legs$base_role[mask_index[1]]),
            n_outcomes = as.integer(role_legs$n_outcomes[mask_index[1]]),
            allowed_outcomes = paste(mask, collapse = "+"),
            actual_outcome = NA_character_, admitted = NA,
            reason = "not_settled"))
        }
        actual <- unname(outcome_of[[fixture_id]])
        tibble::tibble(group_id = group_id,
          group_slot = as.integer(role_legs$group_slot[mask_index[1]]),
          leg_order = as.integer(legs$leg_order[j]), fixture_id = fixture_id,
          selection_id = as.integer(role_legs$selection_id[mask_index[1]]),
          base_role = as.integer(role_legs$base_role[mask_index[1]]),
          n_outcomes = as.integer(role_legs$n_outcomes[mask_index[1]]),
          allowed_outcomes = paste(mask, collapse = "+"),
          actual_outcome = actual, admitted = actual %in% mask,
          reason = if (actual %in% mask) "admitted" else "unadmitted_outcome")
      }) |> dplyr::bind_rows()
    }) |> dplyr::bind_rows()
  }

  returns <- settled$group_returns
  group_outcomes <- if (nrow(returns) == 0L) {
    .ParlayGroupOutcomeEmpty()
  } else {
    tallies <- if (nrow(coverage) == 0L) {
      tibble::tibble(group_id = character(), legs = integer(),
                     unadmitted_legs = integer(), unsettled_legs = integer())
    } else {
      coverage |>
        dplyr::group_by(group_id) |>
        dplyr::summarise(legs = dplyr::n(),
          unadmitted_legs = sum(!is.na(admitted) & !admitted),
          unsettled_legs = sum(is.na(admitted)), .groups = "drop")
    }
    slots <- dplyr::distinct(purchases, group_id, group_slot)
    dplyr::left_join(returns, tallies, by = "group_id") |>
      dplyr::left_join(slots, by = "group_id") |>
      dplyr::mutate(
        legs = dplyr::if_else(is.na(legs), 0L, legs),
        unadmitted_legs = dplyr::if_else(is.na(unadmitted_legs), 0L, unadmitted_legs),
        unsettled_legs = dplyr::if_else(is.na(unsettled_legs), 0L, unsettled_legs),
        status = dplyr::case_when(
          payout_cny > 0 ~ "won",
          unsettled_legs > 0L ~ "unsettled",
          unadmitted_legs > 0L ~ "missed_structure",
          TRUE ~ "missed_admitted")) |>
      dplyr::transmute(group_id, group_slot, legs, unadmitted_legs,
        stake_cny, payout_cny, net_cny, status)
  }

  issue <- settled$issue_returns
  tally <- if (nrow(group_outcomes) == 0L) {
    c(groups = 0L, won = 0L, missed_structure = 0L, missed_admitted = 0L,
      unadmitted_legs = 0L)
  } else {
    c(groups = nrow(group_outcomes),
      won = sum(group_outcomes$status == "won"),
      missed_structure = sum(group_outcomes$status == "missed_structure"),
      missed_admitted = sum(group_outcomes$status == "missed_admitted"),
      unadmitted_legs = sum(group_outcomes$unadmitted_legs))
  }
  summary <- tibble::tibble(
    issue_id = if (nrow(issue)) issue$issue_id[1] else NA_character_,
    stake_cny = if (nrow(issue)) issue$stake_cny[1] else 0,
    payout_cny = if (nrow(issue)) issue$payout_cny[1] else 0,
    net_cny = if (nrow(issue)) issue$net_cny[1] else 0,
    roi = if (nrow(issue)) issue$roi[1] else NA_real_,
    groups = as.integer(tally[["groups"]]),
    won_groups = as.integer(tally[["won"]]),
    missed_structure = as.integer(tally[["missed_structure"]]),
    missed_admitted = as.integer(tally[["missed_admitted"]]),
    legs = as.integer(if (nrow(coverage)) nrow(coverage) else 0L),
    unadmitted_legs = as.integer(tally[["unadmitted_legs"]]))

  return(list(issue_returns = settled$issue_returns,
    group_returns = settled$group_returns, ticket_returns = settled$ticket_returns,
    coverage = coverage, group_outcomes = group_outcomes, summary = summary))
}
