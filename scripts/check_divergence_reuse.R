args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args)) args[[1]] else "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/worst-regroup-v3"
out_dir <- if (length(args) > 1) args[[2]] else "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/divergence-reuse-v1"
source("r/n7_joint_sleeves.R"); source("r/n7_capital_portfolio.R"); source("r/divergence_reuse_allocate.R")
source("r/nowscore_query.R")
settlement_db <- "/run/media/drwho1985/Sandisk/data/beijing-lot/settlement/releases/20260907_history_five_play_v2/nowscore_history_replay.sqlite"
lf <- read.csv("/run/media/drwho1985/Sandisk/data/beijing-lot/audits/half-handicap-line-v1/features.csv", stringsAsFactors = FALSE)
lf <- lf[lf$model == "HALF_CONDITIONAL", , drop = FALSE]
paths <- list.files(file.path(root, "contexts"), pattern = "\\.rds$", full.names = TRUE)
run_one <- function(path) {
  x <- readRDS(path); p <- x$pools$OLD; s <- x$plans[[1]]$settings
  ev <- do.call(rbind, lapply(seq_along(p$fixtures), function(i) {
    f <- p$fixtures[[i]]; h <- lf[lf$issue == f$issue & lf$slot == f$slot & lf$provider_id == f$provider_id, , drop = FALSE]
    data.frame(issue = f$issue, slot = f$slot, provider_id = f$provider_id,
      degree = if (nrow(h)) abs(h$delta[[1]]) else 0)
  }))
  feat <- divergence_reuse_features(p, ev)
  raw <- query_nowscore_settlement(settlement_db, p$issue, play = "spf")$settlement
  fixture_labels <- do.call(rbind, lapply(p$fixtures, function(f) {
    z <- raw[raw$issue == f$issue & raw$slot == f$slot, , drop = FALSE]
    score <- if (nrow(z)) sub("^([0-9]+-[0-9]+).*$", "\\1", z$score[[1]]) else NA_character_
    ab <- if (!is.na(score) && grepl("^[0-9]+-[0-9]+$", score)) as.integer(strsplit(score, "-", fixed = TRUE)[[1]]) else c(NA_integer_, NA_integer_)
    adj <- if (all(is.finite(ab))) ab[[1]] - ab[[2]] + f$handicap else NA_real_
    direction <- if (is.na(adj)) NA_character_ else if (adj > 0) "W" else if (adj == 0) "D" else "L"
    option <- c(W = "胜", D = "平", L = "负")[[direction]]
    sp <- if (!is.na(option)) z$sp[match(option, z$option)] else NA_real_
    if (is.na(direction) || length(sp) != 1 || is.na(sp)) stop("missing or duplicate frozen settlement label")
    data.frame(issue = f$issue, slot = f$slot, provider_id = f$provider_id,
      handicap = f$handicap, actual_direction = direction, spf_sp = sp)
  }))
  worlds <- n7_joint_worlds(p, p$cutoffs, s$seed, 32L)
  scenarios <- n7_joint_returns(p, worlds, p$cutoffs)
  do.call(rbind, lapply(c("D2", "D4", "D2_EV", "D4_EV"), function(nm) {
    wide <- grepl("D4", nm); ev_gate <- if (grepl("EV", nm)) 1 else 0
    z <- divergence_reuse_allocate(p, scenarios, feat, p$cutoffs, 1024, 2,
      if (wide) 4 else 3, if (wide) 4 else 2, 1, ev_gate)
    actual_state <- sum((match(fixture_labels$actual_direction, c("W", "D", "L")) - 1L) * 3^(6:0)) + 1L
    won <- vapply(p$options[z$selected], function(o) actual_state %in% o$state_ids, logical(1))
    gross <- sum(ifelse(won, 2 * .65 * prod(fixture_labels$spf_sp), 0))
    data.frame(issue = p$issue, variant = nm, selected = length(z$selected),
      stake = 1024 - z$cash, model_hit = z$metrics$any_hit[[1]],
      model_gross = sum(scenarios$gross[, z$selected, drop = FALSE]),
      actual_hit = any(won), actual_gross = gross,
      actual_net = gross - (1024 - z$cash),
      max_reuse = max(z$usage), distinct_fixtures = sum(z$usage > 0),
      reuse_hhi = sum((z$usage / max(1, sum(z$usage)))^2),
      high = sum(feat$category == "HIGH"), medium = sum(feat$category == "MEDIUM"),
      low = sum(feat$category == "LOW"))
  }))
}
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
ans <- do.call(rbind, lapply(paths, run_one)); write.csv(ans, file.path(out_dir, "model_metrics.csv"), row.names = FALSE)
writeLines(capture.output(print(ans)), file.path(out_dir, "progress.txt"))
receipt <- list(scope = basename(paths), source_context = normalizePath(root),
  settlement_db = normalizePath(settlement_db), worlds = 32L, budget_cny = 1024,
  payout_factor = 0.65, variants = c("D2", "D4", "D2_EV", "D4_EV"),
  label_rule = "score plus frozen handicap; winner option SP from Nowscore replay")
jsonlite::write_json(receipt, file.path(out_dir, "receipt.json"), auto_unbox = TRUE, pretty = TRUE)
