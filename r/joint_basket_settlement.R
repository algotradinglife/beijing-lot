# Official-SP settlement for the joint-probability basket portfolio.
#
# Scope: post-settlement accounting only. No learning, selection, tuning or
# policy change. The portfolio is read from the frozen 254 artifacts; this
# module never re-derives it.
#
# Payout contract (authoritative in r/n7_purchase_settle.R and
# r/n7_rank_diagnostic.R, and re-derived from the frozen 254 bundles):
#   gross_if_hit = unit_cny * payout_factor * prod(official SP of the 7 legs)
# Every bought ticket is a distinct 7-tuple bought once, so the per-ticket copy
# count is 1 and at most one ticket per basket can win.
#
# SP is read through the authoritative r/nowscore_query.R reader, which also
# applies the sp_correction audit. SP is a dimensionless source multiplier; it is
# money only after the explicit unit/payout constants above.
#
# Missing SP is DATA, not a contract violation: the archive records one option
# row per observation, and for some fixtures that row is absent. Such a basket
# cannot be priced, so it is excluded from the return denominator and counted
# explicitly by jb_priceable_baskets. Hit/coverage does not depend on SP and is
# therefore never affected.

jb_sp_columns <- c("issue", "slot", "provider_id", "option", "sp", "sp_source")
jb_option_of_outcome <- c("1" = "胜", "2" = "平", "3" = "负")

# Read the official SP for every settled spf observation of the given issues.
# One row per issue/slot. Structural problems fail closed; an absent option/SP
# row is preserved as NA so that it can be counted rather than silently dropped.
jb_official_sp <- function(db_path, issues, progress_every = 100L) {
  if (!is.character(db_path) || length(db_path) != 1L || !file.exists(db_path)) {
    stop("jb_official_sp: db_path must be an existing SQLite file")
  }
  issues <- as.character(issues)
  if (!length(issues) || anyNA(issues) || anyDuplicated(issues)) {
    stop("jb_official_sp: issues must be unique and non-missing")
  }
  out <- vector("list", length(issues))
  for (i in seq_along(issues)) {
    s <- query_nowscore_settlement(db_path, issues[i], play = "spf")$settlement
    if (!nrow(s)) stop("jb_official_sp: no spf settlement for issue ", issues[i])
    if (anyDuplicated(s$slot)) stop("jb_official_sp: duplicated slot for issue ", issues[i])
    if (anyNA(s$native_match_id)) stop("jb_official_sp: missing fixture identity for ", issues[i])
    # A finite SP must be usable; NA is a recorded absence, not a bad value.
    if (any(is.finite(s$sp) & s$sp <= 0)) {
      stop("jb_official_sp: non-positive SP for issue ", issues[i])
    }
    # Row-wise, not whole-table: comparing the two flags collapses each side to a
    # single boolean, so a row with an option but no SP next to a row with an SP
    # but no option would cancel out and pass.
    if (any(is.na(s$option) != is.na(s$sp))) {
      stop("jb_official_sp: option and SP absence disagree for issue ", issues[i])
    }
    out[[i]] <- tibble::tibble(
      issue = as.character(s$issue), slot = as.integer(s$slot),
      provider_id = as.character(s$native_match_id),
      option = as.character(s$option), sp = as.numeric(s$sp),
      sp_source = as.character(s$sp_source))
    if (progress_every > 0L && i %% progress_every == 0L) {
      cat(sprintf("  SP: %d / %d issues\n", i, length(issues)))
    }
  }
  sp <- dplyr::bind_rows(out)
  if (!identical(names(sp), jb_sp_columns)) stop("jb_official_sp: unexpected column set")
  sp
}

# Bind each bought leg to its official SP.
#
# Two distinct situations, deliberately separated:
#   * the fixture has no settlement row at all  -> structural, fail closed
#   * the fixture has a row but no SP recorded  -> priceable = FALSE, kept as NA
# Where a winning option is recorded it must agree with jb_outcome_index, which
# makes this an independent check of the direction derivation.
jb_attach_sp <- function(legs, sp) {
  need <- c("issue", "basket", "leg", "slot", "provider_id", "outcome")
  if (!all(need %in% names(legs))) stop("jb_attach_sp: legs must include ", paste(need, collapse = ", "))
  if (!all(jb_sp_columns %in% names(sp))) stop("jb_attach_sp: sp must include ", paste(jb_sp_columns, collapse = ", "))
  if (anyDuplicated(sp[c("issue", "slot")])) stop("jb_attach_sp: duplicated issue/slot in sp")
  if (!nrow(legs)) stop("jb_attach_sp: no legs")
  j <- match(paste(legs$issue, legs$slot), paste(sp$issue, sp$slot))
  if (anyNA(j)) {
    stop("jb_attach_sp: ", sum(is.na(j)), " leg(s) have no settlement row at all")
  }
  if (any(sp$provider_id[j] != legs$provider_id)) {
    stop("jb_attach_sp: provider identity disagrees with the settlement source")
  }
  expected <- unname(jb_option_of_outcome[as.character(legs$outcome)])
  if (anyNA(expected)) stop("jb_attach_sp: outcome outside 1..3")
  recorded <- !is.na(sp$option[j])
  if (any(sp$option[j][recorded] != expected[recorded])) {
    bad <- which(recorded & sp$option[j] != expected)[1]
    stop("jb_attach_sp: outcome/SP option disagreement at issue ", legs$issue[bad],
         " slot ", legs$slot[bad], ": derived ", expected[bad], " vs source ", sp$option[j][bad])
  }
  legs$sp <- sp$sp[j]
  legs$sp_source <- sp$sp_source[j]
  legs
}

# Which baskets can be priced. A basket is priceable only when all 7 legs carry
# a usable SP. Returns one row per basket plus the priced-leg counts, so that a
# reduced denominator is always reported rather than assumed.
jb_priceable_baskets <- function(legs_sp) {
  if (!all(c("issue", "basket", "sp") %in% names(legs_sp))) {
    stop("jb_priceable_baskets: legs_sp must include issue, basket, sp")
  }
  if (!nrow(legs_sp)) stop("jb_priceable_baskets: no legs")
  per <- legs_sp |> dplyr::group_by(.data$issue, .data$basket) |>
    dplyr::summarise(n_legs = dplyr::n(), n_priced = sum(!is.na(.data$sp)),
                     priceable = all(!is.na(.data$sp)), .groups = "drop")
  if (any(per$n_legs != 7L)) stop("jb_priceable_baskets: every basket must carry exactly 7 legs")
  per
}

# Per-basket payout if that basket's settled tuple was among the bought tickets.
# Only priceable baskets may be passed. Fails closed on anything unexpected.
jb_basket_gross <- function(legs_sp, unit_cny = 2, payout_factor = 0.65) {
  if (unit_cny != 2) stop("jb_basket_gross: unit_cny must be 2 CNY")
  if (abs(payout_factor - 0.65) > 1e-12) stop("jb_basket_gross: payout_factor must be 0.65")
  if (!nrow(legs_sp)) stop("jb_basket_gross: no legs")
  if (!all(c("issue", "basket", "leg", "sp", "tickets") %in% names(legs_sp))) {
    stop("jb_basket_gross: legs_sp must include issue, basket, leg, sp, tickets")
  }
  if (anyNA(legs_sp$sp)) {
    stop("jb_basket_gross: unpriceable basket passed; filter with jb_priceable_baskets first")
  }
  chk <- legs_sp |> dplyr::group_by(.data$issue, .data$basket) |>
    dplyr::summarise(n_legs = dplyr::n(), n_leg = dplyr::n_distinct(.data$leg),
                     n_tickets = dplyr::n_distinct(.data$tickets), .groups = "drop")
  if (any(chk$n_legs != 7L) || any(chk$n_leg != 7L)) {
    stop("jb_basket_gross: every basket must carry exactly 7 distinct legs")
  }
  if (any(chk$n_tickets != 1L)) stop("jb_basket_gross: tickets must be constant within a basket")
  if (!all(is.finite(legs_sp$sp)) || any(legs_sp$sp <= 0)) {
    stop("jb_basket_gross: SP must be finite and positive")
  }
  legs_sp |> dplyr::group_by(.data$issue, .data$basket) |>
    dplyr::summarise(tickets = dplyr::first(.data$tickets),
                     gross_if_hit = unit_cny * payout_factor * prod(.data$sp),
                     .groups = "drop") |>
    # Number of tickets at which the stake exactly consumes the payout; beyond it
    # a winning basket loses money. The 3^7 = 2187 clamp matches the lineage
    # (r/n7_rank_diagnostic.R: break_even_depth = min(2187, floor(gross/unit))):
    # the whole tuple space cannot be exceeded, so break-even saturates there.
    dplyr::mutate(break_even_depth = pmin(2187L, floor(.data$gross_if_hit / unit_cny)))
}

# Per-issue realised return over the baskets supplied. Only a hitting basket pays;
# every supplied ticket is paid for. Baskets inside an issue share no fixture, so
# at most one can win. Pass the priceable subset for a subset-denominated ROI.
jb_issue_returns <- function(baskets, gross, unit_cny = 2) {
  if (unit_cny != 2) stop("jb_issue_returns: unit_cny must be 2 CNY")
  key <- c("issue", "basket")
  if (!nrow(baskets)) stop("jb_issue_returns: no baskets")
  if (anyDuplicated(baskets[key])) stop("jb_issue_returns: duplicated issue/basket in baskets")
  if (anyDuplicated(gross[key])) stop("jb_issue_returns: duplicated issue/basket in gross")
  # Both tables carry a ticket count; keep them separate so the join cannot
  # silently suffix one and then assert the wrong column.
  g <- dplyr::rename(gross, tickets_gross = "tickets")
  z <- dplyr::left_join(baskets, g, by = key, relationship = "one-to-one")
  if (anyNA(z$gross_if_hit)) stop("jb_issue_returns: a supplied basket has no payout")
  if (anyNA(z$tickets) || any(z$tickets < 1)) stop("jb_issue_returns: tickets must be >= 1")
  if (!all(z$tickets == z$tickets_gross)) {
    stop("jb_issue_returns: ticket count disagrees with the payout table")
  }
  # The realised tuple is bought exactly when its rank is within the ticket count.
  if (all(c("rank_full", "hit") %in% names(z)) &&
      !all(z$hit == (z$rank_full <= z$tickets))) {
    stop("jb_issue_returns: hit disagrees with the bought-rank definition")
  }
  z$gross <- ifelse(z$hit, z$gross_if_hit, 0)
  z$stake <- z$tickets * unit_cny
  z$net <- z$gross - z$stake
  z |> dplyr::group_by(.data$issue) |>
    dplyr::summarise(cohort = dplyr::first(.data$cohort),
                     baskets = dplyr::n(), tickets = sum(.data$tickets),
                     stake = sum(.data$stake), hits = sum(.data$hit),
                     gross = sum(.data$gross), net = sum(.data$net),
                     .groups = "drop") |>
    dplyr::mutate(roi = .data$net / .data$stake)
}

# Pooled capital-weighted ROI, resampling whole issues because baskets within an
# issue share the same draw and are not independent observations.
jb_bootstrap_roi <- function(returns, n_boot = 2000L, seed = 1L) {
  if (!nrow(returns)) stop("jb_bootstrap_roi: no returns")
  if (!all(c("stake", "net") %in% names(returns))) stop("jb_bootstrap_roi: need stake and net")
  if (!is.finite(seed)) stop("jb_bootstrap_roi: seed must be finite")
  # Scope the RNG mutation so the caller's stream is untouched.
  old_seed <- if (exists(".Random.seed", .GlobalEnv)) get(".Random.seed", .GlobalEnv) else NULL
  on.exit({
    if (is.null(old_seed)) {
      if (exists(".Random.seed", .GlobalEnv)) rm(".Random.seed", envir = .GlobalEnv)
    } else {
      assign(".Random.seed", old_seed, envir = .GlobalEnv)
    }
  }, add = TRUE)
  set.seed(as.integer(seed))
  n <- nrow(returns)
  idx <- matrix(sample.int(n, n * n_boot, replace = TRUE), nrow = n)
  roi <- vapply(seq_len(n_boot), function(b) {
    sum(returns$net[idx[, b]]) / sum(returns$stake[idx[, b]])
  }, numeric(1))
  stats::quantile(roi, c(0.025, 0.5, 0.975), names = FALSE)
}

jb_return_summary <- function(returns, n_boot = 2000L, seed = 1L) {
  scope <- function(d, label) {
    if (!nrow(d)) {
      return(tibble::tibble(scope = label, issues = 0L, tickets = 0, stake = 0,
                            gross = 0, net = 0, roi = NA_real_, hit_issues = 0L,
                            hit_rate = NA_real_, roi_lo = NA_real_,
                            roi_median = NA_real_, roi_hi = NA_real_))
    }
    ci <- jb_bootstrap_roi(d, n_boot, seed)
    tibble::tibble(scope = label, issues = nrow(d), tickets = sum(d$tickets),
                   stake = sum(d$stake), gross = sum(d$gross), net = sum(d$net),
                   roi = sum(d$net) / sum(d$stake),
                   hit_issues = sum(d$hits > 0), hit_rate = mean(d$hits > 0),
                   roi_lo = ci[1], roi_median = ci[2], roi_hi = ci[3])
  }
  dplyr::bind_rows(
    scope(returns, "ALL"),
    scope(dplyr::filter(returns, .data$cohort == "ORIGINAL"), "ORIGINAL"),
    scope(dplyr::filter(returns, .data$cohort == "ADDITIONAL"), "ADDITIONAL"))
}

# Per-issue equity, running peak and drawdown for a fixed-stake, non-compounding
# series. The peak is floored at 0 because not betting is always available, so a
# series that never rises has peak 0 and is underwater from the first issue.
# An issue is the unit of the series: baskets within an issue share one draw.
jb_equity_curve <- function(returns) {
  if (!nrow(returns)) stop("jb_equity_curve: no returns")
  if (!all(c("issue", "net", "stake") %in% names(returns))) {
    stop("jb_equity_curve: returns must include issue, net, stake")
  }
  if (anyNA(returns$net) || anyNA(returns$stake)) {
    stop("jb_equity_curve: net and stake must be complete")
  }
  if (any(!is.finite(returns$net)) || any(!is.finite(returns$stake))) {
    stop("jb_equity_curve: net and stake must be finite")
  }
  if (any(returns$stake <= 0)) stop("jb_equity_curve: stake must be positive")
  if (anyDuplicated(returns$issue)) stop("jb_equity_curve: one row per issue")
  if ("date" %in% names(returns) && anyNA(returns$date)) {
    stop("jb_equity_curve: date must be complete")
  }
  d <- returns[order(returns$issue), , drop = FALSE]
  d$equity <- cumsum(d$net)
  d$peak <- cummax(pmax(d$equity, 0))
  d$underwater <- d$equity - d$peak
  d
}

# Drawdown summary of the same series. Indices are issue positions in the ordered
# curve, so no pre-betting offset is involved. `date` is optional; when present,
# peak-to-trough duration is reported in calendar days.
jb_drawdown <- function(returns, scope = "ALL") {
  d <- jb_equity_curve(returns)
  deployed <- cumsum(d$stake)
  dd <- d$underwater
  trough_at <- which.min(dd)
  peak_value <- max(d$peak)
  # The relevant peak is the one the deepest drawdown is measured from.
  top_at <- which.max(d$peak[seq_len(trough_at)])
  peak_is_prebet <- max(d$peak[seq_len(trough_at)]) <= 0
  # The peak that the reported drawdown is measured FROM, not the global peak.
  # Reporting the global maximum next to a trough taken from a different origin
  # mixes two unrelated points of the curve. When there is no drawdown at all the
  # origin is undefined, and the peak of the whole curve is the meaningful one.
  has_drawdown <- min(dd, na.rm = TRUE) < -1e-9
  if (!has_drawdown) top_at <- which.max(d$peak)
  origin_cny <- d$peak[top_at]
  under <- dd < -1e-9
  runs <- rle(under)
  tibble::tibble(
    scope = scope, issues = nrow(d), stake = sum(d$stake), net = sum(d$net),
    roi = sum(d$net) / sum(d$stake),
    peak_cny = origin_cny,
    peak_issue = if (origin_cny > 0) d$issue[top_at] else NA_character_,
    global_peak_cny = peak_value,
    global_peak_issue = if (peak_value > 0) d$issue[which.max(d$peak)] else NA_character_,
    trough_cny = d$equity[trough_at], trough_issue = d$issue[trough_at],
    max_drawdown_cny = min(dd),
    max_drawdown_share_of_deployed = min(dd) / deployed[trough_at],
    peak_to_trough_issues = if (peak_is_prebet) trough_at else trough_at - top_at,
    peak_to_trough_days = if ("date" %in% names(d)) {
      as.integer(d$date[trough_at] - d$date[top_at])
    } else {
      NA_integer_
    },
    issues_underwater_share = mean(under),
    longest_underwater_run = if (any(runs$values)) max(runs$lengths[runs$values]) else 0L,
    terminal_cny = d$equity[nrow(d)],
    gap_to_peak_cny = d$equity[nrow(d)] - peak_value)
}
