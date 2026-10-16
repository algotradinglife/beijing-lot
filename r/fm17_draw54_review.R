# Rscript r/fm17_draw54_review.R ROOT OUTPUT
# Describe frozen margin geometry and available prematch evidence, not new rules.
args <- commandArgs(TRUE)
stopifnot(length(args) == 2L)
root <- normalizePath(args[1], mustWork = TRUE)
out <- args[2]
suppressPackageStartupMessages(library(tidyverse))
rank_root <- file.path(root, "results/fm17-rank3-scenes-20261016")
prior <- jsonlite::fromJSON(file.path(rank_root, "receipt.json"))
evaluation <- jsonlite::fromJSON(file.path(root, "results/fm17-three-issues-20261013/evaluation.json"))
paths <- c(rank_facts = file.path(rank_root, "fixtures.csv"),
  forecast = prior$sources$forecast, stage = file.path(root, "results/fm16-three-issues-20261012/stage.rds"))
hashes <- map_chr(paths, ~digest::digest(file = .x, algo = "sha256"))
stopifnot(hashes[["rank_facts"]] == prior$output_hashes$fixtures,
  hashes[["forecast"]] == prior$source_hashes$forecast,
  hashes[["stage"]] == evaluation$parent_stage_sha256)
facts <- read_csv(paths[["rank_facts"]], col_types = cols(
  .default = col_guess(), fixture_id = col_character(), issue_id = col_character(), cutoff_utc = col_datetime()))
stopifnot(nrow(problems(facts)) == 0, nrow(facts) == 345L, !anyDuplicated(facts$fixture_id),
  !anyNA(facts$cutoff_utc))
frozen <- readRDS(paths[["forecast"]]); stage <- readRDS(paths[["stage"]])
facts <- facts |> mutate(target_margin = -handicap,
  draw_type = if_else(handicap == 0, "actual_draw_h0", "exact_handicap_nonzero"),
  actual_draw_category = actual_outcome == "D", final_draw_third = outcome_3 == "D",
  draw54 = rank3_hit & actual_outcome == "D")
stopifnot(sum(facts$draw54) == 54L, sum(facts$draw54 & facts$handicap == 0) == 17L)
grids <- features <- forms <- quotes <- articles <- list()
for (id in facts$fixture_id) {
  ix <- match(id, facts$fixture_id); line <- facts$target_margin[ix]
  e <- frozen$entries[[id]]; n <- stage$native[[id]]; packet <- stage$packets[[id]]
  stopifnot(!is.null(n), !is.null(packet),
    identical(as.numeric(e$cutoff$cutoff_utc), as.numeric(facts$cutoff_utc[ix])))
  result <- e$results[["FM-1.7.0"]]
  sources <- list(selected_before_tail = result$base$grid, final = result$final$grid,
    native = n$grid)
  # The native container's schema is checked explicitly rather than guessing.
  if (is.list(sources$native) && !is.data.frame(sources$native)) sources$native <- sources$native$grid
  ref <- stage$references[[id]]$model
  if (!is.null(ref)) sources$market_reference <- ref$grid
  for (source_name in names(sources)) {
    g <- as_tibble(sources[[source_name]])
    stopifnot(all(c("home_goals", "away_goals", "probability") %in% names(g)),
      !anyNA(g), all(g$probability >= 0), abs(sum(g$probability) - 1) < 1e-8)
    m <- g |> mutate(margin = as.integer(home_goals - away_goals)) |>
      group_by(margin) |> summarise(probability = sum(probability), .groups = "drop")
    line_p <- sum(m$probability[m$margin == line])
    mean_m <- sum(m$margin * m$probability)
    marginal_mode <- m$margin[abs(m$probability - max(m$probability)) < 1e-12]
    features[[paste(id, source_name)]] <- tibble(fixture_id = id, distribution = source_name,
      expected_home = sum(g$home_goals * g$probability),
      expected_away = sum(g$away_goals * g$probability), expected_total = sum((g$home_goals + g$away_goals) * g$probability),
      expected_margin = mean_m, margin_sd = sqrt(sum((m$margin - mean_m)^2 * m$probability)),
      target_margin = line, line_probability = line_p,
      left_probability = sum(m$probability[m$margin < line]),
      right_probability = sum(m$probability[m$margin > line]),
      line_margin_rank = as.integer(1 + sum(m$probability > line_p + 1e-12)),
      line_is_mode = line %in% marginal_mode,
      modal_margins = paste(marginal_mode, collapse = ","),
      line_to_mean = line - mean_m,
      probability_line_minus1 = sum(m$probability[m$margin == line - 1]),
      probability_line_plus1 = sum(m$probability[m$margin == line + 1]),
      probability_radius1 = sum(m$probability[abs(m$margin - line) <= 1]))
    grids[[paste(id, source_name)]] <- m |> mutate(fixture_id = id, distribution = source_name,
      target_margin = line, relative_margin = margin - line, .before = 1)
  }
  forms[[id]] <- as_tibble(n$native$rates) |> mutate(fixture_id = id, .before = 1)
  for (market in c("euro", "asian", "totals")) {
    q <- as_tibble(packet[[market]])
    if (nrow(q) == 0L) next
    stopifnot("quote_at" %in% names(q), !anyNA(q$quote_at),
      all(q$quote_at < facts$cutoff_utc[ix]), all(q$fixture_id == id))
    q <- q |> mutate(market = market, .before = 1)
    quotes[[paste(id, market)]] <- q
  }
  af <- as_tibble(packet$article_facts)
  if (nrow(af) > 0L) {
    stopifnot(!anyNA(af$availability_proxy_utc), all(af$availability_proxy_utc < facts$cutoff_utc[ix]))
    articles[[id]] <- af |> mutate(fixture_id = id, .before = 1)
  }
}
features <- bind_rows(features); margins <- bind_rows(grids); forms <- bind_rows(forms)
q <- bind_rows(quotes); article_facts <- bind_rows(articles)
if (nrow(article_facts) == 0L) article_facts <- tibble(fixture_id = character(), evidence_id = character(),
  dimension = character(), fact = character(), availability_proxy_utc = as.POSIXct(character(), tz = "UTC"),
  availability_class = character(), source_sha256 = character())
final <- features |> filter(distribution == "final") |> select(-distribution)
before <- features |> filter(distribution == "selected_before_tail") |>
  select(fixture_id, before_line_probability = line_probability, before_line_margin_rank = line_margin_rank,
    before_expected_total = expected_total, before_expected_margin = expected_margin)
native <- features |> filter(distribution == "native") |>
  select(fixture_id, native_home = expected_home, native_away = expected_away,
    native_line_probability = line_probability, native_line_margin_rank = line_margin_rank)
market <- features |> filter(distribution == "market_reference") |>
  select(fixture_id, market_home = expected_home, market_away = expected_away,
    market_line_probability = line_probability, market_line_margin_rank = line_margin_rank)
all <- facts |> select(-target_margin) |>
  left_join(final, by = "fixture_id", relationship = "one-to-one") |>
  left_join(before, by = "fixture_id", relationship = "one-to-one") |>
  left_join(native, by = "fixture_id", relationship = "one-to-one") |>
  left_join(market, by = "fixture_id", relationship = "one-to-one") |>
  mutate(draw_category_rank = case_when(outcome_1 == "D" ~ 1L, outcome_3 == "D" ~ 3L, TRUE ~ 2L),
    draw_gap_to_second = if_else(draw_category_rank == 3L, probability_2 - line_probability, NA_real_),
    tail_draw_delta = line_probability - before_line_probability,
    within_half_goal_mean = abs(line_to_mean) <= .5,
    margin_top2 = line_margin_rank <= 2L,
    total_band = cut(before_expected_total, c(0, 2, 2.5, 3, Inf), right = FALSE),
    second_gap_band = cut(draw_gap_to_second, c(0, .02, .05, .1, Inf), right = FALSE))
form_wide <- forms |>
  select(fixture_id, role, matches, recent_matches, long_for, long_against, recent_for, recent_against, goals_for, goals_against, ess) |>
  pivot_wider(names_from = role, values_from = c(matches, recent_matches, long_for, long_against,
    recent_for, recent_against, goals_for, goals_against, ess))
all <- all |> left_join(form_wide, by = "fixture_id", relationship = "one-to-one") |>
  mutate(native_line_to_mean = target_margin - (native_home - native_away),
    native_within_half_goal_mean = abs(native_line_to_mean) <= .5)
stopifnot(all(abs(all$line_probability[all$draw54] - all$p3[all$draw54]) < 1e-10),
  all(abs(all$left_probability + all$line_probability + all$right_probability - 1) < 1e-8))
third_control <- all |> filter(final_draw_third)
groups <- list()
for (dimension in c("draw_type", "event_type", "selected_source", "line_is_mode", "margin_top2", "within_half_goal_mean", "native_within_half_goal_mean", "total_band", "second_gap_band")) {
  groups[[dimension]] <- third_control |> group_by(stratum = as.character(.data[[dimension]])) |>
    summarise(n = n(), missed_draws = sum(draw54), draw_rate = mean(actual_draw_category),
      mean_draw_probability = mean(line_probability), .groups = "drop") |>
    mutate(dimension = dimension, .before = 1)
}
cases <- all |> filter(draw54)
ah <- q |> filter(market == "asian") |> select(fixture_id, company_id, quote_at, handicap, home_decimal, away_decimal) |>
  rename(asian_handicap = handicap) |>
  left_join(all |> select(fixture_id, target_margin), by = "fixture_id", relationship = "many-to-one") |>
  mutate(line_minus_asian_center = target_margin + asian_handicap)
stopifnot(!anyDuplicated(ah$fixture_id))
case_review <- cases |>
  left_join(ah |> select(fixture_id, asian_handicap, line_minus_asian_center),
    by = "fixture_id", relationship = "one-to-one") |>
  mutate(structure_note = if_else(line_is_mode,
    "让平对应净胜球为众数；单档中心支持保留，但不证明应高于左右整类",
    "让平对应净胜球为第二档；靠近中心，仍需比较整类与盘口"),
    fundamental_note = sprintf("原生λ主/客 %.2f/%.2f；目标净胜球%+.0f，距原生均值%+.2f；近期/长期主进球 %.2f/%.2f，客进球 %.2f/%.2f",
      native_home, native_away, target_margin, native_line_to_mean,
      recent_for_home, long_for_home, recent_for_away, long_for_away),
    market_note = if_else(is.na(asian_handicap), "冻结亚盘缺失，不能作盘口支持判断",
      sprintf("亚盘主%+.2f，对应净胜中线%+.2f；目标距该线%+.2f球",
        asian_handicap, -asian_handicap, line_minus_asian_center)),
    conclusion = "支持将让平保留为可讨论场景；是否取代第二名仍未证明",
    qualitative_gap = "本场冻结文章事实为空；阵容、伤停、战意及独立排名未完成逐场核验")
ah_controls <- third_control |>
  left_join(ah |> select(fixture_id, line_minus_asian_center), by = "fixture_id", relationship = "one-to-one") |>
  mutate(ah_alignment = case_when(is.na(line_minus_asian_center) ~ "missing",
    abs(line_minus_asian_center) <= .5 ~ "within_half_goal", TRUE ~ "outside_half_goal")) |>
  group_by(ah_alignment) |> summarise(n = n(), missed_draws = sum(draw54),
    draw_rate = mean(actual_draw_category), .groups = "drop")
tables <- list(all_fixtures = all, cases54 = cases, margin_features = features,
  case_margins = margins |> filter(fixture_id %in% cases$fixture_id),
  case_forms = forms |> filter(fixture_id %in% cases$fixture_id),
  case_quotes = q |> filter(fixture_id %in% cases$fixture_id),
  case_review = case_review,
  case_article_facts = article_facts |> filter(fixture_id %in% cases$fixture_id),
  asian_alignment = ah |> filter(fixture_id %in% cases$fixture_id),
  asian_controls = ah_controls,
  controls = bind_rows(groups))
dir.create(out, recursive = TRUE, showWarnings = FALSE)
for (name in names(tables)) write_csv(tables[[name]], file.path(out, paste0(name, ".csv")))
jsonlite::write_json(list(mode = "POSTHOC_DRAW54_MARGIN_AND_FROZEN_FUNDAMENTAL_REVIEW",
  sources = as.list(paths), source_hashes = as.list(hashes),
  client_sha256 = digest::digest(file = file.path(root, "r/fm17_draw54_review.R"), algo = "sha256"),
  output_hashes = as.list(set_names(map_chr(names(tables),
    ~digest::digest(file = file.path(out, paste0(.x, ".csv")), algo = "sha256")), names(tables))),
  sample = list(all = nrow(all), final_draw_third = nrow(third_control), cases = nrow(cases),
    ordinary_draw = sum(cases$handicap == 0), exact_handicap = sum(cases$handicap != 0),
    article_rows_all = nrow(article_facts), article_rows_cases = sum(article_facts$fixture_id %in% cases$fixture_id)),
  support_interpretation = "Modal/top2 margin and mean proximity describe geometry, not a recommendation to promote D over aggregate W/L. Realized 54 selected by outcome; compare 197 final-D-third controls.",
  cutoff_governance = "No fitting, threshold selection or decisions. Frozen fixture cutoff preserved. Quotes strictly before cutoff; proxy article evidence not upgraded to observed availability.",
  generated_at = format(Sys.time(), tz = "UTC", usetz = TRUE)), file.path(out, "receipt.json"), pretty = TRUE, auto_unbox = TRUE)
print(cases |> group_by(draw_type) |> summarise(n = n(), modal = sum(line_is_mode),
  margin_top2 = sum(margin_top2), within_half = sum(within_half_goal_mean),
  mean_draw = mean(line_probability), mean_total = mean(before_expected_total),
  mean_tail_delta = mean(tail_draw_delta), .groups = "drop"), width = Inf)
print(tables$controls, n = 50, width = Inf)
