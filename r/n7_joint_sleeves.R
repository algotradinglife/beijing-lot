# Joint N7 research. Selection uses frozen probabilities and estimated prices
# only. All decision entry points require the exact fixture cutoff map. Native
# chronology validation is delegated to src/temporal_learning through the existing
# rank_double_candidates boundary; no historical fitting or temporal utilities
# are implemented here. See docs/research/n7_joint_contract.md for the estimand.

# Validate prediction-only fixtures with the shared Python Cutoff class. python
# is an explicit interpreter path; this initializes reticulate, but performs no
# network, database or file writes. Returns the unchanged cutoff map; invalid
# identities, probabilities, clocks or result-bearing columns stop.
n7_joint_validate <- function(fixtures, cutoffs, python) {
  stopifnot(is.character(python), length(python) == 1L, file.exists(python),
            is.list(cutoffs), length(cutoffs) > 0L)
  reticulate::use_python(python, required = TRUE)
  core <- reticulate::import("src.temporal_learning", convert = TRUE)
  boundary <- reticulate::import("src.fundamentals_n7_baseline", convert = TRUE)
  frame <- dplyr::bind_rows(fixtures)
  stopifnot(is.character(frame$issue), length(unique(frame$issue)) == 1L)
  native <- lapply(cutoffs, function(epoch) core$Cutoff$decision_epoch(frame$issue[1], epoch))
  checked <- boundary$rank_double_candidates(reticulate::r_to_py(frame), cutoffs = native)
  stopifnot(identical(checked[[2]][sort(names(cutoffs))], cutoffs[sort(names(cutoffs))]))
  cutoffs
}

# Build R-native 2187-state PROB / VALUE / constrained FRONTIER subsets for each
# frozen seven-fixture set. State columns are 1-based, fixture indices 1-based.
# Returns finite matrices and one option per (set, rule). No labels or I/O.
# Frontier selects exactly 64 states, maximizes modeled gross, and requires
# >= coverage_fraction * PROB mass and expected ROI >= minimum_roi.
n7_joint_options <- function(bundle, cutoffs, python, model_id, unit_cny,
                             payout_factor, coverage_fraction, minimum_roi,
                             solver_nodes, solver_gap) {
  stopifnot(is.numeric(unit_cny), length(unit_cny) == 1L, unit_cny == 2,
            is.numeric(payout_factor), length(payout_factor) == 1L, payout_factor == .65,
            coverage_fraction > 0, coverage_fraction <= 1, minimum_roi >= -1,
            solver_nodes >= 1, solver_nodes == floor(solver_nodes),
            solver_gap >= 0, solver_gap < 1)
  n7_joint_validate(bundle$expanded_pool$fixtures, cutoffs, python)
  view <- n7_sleeve_tables(bundle, cutoffs, model_id)
  stopifnot(!anyDuplicated(vapply(bundle$sleeves,
    function(g) paste(unlist(g$fixture_indices), collapse = ","), character(1))))
  options <- list(); statuses <- list()
  for (j in seq_along(bundle$sleeves)) {
    g <- bundle$sleeves[[j]]; p <- view$prob_mat[j, ]; v <- view$value_mat[j, ]
    prob <- order(-p, -v, seq_along(p))[seq_len(64)]
    value <- order(-v, -p, seq_along(p))[seq_len(64)]
    fit <- highs::highs_solve(L = v, lower = rep(0, 2187), upper = rep(1, 2187),
      A = rbind(rep(1, 2187), p, v), lhs = c(64, coverage_fraction * sum(p[prob]), 128 * (1 + minimum_roi)),
      rhs = c(64, Inf, Inf), types = rep("I", 2187), maximum = TRUE,
      control = highs::highs_control(mip_max_nodes = as.integer(solver_nodes),
        mip_rel_gap = solver_gap, threads = 1L, random_seed = 0L, log_to_console = FALSE))
    selected <- list(PROB = prob, VALUE = value)
    status <- as.character(fit$status_message)
    if (identical(status, "Optimal")) {
      ix <- which(fit$primal_solution > .5)
      stopifnot(length(ix) == 64L, sum(p[ix]) + 1e-7 >= coverage_fraction * sum(p[prob]),
                sum(v[ix]) + 1e-7 >= 128 * (1 + minimum_roi))
      selected$FRONTIER <- ix
    }
    statuses[[j]] <- tibble::tibble(sleeve_id = g$id, frontier_status = status)
    for (rule in names(selected)) {
      ix <- selected[[rule]]
      options[[length(options) + 1L]] <- list(sleeve_id = g$id, rule = rule,
        fixtures = as.integer(unlist(g$fixture_indices)) + 1L, state_ids = ix,
        coverage = sum(p[ix]), expected_gross = sum(v[ix]),
        state_payout = view$payout_hat_mat[j, ], state_probability = p)
    }
  }
  list(issue = bundle$issue, cutoffs = cutoffs, fixtures = bundle$expanded_pool$fixtures,
       options = options, statuses = dplyr::bind_rows(statuses),
       model_id = model_id, historical_admission = FALSE)
}

# Draw worlds with independent fixture outcomes, sharing each fixture realization
# across every overlapping sleeve. seed/worlds are explicit; global RNG restored.
# The returned integer matrix is worlds x fixtures, values 0=W,1=D,2=L.
n7_joint_worlds <- function(pool, cutoffs, seed, worlds) {
  stopifnot(identical(pool$cutoffs, cutoffs), length(seed) == 1L, is.finite(seed),
            seed >= 0, seed == floor(seed), worlds >= 1, worlds == floor(worlds))
  withr::with_seed(seed, {
    vapply(pool$fixtures, function(f) {
      p <- c(f$p_W, f$p_D, f$p_L)
      stopifnot(length(p) == 3L, all(is.finite(p)), all(p >= 0), abs(sum(p) - 1) < 1e-8)
      u <- runif(worlds)
      as.integer((u >= p[1]) + (u >= p[1] + p[2]))
    }, integer(worlds))
  })
}

# Project shared worlds into option-level hit and q-estimated gross matrices.
# Within a sleeve the 64 states are mutually exclusive, so at most one pays.
n7_joint_returns <- function(pool, worlds, cutoffs) {
  stopifnot(identical(pool$cutoffs, cutoffs), is.matrix(worlds), nrow(worlds) > 0,
            ncol(worlds) == length(pool$fixtures), all(worlds %in% 0:2))
  hits <- gross <- matrix(0, nrow(worlds), length(pool$options))
  for (j in seq_along(pool$options)) {
    o <- pool$options[[j]]
    state <- as.integer(worlds[, o$fixtures, drop = FALSE] %*% (3^(6:0))) + 1L
    hits[, j] <- as.integer(state %in% o$state_ids)
    gross[, j] <- hits[, j] * o$state_payout[state]
  }
  list(hits = hits, gross = gross, cutoffs = cutoffs)
}

# Descriptive maximum cash drawdown for contiguous fixed-length synthetic paths.
# gross is CNY payout per round, stake is CNY per round. Returns one nonnegative
# drawdown per path, including initial equity zero. Length must divide steps.
n7_joint_path_drawdowns <- function(gross, steps, stake) {
  stopifnot(is.numeric(gross), length(gross) > 0L, all(is.finite(gross)), all(gross >= 0),
            steps >= 1, steps == floor(steps), length(gross) %% steps == 0,
            is.finite(stake), stake >= 0)
  paths <- matrix(gross - stake, ncol = steps, byrow = TRUE)
  apply(paths, 1, function(p) {
    equity <- c(0, cumsum(p))
    max(cummax(equity) - equity)
  })
}

# Joint mixed integer maximum-union problem, optionally subject to modeled return,
# fixture reuse U, pair overlap P, and mean simulated five-round path drawdown.
# All limits are explicit fixed research conventions, never fitted to settlement.
# A deterministic node budget avoids wall-clock dependent acceptance. Only solver
# status Optimal plus independent constraint checks can fund a plan. No incumbent
# fallback. choose supports small exact synthetic tests; production requires 8.
n7_joint_solve <- function(pool, scenarios, cutoffs, choose, budget_cny,
                           unit_cny, reuse_cap, overlap_cap, minimum_roi,
                           path_steps, mean_drawdown_cap, solver_nodes, solver_gap) {
  stopifnot(identical(pool$cutoffs, cutoffs), identical(scenarios$cutoffs, cutoffs),
    choose >= 1, choose == floor(choose), budget_cny == choose * 64 * unit_cny,
    unit_cny == 2, reuse_cap >= 1, overlap_cap >= 0, overlap_cap <= 7,
    minimum_roi >= -1, path_steps >= 1, path_steps == floor(path_steps),
    mean_drawdown_cap >= 0, solver_nodes >= 1, solver_nodes == floor(solver_nodes),
    solver_gap >= 0, solver_gap < 1)
  k <- length(pool$options); w <- nrow(scenarios$hits)
  stopifnot(k > 0, identical(dim(scenarios$hits), c(w, k)),
    identical(dim(scenarios$gross), c(w, k)), all(scenarios$hits %in% 0:1),
    all(is.finite(scenarios$gross)), all(scenarios$gross >= 0), w %% path_steps == 0)
  risk <- is.finite(mean_drawdown_cap); paths <- if (risk) w / path_steps else 0L
  nvars <- k + w + paths
  rows <- list(); lo <- hi <- numeric()
  # Explicit sparse blocks, avoiding a bespoke solver or callback abstraction.
  rows[[1]] <- cbind(Matrix::Matrix(rep(1, k), nrow = 1, sparse = TRUE), Matrix::Matrix(0, 1, w + paths))
  lo <- choose; hi <- choose
  groups <- vapply(pool$options, function(o) o$sleeve_id, numeric(1))
  incidence <- vapply(pool$options, function(o) as.numeric(seq_along(pool$fixtures) %in% o$fixtures),
                      numeric(length(pool$fixtures)))
  group_incidence <- outer(unique(groups), groups, `==`) * 1
  fixed <- rbind(group_incidence, incidence,
                 vapply(pool$options, function(o) o$expected_gross, numeric(1)))
  rows[[2]] <- cbind(Matrix::Matrix(fixed, sparse = TRUE), Matrix::Matrix(0, nrow(fixed), w + paths))
  lo <- c(lo, rep(-Inf, nrow(fixed) - 1), budget_cny * (1 + minimum_roi))
  hi <- c(hi, rep(1, nrow(group_incidence)), rep(reuse_cap, nrow(incidence)), Inf)
  bad <- which(crossprod(incidence) > overlap_cap & outer(groups, groups, `!=`) & upper.tri(matrix(0, k, k)), arr.ind = TRUE)
  if (nrow(bad)) {
    a <- Matrix::sparseMatrix(i = rep(seq_len(nrow(bad)), 2), j = c(bad[, 1], bad[, 2]),
                             x = 1, dims = c(nrow(bad), nvars))
    rows[[length(rows) + 1L]] <- a
    lo <- c(lo, rep(-Inf, nrow(bad))); hi <- c(hi, rep(1, nrow(bad)))
  }
  # y_s <= sum_j hit_sj*x_j, 0<=y<=1 measures the union in the same world.
  rows[[length(rows) + 1L]] <- cbind(Matrix::Matrix(scenarios$hits, sparse = TRUE),
                                    -Matrix::Diagonal(w), Matrix::Matrix(0, w, paths))
  lo <- c(lo, rep(0, w)); hi <- c(hi, rep(Inf, w))
  if (risk) {
    for (start in seq_len(path_steps)) for (end in start:path_steps) {
      totals <- matrix(0, paths, k)
      for (step in start:end) totals <- totals + scenarios$gross[seq(step, w, by = path_steps), , drop = FALSE]
      rows[[length(rows) + 1L]] <- cbind(Matrix::Matrix(totals, sparse = TRUE),
        Matrix::Matrix(0, paths, w), Matrix::Diagonal(paths))
      lo <- c(lo, rep((end - start + 1) * budget_cny, paths)); hi <- c(hi, rep(Inf, paths))
    }
    rows[[length(rows) + 1L]] <- Matrix::sparseMatrix(i = rep(1L, paths), j = k + w + seq_len(paths),
      x = rep(1 / paths, paths), dims = c(1, nvars))
    lo <- c(lo, -Inf); hi <- c(hi, mean_drawdown_cap)
  }
  fit <- highs::highs_solve(L = c(rep(0, k), rep(1 / w, w), rep(0, paths)),
    lower = rep(0, nvars), upper = c(rep(1, k + w), rep(Inf, paths)),
    A = do.call(rbind, rows), lhs = lo, rhs = hi, types = c(rep("I", k), rep("C", w + paths)),
    maximum = TRUE, control = highs::highs_control(mip_max_nodes = as.integer(solver_nodes),
      mip_rel_gap = solver_gap, threads = 1L, random_seed = 0L, log_to_console = FALSE))
  status <- as.character(fit$status_message)
  selected <- if (identical(status, "Optimal")) which(fit$primal_solution[seq_len(k)] > .5) else integer()
  if (length(selected)) {
    stopifnot(length(selected) == choose, !anyDuplicated(groups[selected]),
      max(rowSums(incidence[, selected, drop = FALSE])) <= reuse_cap,
      sum(vapply(pool$options[selected], function(o) o$expected_gross, numeric(1))) + 1e-6 >= budget_cny * (1 + minimum_roi))
    pair <- crossprod(incidence[, selected, drop = FALSE]); diag(pair) <- 0
    stopifnot(max(pair) <= overlap_cap)
    dd <- n7_joint_path_drawdowns(rowSums(scenarios$gross[, selected, drop = FALSE]), path_steps, budget_cny)
    stopifnot(mean(dd) <= mean_drawdown_cap + 1e-5)
  }
  list(status = status, selected = selected, cutoffs = cutoffs,
       solver = fit$info, historical_admission = FALSE)
}

# Package an already selected set of option indices into canonical physical
# tickets. Returns no seal: the runner seals via shared stable_json_hash. Numeric
# indices in the interchange plan are zero-based; official outcomes remain WDL.
# No settlement is read here. Empty selection holds the entire CNY1024 budget.
n7_joint_plan <- function(pool, selected, cutoffs, arm, seed, training, evaluation,
                          status, solver, config) {
  stopifnot(identical(pool$cutoffs, cutoffs), identical(training$cutoffs, cutoffs),
    identical(evaluation$cutoffs, cutoffs), !anyDuplicated(selected),
    length(selected) %in% c(0, 8), all(selected %in% seq_along(pool$options)),
    config$budget_cny == 1024, config$unit_cny == 2, config$payout_factor == .65)
  canonical <- as.matrix(expand.grid(rep(list(0:2), 7)))[, 7:1, drop = FALSE]
  indices <- outcomes <- matrix(integer(), 0, 7)
  keys <- list()
  for (j in selected) {
    o <- pool$options[[j]]
    stopifnot(length(o$state_ids) == 64, !anyDuplicated(o$state_ids))
    indices <- rbind(indices, matrix(rep(o$fixtures - 1L, each = 64), ncol = 7))
    outcomes <- rbind(outcomes, canonical[o$state_ids, , drop = FALSE])
    keys[[length(keys) + 1L]] <- list(sleeve_id = o$sleeve_id, rule = o$rule,
      coverage = o$coverage, expected_gross = o$expected_gross,
      state_ids = as.list(o$state_ids - 1L))
  }
  stopifnot(!anyDuplicated(apply(3 * indices + outcomes, 1, paste, collapse = ",")))
  incidence <- vapply(pool$options[selected], function(o)
    as.numeric(seq_along(pool$fixtures) %in% o$fixtures), numeric(length(pool$fixtures)))
  if (!length(selected)) incidence <- matrix(0, length(pool$fixtures), 0)
  overlap <- crossprod(incidence); diag(overlap) <- 0
  stake <- nrow(indices) * config$unit_cny
  train_gross <- rowSums(training$gross[, selected, drop = FALSE])
  eval_gross <- rowSums(evaluation$gross[, selected, drop = FALSE])
  expected <- sum(vapply(pool$options[selected], function(o) o$expected_gross, numeric(1)))
  list(issue = pool$issue, arm = arm, seed = seed, model_id = pool$model_id,
    fixtures = pool$fixtures, cutoffs = cutoffs, fixture_indices = indices, outcomes = outcomes,
    groups = nrow(indices), stake = stake, cash_cny = config$budget_cny - stake,
    budget_cny = config$budget_cny, unit_cny = config$unit_cny, payout_factor = config$payout_factor,
    sleeve_keys = keys, solver_status = status, solver = solver,
    expected_net = expected - stake, expected_roi = if (stake > 0) expected / stake - 1 else NULL,
    train_coverage = mean(rowSums(training$hits[, selected, drop = FALSE]) > 0),
    eval_coverage = mean(rowSums(evaluation$hits[, selected, drop = FALSE]) > 0),
    train_path_drawdown = mean(n7_joint_path_drawdowns(train_gross, config$path_steps, stake)),
    eval_path_drawdown = mean(n7_joint_path_drawdowns(eval_gross, config$path_steps, stake)),
    max_reuse = max(c(0, rowSums(incidence))), max_overlap = max(c(0, overlap)),
    mean_sleeve_coverage = if (length(selected)) mean(vapply(pool$options[selected], function(o) o$coverage, numeric(1))) else NULL,
    historical_admission = FALSE)
}

# Complete one prediction-only issue for every fixed arm/seed. Caller supplies a
# validated source bundle and explicit configuration; all computation is R-native
# except native Cutoff validation. No I/O, fitting, target labels or caches.
n7_joint_issue <- function(bundle, cutoffs, config, python) {
  stopifnot(config$n == 7, config$sleeves == 8, config$tickets_per_sleeve == 64,
    config$budget_cny == 1024, config$unit_cny == 2, config$payout_factor == .65,
    identical(config$mode, "EXPOSED_HISTORICAL_DIAGNOSTIC"),
    !anyDuplicated(unlist(config$seeds)),
    setequal(unlist(config$arms), c("QUALITY_PROB", "UNION_PROB", "JOINT_UNION", "JOINT_RETURN",
      "JOINT_UP", "JOINT_FULL", "JOINT_NO_RETURN", "JOINT_NO_UP")))
  pool <- n7_joint_options(bundle, cutoffs, python, config$model_id, config$unit_cny,
    config$payout_factor, config$coverage_fraction, config$minimum_roi, config$solver_nodes, config$solver_gap)
  result <- list(); world_receipts <- list()
  for (seed in unlist(config$seeds)) {
    training_worlds <- n7_joint_worlds(pool, cutoffs, seed, config$training_worlds)
    evaluation_worlds <- n7_joint_worlds(pool, cutoffs, seed + config$evaluation_seed_offset, config$evaluation_worlds)
    train <- n7_joint_returns(pool, training_worlds, cutoffs)
    evaluation <- n7_joint_returns(pool, evaluation_worlds, cutoffs)
    world_receipts[[length(world_receipts) + 1L]] <- list(seed = seed,
      training = training_worlds, evaluation = evaluation_worlds)
    for (arm in unlist(config$arms)) {
      allowed <- seq_along(pool$options)
      if (arm %in% c("QUALITY_PROB", "UNION_PROB"))
        allowed <- allowed[vapply(pool$options, function(o) o$rule == "PROB", logical(1))]
      local <- pool; local$options <- pool$options[allowed]
      local_train <- train
      local_train$hits <- train$hits[, allowed, drop = FALSE]
      local_train$gross <- train$gross[, allowed, drop = FALSE]
      if (arm == "QUALITY_PROB") {
        mass <- vapply(local$options, function(o) o$coverage, numeric(1))
        value <- vapply(local$options, function(o) o$expected_gross, numeric(1))
        selected <- if (length(mass) >= 8) order(-mass, -value, seq_along(mass))[1:8] else integer()
        fit <- list(selected = selected, status = if (length(selected)) "FIXED_RULE" else "INSUFFICIENT_G", solver = NULL)
      } else {
        use_return <- arm %in% c("JOINT_RETURN", "JOINT_UP", "JOINT_FULL", "JOINT_NO_UP")
        use_up <- arm %in% c("JOINT_UP", "JOINT_FULL", "JOINT_NO_RETURN")
        use_risk <- arm %in% c("JOINT_FULL", "JOINT_NO_RETURN", "JOINT_NO_UP")
        fit <- n7_joint_solve(local, local_train, cutoffs, config$sleeves, config$budget_cny,
          config$unit_cny, if (use_up) config$reuse_cap else 8, if (use_up) config$overlap_cap else 7,
          if (use_return) config$minimum_roi else -1, config$path_steps,
          if (use_risk) config$mean_drawdown_cap else Inf, config$solver_nodes, config$solver_gap)
      }
      result[[length(result) + 1L]] <- n7_joint_plan(pool, allowed[fit$selected], cutoffs,
        arm, seed, train, evaluation, fit$status, fit$solver, config)
    }
  }
  list(plans = result, frontier_status = pool$statuses, worlds = world_receipts,
       cutoffs = cutoffs, historical_admission = FALSE)
}
