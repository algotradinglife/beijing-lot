#' Select fixed purchase blocks by exact incremental union coverage
#'
#' @param decision Explicit list with cutoff, probabilities (fixture_id, outcome,
#'   probability), candidates (group_id, ticket_id, probability), source_bindings,
#'   source_receipt and input_hash. input_hash is rlang::hash() of those five fields in that
#'   order. Source bindings identify previously validated immutable inputs; this
#'   function performs no source IO or historical fitting.
#' @param max_groups Positive whole maximum number of distinct candidate blocks.
#' @param unit_cny Explicit positive ticket price in CNY. Every candidate must
#'   contain the same positive number of tickets; no block is refilled or reranked.
#' @return List with selected purchases, selection trace, and cutoff/input/code
#'   receipt. Tables are tibbles. Empty candidates return typed empty tables.
#' @details Fixed-policy lazy greedy maximum coverage, not a global optimum.
#'   Each candidate is a mutually exclusive set of canonical physical tickets on
#'   one fixture set. The exact compiled union kernel shares each fixture across
#'   groups. Different fixtures are independent. Duplicate copies across groups
#'   retain cost and expected wins but contribute no additional union coverage.
#'   Equal gains use group_id. Selects up to max_groups, including zero-gain blocks
#'   when available, to permit fixed-budget comparisons. Missing probabilities,
#'   stale input bindings, inconsistent blocks, or invalid tickets fail closed.
#' @noRd
SelectFixedTicketGroups <- function(decision, max_groups, unit_cny) {
  checkmate::assert_list(decision)
  match_require_cutoff(decision$cutoff)
  checkmate::assert_count(max_groups, positive = TRUE)
  checkmate::assert_number(unit_cny, lower = .Machine$double.eps, finite = TRUE)
  if (is.object(max_groups) || is.object(unit_cny)) stop("plain selection constants required")
  payload <- decision[c("cutoff", "probabilities", "candidates", "source_bindings", "source_receipt")]
  if (!length(decision$source_bindings) || !identical(decision$input_hash, rlang::hash(payload)))
    stop("fixed-ticket input binding mismatch")
  upstream <- decision$source_receipt
  match_require_cutoff(upstream$cutoff)
  if (!identical(upstream$cutoff, decision$cutoff) ||
      !identical(upstream$probability_hash, rlang::hash(decision$probabilities)) ||
      !identical(upstream$candidate_hash, rlang::hash(decision$candidates)))
    stop("upstream cutoff/probability/candidate binding mismatch")
  at <- upstream$max_source_available_utc
  if (!inherits(at, "POSIXct") || length(at) != 1L || anyNA(at) ||
      !is.finite(as.numeric(at)) || !identical(attr(at, "tzone"), "UTC") ||
      at >= decision$cutoff$cutoff_utc) stop("upstream source availability is not before cutoff")
  hashes <- unlist(upstream$source_snapshots, use.names = FALSE)
  if (!length(hashes) || anyNA(hashes) || !all(grepl("^[0-9a-f]{64}$", hashes)))
    stop("upstream source snapshot hashes required")
  q <- parlay_probability_wide(decision$probabilities)
  t <- decision$candidates
  if (!tibble::is_tibble(t) || !all(c("group_id", "ticket_id", "probability") %in% names(t)))
    stop("candidates must be a tibble with group_id, ticket_id, probability")
  match_check_character_id(t$group_id, "group_id")
  match_check_character_id(t$ticket_id, "ticket_id")
  checkmate::assert_numeric(t$probability, finite = TRUE, any.missing = FALSE, lower = 0, upper = 1)
  if (anyDuplicated(t[c("group_id", "ticket_id")])) stop("duplicate ticket within candidate")
  ids <- sort(unique(t$group_id), method = "radix")
  rows <- split(seq_len(nrow(t)), factor(t$group_id, levels = ids))
  if (length(unique(lengths(rows))) > 1L) stop("candidate blocks must have equal ticket counts")
  if (!identical(ComponentUnionKernelIdentity(), .ParlayKernelSourceHash()))
    stop("compiled probability kernel identity mismatch")
  pm <- as.matrix(q[, c("W", "D", "L")])
  fixtures <- q$fixture_id
  events <- vector("list", length(ids)); masses <- numeric(length(ids))
  for (i in seq_along(ids)) {
    block <- t[rows[[i]], ]
    pieces <- strsplit(block$ticket_id, "|", fixed = TRUE)
    events[[i]] <- vector("list", length(pieces)); fixture_set <- NULL
    for (j in seq_along(pieces)) {
      event <- stats::setNames(as.integer(sub(".*:", "", pieces[[j]])),
                              sub(":[^:]+$", "", pieces[[j]]))
      if (anyNA(event) || any(!event %in% 1:3) || anyDuplicated(names(event)) ||
          !all(names(event) %in% fixtures) ||
          !identical(parlay_physical_ticket_key(names(event), unname(event)), block$ticket_id[j]))
        stop("invalid canonical ticket")
      if (is.null(fixture_set)) fixture_set <- sort(names(event))
      if (!identical(sort(names(event)), fixture_set)) stop("candidate has mixed fixture sets")
      mass <- prod(pm[cbind(match(names(event), fixtures), unname(event))])
      if (abs(mass - block$probability[j]) > 1e-12) stop("ticket probability mismatch")
      events[[i]][[j]] <- event
    }
    masses[i] <- sum(block$probability)
  }
  upper <- masses; refreshed <- rep(0L, length(ids)); remaining <- seq_along(ids)
  selected <- integer(); owned <- list(); coverage <- 0; trace <- list(); probes <- 0L
  for (step in seq_len(min(max_groups, length(ids)))) {
    repeat {
      best <- remaining[order(-upper[remaining], ids[remaining], method = "radix")][1L]
      if (refreshed[best] == step - 1L) break
      total <- .parlay_ranked_component_union(c(owned, events[[best]]), fixtures,
        function(id, code) pm[match(id, fixtures), code])
      gain <- total - coverage
      if (gain < -1e-10 || gain > masses[best] + 1e-10) stop("invalid marginal union mass")
      upper[best] <- max(0, gain); refreshed[best] <- step - 1L; probes <- probes + 1L
    }
    selected <- c(selected, best); remaining <- setdiff(remaining, best)
    coverage <- coverage + upper[best]; owned <- c(owned, events[[best]])
    trace[[step]] <- tibble::tibble(group = as.integer(step), group_id = ids[best],
      standalone_coverage = masses[best], marginal_coverage = upper[best],
      cumulative_coverage = coverage, cumulative_expected_wins = sum(masses[selected]),
      cumulative_cost_cny = sum(lengths(rows[selected])) * unit_cny)
  }
  selection <- if (length(trace)) dplyr::bind_rows(trace) else tibble::tibble(
    group = integer(), group_id = character(), standalone_coverage = numeric(),
    marginal_coverage = numeric(), cumulative_coverage = numeric(),
    cumulative_expected_wins = numeric(), cumulative_cost_cny = numeric())
  purchases <- dplyr::inner_join(t, selection[, c("group_id", "group")],
    by = "group_id", relationship = "many-to-one")
  receipt <- list(cutoff = decision$cutoff, input_hash = decision$input_hash,
    source_bindings = decision$source_bindings, max_groups = max_groups, unit_cny = unit_cny,
    code_hash = .rank_outcome_code_hash(roots = "SelectFixedTicketGroups"),
    kernel_identity = ComponentUnionKernelIdentity(),
    output_hash = rlang::hash(list(selection, purchases)), exact_union_probes = probes,
    algorithm = "LAZY_GREEDY_EXACT_UNION_EQUAL_COST_FIXED_BLOCKS")
  list(selection = selection, purchases = purchases, receipt = receipt)
}
