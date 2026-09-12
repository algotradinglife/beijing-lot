# Descriptive report for frozen/evaluated R-native joint plans. One input row per
# issue/arm/seed. Amounts CNY, probability inputs fractions, displayed rates %.
# Existing equity and sleeve summary functions must be sourced by the entry point.
# No fitting, selection, chronology inference, source mutation or I/O.
n7_joint_report <- function(rows, issue_order, initial_capital_cny, budget_cny,
                            mean_drawdown_cap) {
  stopifnot(all(c("solver_status", "train_path_drawdown", "eval_path_drawdown") %in% names(rows)),
    all(c("QUALITY_PROB", "JOINT_UNION", "JOINT_FULL") %in% rows$arm),
    is.finite(mean_drawdown_cap), mean_drawdown_cap >= 0)
  base <- n7_sleeve_summary(rows, issue_order, initial_capital_cny, budget_cny)
  base$curves <- base$curves |> dplyr::mutate(
    drawdown_percent = 100 * drawdown_cny / (equity_cny + drawdown_cny))
  dd <- base$curves |> dplyr::group_by(model, policy) |>
    dplyr::summarise(max_drawdown_percent = max(drawdown_percent), .groups = "drop")
  base$summary <- base$summary |> dplyr::left_join(dd, by = c("model", "policy"), relationship = "one-to-one")
  base$grid <- base$grid |> dplyr::left_join(
    dd |> dplyr::group_by(model) |> dplyr::summarise(max_drawdown_percent = median(max_drawdown_percent), .groups = "drop"),
    by = "model", relationship = "one-to-one")
  comparisons <- list()
  for (control in c("QUALITY_PROB", "JOINT_UNION", "JOINT_FULL")) {
    reference <- base$periods |> dplyr::filter(arm == control) |>
      dplyr::select(issue, seed, base_stake = stake, base_net = net, base_hits = hits)
    joined <- base$periods |> dplyr::left_join(reference, by = c("issue", "seed"), relationship = "many-to-one")
    stopifnot(!anyNA(joined[c("base_stake", "base_net", "base_hits")]))
    comparisons[[control]] <- joined |> dplyr::mutate(full = stake == budget_cny & base_stake == budget_cny) |>
      dplyr::group_by(arm, seed) |> dplyr::summarise(control = control, matched_issues = sum(full),
        roi_percent = if (sum(full)) 100 * sum(net[full]) / sum(stake[full]) else NA_real_,
        control_roi_percent = if (sum(full)) 100 * sum(base_net[full]) / sum(base_stake[full]) else NA_real_,
        matched_net_difference = sum(net[full] - base_net[full]),
        gained_hit_issues = sum(full & hits > 0 & base_hits == 0),
        lost_hit_issues = sum(full & hits == 0 & base_hits > 0), .groups = "drop")
  }
  constraints <- rows |> dplyr::filter(!is.na(solver_status)) |>
    dplyr::count(arm, seed, solver_status, name = "issues")
  numerical <- rows |> dplyr::filter(!is.na(solver_status), stake > 0) |>
    dplyr::group_by(arm, seed) |> dplyr::summarise(funded_issues = dplyr::n(),
      train_coverage_percent = 100 * mean(train_coverage),
      eval_coverage_percent = 100 * mean(eval_coverage),
      optimism_pp = 100 * mean(train_coverage - eval_coverage),
      train_mean_path_drawdown_cny = mean(train_path_drawdown),
      eval_mean_path_drawdown_cny = mean(eval_path_drawdown),
      evaluation_risk_exceedances = sum(eval_path_drawdown > mean_drawdown_cap), .groups = "drop")
  segments <- base$periods |> dplyr::mutate(
    segment = ifelse(period <= ceiling(length(issue_order) / 2), "前半期次", "后半期次")) |>
    dplyr::group_by(arm, seed, segment) |> dplyr::summarise(issues = dplyr::n(),
      stake_cny = sum(stake), net_cny = sum(net), hit_issues = sum(hits > 0),
      profitable_issues = sum(net > 0), roi_percent = if (sum(stake) > 0) 100 * sum(net) / sum(stake) else NA_real_,
      .groups = "drop")
  c(base, list(paired = dplyr::bind_rows(comparisons), constraints = constraints,
               numerical = numerical, segments = segments))
}

# Paired issue-cluster percentile bootstrap of treatment minus control ROI (pp).
# Resamples whole issues with all seeds together, so three seeds do not pretend
# to be three independent histories. Each seed/issue must exist in both arms;
# retain only pairs with the same full budget. No new selection or tuning.
# Returns point estimate, 95% interval, complete-draw count and matched issues.
# No overlap returns an explicit unavailable interval, never zero improvement.
n7_joint_bootstrap <- function(periods, treatment, control, budget_cny, reps, seed) {
  stopifnot(all(c("issue", "arm", "seed", "stake", "net") %in% names(periods)),
    reps >= 20, reps == floor(reps), seed >= 0, seed == floor(seed), budget_cny > 0,
    !anyDuplicated(periods[c("issue", "arm", "seed")]))
  a <- periods |> dplyr::filter(arm == treatment) |>
    dplyr::select(issue, seed, a_stake = stake, a_net = net)
  b <- periods |> dplyr::filter(arm == control) |>
    dplyr::select(issue, seed, b_stake = stake, b_net = net)
  stopifnot(nrow(a) > 0, nrow(b) > 0)
  paired <- dplyr::full_join(a, b, by = c("issue", "seed"), relationship = "one-to-one")
  stopifnot(!anyNA(paired))
  blocks <- paired |> dplyr::filter(a_stake == budget_cny, b_stake == budget_cny) |>
    dplyr::group_by(issue) |> dplyr::summarise(stake = sum(a_stake), difference = sum(a_net - b_net), .groups = "drop")
  if (nrow(blocks) < 2) return(tibble::tibble(treatment = treatment, control = control,
    matched_issues = nrow(blocks), delta_roi_pp = NA_real_, lower95_pp = NA_real_, upper95_pp = NA_real_,
    bootstrap_reps = 0L, status = "INSUFFICIENT_MATCHED_ISSUES"))
  statistic <- function(data, i) 100 * sum(data$difference[i]) / sum(data$stake[i])
  fit <- withr::with_seed(seed, boot::boot(blocks, statistic, R = reps))
  interval <- stats::quantile(fit$t[, 1], c(.025, .975), names = FALSE)
  tibble::tibble(treatment = treatment, control = control, matched_issues = nrow(blocks),
    delta_roi_pp = as.numeric(fit$t0), lower95_pp = interval[1], upper95_pp = interval[2],
    bootstrap_reps = reps, status = "PAIRED_ISSUE_CLUSTER_DIAGNOSTIC")
}
