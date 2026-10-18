#' Fit fixed prior-only residual calibration of handicap probabilities
#' @param history Tibble, one row per fixture: fixture_id, issue_code, issue_year,
#'   label_available_ts, data_available_ts, actual_outcome, W/D/L, entropy and
#'   local_mass. UTC clocks are explicit strings. No missing values are admitted.
#' @param cutoff Explicit issue_id/cutoff_utc decision epoch.
#' @param policy Explicit prior_issues nomination, features (empty or entropy/local_mass), minimum_ess,
#'   minimum_class_count and epsilon. No tuning is performed.
#' @param source_hashes Named immutable source SHA256 bindings.
#' @param repository_root Repository containing the authoritative shared backend.
#' @param python Explicit project Python interpreter.
#' @return Coefficients/fit diagnostics, admitted history, weight ledger and cutoff-bound
#'   shared receipt. Historical diagnostic only; no IO writes or network calls.
#' @details Uses shared temporal_learning admission/partitions/weights. Three
#'   binomial GLMs use original log odds as offsets; predictions are normalized.
#'   Sparse history, singular/nonconvergent fits and ambiguous inputs fail closed.
#' @noRd
FitMarginShapeCalibration <- function(history, cutoff, policy, source_hashes,
                                     repository_root, python) {
  match_require_cutoff(cutoff)
  required <- c("fixture_id", "issue_code", "issue_year", "label_available_ts",
    "data_available_ts", "actual_outcome", "W", "D", "L", "entropy", "local_mass")
  if (!tibble::is_tibble(history) || !all(required %in% names(history)) ||
      !nrow(history) || anyDuplicated(history$fixture_id)) stop("invalid history contract")
  if (!is.character(policy$prior_issues) || !length(policy$prior_issues) ||
      anyNA(policy$prior_issues) || anyDuplicated(policy$prior_issues) ||
      !all(grepl("^[0-9]{1,10}$",c(policy$prior_issues,cutoff$issue_id))) ||
      any(as.numeric(policy$prior_issues)>=as.numeric(cutoff$issue_id)))
    stop("explicit strictly prior issue nomination required")
  if (!is.character(policy$features) || anyDuplicated(policy$features) ||
      !all(policy$features %in% c("entropy", "local_mass"))) stop("invalid shape features")
  checkmate::assert_number(policy$minimum_ess, lower = 1, finite = TRUE)
  checkmate::assert_count(policy$minimum_class_count, positive = TRUE)
  checkmate::assert_number(policy$epsilon, lower = 1e-12, upper = .01, finite = TRUE)
  if (is.null(names(source_hashes)) || !length(source_hashes) ||
      !all(grepl("^[a-f0-9]{64}$", unlist(source_hashes)))) stop("source hashes required")
  nominated <- dplyr::filter(history,issue_code %in% policy$prior_issues)
  if (!nrow(nominated)) stop("no nominated prior history")
  invisible(python_backend(python))
  shared <- reticulate::import("beidan_backend.temporal_learning", convert = FALSE)
  partitions <- reticulate::import("beidan_backend.temporal_learning.issue_partitions", convert = FALSE)
  pd <- reticulate::import("pandas", convert = FALSE)
  frame <- pd$DataFrame(jsonlite::fromJSON(jsonlite::toJSON(nominated,
    dataframe = "rows", auto_unbox = TRUE, digits = NA), simplifyVector = FALSE))
  epoch <- shared$Cutoff$decision_epoch(cutoff$issue_id,
    format(cutoff$cutoff_utc, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  bindings <- c(source_hashes, list(history = digest::digest(history, algo = "sha256"),
    R_implementation = .rank_outcome_code_hash(roots = c("FitMarginShapeCalibration",
      "PredictMarginShapeCalibration")), policy = digest::digest(policy, algo = "sha256")))
  ctx <- shared$prepare_learning_context(frame, epoch, source_hashes = bindings,
    repository_root = reticulate::import("pathlib", convert = FALSE)$Path(repository_root),
    implementation_modules = list("beidan_backend.temporal_learning.issue_partitions"),
    implementation_distributions = list("pandas", "numpy"),
    availability = shared$AvailabilityFilter(shared$AvailabilityPolicy$historical_proxy(
      "FM171_RECONSTRUCTED_FORECAST_OBSERVED_LABEL"), data_available_column = "data_available_ts"),
    intended_use = "HISTORICAL_DIAGNOSTIC",
    partition_policy = shared$PartitionPolicy("FIXED_PRIOR_FIT", 0L, 0L, 1L),
    weighting_policy = shared$WeightingPolicy$expanding_equal(minimum_ess = policy$minimum_ess))
  admitted <- tibble::as_tibble(jsonlite::fromJSON(reticulate::py_to_r(
    ctx$partitions[["fit"]]$to_json(orient = "records", date_format = "iso", double_precision = 15L))))
  p <- as.matrix(admitted[c("W", "D", "L")])
  if (anyNA(admitted[required]) || !all(admitted$actual_outcome %in% c("W","D","L")) ||
      !is.numeric(p) || any(!is.finite(p)) || any(p <= 0 | p >= 1) ||
      any(abs(rowSums(p)-1)>1e-9) || any(!is.finite(admitted$entropy)) ||
      any(admitted$entropy<0) || any(!is.finite(admitted$local_mass)) ||
      any(admitted$local_mass<0 | admitted$local_mass>1)) stop("invalid admitted history probabilities/features")
  weights <- as.numeric(reticulate::py_to_r(ctx$weights$to_numpy()))
  if (any(table(factor(admitted$actual_outcome, levels = c("W", "D", "L"))) <
      policy$minimum_class_count)) stop("insufficient class support")
  weights <- weights / sum(weights) * nrow(admitted)
  fits <- list()
  for (outcome in c("W", "D", "L")) {
    d <- admitted
    d$target <- as.numeric(d$actual_outcome == outcome)
    d$baseline_logit <- stats::qlogis(pmax(policy$epsilon, pmin(1-policy$epsilon, d[[outcome]])))
    d$fit_weight <- weights
    formula <- stats::reformulate(c(policy$features, "offset(baseline_logit)"), response = "target")
    fit <- stats::glm(formula, data = d, family = stats::binomial(), weights = fit_weight)
    if (!isTRUE(fit$converged) || anyNA(stats::coef(fit)) ||
        any(!is.finite(stats::coef(fit)))) stop("nonconvergent or singular calibration")
    fits[[outcome]] <- fit
  }
  parameters <- lapply(fits, stats::coef)
  receipt <- reticulate::py_to_r(partitions$bind_model_receipt(ctx, epoch,
    model_identity = "FM171_MARGIN_RESIDUAL_GLM", model_parameters = list(
      policy = policy, coefficients = parameters, R_bindings = bindings)))
  receipt$domain_nomination <- list(prior_issues=policy$prior_issues,
    input_rows=nrow(history),nominated_rows=nrow(nominated),
    excluded_non_nominated_rows=nrow(history)-nrow(nominated))
  ledger <- tibble::as_tibble(jsonlite::fromJSON(reticulate::py_to_r(
    ctx$weight_ledger$to_json(orient = "records", date_format = "iso", double_precision = 15L))))
  diagnostics <- tibble::tibble(outcome=names(fits),
    iterations=vapply(fits,function(f)as.integer(f$iter),integer(1)),
    rank=vapply(fits,function(f)as.integer(f$rank),integer(1)),
    deviance=vapply(fits,function(f)f$deviance,numeric(1)))
  result <- list(cutoff = cutoff, policy = policy, coefficients = parameters,
    diagnostics = diagnostics, admitted = admitted, ledger = ledger, receipt = receipt)
  result$binding <- rlang::hash(result)
  result
}

#' Predict from a frozen, cutoff-bound residual calibration
#' @param fit Result of FitMarginShapeCalibration, with intact binding.
#' @param decision List with cutoff, features tibble (fixture_id,W,D,L,entropy,
#'   local_mass), and upstream receipt binding cutoff, feature_hash and maximum
#'   source time. No labels are accepted or needed.
#' @return Normalized long tibble fixture_id/outcome/probability. Pure prediction;
#'   empty, stale, malformed or differently dated inputs fail closed.
#' @noRd
PredictMarginShapeCalibration <- function(fit, decision) {
  match_require_cutoff(decision$cutoff)
  payload <- fit; payload$binding <- NULL
  if (!identical(rlang::hash(payload), fit$binding) ||
      !identical(fit$cutoff, decision$cutoff)) stop("calibration cutoff/binding mismatch")
  f <- decision$features; r <- decision$receipt
  if (!tibble::is_tibble(f) || !nrow(f) ||
      !all(c("fixture_id", "W", "D", "L", "entropy", "local_mass") %in% names(f)) ||
      anyDuplicated(f$fixture_id) || anyNA(f) ||
      !identical(r$cutoff, decision$cutoff) || !identical(r$feature_hash, rlang::hash(f)) ||
      !inherits(r$max_source_available_utc, "POSIXct") ||
      length(r$max_source_available_utc) != 1L || anyNA(r$max_source_available_utc) ||
      !is.finite(as.numeric(r$max_source_available_utc)) ||
      r$max_source_available_utc >= decision$cutoff$cutoff_utc) stop("invalid prediction receipt")
  p <- as.matrix(f[c("W", "D", "L")])
  if (!is.numeric(p) || any(!is.finite(p)) || any(p <= 0 | p >= 1) ||
      any(abs(rowSums(p)-1) > 1e-9) || any(!is.finite(f$entropy)) ||
      any(f$entropy < 0) || any(!is.finite(f$local_mass)) ||
      any(f$local_mass < 0 | f$local_mass > 1)) stop("invalid prediction probabilities/features")
  for (outcome in c("W", "D", "L")) {
    baseline_logit <- stats::qlogis(pmax(fit$policy$epsilon,
      pmin(1-fit$policy$epsilon, f[[outcome]])))
    design <- stats::model.matrix(stats::reformulate(if(length(fit$policy$features))
      fit$policy$features else "1"),data=f)
    if (!identical(colnames(design),names(fit$coefficients[[outcome]])))
      stop("calibration coefficient/design mismatch")
    p[, outcome] <- stats::plogis(baseline_logit+as.numeric(design %*% fit$coefficients[[outcome]]))
  }
  if (any(!is.finite(p)) || any(rowSums(p) <= 0)) stop("invalid calibration output")
  p <- p / rowSums(p)
  tibble::as_tibble(p) |> dplyr::mutate(fixture_id = f$fixture_id) |>
    tidyr::pivot_longer(c("W", "D", "L"), names_to = "outcome", values_to = "probability") |>
    dplyr::select(fixture_id, outcome, probability)
}

#' Compare fixed and incremental purchases over complete outcome spaces
#' @param decision Same bound decision contract as SelectFixedTicketGroups.
#'   candidates must contain each group's complete 3^n mutually exclusive space,
#'   ranked 1..3^n by decreasing probability. Each group is purchased once.
#' @param tickets_per_group Explicit positive ticket count per group.
#' @param fixed_start Explicit first rank of fixed comparison window.
#' @param unit_cny Explicit CNY cost per ticket.
#' @param maximum_worlds Explicit resource limit for exact shared-fixture worlds.
#' @return Purchases and coverage trace tibbles for FIXED, TOP, DYNAMIC_WINDOW,
#'   DYNAMIC_SET; input/policy/output/code receipt. Labels never enter selection.
#' @details Uses existing canonical ticket validation and scalar union API.
#'   The missing capability is the vector of uncovered mass per candidate ticket:
#'   base rowsum integrates it over the complete shared outcome space. Different
#'   fixtures are independent; each fixture is shared exactly across groups.
#'   Dynamic policies greedily choose the remaining group and block/set with
#'   highest incremental union mass, not global optimality. Ties use group_id,
#'   then earliest rank. Duplicate copies retain cost and expected-win mass.
#'   Missing/incomplete spaces and resource overflow fail closed; no sampling.
#' @noRd
SelectJointOutcomeTickets <- function(decision, tickets_per_group, fixed_start,
                                     unit_cny, maximum_worlds) {
  checkmate::assert_count(tickets_per_group, positive = TRUE)
  checkmate::assert_count(fixed_start, positive = TRUE)
  checkmate::assert_number(maximum_worlds, lower = 1, finite = TRUE)
  # Authoritative validation includes cutoff/source/canonical/product bindings.
  invisible(SelectFixedTicketGroups(decision, 1L, unit_cny))
  t <- decision$candidates
  if (!nrow(t) || !"rank" %in% names(t)) stop("nonempty complete ranked spaces required")
  q <- parlay_probability_wide(decision$probabilities)
  ids <- sort(unique(t$group_id), method = "radix")
  fixtures <- q$fixture_id
  nworld <- 3^length(fixtures)
  if (nworld > maximum_worlds || nworld > .Machine$integer.max) stop("exact world resource limit")
  pieces <- strsplit(t$ticket_id, "|", fixed = TRUE)
  sizes <- lengths(pieces)
  rows <- split(seq_len(nrow(t)), factor(t$group_id, levels = ids))
  indices <- spaces <- list()
  world <- seq_len(nworld)-1L
  mass <- rep(1, nworld)
  for (j in seq_along(fixtures)) {
    digit <- (world %/% 3^(j-1L)) %% 3L
    mass <- mass * unlist(q[j, c("W", "D", "L")], use.names = FALSE)[digit+1L]
  }
  for (g in ids) {
    z <- t[rows[[g]], ] |> dplyr::arrange(rank)
    n <- unique(sizes[rows[[g]]])
    if (length(n) != 1L || nrow(z) != 3^n ||
        !identical(as.integer(z$rank), seq_len(nrow(z))) ||
        any(diff(z$probability) > 1e-12) ||
        fixed_start+tickets_per_group-1L > nrow(z)) stop("incomplete or invalid ranked space")
    tokens <- strsplit(z$ticket_id, "|", fixed = TRUE)
    fx <- sub(":[^:]+$", "", tokens[[1]])
    code <- vapply(tokens, function(v) 1L+sum((as.integer(sub(".*:", "", v))-1L)*3^(seq_along(v)-1L)), numeric(1))
    if (anyDuplicated(code)) stop("incomplete distinct outcome space")
    wi <- rep(1L, nworld)
    for (j in seq_along(fx)) wi <- wi + as.integer(((world %/%
      3^(match(fx[j], fixtures)-1L)) %% 3L)*3^(j-1L))
    indices[[g]] <- match(wi, code)
    spaces[[g]] <- z
  }
  purchases <- traces <- list()
  for (policy in c("FIXED", "TOP", "DYNAMIC_WINDOW", "DYNAMIC_SET")) {
    covered <- rep(FALSE, nworld); remaining <- ids; expected <- 0
    for (step in seq_along(ids)) {
      best_gain <- -1; best_group <- NULL; best_rows <- NULL
      candidates <- if (policy %in% c("FIXED", "TOP")) remaining[1] else remaining
      for (g in candidates) {
        marginal <- rowsum(mass * !covered, indices[[g]], reorder = FALSE)
        gains <- numeric(nrow(spaces[[g]]))
        gains[as.integer(rownames(marginal))] <- marginal[, 1]
        if (policy == "DYNAMIC_SET") {
          take <- order(-gains, spaces[[g]]$rank)[seq_len(tickets_per_group)]
        } else {
          start <- if (policy == "FIXED") fixed_start else 1L
          if (policy == "DYNAMIC_WINDOW") {
            cs <- c(0, cumsum(gains)); starts <- seq_len(length(gains)-tickets_per_group+1L)
            start <- which.max(cs[starts+tickets_per_group]-cs[starts])
          }
          take <- seq.int(start, length.out = tickets_per_group)
        }
        gain <- sum(gains[take])
        if (gain > best_gain+1e-14) {best_gain <- gain; best_group <- g; best_rows <- take}
      }
      g <- best_group; z <- spaces[[g]][best_rows, ]
      covered <- covered | indices[[g]] %in% best_rows
      expected <- expected+sum(z$probability)
      purchases[[paste(policy, step)]] <- dplyr::mutate(z, policy = policy, step = step)
      traces[[paste(policy, step)]] <- tibble::tibble(policy = policy, step = step,
        group_id = g, marginal_coverage = best_gain, cumulative_coverage = sum(mass[covered]),
        expected_wins = expected, cost_cny = step*tickets_per_group*unit_cny,
        min_rank = min(z$rank), max_rank = max(z$rank))
      remaining <- setdiff(remaining, g)
    }
  }
  result <- list(purchases = dplyr::bind_rows(purchases), trace = dplyr::bind_rows(traces))
  result$receipt <- list(cutoff = decision$cutoff, input_hash = decision$input_hash,
    code_hash = .rank_outcome_code_hash(roots = "SelectJointOutcomeTickets"),
    constants = list(tickets_per_group = tickets_per_group, fixed_start = fixed_start,
      unit_cny = unit_cny, maximum_worlds = maximum_worlds), worlds = nworld,
    output_hash = rlang::hash(result))
  result
}
