args <- commandArgs(trailingOnly = TRUE)
root <- if (length(args)) args[[1]] else "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/worst-regroup-v3"
out_dir <- if (length(args) > 1) args[[2]] else "/run/media/drwho1985/Sandisk/data/beijing-lot/audits/divergence-reuse-v1"
source("r/n7_joint_sleeves.R"); source("r/n7_capital_portfolio.R"); source("r/divergence_reuse_allocate.R")
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
  worlds <- n7_joint_worlds(p, p$cutoffs, s$seed, 32L)
  scenarios <- n7_joint_returns(p, worlds, p$cutoffs)
  do.call(rbind, lapply(c("D2", "D4"), function(nm) {
    z <- divergence_reuse_allocate(p, scenarios, feat, p$cutoffs, 1024, 2,
      if (nm == "D4") 4 else 3, 2, 1, 0)
    data.frame(issue = p$issue, variant = nm, selected = length(z$selected),
      stake = 1024 - z$cash, model_hit = z$metrics$any_hit[[1]],
      model_gross = sum(scenarios$gross[, z$selected, drop = FALSE]),
      high = sum(feat$category == "HIGH"), medium = sum(feat$category == "MEDIUM"),
      low = sum(feat$category == "LOW"))
  }))
}
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
ans <- do.call(rbind, lapply(paths, run_one)); write.csv(ans, file.path(out_dir, "model_metrics.csv"), row.names = FALSE)
writeLines(capture.output(print(ans)), file.path(out_dir, "progress.txt"))
