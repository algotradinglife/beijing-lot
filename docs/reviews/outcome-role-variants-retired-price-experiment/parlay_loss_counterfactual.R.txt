#' Replay bounded, label-free diagnostic alternatives to frozen betting plans
#'
#' @param x Issue26098 frozen `plans.rds` list containing named outputs with pool/evaluated.
#'   Cutoff, probability and SP receipts must remain valid. No settlements accepted.
#' @return List with named evaluations, tibble metadata, common cutoff and a
#'   receipt binding the input object and this implementation. Unsupported mask
#'   experiments are reported, never implemented by bypassing public validation.
#' @details Uses CNY256 per group, unlimited total, reuse/overlap 2, no improvement.
#'   Alternatives are retrospective mechanism diagnostics, not learned policies.
#'   No files, network or mutable settings are changed. Invalid inputs fail.
ParlayLossCounterfactuals <- function(x) {
  checkmate::assert_list(x$outputs, min.len = 1L, names = "unique")
  results <- list()
  rows <- list()
  cutoff <- x$outputs[[1]]$pool$cutoff
  if (!identical(cutoff$issue_id, "26098")) stop("diagnostic requires issue26098")
  for (pattern in names(x$outputs)) {
    original <- x$outputs[[pattern]]
    pool <- original$pool
    if (!identical(pool$cutoff, cutoff)) stop("mixed cutoffs")
    # Validate the returned baseline itself, not only a separately coherent pool.
    beidan:::.ParlayRiskPrepare(original$evaluated, cutoff)
    bindings <- list(cutoff_hash = pool$cutoff_hash,
      settings_hash = rlang::hash(pool$settings),
      probability_hash = rlang::hash(pool$probabilities),
      prematch_sp_hash = rlang::hash(pool$prematch_sp))
    for (binding in names(bindings)) {
      if (is.null(bindings[[binding]]) ||
          !identical(bindings[[binding]], original$evaluated$receipt[[binding]]))
        stop("pool and original evaluation binding mismatch: ", binding)
    }
    # Public evaluator verifies original frozen input receipts before experiments.
    beidan::parlay_evaluate_portfolio(pool, group_budget_cny = 256,
      budget_cny = NULL, constraints = list(max_reuse = 2L, max_overlap = 2L),
      improve = FALSE)
    fixed <- pool
    gl <- original$evaluated$final$plan$group_legs
    ids <- unique(gl$group_id)
    fixed$groups <- tibble::tibble(group_slot = as.integer(sub(".*:", "", ids)),
      group_id = ids, complete = TRUE)
    fixed$role_legs <- dplyr::left_join(gl, fixed$groups, by = "group_id",
      relationship = "many-to-one") |>
      dplyr::transmute(group_slot = as.integer(.data$group_slot), group_id,
        fixture_id, role = as.integer(pool$pattern[.data$leg_order]),
        round = as.integer(.data$leg_order)) |>
      dplyr::left_join(dplyr::select(pool$scores, fixture_id, role,
        allowed_outcomes, retained_probability), by = c("fixture_id", "role"),
        relationship = "many-to-one")
    # Verify final supports, not merely initial candidate assignments.
    expected <- dplyr::select(original$evaluated$final$plan$supports,
      candidate_id, fixture_id, outcome, allowed)
    for (scenario in c("baseline", "fixed_replay", "slot134_role3", "no_reuse",
                       "shared_role3", "sp_masks", "diverse_masks")) {
      id <- paste(pattern, scenario, sep = ":")
      value <- NULL
      status <- "ok"
      note <- "post-outcome diagnostic; no labels used in construction"
      candidate <- fixed
      constraints <- list(max_reuse = 2L, max_overlap = 2L)
      if (scenario == "baseline") value <- original$evaluated
      if (scenario %in% c("sp_masks", "diverse_masks")) {
        status <- "unsupported"
        note <- "public evaluator requires model Top-role masks; alternative masks require an explicit future API change"
      }
      if (scenario == "slot134_role3") {
        legs <- candidate$role_legs
        for (g in ids) {
          target <- which(legs$group_id == g & legs$fixture_id == "26098:134")
          donors <- which(legs$group_id == g & legs$role == 3L)
          if (!length(target) || legs$role[target] == 3L) next
          if (!length(donors)) stop("no role3 donor")
          scores <- dplyr::filter(pool$scores, .data$role == 3L)
          donor <- donors[order(scores$score[match(legs$fixture_id[donors], scores$fixture_id)],
            legs$fixture_id[donors])[1]]
          # Swap fixtures between role positions; pattern and group identity unchanged.
          legs$fixture_id[c(target, donor)] <- legs$fixture_id[c(donor, target)]
        }
        candidate$role_legs <- dplyr::select(legs, -allowed_outcomes, -retained_probability) |>
          dplyr::left_join(dplyr::select(pool$scores, fixture_id, role,
            allowed_outcomes, retained_probability), by = c("fixture_id", "role"),
            relationship = "many-to-one")
      }
      if (scenario == "no_reuse") {
        candidate <- pool
        constraints <- list(max_reuse = 1L, max_overlap = 0L)
        note <- "unequal spend: fewer groups possible; not an equal-budget comparison"
      }
      if (scenario == "shared_role3") {
        pairs <- utils::combn(pool$groups$group_id[pool$groups$complete], 2L)
        best <- -Inf
        status <- "infeasible"
        note <- "no legal candidate pair with every shared fixture role3 in both groups"
        for (j in seq_len(ncol(pairs))) {
          pair <- pairs[, j]
          a <- dplyr::filter(pool$role_legs, .data$group_id == pair[1])
          b <- dplyr::filter(pool$role_legs, .data$group_id == pair[2])
          shared <- intersect(a$fixture_id, b$fixture_id)
          if (length(shared) > 2L || any(a$role[a$fixture_id %in% shared] != 3L) ||
              any(b$role[b$fixture_id %in% shared] != 3L)) next
          candidate <- pool
          candidate$groups <- dplyr::filter(pool$groups, .data$group_id %in% pair)
          candidate$role_legs <- dplyr::filter(pool$role_legs, .data$group_id %in% pair)
          evaluated <- beidan::parlay_evaluate_portfolio(candidate,
            group_budget_cny = 256, budget_cny = NULL, constraints = constraints,
            improve = FALSE)
          # authoritative purchased probability from ticket ledger
          bought <- evaluated$final$plan$purchases
          score <- sum(evaluated$final$plan$tickets$probability[
            match(bought$ticket_id, evaluated$final$plan$tickets$ticket_id)])
          if (score > best) { best <- score; value <- evaluated; status <- "ok"
            note <- "best probability-sum legal pair among original candidate pairs" }
        }
      }
      if (status == "ok" && is.null(value)) value <- beidan::parlay_evaluate_portfolio(
        candidate, group_budget_cny = 256, budget_cny = NULL,
        constraints = constraints, improve = FALSE)
      if (scenario == "fixed_replay") {
        actual <- dplyr::select(value$final$plan$supports,
          candidate_id, fixture_id, outcome, allowed)
        if (nrow(dplyr::anti_join(expected, actual, by = names(expected))) ||
            nrow(dplyr::anti_join(actual, expected, by = names(actual))))
          stop(paste("frozen final support replay mismatch", pattern,
            paste(unique(dplyr::anti_join(expected, actual, by = names(expected))$candidate_id), collapse = ";")))
        before <- original$evaluated$final$plan$purchases
        after <- value$final$plan$purchases
        keys <- c("ticket_id", "stake_cny", "group_id")
        if (nrow(dplyr::anti_join(before, after, by = keys)) ||
            nrow(dplyr::anti_join(after, before, by = keys))) stop("physical purchase replay mismatch")
      }
      if (!is.null(value)) results[[id]] <- value
      rows[[length(rows) + 1L]] <- tibble::tibble(scenario_id = id, pattern,
        scenario, status, note, cost_cny = if (is.null(value)) NA_real_ else
          sum(value$final$plan$purchases$stake_cny))
    }
  }
  list(results = results, metadata = dplyr::bind_rows(rows), cutoff = cutoff,
    receipt = list(source_hash = rlang::hash(x),
      implementation_hash = rlang::hash(body(ParlayLossCounterfactuals)),
      diagnostic_only = TRUE, settlement_used = FALSE))
}
