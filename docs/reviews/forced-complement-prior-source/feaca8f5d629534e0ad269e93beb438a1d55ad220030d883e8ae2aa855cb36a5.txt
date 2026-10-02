#' Typed empty joint-risk summary
#' @return Zero-row tibble with CNY amounts, probabilities and Monte Carlo errors.
#' @details No inputs, missing values or side effects.
#' @noRd
.ParlayRiskEmpty <- function() {
  return(tibble::tibble(scenario_id = character(), prefix_groups = integer(),
    cost_cny = double(), purchased_tickets = integer(), expected_winning_tickets = double(),
    hit_probability = double(), break_even_probability = double(), expected_net_cny = double(),
    net_p05_cny = double(), roi_est = double(), sp_complete = logical(),
    hit_se = double(), break_even_se = double()))
}

#' Canonicalize a validated table for comparisons
#' @param data Tibble; empty tables retain their schema.
#' @param keys Existing column names defining a deterministic row order.
#' @return Sorted tibble. Invalid keys error; no side effects.
#' @noRd
.ParlayRiskCanonical <- function(data, keys) {
  return(tibble::as_tibble(data[do.call(order, unname(as.list(data[keys]))), , drop = FALSE]))
}

#' Bind loaded implementation and dependency versions
#' @return Character hash of all loaded package functions and dependency versions.
#' @details Conservative superset of transitive helpers; no filesystem reads or I/O.
#' @noRd
.ParlayRiskCodeHash <- function() {
  ns <- asNamespace("beidan")
  ids <- sort(ls(ns, all.names = TRUE))
  code <- lapply(ids, function(id) {
    fn <- get(id, envir = ns, inherits = FALSE)
    if (is.function(fn)) return(list(name = id, arguments = formals(fn), body = deparse(body(fn))))
    return(NULL)
  })
  deps <- c("tibble", "dplyr", "tidyr", "rlang", "checkmate", "lubridate")
  versions <- stats::setNames(vapply(deps, function(pkg) as.character(utils::packageVersion(pkg)), character(1)), deps)
  return(rlang::hash(list(code = code, R = as.character(getRversion()), dependencies = versions)))
}

#' Validate and revalue a frozen scenario's purchased physical tickets
#' @param evaluation Portfolio evaluation containing its final frozen result.
#' @param cutoff Validated shared decision cutoff; it is never advanced.
#' @return Internal list of canonical probabilities, SP, settings, purchases,
#'   revalued tickets and legs. Missing SP remains NA; empty purchases are allowed.
#' @details Altered hashes, chronology, physical identities, probabilities, stake
#'   units or ledgers error. No fitting, persistence or settlement input is used.
#' @noRd
.ParlayRiskPrepare <- function(evaluation, cutoff) {
  checkmate::assert_list(evaluation)
  result <- evaluation$final
  parlay_check_saved_result(result)
  match_require_cutoff(result$cutoff)
  if (!identical(result$cutoff, cutoff) || !identical(evaluation$cutoff, cutoff)) stop("risk cutoff mismatch")
  # The evaluator receipt is the frozen chronology binding; final provenance
  # has a different schema and cannot substitute for this mandatory hash.
  if (!identical(evaluation$receipt$cutoff, cutoff) ||
      !identical(evaluation$receipt$cutoff_hash,
        rlang::hash(list(as.character(cutoff$issue_id), as.numeric(cutoff$cutoff_utc))))) {
    stop("risk missing or mismatched frozen cutoff binding")
  }
  settings <- result$constants
  parlay_validate_settings(settings)
  if (!identical(settings, result$plan$constants)) stop("risk frozen settings mismatch")
  p <- match_validate_table(result$probabilities, "probabilities", keys = c("fixture_id", "outcome"))
  match_check_character_id(p$fixture_id, "fixture_id")
  if (anyNA(p$outcome) || any(!p$outcome %in% match_outcomes())) stop("invalid probability outcomes")
  if (is.object(p$probability) || !is.null(dim(p$probability))) stop("probabilities must be plain numeric")
  wide <- parlay_probability_wide(p)
  sp <- .parlay_role_validate_prematch_sp(result$prematch_sp, cutoff)
  hashes <- list(probability_hash = rlang::hash(p), prematch_sp_hash = rlang::hash(sp))
  for (container in list(result$provenance, evaluation$receipt)) {
    if (!is.list(container) || any(vapply(container[c("probability_hash", "prematch_sp_hash")], is.null, logical(1)))) stop("risk missing provenance hash")
    for (name in names(hashes)) {
      if (!is.null(container[[name]]) && !identical(container[[name]], hashes[[name]])) stop("risk ", name, " mismatch")
    }
    if (!is.null(container[["cutoff"]]) && !identical(container[["cutoff"]], cutoff)) stop("risk receipt cutoff mismatch")
    if (!is.null(container[["cutoff_hash"]]) && !identical(container[["cutoff_hash"]],
        rlang::hash(list(as.character(cutoff$issue_id), as.numeric(cutoff$cutoff_utc))))) stop("risk cutoff hash mismatch")
  }
  tickets <- match_validate_table(result$plan$tickets, "tickets", keys = "ticket_id")
  legs <- match_validate_table(result$plan$ticket_legs, "ticket_legs", keys = c("ticket_id", "fixture_id"))
  purchases <- match_validate_table(result$plan$purchases, "purchases", keys = "ticket_id")
  for (name in c("ticket_id", "group_id", "candidate_id")) match_check_character_id(purchases[[name]], name)
  if (is.object(purchases$stake_cny) || !is.null(dim(purchases$stake_cny)) ||
      anyNA(purchases$stake_cny) || any(!is.finite(purchases$stake_cny)) ||
      any(purchases$stake_cny <= 0) ||
      any(abs(purchases$stake_cny / settings$unit_cny - round(purchases$stake_cny / settings$unit_cny)) > 1e-9)) stop("invalid purchased stake units")
  selected <- match(purchases$ticket_id, tickets$ticket_id)
  if (anyNA(selected)) stop("purchased physical ticket absent from plan")
  tickets <- tickets[selected, , drop = FALSE]
  legs <- legs[legs$ticket_id %in% tickets$ticket_id, , drop = FALSE]
  p_key <- paste(p$fixture_id, p$outcome, sep = "\r")
  for (i in seq_len(nrow(tickets))) {
    tl <- legs[legs$ticket_id == tickets$ticket_id[i], , drop = FALSE]
    if (nrow(tl) != settings$n_legs || anyNA(tl$outcome) || any(!tl$outcome %in% match_outcomes())) stop("invalid purchased ticket legs")
    group_fixtures <- result$plan$group_legs$fixture_id[result$plan$group_legs$group_id == purchases$group_id[i]]
    if (!setequal(tl$fixture_id, group_fixtures)) stop("purchased ticket group mismatch")
    index <- match(paste(tl$fixture_id, tl$outcome, sep = "\r"), p_key)
    if (anyNA(index)) stop("ticket fixture absent from probabilities")
    probability <- prod(p$probability[index])
    if (!is.finite(tickets$probability[i]) || abs(tickets$probability[i] - probability) > 1e-12) stop("saved ticket probability mismatch")
    tickets$probability[i] <- probability
  }
  tickets <- parlay_value_tickets(tickets, legs, sp, cutoff, settings$sp_threshold,
    settings$sp_replacement, settings$unit_cny, settings$payout_factor)
  saved_values <- match_validate_table(result$plan$valued, "tickets", keys = "ticket_id")
  saved_index <- match(tickets$ticket_id, saved_values$ticket_id)
  if (anyNA(saved_index) || !isTRUE(all.equal(
      saved_values[saved_index, c("probability", "sp_product_est", "ev_net_est"), drop = FALSE],
      tickets[, c("probability", "sp_product_est", "ev_net_est"), drop = FALSE],
      tolerance = 1e-12, check.attributes = FALSE))) stop("saved valuation disagrees with bound inputs or settings")
  tickets$payout_cny <- purchases$stake_cny * settings$payout_factor * tickets$sp_product_est
  if (any(!is.na(tickets$payout_cny) & !is.finite(tickets$payout_cny))) stop("nonfinite ticket payout")
  return(list(probabilities = .ParlayRiskCanonical(p, c("fixture_id", "outcome")),
    wide = .ParlayRiskCanonical(wide, "fixture_id"),
    sp = .ParlayRiskCanonical(sp, c("fixture_id", "outcome", "quote_at", "source_url", "sp_raw")),
    settings = settings, purchases = purchases, tickets = tickets, legs = legs))
}

#' Compare joint hit and reference return risks of frozen alternatives
#'
#' Each fixture has one shared W/D/L outcome in each joint state, reused across
#' every group and scenario. Different fixtures are assumed independent. These
#' are model-based estimates, not guarantees or realized settlement returns.
#' @param exploration Result of [parlay_explore_portfolios()]; its bound cutoff,
#'   common probabilities, SP and business settings must remain coherent.
#' @param method One of `auto`, `exact`, or `mc`. Auto enumerates within the cap.
#' @param n_draws Positive integer Monte Carlo sample size; default 20000.
#' @param seed Nonnegative integer seed. Caller RNG kind and state are restored.
#' @param max_exact_states Positive integer state cap; default 600000 permits
#'   12 fixtures (531441 states). Explicit exact above the cap errors.
#' @param include_group_prefixes Logical; TRUE evaluates zero through all bought
#'   groups, ordered by purchased probability mass then group_id. FALSE returns
#'   zero and the full plan. Empty exploration returns a typed empty table.
#' @return List with a summary tibble, machine-readable receipt, and unchanged
#'   cutoff. Each row identifies scenario and group prefix. Amounts are CNY;
#'   expected winning tickets and expected net are analytic. `net_p05_cny` is
#'   the inverse-CDF 5th percentile (empirical for MC). `hit_se` and
#'   `break_even_se` describe Monte Carlo sampling error only, zero for exact.
#'   Missing purchased SP leaves hit available but return metrics NA. Zero
#'   investment has hit/net/quantile zero and break-even/ROI NA.
#' @details Revalues actual stakes with one ticket-level payout factor and the
#'   existing SP transform. Rejects malformed/tampered contexts. No fitting,
#'   future SP, settlement, cache reuse, writes or network activity occurs.
#' @export
parlay_compare_risk <- function(exploration, method = "auto", n_draws = 20000L,
                                seed = 1L, max_exact_states = 600000L,
                                include_group_prefixes = TRUE) {
  checkmate::assert_choice(method, c("auto", "exact", "mc"))
  checkmate::assert_count(n_draws, positive = TRUE)
  checkmate::assert_count(seed)
  checkmate::assert_count(max_exact_states, positive = TRUE)
  checkmate::assert_flag(include_group_prefixes)
  for (value in list(n_draws, seed, max_exact_states)) {
    if (is.object(value) || !is.null(dim(value)) || value > .Machine$integer.max) stop("risk integer parameter out of range")
  }
  checkmate::assert_list(exploration)
  match_require_cutoff(exploration$cutoff)
  cutoff <- exploration$cutoff
  checkmate::assert_true(tibble::is_tibble(exploration$summary))
  checkmate::assert_character(exploration$summary$scenario_id, any.missing = FALSE, min.chars = 1L, unique = TRUE)
  checkmate::assert_list(exploration$results)
  ids <- exploration$summary$scenario_id
  if (length(ids) != length(exploration$results) ||
      (length(ids) && (!setequal(ids, names(exploration$results)) || anyDuplicated(names(exploration$results))))) stop("risk scenario/result identity mismatch")
  prepared <- lapply(exploration$results[ids], .ParlayRiskPrepare, cutoff = cutoff)
  business <- c("n_legs", "unit_cny", "payout_factor", "sp_threshold", "sp_replacement")
  if (length(prepared)) {
    reference <- prepared[[1L]]
    for (item in prepared) {
      if (!identical(item$probabilities, reference$probabilities)) stop("risk scenarios need common probabilities")
      if (!identical(item$sp, reference$sp)) stop("risk scenarios need common SP")
      if (!identical(item$settings[business], reference$settings[business])) stop("risk scenarios need common business settings")
    }
  }
  fixtures <- sort(unique(unlist(lapply(prepared, function(x) x$legs$fixture_id), use.names = FALSE)))
  n_fixtures <- length(fixtures)
  state_count <- 3^n_fixtures
  if (method == "exact" && state_count > max_exact_states) stop("exact joint universe exceeds max_exact_states")
  actual_method <- if (method == "auto") if (state_count <= max_exact_states) "exact" else "mc" else method
  count <- if (actual_method == "exact") as.integer(state_count) else as.integer(n_draws)
  rng_kind <- RNGkind()
  rng_exists <- exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  rng_state <- if (rng_exists) get(".Random.seed", envir = .GlobalEnv) else NULL
  if (actual_method == "mc") {
    on.exit({
      do.call(RNGkind, as.list(rng_kind))
      if (rng_exists) assign(".Random.seed", rng_state, envir = .GlobalEnv)
      else if (exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)) rm(".Random.seed", envir = .GlobalEnv)
    }, add = TRUE)
    RNGkind("Mersenne-Twister", "Inversion", "Rejection")
    set.seed(as.integer(seed))
  }
  outcomes <- matrix(0L, nrow = count, ncol = n_fixtures)
  weights <- rep(if (actual_method == "exact") 1 else 1 / count, count)
  if (n_fixtures) {
    probability_matrix <- as.matrix(reference$wide[match(fixtures, reference$wide$fixture_id), match_outcomes()])
    # Contract-validated rows are normalized only for floating-point roundoff.
    probability_matrix <- probability_matrix / rowSums(probability_matrix)
    for (j in seq_len(n_fixtures)) {
      if (actual_method == "exact") {
        outcomes[, j] <- (seq_len(count) - 1L) %/% (3^(j - 1L)) %% 3
        weights <- weights * probability_matrix[j, outcomes[, j] + 1L]
      } else {
        u <- stats::runif(count)
        outcomes[, j] <- as.integer(u >= probability_matrix[j, 1L]) +
          as.integer(u >= sum(probability_matrix[j, 1:2]))
      }
    }
  }
  if (actual_method == "exact") weights <- weights / sum(weights)
  rows <- list()
  ordered_groups <- stats::setNames(vector("list", length(ids)), ids)
  for (scenario in ids) {
    item <- prepared[[scenario]]
    purchases <- item$purchases
    tickets <- item$tickets
    groups <- sort(unique(purchases$group_id))
    mass <- vapply(groups, function(g) sum(tickets$probability[purchases$group_id == g]), numeric(1))
    groups <- groups[order(-mass, groups)]
    ordered_groups[[scenario]] <- groups
    wins <- rep(FALSE, count)
    gross <- numeric(count)
    cost <- expected_wins <- expected_gross <- 0
    purchased <- 0L
    complete <- TRUE
    prefixes <- if (include_group_prefixes) seq.int(0L, length(groups)) else unique(c(0L, length(groups)))
    for (prefix in seq.int(0L, length(groups))) {
      if (prefix > 0L) {
        index <- which(purchases$group_id == groups[prefix])
        gl <- item$legs[item$legs$ticket_id %in% tickets$ticket_id[index], , drop = FALSE]
        group_fixtures <- sort(unique(gl$fixture_id))
        if (length(group_fixtures) > 33L) stop("group base-3 identity exceeds exact numeric precision")
        powers <- 3^(seq_along(group_fixtures) - 1L)
        state_codes <- as.vector(outcomes[, match(group_fixtures, fixtures), drop = FALSE] %*% powers)
        ticket_codes <- vapply(tickets$ticket_id[index], function(id) {
          legs <- gl[gl$ticket_id == id, , drop = FALSE]
          return(sum((match(legs$outcome[match(group_fixtures, legs$fixture_id)], match_outcomes()) - 1L) * powers))
        }, numeric(1))
        if (anyDuplicated(ticket_codes)) stop("duplicate physical purchase within group")
        hit <- match(state_codes, ticket_codes)
        wins <- wins | !is.na(hit)
        cost <- cost + sum(purchases$stake_cny[index])
        purchased <- purchased + length(index)
        expected_wins <- expected_wins + sum(tickets$probability[index])
        group_complete <- all(!is.na(tickets$payout_cny[index]))
        complete <- complete && group_complete
        if (complete) {
          payout <- numeric(count)
          payout[!is.na(hit)] <- tickets$payout_cny[index][hit[!is.na(hit)]]
          gross <- gross + payout
          expected_gross <- expected_gross + sum(tickets$probability[index] * tickets$payout_cny[index])
        }
      }
      if (!prefix %in% prefixes) next
      hit_probability <- sum(weights[wins])
      hit_se <- if (actual_method == "exact") 0 else sqrt(hit_probability * (1 - hit_probability) / count)
      net <- if (complete) expected_gross - cost else NA_real_
      be <- if (cost > 0 && complete) sum(weights[gross >= cost - 1e-10]) else NA_real_
      be_se <- if (is.na(be)) NA_real_ else if (actual_method == "exact") 0 else sqrt(be * (1 - be) / count)
      q05 <- if (complete) {
        ord <- order(gross)
        (gross[ord][which(cumsum(weights[ord]) >= .05)[1L]] - cost)
      } else NA_real_
      rows[[length(rows) + 1L]] <- tibble::tibble(scenario_id = scenario,
        prefix_groups = as.integer(prefix), cost_cny = cost, purchased_tickets = as.integer(purchased),
        expected_winning_tickets = expected_wins, hit_probability = hit_probability,
        break_even_probability = be, expected_net_cny = net, net_p05_cny = q05,
        roi_est = if (cost > 0) net / cost else NA_real_, sp_complete = complete,
        hit_se = hit_se, break_even_se = be_se)
    }
  }
  summary <- if (length(rows)) dplyr::bind_rows(rows) else .ParlayRiskEmpty()
  receipt <- list(cutoff = cutoff, method = actual_method, requested_method = method,
    joint_state_count = state_count, evaluated_states = count, n_draws = as.integer(n_draws),
    seed = as.integer(seed), max_exact_states = max_exact_states,
    rng_kind = if (actual_method == "mc") c("Mersenne-Twister", "Inversion", "Rejection") else NULL,
    rng_restored = TRUE, fixture_ids = fixtures, include_group_prefixes = include_group_prefixes,
    model = "independent fixtures; shared joint outcome universe across groups and scenarios",
    uncertainty = "Monte Carlo standard errors exclude model and SP uncertainty",
    probability_normalization = "validated W/D/L rows; floating-point roundoff normalization",
    ordered_groups = ordered_groups, source_hash = rlang::hash(exploration),
    source_hashes = stats::setNames(lapply(ids, function(id) {
      x <- exploration$results[[id]]$final
      return(list(plan = rlang::hash(x$plan), probabilities = rlang::hash(x$probabilities),
        settings = rlang::hash(x$constants), prematch_sp = rlang::hash(x$prematch_sp)))
    }), ids), implementation_hash = .ParlayRiskCodeHash(), historical_learning = FALSE)
  return(list(summary = summary, receipt = receipt, cutoff = cutoff))
}
