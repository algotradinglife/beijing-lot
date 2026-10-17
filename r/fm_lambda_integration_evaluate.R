# Rscript r/fm_lambda_integration_evaluate.R ROOT OUTPUT
# Fixed integrated-lambda descriptive scoring, only after complete independent replay.
args <- commandArgs(TRUE); stopifnot(length(args) == 2L)
root <- normalizePath(args[1], mustWork = TRUE); out <- args[2]
suppressPackageStartupMessages(library(tidyverse))
library(beidan, lib.loc = file.path(root, "results/fm17-diagnostic-iterations-20261013/library"))
manifest <- jsonlite::fromJSON(file.path(out, "manifest.json"))
replay <- jsonlite::fromJSON(file.path(out, "replay.json"))
path <- file.path(out, "forecasts.rds")
stopifnot(replay$status == "FULL_IDENTICAL_REPLAY", replay$forecasts == 346L,
  replay$sha256 == manifest$forecast_sha256,
  digest::digest(file = path, algo = "sha256") == manifest$forecast_sha256)
alpha <- readRDS(path)
# Frozen statistical fits can only be consumed with their recorded R dependencies.
for(entry in alpha$entries) if(!is.null(entry$fit)) {
  dependencies <- entry$fit$receipt$dependencies
  actual <- vapply(names(dependencies),function(package)as.character(utils::packageVersion(package)),character(1))
  stopifnot(identical(unname(actual),unname(unlist(dependencies))))
}
parent_root <- file.path(root, "results/fm17-three-issues-20261013")
eval <- jsonlite::fromJSON(file.path(parent_root, "evaluation.json"))
event <- jsonlite::fromJSON(file.path(root, "results/fm17-event-types-20261015/receipt.json"))
paths <- c(parent = file.path(parent_root, "forecasts.rds"), labels = file.path(parent_root, "labels.csv"),
  sp = file.path(root, eval$sp_path), coverage = file.path(root, "results/fm17-event-types-20261015/coverage.csv"))
hashes <- map_chr(paths, ~digest::digest(file = .x, algo = "sha256"))
stopifnot(hashes[["parent"]] == manifest$bindings$parent_forecast_sha256,
  hashes[["labels"]] == eval$labels_csv_sha256, hashes[["sp"]] == eval$sp_sha256,
  hashes[["coverage"]] == event$output_hashes$coverage)
parent <- readRDS(paths[["parent"]])
labels <- read_csv(paths[["labels"]], col_types = cols(.default = col_character()))
coverage <- read_csv(paths[["coverage"]], col_types = cols(.default = col_character())) |>
  select(fixture_id, issue_id, event_type, league, home, away)
old_alpha_path <- file.path(root,"results/fm18-three-issues-20261017/forecasts.rds")
stopifnot(digest::digest(file=old_alpha_path,algo="sha256")==manifest$bindings$old_alpha_sha256)
old_alpha <- readRDS(old_alpha_path)
roster <- old_alpha$audit |> select(fixture_id, handicap, cutoff_utc, selected_source, triggered) |>
  left_join(alpha$audit |> select(fixture_id,state,changed_native),by="fixture_id",relationship="one-to-one")
stopifnot(nrow(labels) == 345L, nrow(roster) == 346L, !anyDuplicated(labels$fixture_id),
  !anyDuplicated(coverage$fixture_id), !anyDuplicated(roster$fixture_id))
sp <- read_csv(paths[["sp"]], show_col_types = FALSE) |>
  inner_join(roster |> select(fixture_id, cutoff_utc), by = "fixture_id", relationship = "many-to-one")
stopifnot(!anyDuplicated(sp[c("fixture_id", "mode")]), all(sp$sp_w > 0 & sp$sp_d > 0 & sp$sp_l > 0),
  all(sp$quote_at < sp$selection_cutoff), all(sp$quote_at < sp$kickoff_utc),
  all(sp$selection_cutoff[sp$mode == "same_cutoff"] == sp$cutoff_utc[sp$mode == "same_cutoff"]))
bd <- sp |> transmute(fixture_id, comparison = mode, W = 1/sp_w, D = 1/sp_d, L = 1/sp_l) |>
  mutate(mass = W + D + L, across(c(W, D, L), ~.x/mass)) |> select(-mass) |>
  pivot_longer(c(W, D, L), names_to = "outcome", values_to = "probability") |>
  mutate(model = if_else(comparison == "same_cutoff", "BEIDAN_T24", "BEIDAN_LATER"))
forecasts <- bind_rows(alpha$probabilities, old_alpha$probabilities,
  parent$probabilities |> filter(model %in% c("FM-1.7.0", "FM17-source-before-tail")) |>
    select(fixture_id, model, outcome, probability))
metrics <- scores <- calibration <- list()
for (comparison in c("same_cutoff", "near_sale")) {
  ids <- Reduce(intersect, list(labels$fixture_id, forecasts$fixture_id, bd$fixture_id[bd$comparison == comparison]))
  grouping <- coverage |> filter(fixture_id %in% ids) |>
    left_join(roster |> select(fixture_id, handicap, selected_source, triggered,state,changed_native), by = "fixture_id", relationship = "one-to-one") |>
    mutate(draw_type = if_else(handicap == 0, "zero_handicap", "nonzero_handicap"))
  stopifnot(!anyNA(grouping))
  groups <- bind_rows(grouping |> mutate(dimension = "all", stratum = "ALL"),
    grouping |> mutate(dimension = "issue", stratum = issue_id),
    grouping |> mutate(dimension = "event_type", stratum = event_type),
    grouping |> mutate(dimension = "draw_type", stratum = draw_type),
    grouping |> mutate(dimension = "source", stratum = selected_source),
    grouping |> mutate(dimension = "trigger", stratum = as.character(triggered)),
    grouping |> mutate(dimension="changed_native",stratum=as.character(changed_native)),
    grouping |> mutate(dimension="fit_state",stratum=state))
  p <- bind_rows(forecasts |> filter(fixture_id %in% ids),
    bd |> filter(.data$comparison == .env$comparison, fixture_id %in% ids) |> select(-comparison))
  for (key in unique(paste(groups$dimension, groups$stratum, sep = ":"))) {
    g <- groups |> filter(paste(dimension, stratum, sep = ":") == key)
    d <- beidan:::DcAccuracyDiagnostic(p |> filter(fixture_id %in% g$fixture_id),
      labels |> filter(fixture_id %in% g$fixture_id) |> select(fixture_id, actual_outcome))
    index <- paste(comparison, key)
    metrics[[index]] <- d$summary |> mutate(comparison = comparison, dimension = g$dimension[1], stratum = g$stratum[1], .before = 1)
    calibration[[index]] <- p |> filter(fixture_id %in% g$fixture_id, outcome == "D") |>
      left_join(labels |> select(fixture_id, actual_outcome), by = "fixture_id", relationship = "many-to-one") |>
      group_by(model) |> summarise(n = n(), actual_draws = sum(actual_outcome == "D"),
        mean_draw_probability = mean(probability), actual_draw_rate = mean(actual_outcome == "D"),
        binary_draw_brier = mean((probability - as.double(actual_outcome == "D"))^2), .groups = "drop") |>
      mutate(comparison = comparison, dimension = g$dimension[1], stratum = g$stratum[1], .before = 1)
    if (key == "all:ALL") scores[[comparison]] <- d$scores |> mutate(comparison = comparison, .before = 1)
  }
}
metrics <- bind_rows(metrics); scores <- bind_rows(scores); calibration <- bind_rows(calibration)
changes <- list()
for(candidate in c("FM17+OPPONENT_NATIVE","FM17+SAME_SUPPORT_RAW","ALPHA+OPPONENT_NATIVE","ALPHA+SAME_SUPPORT_RAW")) {
  reference <- if(startsWith(candidate,"FM17")) "FM-1.7.0" else "FM-1.8.0-alpha.1"
  ref <- scores |> filter(comparison=="near_sale",model==reference) |>
    select(fixture_id,actual_outcome,old_top1=top1,old_top2=top2,old_brier=brier,old_logloss=logloss)
  changes[[candidate]] <- scores |> filter(comparison=="near_sale",model==candidate) |>
    inner_join(ref,by="fixture_id",relationship="one-to-one") |>
    left_join(coverage,by="fixture_id",relationship="one-to-one") |>
    left_join(roster,by="fixture_id",relationship="one-to-one") |>
    mutate(reference=reference,saved_top1=top1 & !old_top1,lost_top1=!top1 & old_top1,
      saved_top2=top2 & !old_top2,lost_top2=!top2 & old_top2,
      brier_delta=brier-old_brier,logloss_delta=logloss-old_logloss)
}
changes <- bind_rows(changes)
draw_selection <- scores |> filter(comparison == "near_sale") |>
  group_by(model) |> summarise(n = n(), draw_top1_count = sum(predicted_outcome == "D"),
    draw_top1_hits = sum(predicted_outcome == "D" & actual_outcome == "D"),
    missed_draws_top2 = sum(actual_outcome == "D" & !top2), .groups = "drop")
tables <- list(metrics = metrics, scores = scores, draw_calibration = calibration,
  changes = changes, draw_selection = draw_selection,
  exclusions = coverage |> filter(!fixture_id %in% labels$fixture_id))
for (name in names(tables)) write_csv(tables[[name]], file.path(out, paste0(name, ".csv")))
jsonlite::write_json(list(mode = "POSTHOC_FIXED_INTEGRATED_LAMBDA_COMPARISON", model_id = "FM17_ALPHA_SAME_COMPETITION_OPPONENT",
  candidate_sha256 = manifest$forecast_sha256, source_hashes = as.list(hashes),
  client_sha256 = digest::digest(file = file.path(root, "r/fm_lambda_integration_evaluate.R"), algo = "sha256"),
  output_hashes = as.list(set_names(map_chr(names(tables), ~digest::digest(file = file.path(out, paste0(.x, ".csv")), algo = "sha256")), names(tables))),
  native_lambda_experiments_included = TRUE,
  interpretation = "Frozen routing unchanged. New same-competition and opponent lambdas replace only estimable native-selected grids before each registered FM17/alpha transform. Market-selected and unestimated native rows explicitly retain parent. Raw same-support control separates competition sampling from normalization; known outcomes diagnostic only.",
  runtime = list(R = as.character(getRversion()), beidan = as.character(packageVersion("beidan")),
    dplyr = as.character(packageVersion("dplyr"))),
  generated_at = format(Sys.time(), tz = "UTC", usetz = TRUE)), file.path(out, "evaluation.json"), pretty = TRUE, auto_unbox = TRUE)
print(metrics |> filter(dimension == "all"), width = Inf)
print(draw_selection)
