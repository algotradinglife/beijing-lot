# The N7 minimal replay: turn one decision epoch's available quotes into a
# frozen, settled set of seven-fixture groups, and score it.
#
# Pipeline, in the order the contract fixes it:
#   source snapshot -> probability -> candidate -> legal TopK -> period budget /
#   constraint check -> freeze -> settle -> QMD
#
# Required sources (the repo has no package namespace; callers source these in
# order, as r/fundamentals_total_market.R already assumes of its helpers):
#   r/dixon_coles_grid.R           dc_validate_rho, dixon_coles_score_grid
#   r/joint_basket_dc_fit.R        jc_devig, jc_fit_rates_free, jc_rates_at_handicap
#   r/n7_fixture_portfolio.R       grid, ranking, TopK funding, coverage, groups
#   r/n7_experiment_contract.R     epochs, eligibility, snapshots, budget, admission
#
# No function here reads a database, a file, or the settlement of a period whose
# selection it influences. Settlement enters only after the ticket set is frozen.

# ---- Probability base --------------------------------------------------------

# De-vig the average European 1X2 of one priced snapshot and read the resulting
# Dixon-Coles score grid at the fixture's own 北单 handicap line.
#
# Why the fit is free (1X2 only): the European market carries no handicap, so it
# constrains the two goal rates on the zero line and the total is a by-product.
# The 北单 handicap is applied afterwards, when the same fitted grid is read at
# the fixture's line. No total-goals market is used, so no over/under input is
# invented; when a caller does have one it should fit with jc_fit_rates instead
# and pass the resulting rates here.
#
# Returns list(probabilities = <tibble>, excluded = <tibble>). A fixture whose
# fit residual exceeds `max_residual` is excluded rather than silently priced:
# a contradictory market is a fitting failure, not a signal.
n7_euro_probabilities <- function(priced, fixtures, rho,
                                  tail_tolerance = 1e-6, max_residual = 0.02,
                                  total_range = c(0.5, 8)) {
  if (!is.data.frame(priced) || !all(c("match_id", "issue", "epoch_utc",
                                       "eu_h", "eu_d", "eu_a",
                                       "sp_3", "sp_1", "sp_0") %in% names(priced))) {
    stop("n7_euro_probabilities: priced needs match_id, issue, epoch_utc, eu_h, eu_d, eu_a, sp_3, sp_1, sp_0")
  }
  if (!is.data.frame(fixtures) || !all(c("match_id", "handicap_line") %in% names(fixtures))) {
    stop("n7_euro_probabilities: fixtures needs match_id and handicap_line")
  }
  if (!is.character(fixtures$match_id) || anyNA(fixtures$match_id) ||
      anyDuplicated(fixtures$match_id)) {
    stop("n7_euro_probabilities: fixtures$match_id must be unique and non-missing")
  }
  if (!is.numeric(fixtures$handicap_line) || anyNA(fixtures$handicap_line) ||
      any(!is.finite(fixtures$handicap_line))) {
    stop("n7_euro_probabilities: every fixture needs a finite handicap_line")
  }
  dc_validate_rho(rho)
  if (length(max_residual) != 1L || !is.finite(max_residual) || max_residual <= 0) {
    stop("n7_euro_probabilities: max_residual must be one positive finite value")
  }
  probabilities <- excluded <- list()
  for (i in seq_len(nrow(priced))) {
    row <- priced[i, ]
    index <- match(row$match_id, fixtures$match_id)
    if (is.na(index)) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = row$match_id, issue = row$issue, reason = "FIXTURE_NOT_IN_MATCH_TABLE")
      next
    }
    target <- jc_devig(c(row$eu_h, row$eu_d, row$eu_a))
    if (anyNA(target)) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = row$match_id, issue = row$issue, reason = "ODDS_NOT_DEVIGGABLE")
      next
    }
    handicap <- fixtures$handicap_line[index]
    if (handicap != as.integer(handicap)) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = row$match_id, issue = row$issue, reason = "NON_INTEGER_HANDICAP_LINE")
      next
    }
    fit <- tryCatch(
      jc_fit_rates_free(target, rho, total_range = total_range,
                        tail_tolerance = tail_tolerance),
      error = function(e) NULL)
    if (is.null(fit)) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = row$match_id, issue = row$issue, reason = "DIXON_COLES_FIT_FAILED")
      next
    }
    if (fit$residual > max_residual) {
      excluded[[length(excluded) + 1L]] <- tibble::tibble(
        match_id = row$match_id, issue = row$issue, reason = "FIT_RESIDUAL_EXCEEDED")
      next
    }
    p <- jc_rates_at_handicap(fit$lambda_home, fit$lambda_away,
                              as.integer(handicap), rho, tail_tolerance)
    probabilities[[length(probabilities) + 1L]] <- tibble::tibble(
      match_id = row$match_id, issue = row$issue, epoch_utc = row$epoch_utc,
      p_W = unname(p[["W"]]), p_D = unname(p[["D"]]), p_L = unname(p[["L"]]),
      lambda_home = fit$lambda_home, lambda_away = fit$lambda_away,
      expected_total = fit$expected_total, fit_residual = fit$residual,
      rho = rho,
      # Carried through from the priced poll for the ESTIMATED-return view only.
      # Never an input to p_W/p_D/p_L and never an input to settlement.
      sp_3 = row$sp_3, sp_1 = row$sp_1, sp_0 = row$sp_0)
  }
  template <- n7_contract_templates()$probabilities
  excluded_template <- tibble::tibble(match_id = character(), issue = character(),
                                      reason = character())
  list(probabilities = dplyr::bind_rows(template, probabilities),
       excluded = dplyr::bind_rows(excluded_template, excluded))
}

# The probability matrix in the column order the construction module requires:
# one row per fixture, columns W/D/L, so grid outcome code 1 is W, 2 is D, 3 is L.
n7_probability_matrix <- function(probabilities) {
  if (!is.data.frame(probabilities) || !all(c("p_W", "p_D", "p_L") %in% names(probabilities))) {
    stop("n7_probability_matrix: probabilities needs p_W, p_D, p_L")
  }
  n7_check_probabilities(as.matrix(probabilities[, c("p_W", "p_D", "p_L")]))
}

# ---- Candidate construction and legal TopK funding --------------------------

# Build the groups for one epoch out of EVERY eligible fixture. The pool is the
# eligible set itself, so no earlier strategy's candidate list can narrow it.
# Ranking and the balance heuristic come from r/n7_fixture_portfolio.R.
n7_build_groups <- function(probabilities, n_groups, max_reuse, max_overlap,
                            seed = 1L) {
  p <- n7_probability_matrix(probabilities)
  ids <- as.character(probabilities$match_id)
  if (nrow(p) < N7_LEGS) {
    stop("n7_build_groups: fewer eligible fixtures than one group needs")
  }
  groups <- n7_balance_groups(p, n_groups, legs = N7_LEGS,
                              max_uses = max_reuse, max_overlap = max_overlap,
                              seed = seed)
  lapply(groups, function(rows) ids[rows])
}

# Fund the top-K legal combinations of one group by ORIGINAL combination
# probability, with no renormalisation after masking. A group with fewer than K
# legal combinations funds all of them; it is never padded.
n7_fund_group <- function(probabilities, group_ids, tickets, blocked = NULL) {
  index <- match(group_ids, as.character(probabilities$match_id))
  if (anyNA(index)) stop("n7_fund_group: group member is not in the probability table")
  if (length(unique(index)) != N7_LEGS) {
    stop("n7_fund_group: a group must hold 7 distinct fixtures")
  }
  p_group <- n7_probability_matrix(probabilities[index, , drop = FALSE])
  available <- if (is.null(blocked)) N7_COMBINATIONS else n7_available_combos(blocked)
  funded <- min(as.integer(tickets), available)
  selected <- n7_select_tickets(p_group, funded, blocked = blocked)
  grid <- n7_combo_grid()
  keys <- vapply(seq_along(selected), function(i)
    n7_physical_ticket_key(group_ids, grid[selected[i], ]), character(1L))
  if (anyDuplicated(keys)) stop("n7_fund_group: the funded set repeats a physical ticket")
  tibble::tibble(
    combo_row = as.integer(selected),
    ticket_key = keys,
    probability = vapply(seq_along(selected), function(i)
      prod(vapply(seq_len(N7_LEGS),
                  function(leg) p_group[leg, grid[selected[i], leg]], numeric(1L))),
      numeric(1L)))
}

# ---- Settlement --------------------------------------------------------------

# Map a settled 北单 result code onto the grid outcome code used everywhere else.
# 北单 让球胜平负 is recorded after the handicap, so no handicap is reapplied
# here; this is a pure relabelling and the mapping is asserted in the tests.
n7_outcome_code <- function(result_code) {
  if (!is.character(result_code)) stop("n7_outcome_code: result_code must be character")
  mapping <- c("3" = 1L, "1" = 2L, "0" = 3L)
  out <- unname(mapping[result_code])
  if (anyNA(out)) {
    stop("n7_outcome_code: unknown result_code value(s): ",
         paste(unique(result_code[is.na(out)]), collapse = ", "))
  }
  as.integer(out)
}

# Settle a frozen ticket set against the authoritative settlement table.
#
#   * hit       — the settled outcome tuple is one of the funded tickets
#   * settleable— every one of the seven legs carries a usable actual SP
#   * payout    — 2 CNY * 0.65 * prod(actual SP of the seven legs), applied ONCE
#                 at the complete-ticket level, and only when hit
#
# A group that is not settleable is NOT counted as a loss: its payout is NA and
# the caller excludes it from the return denominator explicitly. An un-hit group
# is a real loss of its stake and is kept.
n7_settle_group <- function(probabilities, group_ids, tickets, settlement,
                            blocked = NULL, unit_cny = N7_UNIT_CNY,
                            payout_factor = N7_PAYOUT_FACTOR) {
  if (!is.data.frame(tickets) || !all(c("combo_row", "ticket_key") %in% names(tickets))) {
    stop("n7_settle_group: tickets needs combo_row and ticket_key")
  }
  if (!is.data.frame(settlement) || !all(c("match_id", "result_code", "winning_sp") %in%
                                         names(settlement))) {
    stop("n7_settle_group: settlement needs match_id, result_code, winning_sp")
  }
  if (anyDuplicated(settlement$match_id)) {
    stop("n7_settle_group: settlement must hold one row per match_id")
  }
  if (unit_cny != 2) stop("n7_settle_group: unit_cny must be 2 CNY")
  if (abs(payout_factor - N7_PAYOUT_FACTOR) > 1e-12) {
    stop("n7_settle_group: payout_factor must be 0.65")
  }
  index <- match(group_ids, settlement$match_id)
  # A group member with no settlement row at all is a structural failure, not a
  # recorded absence: it fails closed. A row that exists but records no SP is the
  # recorded absence, handled below as un-settleable.
  if (anyNA(index)) {
    stop("n7_settle_group: ", sum(is.na(index)),
         " group member(s) have no settlement row at all")
  }
  true_outcomes <- n7_outcome_code(settlement$result_code[index])
  true_row <- n7_combo_index(true_outcomes)
  covered <- !is.na(true_row) && true_row %in% tickets$combo_row
  # Depth: where the realised tuple sits in the group's own probability order,
  # 1 being the most likely of the 3^7 combinations. Reported so a low coverage
  # cannot hide behind a shallow-but-favoured construction.
  true_rank <- if (is.na(true_row)) NA_integer_ else n7_combination_rank(probabilities,
                                                                        group_ids, true_row)
  mask_excluded <- if (is.na(true_row) || is.null(blocked)) FALSE else {
    grid <- n7_combo_grid()
    any(vapply(seq_len(N7_LEGS),
               function(leg) blocked[leg, grid[true_row, leg]], logical(1L)))
  }
  leg_sp <- settlement$winning_sp[index]
  settleable <- all(is.finite(leg_sp)) && all(leg_sp > 0)
  # The payout arithmetic belongs to the authoritative settlement implementation,
  # not to this replay: a second copy of the 0.65 rule is a second place for it to
  # drift. This adapter only maps the result and decides whether the funded tuple
  # was the realised one.
  if (!exists("jb_basket_gross", mode = "function")) {
    stop("n7_settle_group: the authoritative jb_basket_gross() from ",
         "r/joint_basket_settlement.R must be sourced")
  }
  gross_if_hit <- if (!settleable) {
    NA_real_
  } else {
    jb_basket_gross(tibble::tibble(issue = "N7", basket = "G1",
                                   leg = seq_len(N7_LEGS), sp = leg_sp,
                                   tickets = nrow(tickets)),
                    unit_cny = unit_cny, payout_factor = payout_factor)$gross_if_hit
  }
  # An un-settleable group is not a loss, whether or not its tuple was funded, so
  # its payout is an explicit NA and the caller keeps it out of the denominator.
  payout <- if (!settleable) NA_real_ else if (covered) gross_if_hit else 0
  list(hit = isTRUE(covered), settleable = settleable, payout_cny = payout,
       true_combo_row = true_row, true_rank = true_rank,
       mask_excluded = isTRUE(mask_excluded))
}

# The decision-time ESTIMATED expected return of one funded group, under the fixed
# SP rule: keep the poll's own SP, except that a value above 10 is estimated at
# 4.5. This is a decision-time quantity only. It uses the poll's SP, never the
# settled SP, so it can never be confused with the realised return, and the
# estimate is never an input to a probability.
#
# Returns NA when any leg of the group has no decision-time SP: a partial estimate
# would be a made-up number.
n7_estimated_expected_return <- function(priced, group_ids, funded, unit_cny = N7_UNIT_CNY,
                                         payout_factor = N7_PAYOUT_FACTOR) {
  index <- match(group_ids, as.character(priced$match_id))
  if (anyNA(index)) stop("n7_estimated_expected_return: group member has no priced poll")
  sp <- rbind(n7_sp_estimate(priced$sp_3[index]), n7_sp_estimate(priced$sp_1[index]),
              n7_sp_estimate(priced$sp_0[index]))
  if (anyNA(sp)) return(NA_real_)
  grid <- n7_combo_grid()
  rows <- grid[funded$combo_row, , drop = FALSE]
  # Built explicitly rather than with vapply, because vapply simplifies to a bare
  # vector when a group funds exactly one ticket and apply() would then fail. A
  # one-ticket group is legal (a masked group can leave a single combination).
  leg_sp <- matrix(NA_real_, nrow = nrow(rows), ncol = N7_LEGS)
  for (leg in seq_len(N7_LEGS)) leg_sp[, leg] <- sp[rows[, leg], leg]
  payout <- unit_cny * payout_factor * apply(leg_sp, 1L, prod)
  sum(funded$probability * payout)
}

# Rank of one combination of one group among all 3^7 combinations, ordered by the
# group's own probability, 1 being the most likely. The ranking uses the ORIGINAL
# per-leg probabilities with no renormalisation, so it is the same order the
# funding rule uses.
n7_combination_rank <- function(probabilities, group_ids, combo_row) {
  index <- match(group_ids, as.character(probabilities$match_id))
  if (anyNA(index)) stop("n7_combination_rank: group member not in the probability table")
  p_group <- n7_probability_matrix(probabilities[index, , drop = FALSE])
  grid <- n7_combo_grid()
  log_p <- rep(0, nrow(grid))
  for (leg in seq_len(N7_LEGS)) log_p <- log_p + log(p_group[leg, grid[, leg]])
  order(order(log_p, decreasing = TRUE))[combo_row]
}

# ---- One period's plan -------------------------------------------------------

# Walk one period's decision epochs in order and buy as much of the period plan as
# the remaining budget and the epoch's own priced pool allow.
#
# The plan is a PERIOD plan: `group_tickets` lists the ticket count of each group
# the period intends to open, in order, and the period budget is shared across
# every epoch. This is what makes the cross-day rules real:
#   * the balance is not reset per day,
#   * an epoch whose pool has fewer than seven priced fixtures opens nothing and
#     records INSUFFICIENT_PRICED_FIXTURES,
#   * an epoch that can no longer afford its next group records BUDGET_EXHAUSTED,
#   * a period that ends with cash left records the cash rather than forcing a bet.
#
# Returns list(groups, tickets, settled, ledger) with one row per opened group and
# one ledger row per epoch, including the epochs that bought nothing.
n7_run_period_plan <- function(epoch_utc, probabilities, settlement, group_tickets,
                               max_reuse, max_overlap,
                               budget_cny = N7_PERIOD_BUDGET_CNY,
                               unit_cny = N7_UNIT_CNY, seed = 1L,
                               issue = NA_character_, structure = "unnamed") {
  if (!is.character(epoch_utc) || !length(epoch_utc) || anyNA(epoch_utc) ||
      anyDuplicated(epoch_utc)) {
    stop("n7_run_period_plan: epoch_utc must be unique, non-missing, non-empty")
  }
  if (is.unsorted(epoch_utc)) stop("n7_run_period_plan: epoch_utc must be in order")
  if (!is.numeric(group_tickets) || !length(group_tickets) || anyNA(group_tickets) ||
      any(group_tickets != trunc(group_tickets)) || any(group_tickets < 1)) {
    stop("n7_run_period_plan: group_tickets must be whole positive ticket counts")
  }
  if (!is.data.frame(probabilities) || !all(c("match_id", "epoch_utc", "p_W", "p_D", "p_L") %in%
                                            names(probabilities))) {
    stop("n7_run_period_plan: probabilities needs match_id, epoch_utc, p_W, p_D, p_L")
  }
  n_groups <- length(group_tickets)
  opened <- list(); ticket_keys <- character(0); stakes <- numeric(0)
  groups_out <- list(); tickets_out <- list(); settled_out <- list(); ledger <- list()
  group_index <- 0L
  for (e in seq_along(epoch_utc)) {
    epoch <- epoch_utc[e]
    remaining <- budget_cny - sum(stakes)
    plan_remaining <- n_groups - group_index
    pool <- probabilities[probabilities$epoch_utc == epoch, , drop = FALSE]
    capacity <- floor(nrow(pool) / N7_LEGS)
    # Affordability is cumulative over the groups this epoch would actually open.
    # The planned groups have DIFFERENT sizes, so testing only the next group's
    # ticket count against the balance would let a mixed plan spend past the
    # ceiling; each further group is therefore checked against what is still left.
    take <- 0L
    planned <- 0
    for (k in seq_len(min(plan_remaining, capacity))) {
      cost <- group_tickets[group_index + k] * unit_cny
      if (planned + cost > remaining) break
      planned <- planned + cost
      take <- k
    }
    reason <- if (plan_remaining <= 0L) "PLAN_COMPLETE"
      else if (capacity < 1L) "INSUFFICIENT_PRICED_FIXTURES"
      else if (take < 1L) "BUDGET_EXHAUSTED"
      else "OPENED_GROUPS"
    if (take < 1L) {
      ledger[[length(ledger) + 1L]] <- tibble::tibble(
        structure = structure, issue = issue, epoch_utc = epoch,
        n_priced = nrow(pool), groups_opened = 0L, tickets = 0L, stake_cny = 0,
        remaining_after_cny = remaining, reason = reason)
      next
    }
    built <- n7_build_groups(pool, take, max_reuse, max_overlap, seed = seed)
    epoch_stake <- 0
    for (g in seq_along(built)) {
      ids <- built[[g]]
      admission <- n7_group_admission(opened, ids, max_reuse, max_overlap)
      if (!admission$admitted) {
        stop("n7_run_period_plan: group refused by admission: ", admission$reason)
      }
      group_index <- group_index + 1L
      funded <- n7_fund_group(pool, ids, group_tickets[group_index])
      repeated <- n7_ticket_admission(ticket_keys, funded$ticket_key)
      if (any(repeated$duplicate_of_period)) {
        stop("n7_run_period_plan: a physical ticket would be bought twice in one period")
      }
      ticket_keys <- c(ticket_keys, funded$ticket_key)
      opened[[length(opened) + 1L]] <- ids
      stake <- n7_stake_cny(nrow(funded), unit_cny)
      # The planned cost and the actual cost agree because funding never exceeds
      # the requested ticket count, but the ceiling is asserted per purchase so a
      # negative balance can never be reported as a normal result.
      if (stake > budget_cny - sum(stakes)) {
        stop("n7_run_period_plan: the period ceiling would be exceeded")
      }
      stakes <- c(stakes, stake)
      epoch_stake <- epoch_stake + stake
      group_key <- n7_group_key(ids)
      # A decision-time quantity: it uses the poll's own SP under the fixed rule and
      # never the settled SP, so it is comparable across structures without being
      # confusable with the realised return.
      estimated <- n7_estimated_expected_return(pool, ids, funded, unit_cny)
      groups_out[[length(groups_out) + 1L]] <- tibble::tibble(
        structure = structure, issue = issue, epoch_utc = epoch, group = group_index,
        group_key = group_key, tickets = nrow(funded), stake_cny = stake,
        max_uses_after = admission$max_uses_after,
        max_overlap_seen = admission$max_overlap_seen)
      tickets_out[[length(tickets_out) + 1L]] <- tibble::tibble(
        structure = structure, issue = issue, epoch_utc = epoch, group = group_index,
        group_key = group_key, ticket_key = funded$ticket_key,
        combo_row = funded$combo_row, probability = funded$probability)
      # A leg with no settlement row at all is a structural gap, not a recorded
      # absence: the group is kept but marked un-settleable, never a loss, and its
      # outcome is UNKNOWN so it must stay out of the coverage denominator.
      if (!all(ids %in% settlement$match_id)) {
        settled_out[[length(settled_out) + 1L]] <- tibble::tibble(
          structure = structure, issue = issue, epoch_utc = epoch, group = group_index,
          group_key = group_key, tickets = nrow(funded), cost_cny = stake,
          settleable = FALSE, outcome_known = FALSE, hit = FALSE, payout_cny = NA_real_,
          estimated_expected_return_cny = estimated,
          true_rank = NA_integer_, covered = FALSE, mask_excluded = FALSE,
          reason = "NO_SETTLEMENT_ROW_FOR_A_LEG")
      } else {
        settled <- n7_settle_group(pool, ids, funded, settlement)
        settled_out[[length(settled_out) + 1L]] <- tibble::tibble(
          structure = structure, issue = issue, epoch_utc = epoch, group = group_index,
          group_key = group_key, tickets = nrow(funded), cost_cny = stake,
          settleable = settled$settleable, outcome_known = TRUE, hit = settled$hit,
          payout_cny = settled$payout_cny,
          estimated_expected_return_cny = estimated,
          true_rank = settled$true_rank,
          covered = settled$hit, mask_excluded = settled$mask_excluded,
          reason = if (settled$settleable) "SETTLED" else "MISSING_ACTUAL_SP")
      }
    }
    ledger[[length(ledger) + 1L]] <- tibble::tibble(
      structure = structure, issue = issue, epoch_utc = epoch, n_priced = nrow(pool),
      groups_opened = length(built), tickets = as.integer(round(epoch_stake / unit_cny)),
      stake_cny = epoch_stake, remaining_after_cny = budget_cny - sum(stakes),
      reason = reason)
  }
  # Typed templates, so a period that buys nothing still returns the contract's
  # schemas instead of the zero-column tibbles bind_rows() would produce.
  templates <- n7_contract_templates()
  list(groups = dplyr::bind_rows(templates$groups, groups_out),
       tickets = dplyr::bind_rows(templates$tickets, tickets_out),
       settled = dplyr::bind_rows(templates$settlements, settled_out),
       ledger = dplyr::bind_rows(templates$ledger, ledger))
}

# ---- Metrics -----------------------------------------------------------------

# Absolute drawdown of a cumulative net-return path, in CNY. The path is
# cumulative net (payout minus stake) in epoch order; the drawdown is the largest
# peak-to-trough fall. No starting capital is assumed, so this is an absolute
# figure and not a percentage.
n7_absolute_drawdown <- function(path_cny) {
  if (!is.numeric(path_cny) || anyNA(path_cny) || any(!is.finite(path_cny))) {
    stop("n7_absolute_drawdown: path_cny must be finite numeric")
  }
  if (!length(path_cny)) return(0)
  # Running peak measured from a notional start of zero, so a path that only ever
  # loses has a drawdown equal to its worst cumulative loss.
  peak <- cummax(c(0, path_cny))[-1L]
  max(0, max(peak - path_cny))
}

# The headline metrics the contract asks to be shown side by side. Coverage
# depth, payout concentration and support counts are reported next to the return
# so that a positive return cannot be read without its support.
#
# Return uses only settleable groups in the denominator, and reports the
# excluded cost separately; the stake of an un-settleable group is not a loss.
n7_experiment_metrics <- function(settled) {
  required <- c("issue", "epoch_utc", "group", "tickets", "cost_cny",
                "settleable", "outcome_known", "hit", "payout_cny",
                "estimated_expected_return_cny", "true_rank", "covered",
                "mask_excluded")
  if (!is.data.frame(settled) || !all(required %in% names(settled)) || !nrow(settled)) {
    stop("n7_experiment_metrics: settled needs ", paste(required, collapse = ", "),
         " and at least one row")
  }
  if (anyNA(settled$cost_cny) || any(settled$cost_cny <= 0)) {
    stop("n7_experiment_metrics: cost_cny must be positive and non-missing")
  }
  if (anyNA(settled$settleable) || anyNA(settled$outcome_known) || anyNA(settled$hit) ||
      anyNA(settled$covered) || anyNA(settled$mask_excluded)) {
    stop("n7_experiment_metrics: settleable, outcome_known, hit, covered and ",
         "mask_excluded must not be missing")
  }
  # A group with no settlement row has an UNKNOWN outcome. Counting it as a
  # coverage miss would let adding an unobservable group lower the reported
  # coverage rate, so coverage is computed over the known-outcome groups only.
  known <- settled[settled$outcome_known, , drop = FALSE]
  # A portfolio in which NOTHING has settled yet is still a valid position: its
  # stake is spent and its result is undetermined. Aborting here would make the
  # required money report unavailable exactly when "undetermined" matters most, so
  # the known-outcome measures degrade to NA instead.
  priced <- settled[settled$settleable, , drop = FALSE]
  if (anyNA(priced$payout_cny)) {
    stop("n7_experiment_metrics: a settleable group must carry a payout")
  }
  # Net path per epoch over the settleable groups only, so an un-settleable
  # group cannot move the drawdown it cannot be paid for.
  per_epoch <- if (nrow(priced)) {
    aggregate(list(cost = priced$cost_cny, payout = priced$payout_cny),
              by = list(epoch_utc = priced$epoch_utc), FUN = sum)
  } else {
    data.frame(epoch_utc = character(), cost = numeric(), payout = numeric())
  }
  per_epoch <- per_epoch[order(per_epoch$epoch_utc), , drop = FALSE]
  # The drawdown is measured on the cumulative net path in epoch order, not on
  # the per-epoch deltas.
  net <- cumsum(per_epoch$payout - per_epoch$cost)
  per_issue <- if (nrow(priced)) {
    aggregate(list(cost = priced$cost_cny, payout = priced$payout_cny),
              by = list(issue = priced$issue), FUN = sum)
  } else {
    data.frame(issue = character(), cost = numeric(), payout = numeric())
  }
  payout_share <- if (sum(priced$payout_cny) > 0) {
    sort(priced$payout_cny / sum(priced$payout_cny), decreasing = TRUE)
  } else {
    numeric(0)
  }
  # Money denominators are kept separate and named for what they actually divide.
  # A group with no settlement row is PENDING, not lost: its stake is still spent
  # but its outcome is unknown, so it belongs to no realised return, and while any
  # stake is pending the scheme's final net result is UNDETERMINED. Reporting one
  # blended "net profit / ROI" over mixed denominators is what this block exists
  # to prevent.
  total_cost <- sum(settled$cost_cny)
  settleable_cost <- if (nrow(priced)) sum(priced$cost_cny) else 0
  pending_cost <- total_cost - settleable_cost
  known_payout <- if (nrow(priced)) sum(priced$payout_cny) else 0
  settled_net <- known_payout - settleable_cost
  tibble::tibble(
    期数 = length(unique(settled$issue)),
    决策时点数 = length(unique(settled$epoch_utc)),
    组数 = nrow(settled),
    票数 = sum(as.integer(settled$tickets)),
    总投入 = total_cost,
    可结算投入 = settleable_cost,
    待结算投入 = pending_cost,
    已知回款 = known_payout,
    已结算净收益 = settled_net,
    已结算净ROI = if (settleable_cost > 0) settled_net / settleable_cost else NA_real_,
    回收倍数 = if (settleable_cost > 0) known_payout / settleable_cost else NA_real_,
    # Only meaningful as "money back so far minus money spent so far"; it is NOT a
    # final result while any stake is pending.
    截至当前回款减累计投入 = known_payout - total_cost,
    最终净收益 = if (pending_cost > 0) NA_real_ else settled_net,
    最终净收益口径 = if (pending_cost > 0) "未定：存在待结算投入" else "已定",
    可结算组数 = nrow(priced),
    不可结算组数 = nrow(settled) - nrow(priced),
    盈利期数_可结算 = if (nrow(per_issue)) sum(per_issue$payout > per_issue$cost) else 0L,
    全损期数_可结算 = if (nrow(per_issue)) sum(per_issue$payout == 0) else 0L,
    绝对回撤_可结算 = n7_absolute_drawdown(net),
    命中组数 = sum(settled$hit),
    已知结果组数 = nrow(known),
    未知结果组数 = nrow(settled) - nrow(known),
    覆盖命中率 = if (nrow(known)) mean(known$covered) else NA_real_,
    掩码排除数 = sum(settled$mask_excluded),
    掩码排除率 = mean(settled$mask_excluded),
    真实组合排名中位数 = if (all(is.na(settled$true_rank))) NA_real_
      else stats::median(settled$true_rank, na.rm = TRUE),
    真实组合排名最差 = if (all(is.na(settled$true_rank))) NA_integer_
      else max(settled$true_rank, na.rm = TRUE),
    尾部集中度_最大单组 = if (length(payout_share)) payout_share[1] else NA_real_,
    尾部集中度_前三组 = if (length(payout_share)) sum(payout_share[seq_len(min(3L, length(payout_share)))]) else NA_real_,
    # The ESTIMATED view, kept in its own columns and computed only from the
    # decision-time poll under the fixed SP rule. It is never netted against the
    # realised return, and an un-estimable group is excluded from its denominator.
    可估算组数 = sum(!is.na(settled$estimated_expected_return_cny)),
    估算期望回收 = sum(settled$estimated_expected_return_cny, na.rm = TRUE),
    估算期望净收益 = sum(settled$estimated_expected_return_cny, na.rm = TRUE) -
      sum(settled$cost_cny[!is.na(settled$estimated_expected_return_cny)]),
    # Gross expected payout per unit of estimable stake. It does NOT subtract the
    # stake, so it is a RECOVERY MULTIPLE and deliberately not named "ROI" (the
    # settled figure, 已结算净ROI, does subtract stake).
    估算期望回收倍数 = if (sum(settled$cost_cny[!is.na(settled$estimated_expected_return_cny)]) > 0) {
      sum(settled$estimated_expected_return_cny, na.rm = TRUE) /
        sum(settled$cost_cny[!is.na(settled$estimated_expected_return_cny)])
    } else NA_real_)
}

# ---- Freeze ------------------------------------------------------------------

# Seal an assembled artifact so a later run cannot silently change the inputs.
# The seal is the sha256 of the canonical JSON, so the receipt binds values
# rather than R object identity.
n7_seal_artifact <- function(artifact) {
  canonical <- jsonlite::toJSON(artifact, auto_unbox = TRUE, digits = 17,
                                null = "null", dataframe = "rows")
  list(canonical_json = canonical,
       seal = digest::digest(as.character(canonical), algo = "sha256", serialize = FALSE))
}

# Confirm a sealed artifact still hashes to its recorded seal.
n7_verify_seal <- function(canonical_json, seal) {
  if (!is.character(canonical_json) || length(canonical_json) != 1L) {
    stop("n7_verify_seal: canonical_json must be one string")
  }
  digest::digest(canonical_json, algo = "sha256", serialize = FALSE) == seal
}
