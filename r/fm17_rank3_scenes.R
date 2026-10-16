# Rscript r/fm17_rank3_scenes.R ROOT OUTPUT
# Fixed, descriptive contrasts of sealed final FM17 outcomes; no new learning.
args <- commandArgs(TRUE)
stopifnot(length(args) == 2L)
root <- normalizePath(args[1], mustWork = TRUE)
out <- args[2]
suppressPackageStartupMessages(library(tidyverse))
input_root <- file.path(root, "results/fm17-top1-calibration-20261016")
receipt <- jsonlite::fromJSON(file.path(input_root, "receipt.json"))
sources <- c(fixtures = file.path(input_root, "fixtures.csv"),
  forecast = receipt$sources$forecast, labels = receipt$sources$labels,
  coverage = receipt$sources$coverage, sp = receipt$sources$sp)
hashes <- map_chr(sources, ~digest::digest(file = .x, algo = "sha256"))
stopifnot(hashes[["fixtures"]] == receipt$output_hashes$fixtures,
  all(hashes[c("forecast", "labels", "coverage", "sp")] == unlist(receipt$source_hashes[c("forecast", "labels", "coverage", "sp")])))
source <- read_csv(sources[["fixtures"]], col_types = cols(
  .default = col_character(), actual_rank = col_integer(), actual_probability = col_double(),
  brier = col_double(), logloss = col_double(), top1 = col_logical(), top2 = col_logical(),
  top3 = col_logical(), p1 = col_double(), p12 = col_double(), bin = col_integer()))
stopifnot(nrow(problems(source)) == 0L,
  !anyDuplicated(source[c("comparison", "model", "fixture_id")]))
frozen <- readRDS(sources[["forecast"]])
labels <- read_csv(sources[["labels"]], col_types = cols(.default = col_character()))
coverage <- read_csv(sources[["coverage"]], col_types = cols(.default = col_character())) |>
  select(fixture_id, league, home, away, handicap)
stopifnot(!anyDuplicated(labels$fixture_id), !anyDuplicated(coverage$fixture_id))
ranked <- frozen$probabilities |> filter(model == "FM-1.7.0", fixture_id %in% labels$fixture_id) |>
  arrange(fixture_id, desc(probability), match(outcome, c("W", "D", "L"))) |>
  group_by(fixture_id) |> mutate(position = row_number()) |> ungroup() |>
  select(fixture_id, position, outcome, probability) |>
  pivot_wider(names_from = position, values_from = c(outcome, probability))
facts <- source |> filter(comparison == "near_sale", model == "FM-1.7.0") |>
  select(-comparison, -model) |>
  left_join(coverage, by = "fixture_id", relationship = "one-to-one") |>
  left_join(labels |> select(fixture_id, score), by = "fixture_id", relationship = "one-to-one") |>
  left_join(ranked, by = "fixture_id", relationship = "one-to-one") |>
  mutate(handicap = as.double(handicap),
    home_goals = as.integer(str_extract(score, "^[0-9]+")),
    away_goals = as.integer(str_extract(score, "[0-9]+$")),
    margin = home_goals - away_goals,
    rank3_hit = actual_rank == 3L, p3 = probability_3, gap23 = probability_2 - probability_3,
    ranked_order = paste(outcome_1, outcome_2, outcome_3, sep = ">"),
    handicap_group = case_when(handicap == 0 ~ "zero", abs(handicap) == 1 ~ "abs1", TRUE ~ "abs2plus"),
    top1_band = cut(p1, c(1/3, .4, .5, .6, 1), right = FALSE, include.lowest = TRUE),
    p3_band = cut(p3, c(0, .1, .2, .25, .3, 1/3 + 1e-8), right = FALSE, include.lowest = TRUE),
    gap23_band = cut(gap23, c(0, .02, .05, .1, 1), right = FALSE, include.lowest = TRUE),
    goal_difference_case = case_when(
      handicap == 0 & margin == 0 ~ "zero_handicap_actual_draw",
      handicap == 0 & margin > 0 ~ "zero_handicap_home_win",
      handicap == 0 & margin < 0 ~ "zero_handicap_away_win",
      margin == 0 ~ "nonzero_handicap_actual_draw",
      sign(margin) == sign(handicap) ~ "receiving_side_actual_win",
      abs(margin) < abs(handicap) ~ "giving_side_win_below_handicap",
      abs(margin) == abs(handicap) ~ "giving_side_win_exact_handicap",
      TRUE ~ "giving_side_win_above_handicap"))
stopifnot(nrow(facts) == 345L, sum(facts$rank3_hit) == 95L,
  !anyNA(facts), all(abs(facts$p1 - facts$probability_1) < 1e-12),
  all(abs(facts$p12 + facts$p3 - 1) < 1e-8),
  all(if_else(facts$margin + facts$handicap > 0, "W",
    if_else(facts$margin + facts$handicap == 0, "D", "L")) == facts$actual_outcome))
pre_tail <- source |> filter(comparison == "near_sale", model == "FM17-source-before-tail") |>
  select(fixture_id, before_actual_rank = actual_rank, before_actual_probability = actual_probability,
    before_predicted_outcome = predicted_outcome)
facts <- facts |> left_join(pre_tail, by = "fixture_id", relationship = "one-to-one") |>
  mutate(tail_transition = paste0(before_actual_rank, "->", actual_rank),
    tail_probability_delta = actual_probability - before_actual_probability)
# Final frozen evidence inventory; absence is unknown, never a zero quote price.
evidence <- tibble(fixture_id = character(), euro_rows = integer(), asian_rows = integer(),
  total_rows = integer(), market_sufficient = logical(), market_consistent = logical(),
  base_expected_margin = double(), final_expected_margin = double(), tail_decision = character(),
  actual_margin_in_core = logical(), final_tied_rank = logical())
for (id in facts$fixture_id) {
  e <- frozen$entries[[id]]
  ids <- map_chr(e$evidence_rows, "evidence_id")
  result <- e$results[["FM-1.7.0"]]
  g <- result$base$grid
  fg <- result$final$grid
  evidence <- bind_rows(evidence, tibble(fixture_id = id,
    euro_rows = as.integer(sum(str_detect(ids, "^euro-"))),
    asian_rows = as.integer(sum(str_detect(ids, "^asian-"))),
    total_rows = as.integer(sum(str_detect(ids, "^totals-"))),
    market_sufficient = e$parent_review$market_sufficient,
    market_consistent = e$parent_review$market_consistent,
    base_expected_margin = sum((g$home_goals - g$away_goals) * g$probability),
    final_expected_margin = sum((fg$home_goals - fg$away_goals) * fg$probability),
    tail_decision = result$review$decision,
    actual_margin_in_core = facts$margin[match(id, facts$fixture_id)] %in% result$core$core_margins,
    final_tied_rank = any(frozen$probabilities$tied_rank[
      frozen$probabilities$fixture_id == id & frozen$probabilities$model == "FM-1.7.0"])))
}
facts <- facts |> left_join(evidence, by = "fixture_id", relationship = "one-to-one") |>
  mutate(model_direction_reversed = sign(base_expected_margin) * sign(margin) < 0,
    market_evidence = case_when(market_sufficient & market_consistent ~ "sufficient_consistent",
      euro_rows + asian_rows + total_rows == 0L ~ "no_frozen_quote_rows",
      TRUE ~ "partial_or_not_admitted"))
for (mode in c("near_sale", "same_cutoff")) {
  bd <- source |> filter(comparison == mode, model %in% c("BEIDAN_LATER", "BEIDAN_T24")) |>
    select(fixture_id, bd_actual_rank = actual_rank, bd_predicted_outcome = predicted_outcome,
      bd_actual_probability = actual_probability)
  names(bd)[-1] <- paste0(mode, "_", names(bd)[-1])
  facts <- facts |> left_join(bd, by = "fixture_id", relationship = "one-to-one")
}
quotes <- read_csv(sources[["sp"]], show_col_types = FALSE) |>
  filter(fixture_id %in% facts$fixture_id) |>
  left_join(facts |> select(fixture_id, cutoff_utc), by = "fixture_id", relationship = "many-to-one") |>
  mutate(cutoff_utc = lubridate::ymd_hms(cutoff_utc, tz = "UTC"))
stopifnot(!anyDuplicated(quotes[c("fixture_id", "mode")]),
  all(quotes$sp_w > 0 & quotes$sp_d > 0 & quotes$sp_l > 0),
  !anyNA(quotes$cutoff_utc),
  all(quotes$quote_at < quotes$selection_cutoff), all(quotes$quote_at < quotes$kickoff_utc),
  all(quotes$selection_cutoff[quotes$mode == "same_cutoff"] == quotes$cutoff_utc[quotes$mode == "same_cutoff"]))
for (mode in c("near_sale", "same_cutoff")) {
  q <- quotes |> filter(.data$mode == .env$mode) |>
    transmute(fixture_id, W = 1/sp_w, D = 1/sp_d, L = 1/sp_l) |>
    mutate(mass = W + D + L, across(c(W, D, L), ~.x/mass)) |>
    select(-mass) |> pivot_longer(c(W, D, L), names_to = "outcome_3", values_to = "bd_probability_fm_third") |>
    inner_join(facts |> select(fixture_id, outcome_3),
      by = c("fixture_id", "outcome_3"), relationship = "one-to-one") |>
    select(-outcome_3) |>
    rename(!!paste0(mode, "_bd_probability_fm_third") := bd_probability_fm_third)
  facts <- facts |> left_join(q, by = "fixture_id", relationship = "one-to-one")
  predicted <- paste0(mode, "_bd_predicted_outcome")
  facts[[paste0(mode, "_bd_top1_is_fm_third")]] <- facts[[predicted]] == facts$outcome_3
}
# Fixed question family, full denominators: do not only count the 95 failures.
dimensions <- c("issue_id", "event_type", "league", "selected_source", "handicap_group",
  "outcome_3", "ranked_order", "top1_band", "p3_band", "gap23_band", "goal_difference_case",
  "market_evidence", "model_direction_reversed", "actual_margin_in_core", "final_tied_rank")
strata <- list()
for (dimension in dimensions) {
  strata[[dimension]] <- facts |>
    mutate(stratum = as.character(.data[[dimension]])) |>
    group_by(stratum) |> summarise(n = n(), rank3_hits = sum(rank3_hit),
      rank3_rate = mean(rank3_hit), mean_p3 = mean(p3),
      calibration_gap = mean(rank3_hit) - mean(p3),
      share_of_95 = sum(rank3_hit)/95, .groups = "drop") |>
    mutate(dimension = dimension, .before = 1)
  if (dimension %in% c("goal_difference_case", "model_direction_reversed", "actual_margin_in_core")) {
    # Groups use realized outcomes: their rates cannot be calibrated against p3.
    strata[[dimension]] <- strata[[dimension]] |>
      mutate(mean_p3 = NA_real_, calibration_gap = NA_real_)
  }
}
transition <- facts |> count(before_actual_rank, actual_rank, name = "n")
cross <- list()
for (mode in c("near_sale", "same_cutoff")) {
  column <- paste0(mode, "_bd_actual_rank")
  cross[[mode]] <- facts |>
    filter(!is.na(.data[[column]])) |>
    mutate(bd_rank = .data[[column]]) |>
    count(actual_rank, bd_rank, name = "n") |> mutate(comparison = mode, .before = 1)
}
source_type <- facts |> group_by(event_type, selected_source) |>
  summarise(n = n(), rank3_hits = sum(rank3_hit), rank3_rate = mean(rank3_hit),
    mean_p3 = mean(p3), .groups = "drop")
market_signal <- list()
for (mode in c("near_sale", "same_cutoff")) {
  flag <- paste0(mode, "_bd_top1_is_fm_third")
  p <- paste0(mode, "_bd_probability_fm_third")
  market_signal[[mode]] <- facts |>
    filter(!is.na(.data[[flag]])) |>
    group_by(bd_top1_is_fm_third = .data[[flag]]) |>
    summarise(n = n(), rank3_hits = sum(rank3_hit), rank3_rate = mean(rank3_hit),
      mean_fm_p3 = mean(p3), mean_bd_probability = mean(.data[[p]]), .groups = "drop") |>
    mutate(comparison = mode, .before = 1)
}
# Deterministic posthoc illustrations of distinct scenes; no decisions inferred.
illustrations <- facts |> filter(rank3_hit) |>
  group_by(goal_difference_case) |> slice_min(p3, n = 1, with_ties = FALSE) |> ungroup()
tables <- list(fixtures = facts, strata = bind_rows(strata), transitions = transition,
  market_cross = bind_rows(cross), source_type = source_type, cases = illustrations)
tables$market_signal <- bind_rows(market_signal)
dir.create(out, recursive = TRUE, showWarnings = FALSE)
for (name in names(tables)) write_csv(tables[[name]], file.path(out, paste0(name, ".csv")))
summary <- list(n = nrow(facts), rank3_hits = sum(facts$rank3_hit),
  mean_p3 = mean(facts$p3), actual_rank3_rate = mean(facts$rank3_hit),
  before_tail_rank3 = sum(facts$before_actual_rank == 3),
  already_third = sum(facts$rank3_hit & facts$before_actual_rank == 3),
  tail_new_third = sum(facts$rank3_hit & facts$before_actual_rank != 3),
  tail_rescued = sum(!facts$rank3_hit & facts$before_actual_rank == 3))
jsonlite::write_json(list(mode = "POSTHOC_FROZEN_FINAL_RANK3_EDA", summary = summary,
  sources = as.list(sources), source_hashes = as.list(hashes),
  client_sha256 = digest::digest(file = file.path(root, "r/fm17_rank3_scenes.R"), algo = "sha256"),
  output_hashes = as.list(set_names(map_chr(names(tables),
    ~digest::digest(file = file.path(out, paste0(.x, ".csv")), algo = "sha256")), names(tables))),
  cutoff_governance = "No new fit, threshold, selection or routing; preserve original cutoff_utc and frozen rank tie order. Source historical proxies remain diagnostic-only.",
  runtime = list(R = as.character(getRversion()), tidyverse = as.character(packageVersion("tidyverse")),
    dplyr = as.character(packageVersion("dplyr")), readr = as.character(packageVersion("readr"))),
  case_rule = "Posthoc lowest-p3 example per realized goal-difference scene; not independent evidence.",
  missingness = "same_cutoff BD missing for 131 fixtures (not imputed); near_sale BD complete; quote-row absence denotes frozen ledger absence, not universal market absence.",
  generated_at = format(Sys.time(), tz = "UTC", usetz = TRUE)),
  file.path(out, "receipt.json"), pretty = TRUE, auto_unbox = TRUE)
print(summary)
print(tables$strata |> filter(dimension %in% c("event_type", "selected_source", "outcome_3", "goal_difference_case", "gap23_band")), n = 50, width = Inf)
print(transition)
print(tables$market_cross)
