# Bounded post-hoc description of sealed FM17 research. No fitting or decisions.
# CLI: Rscript r/fm17_event_type_diagnosis.R ROOT OUTPUT CLASSIFICATION_CSV
# Inputs: immutable forecast/evaluation receipts and explicit event-name mapping.
# Outputs: typed tidy CSV tables + SHA256 receipt; writes only OUTPUT on NVMe.
args <- commandArgs(TRUE)
stopifnot(length(args) == 3L)
root <- normalizePath(args[1], mustWork = TRUE)
out <- args[2]
classification_path <- normalizePath(args[3], mustWork = TRUE)
suppressPackageStartupMessages(library(tidyverse))
runtime <- jsonlite::fromJSON(file.path(root, "config/fm17_opponent_lambda_runtime.json"))
library(beidan, lib.loc = file.path(root, runtime$package_library_input))
study_root <- file.path(root, "results/fm17-opponent-lambda-20261013")
evaluation <- jsonlite::fromJSON(file.path(study_root, "evaluation.json"))
manifest <- jsonlite::fromJSON(file.path(study_root, "manifest.json"))
publication <- jsonlite::fromJSON(file.path(study_root, "publication.json"))
stopifnot(publication$dataset == "fm17_opponent_research", publication$version == "20261013-v2",
  publication$binding_sha256 == "1370961d740a109c74e22c456c91213804335b9d6d0f864a5ca3852dd2f3cee2")
input_paths <- c(
  scores = file.path(study_root, "scores.csv"),
  labels = file.path(study_root, "labels.csv"),
  roster = file.path(root, "results/beidan-full-issues-26092-26102-20261007/full-issue-fixtures.csv"),
  stage = file.path(root, "results/fm16-three-issues-20261012/stage.rds"),
  parent = file.path(root, "results/fm17-three-issues-20261013/forecasts.rds"),
  candidate = file.path(study_root, "forecasts.rds"),
  classification = classification_path
)
input_hashes <- map_chr(input_paths, ~digest::digest(file = .x, algo = "sha256"))
scope <- jsonlite::fromJSON(file.path(root, "results/beidan-full-issues-26092-26102-20261007/acceptance.json"))
parent_manifest <- jsonlite::fromJSON(file.path(root, "results/fm17-three-issues-20261013/manifest.json"))
stopifnot(input_hashes[["scores"]] == evaluation$outputs$scores,
  input_hashes[["labels"]] == evaluation$outputs$labels,
  input_hashes[["roster"]] == scope$fixtures_csv_sha256,
  input_hashes[["stage"]] == evaluation$source_hashes$parent_stage,
  input_hashes[["parent"]] == parent_manifest$forecast_sha256,
  input_hashes[["candidate"]] == manifest$forecast_sha256)
mapping <- read_csv(classification_path, col_types = cols(.default = col_character()))
stopifnot(nrow(problems(mapping)) == 0L, !anyDuplicated(mapping$league),
  !anyNA(mapping), all(mapping$event_type %in% c("league", "cup", "national", "youth")))
roster <- read_csv(input_paths[["roster"]], col_types = cols(.default = col_character())) |>
  filter(issue %in% c("26098", "26101", "26102")) |>
  transmute(fixture_id = paste0(issue, ":", slot), issue_id = issue, league, home, away,
    handicap = as.double(handicap), source_sha256, collected_at,
    age_team_flag = str_detect(paste(home, away), regex("U[ -]?(19|20|21|23)|青年|亚运男足", ignore_case = TRUE))) |>
  left_join(mapping, by = "league", relationship = "many-to-one")
stopifnot(nrow(roster) == 347L, !anyDuplicated(roster$fixture_id), !anyNA(roster$event_type),
  all(is.finite(roster$handicap)), all(roster$handicap == trunc(roster$handicap)))
audit <- read_dataset(publication$dataset, "audit", version = publication$version)
lambdas <- read_dataset(publication$dataset, "lambdas", version = publication$version)
support <- read_dataset(publication$dataset, "support", version = publication$version)
observations <- read_dataset(publication$dataset, "observations", version = publication$version)
margins <- read_dataset(publication$dataset, "margins", version = publication$version)
parent <- readRDS(input_paths[["parent"]])
candidate <- readRDS(input_paths[["candidate"]])
stopifnot(setequal(audit$fixture_id[audit$state == "ESTIMATED"], names(candidate$entries)),
  !anyDuplicated(lambdas$fixture_id), !anyDuplicated(support[c("fixture_id", "team_id", "venue")]))
stage <- readRDS(input_paths[["stage"]])
labels <- read_csv(input_paths[["labels"]], col_types = cols(.default = col_character()))
scores <- read_csv(input_paths[["scores"]], col_types = cols(
  .default = col_character(), actual_rank = col_integer(), actual_probability = col_double(),
  brier = col_double(), logloss = col_double(), top1 = col_logical(), top2 = col_logical(), top3 = col_logical())) |>
  filter(cohort == "FULL_FROZEN_ROUTING_OVERLAY", issue_id == "ALL",
    comparison %in% c("same_cutoff", "near_sale"),
    model %in% c("FM-1.7.0", "FM17_OVERLAY_OPPONENT_NATIVE", "FM17_OVERLAY_SAME_SUPPORT_RAW", "BEIDAN_T24", "BEIDAN_LATER")) |>
  select(-issue_id) |>
  left_join(roster, by = "fixture_id", relationship = "many-to-one")
stopifnot(!anyDuplicated(scores[c("comparison", "model", "fixture_id")]),
  !anyNA(scores$event_type), !anyNA(scores$top1), all(is.finite(scores$brier)),
  all(scores$actual_probability > 0 & scores$actual_probability <= 1),
  n_distinct(scores$fixture_id[scores$comparison == "near_sale"]) == 345L)
metrics <- bind_rows(scores, scores |> mutate(issue_id = "ALL")) |>
  group_by(issue_id, comparison, event_type, model) |>
  summarise(n = n(), hits1 = sum(top1), hits2 = sum(top2), top1 = mean(top1),
    top2 = mean(top2), brier = mean(brier), logloss = mean(logloss), .groups = "drop")
# Freeze identities and source routing unchanged; coverage denominators include exclusions.
coverage <- roster |>
  left_join(parent$audit |> select(fixture_id, selected_source, cutoff_utc),
    by = "fixture_id", relationship = "one-to-one") |>
  left_join(audit |> select(fixture_id, state, reason), by = "fixture_id", relationship = "one-to-one") |>
  mutate(settled_scored = fixture_id %in% labels$fixture_id,
    candidate_estimated = !is.na(state) & state == "ESTIMATED")
coverage_summary <- bind_rows(coverage, coverage |> mutate(issue_id = "ALL")) |>
  group_by(issue_id, event_type) |>
  summarise(roster_n = n(), scored_n = sum(settled_scored),
    native_n = sum(selected_source == "native", na.rm = TRUE),
    market_n = sum(selected_source == "market", na.rm = TRUE),
    estimated_n = sum(candidate_estimated),
    unestimated_native_n = sum(state == "UNESTIMATED", na.rm = TRUE),
    no_forecast_n = sum(is.na(selected_source)), .groups = "drop")
paired <- scores |> filter(comparison == "near_sale") |>
  select(fixture_id, issue_id, event_type, model, top1, top2, actual_probability, brier, logloss) |>
  pivot_wider(names_from = model, values_from = c(top1, top2, actual_probability, brier, logloss)) |>
  mutate(opponent_brier_delta = brier_FM17_OVERLAY_OPPONENT_NATIVE - `brier_FM-1.7.0`,
    raw_brier_delta = brier_FM17_OVERLAY_SAME_SUPPORT_RAW - `brier_FM-1.7.0`,
    opponent_logloss_delta = logloss_FM17_OVERLAY_OPPONENT_NATIVE - `logloss_FM-1.7.0`,
    raw_logloss_delta = logloss_FM17_OVERLAY_SAME_SUPPORT_RAW - `logloss_FM-1.7.0`,
    opponent_lost_top1 = `top1_FM-1.7.0` & !top1_FM17_OVERLAY_OPPONENT_NATIVE,
    opponent_saved_top1 = !`top1_FM-1.7.0` & top1_FM17_OVERLAY_OPPONENT_NATIVE)
effects <- bind_rows(paired, paired |> mutate(issue_id = "ALL")) |>
  group_by(issue_id, event_type) |>
  summarise(n = n(), changed_n = sum(abs(opponent_brier_delta) > 1e-12),
    opponent_brier_delta = mean(opponent_brier_delta), raw_brier_delta = mean(raw_brier_delta),
    opponent_lost_top1 = sum(opponent_lost_top1), opponent_saved_top1 = sum(opponent_saved_top1),
    .groups = "drop")
# Inventory ALL cup fixtures, and ALL changed native fixtures in 26102, not only losers.
case_ids <- coverage$fixture_id[coverage$event_type == "cup" |
  (coverage$issue_id == "26102" & coverage$candidate_estimated)]
cases <- coverage |> filter(fixture_id %in% case_ids) |>
  left_join(labels, by = "fixture_id", relationship = "one-to-one") |>
  left_join(paired |> select(-issue_id, -event_type), by = "fixture_id", relationship = "one-to-one") |>
  left_join(lambdas |> select(fixture_id, old_lambda_home, old_lambda_away,
    raw_same_support_home, raw_same_support_away, lambda_home, lambda_away, fit_rows),
    by = "fixture_id", relationship = "one-to-one")
rates <- tibble(fixture_id = character(), role = character(), matches = integer(),
  recent_matches = integer(), long_for = double(), long_against = double(),
  recent_for = double(), recent_against = double(), goals_for = double(), goals_against = double(), ess = double())
stage_details <- tibble(fixture_id = character(), stage = character(), model = character(),
  outcome = character(), probability = double())
market_evidence <- tibble(fixture_id = character(), available_joint_market = logical(),
  market_lambda_home = double(), market_lambda_away = double(), euro_rows = integer(),
  asian_rows = integer(), total_rows = integer(), market_sufficient = logical(),
  market_consistent = logical())
native_parameters <- tibble(fixture_id = character(), original_lambda_home = double(),
  original_lambda_away = double(), home_id = character(), away_id = character())
for (id in case_ids) {
  native <- stage$native[[id]]
  if (is.null(native)) next
  native_parameters <- bind_rows(native_parameters, tibble(fixture_id = id,
    original_lambda_home = native$native$parameters$lambda_home,
    original_lambda_away = native$native$parameters$lambda_away,
    home_id = as.character(native$fixture$home_id), away_id = as.character(native$fixture$away_id)))
  rates <- bind_rows(rates, native$native$rates |> mutate(fixture_id = id, .before = 1))
  result <- parent$entries[[id]]$results[["FM-1.7.0"]]
  for (phase in c("base", "final")) {
    g <- result[[phase]]$grid
    projection <- g |> mutate(outcome = case_when(
      home_goals - away_goals + native$fixture$handicap > 0 ~ "W",
      home_goals - away_goals + native$fixture$handicap == 0 ~ "D", TRUE ~ "L")) |>
      group_by(outcome) |> summarise(probability = sum(probability), .groups = "drop") |>
      mutate(fixture_id = id, stage = phase, model = "FM-1.7.0", .before = 1)
    stage_details <- bind_rows(stage_details, projection)
  }
  selection <- parent$entries[[id]]$parent_selection
  evidence <- parent$entries[[id]]$evidence_rows
  evidence_ids <- map_chr(evidence, "evidence_id")
  mp <- native$blinded$market_parameters
  if (selection$selected_source == "market") {
    # DC preserves the Poisson marginal means; recover selected market means
    # from its sealed pre-tail grid, rather than the older capture's empty fields.
    bg <- result$base$grid
    mp <- list(lambda_home = sum(bg$home_goals * bg$probability),
      lambda_away = sum(bg$away_goals * bg$probability))
  }
  market_evidence <- bind_rows(market_evidence, tibble(fixture_id = id,
    available_joint_market = !is.null(mp),
    market_lambda_home = if (is.null(mp)) NA_real_ else mp$lambda_home,
    market_lambda_away = if (is.null(mp)) NA_real_ else mp$lambda_away,
    euro_rows = as.integer(sum(str_detect(evidence_ids, "^euro-"))),
    asian_rows = as.integer(sum(str_detect(evidence_ids, "^asian-"))),
    total_rows = as.integer(sum(str_detect(evidence_ids, "^totals-"))),
    market_sufficient = selection$review$market_sufficient,
    market_consistent = selection$review$market_consistent))
}
for (model_name in c("OPPONENT_NATIVE", "SAME_SUPPORT_RAW")) {
  for (phase in c("base", "final")) {
    g <- margins |> filter(fixture_id %in% case_ids, model == model_name, stage == phase) |>
      left_join(roster |> select(fixture_id, handicap), by = "fixture_id", relationship = "many-to-one") |>
      mutate(outcome = case_when(margin + handicap > 0 ~ "W", margin + handicap == 0 ~ "D", TRUE ~ "L")) |>
      group_by(fixture_id, outcome) |> summarise(probability = sum(probability), .groups = "drop") |>
      mutate(stage = phase, model = model_name)
    stage_details <- bind_rows(stage_details, g)
  }
}
stage_check <- stage_details |> group_by(fixture_id, stage, model) |> summarise(mass = sum(probability), .groups = "drop")
stopifnot(all(abs(stage_check$mass - 1) < 1e-8))
frozen_probabilities <- bind_rows(
  parent$probabilities |> filter(model == "FM-1.7.0"), candidate$probabilities) |>
  select(fixture_id, model, outcome, frozen_probability = probability)
projection_check <- stage_details |> filter(stage == "final") |>
  left_join(frozen_probabilities, by = c("fixture_id", "model", "outcome"), relationship = "one-to-one")
stopifnot(!anyNA(projection_check$frozen_probability),
  all(abs(projection_check$probability - projection_check$frozen_probability) < 1e-10))
case_support <- support |> filter(fixture_id %in% case_ids)
case_observations <- observations |> filter(fixture_id %in% case_ids)
cases <- cases |> left_join(native_parameters, by = "fixture_id", relationship = "one-to-one")
support_summary <- case_support |>
  left_join(native_parameters |> select(fixture_id, home_id, away_id),
    by = "fixture_id", relationship = "many-to-one") |>
  mutate(target_team = team_id == home_id | team_id == away_id) |>
  group_by(fixture_id, target_team) |>
  summarise(groups = n(), recent_active_groups = sum(recent_active),
    minimum_matches = min(matches), median_matches = median(matches),
    minimum_ess = min(ess), .groups = "drop")
stage_effects <- stage_details |>
  inner_join(labels |> select(fixture_id, actual_outcome), by = "fixture_id", relationship = "many-to-one") |>
  mutate(squared_error = (probability - as.double(outcome == actual_outcome))^2) |>
  group_by(fixture_id, stage, model) |>
  summarise(brier = sum(squared_error),
    actual_probability = sum(probability[outcome == actual_outcome]), .groups = "drop") |>
  mutate(logloss = -log(actual_probability)) |>
  pivot_wider(names_from = stage, values_from = c(brier, logloss, actual_probability)) |>
  mutate(tail_brier_delta = brier_final - brier_base,
    tail_logloss_delta = logloss_final - logloss_base)
# Outcomes serve descriptive scores ONLY; no estimates, thresholds or source routes are changed.
tables <- list(metrics = metrics, coverage = coverage, coverage_summary = coverage_summary,
  effects = effects, cases = cases, original_rates = rates, stage_probabilities = stage_details,
  market_evidence = market_evidence, support = case_support, observations = case_observations)
tables$support_summary <- support_summary
tables$stage_effects <- stage_effects
dir.create(out, recursive = TRUE, showWarnings = FALSE)
for (name in names(tables)) write_csv(tables[[name]], file.path(out, paste0(name, ".csv")))
receipt <- list(mode = "POSTHOC_DESCRIPTIVE_NO_MODEL_UPDATE", issues = c("26098", "26101", "26102"),
  classification = "Explicit event-name map; youth precedence; mixed senior/U21 cup flagged separately",
  input_paths = as.list(input_paths), input_hashes = as.list(input_hashes), dataset = publication$dataset,
  dataset_version = publication$version,
  implementation_sha256 = digest::digest(file = file.path(root, "r/fm17_event_type_diagnosis.R"), algo = "sha256"),
  output_hashes = as.list(map_chr(names(tables), ~digest::digest(file = file.path(out, paste0(.x, ".csv")), algo = "sha256")) |> set_names(names(tables))),
  generated_at = format(Sys.time(), tz = "UTC", usetz = TRUE),
  transitive_learning_inventory = "No fit/tune/selection/ranking/decision function called; reads frozen scores, probabilities and receipts only. Existing native history proxies retain diagnostic-only status.",
  cutoff_binding = "Original per-fixture cutoff_utc retained in coverage/cases; no new learned artifacts or cross-cutoff cache.")
jsonlite::write_json(receipt, file.path(out, "receipt.json"), pretty = TRUE, auto_unbox = TRUE)
print(coverage_summary |> filter(issue_id == "ALL"))
print(metrics |> filter(issue_id == "ALL", comparison == "near_sale"))
