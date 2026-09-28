# Multi-issue walk-forward backtest of the DC edge rule.
#
# Reads per-issue fixture rosters plus both market histories, fits DC rates
# inside each issue, and settles the e-max decision rule against the actual
# direction. Every issue is an independent evaluation unit; pooled ROI gives
# both the weighted and the equal-weight-per-issue view so a single thick-tailed
# issue cannot masquerade as a general edge.
suppressMessages({library(dplyr); library(tibble); library(jsonlite)})
source('r/dixon_coles_grid.R'); source('r/joint_basket_dc_fit.R')

# Last row of a history payload where every expected column is posted.
#
# Accepts either a character matrix (rows x columns) or the list-of-row-lists
# shape that jsonlite returns for an array of arrays with simplifyVector=FALSE.
# Both spell the same contract: `n_expected` price columns then one time column.
# Returns NULL when no row ever posts a complete vector, so a caller can drop
# the fixture rather than settle on a partial market.
jc_closing_row <- function(m, n_expected) {
  if (is.null(m) || !length(m)) return(NULL)
  rows <- if (is.matrix(m)) {
    lapply(seq_len(nrow(m)), function(i) as.list(m[i, ]))
  } else if (is.list(m)) {
    m
  } else {
    return(NULL)
  }
  for (row in rows) {
    if (length(row) < n_expected + 1L) next
    v <- suppressWarnings(as.numeric(unlist(row[seq_len(n_expected)], use.names = FALSE)))
    if (length(v) == n_expected && all(!is.na(v)) && all(v > 1)) {
      return(list(v = v, ts = as.character(unlist(row[[n_expected + 1L]], use.names = FALSE))))
    }
  }
  NULL
}

# Direction of the handicap outcome from a final score and the home handicap.
jc_direction <- function(score, handicap) {
  if (!is.character(score) || length(score) != 1L || is.na(score) || !grepl('-', score)) return(NA_character_)
  h <- suppressWarnings(as.integer(sub('-.*', '', score)))
  a <- suppressWarnings(as.integer(sub('.*-', '', score)))
  if (is.na(h) || is.na(a)) return(NA_character_)
  hcp <- suppressWarnings(as.numeric(handicap)); if (is.na(hcp)) hcp <- 0
  net <- h - a + hcp
  if (net > 0) 'W' else if (net == 0) 'D' else 'L'
}

# Build one issue's analysable fixture table. Returns an empty tibble when the
# issue has no usable fixture; never drops rows silently otherwise.
jc_issue_table <- function(issue, roster, histories, rho) {
  rows <- roster[[issue]]
  if (is.null(rows) || !nrow(rows)) return(jc_empty_table())
  out <- list()
  for (i in seq_len(nrow(rows))) {
    slot <- as.character(rows$slot[i])
    rec <- histories[[paste0(issue, '_', slot)]]
    if (is.null(rec)) next
    h <- jc_closing_row(rec$t5, 3L)
    t <- jc_closing_row(rec$t6, 8L)
    if (is.null(h) || is.null(t)) next
    p <- jc_devig(h$v)
    if (anyNA(p)) next
    et <- jc_expected_total(t$v)
    if (is.na(et)) next
    hcp <- suppressWarnings(as.numeric(rows$handicap[i])); if (is.na(hcp)) hcp <- 0
    fit <- tryCatch(jc_fit_rates(p, et, as.integer(hcp), rho), error = function(e) NULL)
    if (is.null(fit)) next
    q <- fit$fitted
    out[[length(out) + 1L]] <- tibble(
      issue = issue, slot = rows$slot[i], league = rows$league[i],
      home = rows$home[i], away = rows$away[i], hcp = hcp,
      score = rows$score[i], dirn = jc_direction(rows$score[i], rows$handicap[i]),
      pW = p[1], pD = p[2], pL = p[3],
      qW = q['W'], qD = q['D'], qL = q['L'],
      spW = h$v[1], spD = h$v[2], spL = h$v[3],
      exp_total = et, residual = fit$residual, sp_ts = h$ts)
  }
  d <- bind_rows(out)
  if (!nrow(d)) return(jc_empty_table())
  d |> filter(!is.na(dirn))
}

# Typed empty table for the analysable fixture contract.
jc_empty_table <- function() {
  tibble(issue = character(), slot = integer(), league = character(),
    home = character(), away = character(), hcp = numeric(), score = character(),
    dirn = character(), pW = numeric(), pD = numeric(), pL = numeric(),
    qW = numeric(), qD = numeric(), qL = numeric(),
    spW = numeric(), spD = numeric(), spL = numeric(),
    exp_total = numeric(), residual = numeric(), sp_ts = character())
}

# Apply the e-max decision rule and settle it. Adds the pick, its e, its SP and
# the realised return. Pure column arithmetic on an explicit table.
jc_settle_rule <- function(d) {
  if (!nrow(d)) return(d)
  d |> mutate(
    eW = qW * spW, eD = qD * spD, eL = qL * spL,
    pick = c('W', 'D', 'L')[max.col(cbind(eW, eD, eL), ties.method = 'first')],
    e_pick = pmax(eW, eD, eL),
    sp_pick = case_when(pick == 'W' ~ spW, pick == 'D' ~ spD, TRUE ~ spL),
    hit = pick == dirn,
    fav_sp = pmin(spW, spD, spL),
    fav_out = c('W', 'D', 'L')[max.col(cbind(-spW, -spD, -spL), ties.method = 'first')],
    fav_hit = fav_out == dirn,
    e_fav = pmax(pW, pD, pL),
    gross = sp_pick * hit, gross_fav = fav_sp * fav_hit)
}

# Per-issue ROI under both weightings. `equal` is the headline: it treats each
# issue as one observation so a single thick-tailed issue cannot carry the mean.
jc_roi_by_issue <- function(d) {
  if (!nrow(d)) {
    return(tibble(issue = character(), n = integer(), roi_dc = numeric(),
      roi_fav = numeric(), hits = integer(), e_dc = numeric()))
  }
  d |> group_by(issue) |> summarise(
    n = n(), hits = sum(hit),
    roi_dc = mean(gross) - 1, roi_fav = mean(gross_fav) - 1,
    e_dc = mean(e_pick), .groups = 'drop')
}

