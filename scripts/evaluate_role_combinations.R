source("r/role_combo_generator.R")
source("r/candidate_combo_rank.R")
root <- "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/worst-regroup-v3"
line <- read.csv("/run/media/drwho1985/Sandisk/data/beijing-lot/audits/half-handicap-line-v1/features.csv", stringsAsFactors = FALSE)
line <- line[line$model == "HALF_CONDITIONAL", , drop = FALSE]
out_dir <- "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/role-combo-eval-v1"
paths <- list.files(file.path(root, "contexts"), pattern = "\\.rds$", full.names = TRUE)

fixture_role <- function(p, line) {
  do.call(rbind, lapply(seq_along(p$fixtures), function(i) {
    f <- p$fixtures[[i]]; h <- line[line$issue == f$issue & line$slot == f$slot & line$provider_id == f$provider_id, , drop = FALSE]
    if (nrow(h) != 1) stop("missing line evidence")
    pr <- sort(as.numeric(c(f$p_W, f$p_D, f$p_L)), decreasing = TRUE)
    degree <- abs(h$delta[[1]]); gap <- pr[[2]] - pr[[3]]
    role <- if (degree >= .5) "主力" else if (gap >= .10) "主力" else if (is.finite(1 / min(c(f$q_W, f$q_D, f$q_L))) && gap < .10) "机会" else "排除"
    data.frame(fixture_id = as.character(i), issue = f$issue, slot = f$slot,
      provider_id = f$provider_id, role = role, degree = degree, gap23 = gap,
      p_W = f$p_W, p_D = f$p_D, p_L = f$p_L, q_W = f$q_W, q_D = f$q_D, q_L = f$q_L)
  }))
}

combo_metrics <- function(combo, roles, budget = 1024) {
  ix <- as.integer(strsplit(combo$fixtures, ",", fixed = TRUE)[[1]])
  choices <- lapply(ix, function(i) {
    f <- roles[roles$fixture_id == as.character(i), , drop = FALSE]
    if (nrow(f) != 1) stop("fixture role lookup failed")
    p <- as.numeric(c(f$p_W, f$p_D, f$p_L)); q <- as.numeric(c(f$q_W, f$q_D, f$q_L))
    orderp <- order(-p, seq_along(p)); allowed <- if (f$role == "机会") orderp else orderp[1:2]
    list(outcome = allowed - 1L, p = p[allowed], q = q[allowed])
  })
  grid <- expand.grid(lapply(choices, `[[`, "outcome"), KEEP.OUT.ATTRS = FALSE)
  prob <- apply(grid, 1, function(s) {
    prod(vapply(seq_along(s), function(j) {
      choices[[j]]$p[match(s[[j]], choices[[j]]$outcome)]
    }, numeric(1)))
  })
  payout <- apply(grid, 1, function(s) {
    2 * .65 / prod(vapply(seq_along(s), function(j) {
      choices[[j]]$q[match(s[[j]], choices[[j]]$outcome)]
    }, numeric(1)))
  })
  ord <- order(-prob, -payout); take <- head(ord, floor(budget / 2)); stake <- length(take) * 2
  data.frame(combo_id = combo$combo_id, hit_probability = sum(prob[take]),
    expected_gross = sum(prob[take] * payout[take]), stake_cny = stake,
    legal_mass = sum(prob), states = length(prob), stringsAsFactors = FALSE)
}

rows <- lapply(paths, function(path) {
  x <- readRDS(path); p <- x$pools$OLD; roles <- fixture_role(p, line)
  # Pilot cap: keep the highest Top2-mass main/opp fixtures before combinatorics.
  roles <- roles[order(roles$role != "主力", -(roles$p_W + roles$p_D), roles$fixture_id), , drop = FALSE]
  roles <- rbind(head(roles[roles$role == "主力", , drop = FALSE], 8),
    head(roles[roles$role == "机会", , drop = FALSE], 4))
  roles$fixture_id <- as.character(seq_len(nrow(roles)))
  combos <- generate_role_combinations(roles, max_candidates = 50, seed = 1)
  if (!nrow(combos)) return(NULL)
  metrics <- do.call(rbind, lapply(seq_len(nrow(combos)), function(i) combo_metrics(combos[i, ], roles)))
  z <- rank_role_combinations(combos, metrics, 1024, 2, .5, 0)
  z$issue <- p$issue; z$main_available <- sum(roles$role == "主力"); z$opportunity_available <- sum(roles$role == "机会")
  z[, c("issue", "combo_id", "main_count", "opportunity_count", "average_rank",
    "budget_hit_probability", "budget_expected_gross", "budget_expected_net",
    "budget_roi", "legal_mass", "states", "pareto_frontier",
    "main_available", "opportunity_available")]
})
ans <- do.call(rbind, rows); dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
write.csv(ans, file.path(out_dir, "ranked_role_combinations.csv"), row.names = FALSE)
write.csv(do.call(rbind, lapply(split(ans, ans$issue), function(z) z[which.min(z$average_rank), ])), file.path(out_dir, "selected_per_issue.csv"), row.names = FALSE)
jsonlite::write_json(list(scope = basename(paths), budget_cny = 1024, role_rule = "abs degree >= .5 OR gap23 >= .10 -> MAIN; small gap -> OPPORTUNITY", source = root), file.path(out_dir, "receipt.json"), auto_unbox = TRUE, pretty = TRUE)
