# Blinded native preparation only; target settlements and SP are never opened.
args <- commandArgs(TRUE)
root <- normalizePath(args[1], mustWork = TRUE)
out <- file.path(root, 'results/fm15-two-issues-20261012')
dir.create(out, recursive = TRUE, showWarnings = FALSE)
suppressPackageStartupMessages(library(tidyverse))
library(jsonlite)
library(beidan, lib.loc = file.path(root, 'results/fm15-version-20261012/library'))
reticulate::use_python(file.path(root, '.venv/bin/python'), required = TRUE)
sys <- reticulate::import('sys', convert = FALSE)
sys$path$insert(0L, file.path(root, 'packages/beidan/inst/python'))
shared <- reticulate::import('beidan_backend.temporal_learning', convert = FALSE)
policy <- list(recent_n = 8L, alpha = .5, minimum_matches = 12L, minimum_ess = 8)
packets <- list(); ledger <- list(); entries <- list(); inputs <- list()
for (issue in c('26098', '26101')) {
  parent_path <- file.path(root, 'results/fundamental-issues-20261011/run-20261011T011533.304058Z', paste0(issue, '-frozen.rds'))
  if (issue == '26098') {
    market_path <- file.path(root, 'results/fm13-26098-20261011/issue-stage-frozen-56674f0212ff.rds')
    blind_path <- file.path(root, 'results/fm13-pa-26098-20261011/blinded-inputs.rds')
  } else {
    manifest <- fromJSON(file.path(root, 'results/fm14-26101-20261011/stage-manifest.json'))
    market_path <- file.path(root, 'results/fm14-26101-20261011', manifest$stage_file)
    stopifnot(digest::digest(file = market_path, algo = 'sha256') == manifest$sha256)
    blind_path <- file.path(root, 'results/fm14-26101-20261011/blinded-inputs.rds')
  }
  parent <- readRDS(parent_path); market <- readRDS(market_path); blind <- readRDS(blind_path)
  paths <- c(parent_path, market_path, blind_path, file.path(root, 'r/fm15_two_issue_prepare.R'))
  hashes <- as.list(setNames(map_chr(paths, ~digest::digest(file = .x, algo = 'sha256')), substring(paths, nchar(root)+2)))
  inputs[[issue]] <- hashes
  history <- as_tibble(map(parent$history, identity))
  stopifnot(!anyDuplicated(parent$fixtures$fixture_id), nrow(parent$fixtures) == nrow(market$ledger))
  for (i in seq_len(nrow(parent$fixtures))) {
    f <- as.list(parent$fixtures[i,]); a <- blind$packets[[match(f$fixture_id, map_chr(blind$packets, 'fixture_id'))]]
    if (is.na(f$cutoff_utc)) {
      ledger[[f$fixture_id]] <- tibble(fixture_id=f$fixture_id, issue_id=issue, status='CUTOFF_UNAVAILABLE', reason='Missing explicit fixture decision cutoff')
      next
    }
    cutoff <- shared$Cutoff$decision_epoch(issue, format(f$cutoff_utc, '%Y-%m-%dT%H:%M:%SZ', tz='UTC'))
    h <- filter(history, fixture_id == f$fixture_id) |> mutate(row_key=paste(scope,match_id,sep=':'), event_date=as.character(event_date))
    native_fixture <- f[c('fixture_id','issue_id','provider_id','home_id','away_id')]
    native <- tryCatch(beidan:::estimate_recent_venue_goals(h, native_fixture, as.character(parent$fixtures$provider_id), cutoff, hashes, root, policy), error = identity)
    if (inherits(native, 'error')) {
      ledger[[f$fixture_id]] <- tibble(fixture_id=f$fixture_id, issue_id=issue, status='NATIVE_UNAVAILABLE', reason=conditionMessage(native))
      cat(f$fixture_id, 'unavailable:', conditionMessage(native), '\n')
      next
    }
    parameters <- native$parameters
    grid <- beidan:::dixon_coles_score_grid(parameters$lambda_home, parameters$lambda_away, handicap=0L, tail_tolerance=1e-10, rho=-.1)
    grid <- as_tibble(grid$grid) |> select(home_goals, away_goals, probability)
    margins <- grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |> summarise(probability=sum(probability), .groups='drop') |> arrange(desc(probability), margin)
    j <- match(f$fixture_id, market$ledger$fixture_id)
    q <- market$selected_quotes[[j]]
    packet <- list(fixture_id=f$fixture_id, cutoff_utc=format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'), base_hash=beidan:::.score_margin_hash(grid), home=a$home, away=a$away, competition=a$competition, native_parameters=parameters, native_rates=native$rates, top_margins=head(margins,7), independent_market=if(market$ledger$stage[j]=='UNAVAILABLE') NULL else market$markets[[j]]$ordinary, asian_quotes=q$asian, total_quotes=q$totals, euro_quotes=q$euro, article_facts=a$article_facts, missing=a$missing)
    packets[[f$fixture_id]] <- packet
    entries[[f$fixture_id]] <- list(fixture=f, native=native, grid=grid, source_hashes=hashes, packet=packet, blinded=a, quotes=q)
    ledger[[f$fixture_id]] <- tibble(fixture_id=f$fixture_id, issue_id=issue, status=if(market$ledger$stage[j]=='UNAVAILABLE') 'NATIVE_ONLY_MARKET_INCOMPLETE' else 'READY_FOR_REVIEW', reason='')
    cat(f$fixture_id, 'native', parameters$lambda_home, parameters$lambda_away, '\n')
  }
}
saveRDS(list(entries=entries, ledger=bind_rows(ledger), inputs=inputs, policy=policy), file.path(out,'native-stage.rds'))
write_csv(bind_rows(ledger),file.path(out,'coverage.csv'))
write_json(list(model='FM-1.5.0',fixtures=unname(packets)),file.path(out,'review-inputs.json'),auto_unbox=TRUE,pretty=TRUE,digits=17,POSIXt='ISO8601',na='null')
cat('Coverage:', nrow(bind_rows(ledger)), 'rows;',length(entries),'native estimates.\n')
