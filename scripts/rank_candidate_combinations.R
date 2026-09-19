source("r/candidate_combo_rank.R")
root <- "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/worst-regroup-v3"
out_dir <- "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/candidate-combo-rank-v1"
paths <- list.files(file.path(root, "contexts"), pattern = "\\.rds$", full.names = TRUE)
rows <- lapply(paths, function(path) {
  x <- readRDS(path); p <- x$pools$OLD
  opts <- p$options
  candidates <- do.call(rbind, lapply(seq_along(opts), function(i) {
    o <- opts[[i]]
    data.frame(combo_id = paste0(x$original$issue, "-", i),
      hit_probability = o$coverage, expected_gross = o$expected_gross,
      stake_cny = o$stake, legal_mass = o$coverage)
  }))
  z <- rank_candidate_combinations(candidates, 1024, 2, .5, 0)
  z$issue <- x$original$issue
  z$baseline_rank <- match(z$combo_id, candidates$combo_id)
  z[, c("issue", "combo_id", "average_rank", "hit_rank", "ev_rank",
    "budget_hit_probability", "budget_expected_gross", "budget_expected_net",
    "budget_roi", "legal_mass", "pareto_frontier", "baseline_rank")]
})
ans <- do.call(rbind, rows)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
write.csv(ans, file.path(out_dir, "ranked_combinations.csv"), row.names = FALSE)
summary <- aggregate(cbind(budget_hit_probability, budget_expected_net, budget_roi,
  pareto_frontier) ~ issue, ans, function(x) c(max = max(x), mean = mean(x),
    n = length(x)))
write.csv(summary, file.path(out_dir, "summary.csv"), row.names = FALSE)
jsonlite::write_json(list(issues = unique(ans$issue), budget_cny = 1024,
  unit_cny = 2, ranking = "equal average normalized hit and expected-net ranks",
  source = root), file.path(out_dir, "receipt.json"), auto_unbox = TRUE, pretty = TRUE)
