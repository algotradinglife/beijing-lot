# P0 probability audit for the joint-probability basket framework.
#
# The basket ranking key is the frozen model probability `p`. Before changing any
# objective we must establish what `p` is worth relative to the two market
# signals that already exist:
#
#   p  frozen model probability (bundle p_W/p_D/p_L)
#   q  market probability as carried in the bundle (q_W/q_D/q_L). This is a
#      DERIVED quantity: European 1X2 de-vigged, fitted to independent-Poisson
#      rates and projected through the native handicap line
#      (divergence_profile Q_EU_BJLINE). It is not a raw price.
#   s  raw market: de-vigged inverse official Beijing SP, normalised. This is the
#      quantity that actually drives the payout.
#
# Everything here is pure and deterministic: no I/O, no fitting, no randomness.
# A logistic fit is a *measurement* of the existing signals, not a model that is
# used to select baskets; nothing in this file feeds basket construction.

# Inverse-SP de-vig, mirroring divergence_profile.devig_normalize: strictly
# positive, finite, normalised to sum one. Fails closed rather than clipping.
jb_devig_triplet <- function(w, d, l) {
  m <- cbind(w, d, l)
  if (!is.numeric(m) || ncol(m) != 3L) stop("jb_devig_triplet: need three numeric columns")
  if (anyNA(m)) stop("jb_devig_triplet: missing SP")
  if (any(!is.finite(m))) stop("jb_devig_triplet: non-finite SP")
  if (any(m <= 1)) stop("jb_devig_triplet: decimal SP must exceed 1")
  inv <- 1 / m
  inv / rowSums(inv)
}

# Official SP rows -> one row per fixture with the de-vigged raw-market vector.
# `sp` is the jb_official_sp shape: issue, slot, provider_id, option, sp.
jb_sp_signals <- function(sp, min_sp = 1) {
  need <- c("issue", "slot", "provider_id", "option", "sp")
  if (!all(need %in% names(sp))) stop("jb_sp_signals: sp must include ",
                                      paste(need, collapse = ", "))
  if (!nrow(sp)) stop("jb_sp_signals: no SP rows")
  # A row with no recorded option or no recorded SP cannot be assigned to an
  # outcome. That is MISSING data, not malformed data: count it and move on.
  # An unknown but present label is malformed and still fails closed.
  usable <- !is.na(sp$option) & !is.na(sp$sp)
  dropped_rows <- sum(!usable)
  sp <- sp[usable, , drop = FALSE]
  if (!nrow(sp)) stop("jb_sp_signals: no row carries both an option and an SP")
  key <- c("issue", "slot", "option")
  if (anyDuplicated(sp[key])) stop("jb_sp_signals: duplicated issue/slot/option")
  known <- unname(jb_option_of_outcome)
  if (any(!sp$option %in% known)) {
    stop("jb_sp_signals: unknown option label(s): ",
         paste(utils::head(setdiff(unique(sp$option), known), 3), collapse = ", "))
  }
  wide <- tidyr::pivot_wider(
    dplyr::mutate(sp, outcome = as.integer(names(jb_option_of_outcome)[
      match(.data$option, unname(jb_option_of_outcome))])),
    id_cols = c("issue", "slot", "provider_id"), names_from = "outcome",
    values_from = "sp", names_prefix = "sp_")
  # A fixture missing an outcome column entirely is incomplete data, not a
  # malformed table: materialise the column as NA so the completeness filter
  # below drops and counts it.
  for (col in c("sp_1", "sp_2", "sp_3")) {
    if (!col %in% names(wide)) wide[[col]] <- NA_real_
  }
  # A fixture is usable only when all three outcomes carry a usable SP. A
  # partially priced fixture cannot be de-vigged and is reported, never imputed.
  complete <- stats::complete.cases(wide[, c("sp_1", "sp_2", "sp_3")]) &
    wide$sp_1 > min_sp & wide$sp_2 > min_sp & wide$sp_3 > min_sp
  dropped <- sum(!complete)
  wide <- wide[complete, , drop = FALSE]
  if (!nrow(wide)) stop("jb_sp_signals: no fixture has three usable SP values")
  sv <- jb_devig_triplet(wide$sp_1, wide$sp_2, wide$sp_3)
  out <- tibble::tibble(issue = wide$issue, slot = wide$slot,
                        provider_id = wide$provider_id,
                        s_1 = sv[, 1], s_2 = sv[, 2], s_3 = sv[, 3])
  attr(out, "dropped_fixtures") <- dropped
  attr(out, "dropped_rows") <- dropped_rows
  out
}

# Long cell frame (fixture x outcome) carrying every signal plus the label.
# `frame` columns: issue, slot, provider_id, fixture, outcome, p, q, realized.
jb_probability_signals <- function(frame, sp_signals) {
  need <- c("issue", "slot", "provider_id", "fixture", "outcome", "p", "q", "realized")
  if (!all(need %in% names(frame))) stop("jb_probability_signals: frame must include ",
                                         paste(need, collapse = ", "))
  if (!nrow(frame)) stop("jb_probability_signals: empty frame")
  if (any(!frame$outcome %in% 1:3)) stop("jb_probability_signals: outcome outside 1..3")
  if (anyNA(frame$p) || anyNA(frame$q)) stop("jb_probability_signals: NA probability")
  if (any(frame$p <= 0) || any(frame$q <= 0)) {
    stop("jb_probability_signals: non-positive probability cannot be logit-transformed")
  }
  if (anyDuplicated(frame[c("fixture", "outcome")])) {
    stop("jb_probability_signals: duplicated fixture/outcome cell")
  }
  # Every fixture must contribute exactly three cells summing to one.
  chk <- frame |> dplyr::group_by(.data$fixture) |>
    dplyr::summarise(n = dplyr::n(), sp = sum(.data$p), sq = sum(.data$q),
                     sr = sum(.data$realized), .groups = "drop")
  if (any(chk$n != 3L)) stop("jb_probability_signals: every fixture needs three outcomes")
  if (any(abs(chk$sp - 1) > 1e-6) || any(abs(chk$sq - 1) > 1e-6)) {
    stop("jb_probability_signals: p and q must each sum to one per fixture")
  }
  if (any(chk$sr != 1L)) stop("jb_probability_signals: exactly one realized outcome per fixture")
  sv <- sp_signals |>
    tidyr::pivot_longer(c("s_1", "s_2", "s_3"), names_to = "outcome",
                        names_prefix = "s_", values_to = "s") |>
    dplyr::mutate(outcome = as.integer(.data$outcome))
  out <- dplyr::inner_join(frame, sv, by = c("issue", "slot", "provider_id", "outcome"))
  if (nrow(out) != nrow(frame)) {
    stop("jb_probability_signals: SP join dropped ", nrow(frame) - nrow(out),
         " of ", nrow(frame), " cells")
  }
  out |> dplyr::arrange(.data$fixture, .data$outcome)
}

# Multiclass log-loss, Brier and argmax accuracy per signal, over fixtures.
# Lower log-loss/Brier is better; accuracy is the share of fixtures whose
# realised outcome is the signal's argmax (ties are not counted as hits).
jb_multiclass_scores <- function(signals, prob_cols = c("p", "q", "s")) {
  if (!all(c("fixture", "outcome", "realized") %in% names(signals))) {
    stop("jb_multiclass_scores: signals must include fixture, outcome, realized")
  }
  if (!all(prob_cols %in% names(signals))) stop("jb_multiclass_scores: unknown prob column")
  if (!nrow(signals)) stop("jb_multiclass_scores: no cells")
  purrr::map_dfr(prob_cols, function(col) {
    d <- signals[, c("fixture", "outcome", "realized", col)]
    names(d)[4] <- "prob"
    if (any(d$prob <= 0)) stop("jb_multiclass_scores: non-positive probability in ", col)
    per <- d |> dplyr::group_by(.data$fixture) |>
      dplyr::summarise(
        log_loss = -log(.data$prob[.data$realized == 1L]),
        brier = sum((.data$prob - .data$realized)^2),
        top = which.max(.data$prob), realised = which(.data$realized == 1L),
        n_top = sum(.data$prob == max(.data$prob)),
        .groups = "drop")
    # A tied argmax is a degenerate forecast, not a table defect. It is counted
    # and scored as a miss, never resolved by an arbitrary tie-break.
    tibble::tibble(signal = col, fixtures = nrow(per),
                   log_loss = mean(per$log_loss), brier = mean(per$brier),
                   accuracy = mean(per$top == per$realised & per$n_top == 1L),
                   tied_argmax = mean(per$n_top != 1L))
  })
}

# Binned calibration for one signal: mean forecast vs realised frequency, with a
# binomial z for the gap. Cells (not fixtures) are the unit, so the interval is
# descriptive; fixtures within an issue are not independent.
jb_calibration_table <- function(signals, prob_col,
                                 breaks = c(0, .01, .02, .05, .10, .20, .40, .70, 1)) {
  if (!all(c("realized", prob_col) %in% names(signals))) {
    stop("jb_calibration_table: signals must include realized and ", prob_col)
  }
  if (any(signals[[prob_col]] <= 0)) stop("jb_calibration_table: non-positive probability")
  d <- signals
  d$.bin <- cut(d[[prob_col]], breaks = breaks, include.lowest = TRUE, right = FALSE)
  d |> dplyr::group_by(.data$.bin) |>
    dplyr::summarise(cells = dplyr::n(), forecast = mean(.data[[prob_col]]),
                     realised = mean(.data$realized), .groups = "drop") |>
    dplyr::mutate(gap = .data$realised - .data$forecast,
                  se = sqrt(.data$forecast * (1 - .data$forecast) / .data$cells),
                  z = .data$gap / .data$se) |>
    dplyr::rename(bin = ".bin")
}

# Centered log-ratio divergence of `source` against `anchor` for the row's own
# outcome component. Mirrors divergence_profile.divergence._clr_difference:
#   clr(x)_i = log(x_i) - mean_j log(x_j)
#   divergence = clr(source)[o] - clr(anchor)[o]
# Degenerate components below `eps` make the cell NA; values are never clipped.
jb_clr_divergence <- function(source, anchor, outcome_index, eps = 1e-9) {
  if (any(source <= eps) || any(anchor <= eps)) return(NA_real_)
  diff <- log(source) - log(anchor)
  diff[outcome_index] - mean(diff)
}

# Add p-vs-s and q-vs-s divergence columns plus the 2nd/3rd gap of each signal.
jb_add_divergence <- function(signals, eps = 1e-9) {
  if (!all(c("fixture", "outcome", "p", "q", "s") %in% names(signals))) {
    stop("jb_add_divergence: signals must include fixture, outcome, p, q, s")
  }
  rows <- split(signals, signals$fixture)
  out <- purrr::map_dfr(rows, function(d) {
    d <- d[order(d$outcome), , drop = FALSE]
    o <- d$outcome[d$realized == 1L][1]
    if (is.na(o)) stop("jb_add_divergence: fixture without a realised outcome")
    d$div_p_s <- jb_clr_divergence(d$p, d$s, o, eps)
    d$div_q_s <- jb_clr_divergence(d$q, d$s, o, eps)
    d$div_p_q <- jb_clr_divergence(d$p, d$q, o, eps)
    # Gap between the 2nd and 3rd largest component: a concentration/ambiguity
    # measure, scale-free within a fixture.
    gap23 <- function(v) sort(v, decreasing = TRUE)[2] - sort(v, decreasing = TRUE)[3]
    d$gap23_p <- gap23(d$p); d$gap23_q <- gap23(d$q); d$gap23_s <- gap23(d$s)
    d
  })
  out |> dplyr::arrange(.data$fixture, .data$outcome)
}

# McFadden conditional logit over the same choice sets, used only to ask whether
# one signal adds information beyond the others. `strata` is the fixture, so the
# intercept-free within-fixture comparison is what is estimated.
jb_conditional_logit <- function(signals, prob_cols = c("p", "q", "s")) {
  if (!requireNamespace("survival", quietly = TRUE)) {
    stop("jb_conditional_logit: the survival package is required")
  }
  if (!all(c("fixture", "outcome", "realized") %in% names(signals))) {
    stop("jb_conditional_logit: signals must include fixture, outcome, realized")
  }
  d <- signals
  for (col in prob_cols) {
    if (!col %in% names(d)) stop("jb_conditional_logit: unknown prob column ", col)
    if (any(d[[col]] <= 0) || any(d[[col]] >= 1)) {
      stop("jb_conditional_logit: ", col, " must be strictly inside (0, 1)")
    }
    d[[paste0("logit_", col)]] <- stats::qlogis(d[[col]])
  }
  d$.strata <- factor(d$fixture)
  # survival::clogit() needs two names that it does not import itself: an
  # unqualified strata() inside the formula, and a bare coxph() that it
  # evaluates in its caller's frame. Both resolve only when the survival
  # package happens to be attached, so an unattached session fails. Supplying
  # the two bindings locally keeps clogit's own conditional-likelihood
  # implementation (including its censored Surv() response and exact tie
  # handling) while removing the dependency on session state.
  fit_env <- new.env(parent = asNamespace("survival"))
  fit_env$strata <- survival::strata
  form <- stats::as.formula(
    sprintf("realized ~ %s + strata(.strata)",
            paste0("logit_", prob_cols, collapse = " + ")),
    env = fit_env)
  fit <- local({
    coxph <- survival::coxph
    survival::clogit(form, data = d)
  })
  co <- summary(fit)$coefficients
  tibble::tibble(term = rownames(co), estimate = co[, "coef"],
                 se = co[, "se(coef)"], z = co[, "z"], p = co[, "Pr(>|z|)"],
                 n_cells = nrow(d), n_fixtures = nlevels(d$.strata))
}
