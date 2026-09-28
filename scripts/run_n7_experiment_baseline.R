#!/usr/bin/env Rscript
# N7 experiment baseline driver (issue #493).
#
# Purpose: execute the confirmed N7 experiment contract end to end on the real
# decision-time poll series, for the three same-budget structural definitions, and
# freeze the resulting period/epoch/group/ticket/settlement tables with a
# machine-readable receipt.
#
# It is a thin entry point: the calendar, availability, budget and admission rules
# live in r/n7_experiment_contract.R, the probability/funding/settlement rules in
# r/n7_experiment_replay.R, and the store reading in r/n7_experiment_inputs.R.
#
# Declared engineering parameters (NOT chosen policy thresholds):
#   --max-reuse 1 --max-overlap 0   mutual exclusion, used only to exercise the
#                                   constraint interface; the contract leaves the
#                                   numeric caps to #496.
#   --rho -0.14                     the frozen Dixon-Coles default named by the
#                                   contract; no re-selection is performed here.
#
# Usage:
#   Rscript --vanilla scripts/run_n7_experiment_baseline.R --issues 26061,26069,26077,26085 \
#     --output results/n7_493_baseline_v1
#
# No network access, no writes to the store, no writes outside --output.

suppressWarnings(suppressMessages({
  library(tibble); library(dplyr); library(jsonlite); library(digest)
}))

find_root <- function() {
  path <- normalizePath(".")
  while (!file.exists(file.path(path, "r", "n7_experiment_contract.R"))) {
    parent <- dirname(path)
    if (parent == path) stop("repo root not found")
    path <- parent
  }
  path
}

parse_args <- function(argv) {
  out <- list(issues = NULL, output = NULL, workers = 1L, rho = -0.14,
              max_reuse = 1L, max_overlap = 0L, db = "data/beidan_live.db",
              seed = 1L, cutoff_db = "data/derived/500_bjdc/500_bjdc.sqlite.bak")
  i <- 1L
  while (i <= length(argv)) {
    key <- argv[i]
    value <- if (i < length(argv)) argv[i + 1L] else NA_character_
    if (key == "--issues") out$issues <- strsplit(value, ",", fixed = TRUE)[[1L]]
    else if (key == "--output") out$output <- value
    else if (key == "--workers") out$workers <- as.integer(value)
    else if (key == "--rho") out$rho <- as.numeric(value)
    else if (key == "--max-reuse") out$max_reuse <- as.integer(value)
    else if (key == "--max-overlap") out$max_overlap <- as.integer(value)
    else if (key == "--db") out$db <- value
    else if (key == "--seed") out$seed <- as.integer(value)
    else if (key == "--cutoff-db") out$cutoff_db <- value
    else stop("unknown argument: ", key)
    i <- i + 2L
  }
  if (is.null(out$issues) || is.null(out$output)) {
    stop("--issues and --output are required")
  }
  out
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  root <- find_root()
  setwd(root)
  for (module in c("dixon_coles_grid.R", "joint_basket_dc_fit.R",
                   "joint_basket_settlement.R", "n7_fixture_portfolio.R",
                   "n7_experiment_contract.R", "n7_experiment_replay.R",
                   "n7_experiment_inputs.R")) {
    source(file.path("r", module))
  }
  if (!dir.exists(args$output)) dir.create(args$output, recursive = TRUE)

  connection <- n7_open_store(args$db)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  issues <- sort(args$issues)
  fixtures <- n7_read_fixtures(connection, issues, kickoff_tz = N7_DECISION_TZ)
  snapshots <- n7_read_snapshots(connection, issues)
  settlement <- n7_read_settlements(connection, issues)

  # Per-match cutoffs feed the SCHEDULE-ANOMALY check only; they are not an
  # admission gate. They live in the Nowscore match table, joined on the declared
  # key (issue, match_idx). The key must be unique on both sides or the merge
  # would fan out and attach one fixture's evidence to another, so it is checked
  # rather than assumed. Fixtures the source did not cover keep NA.
  cutoff_connection <- n7_open_store(args$cutoff_db)
  on.exit(DBI::dbDisconnect(cutoff_connection), add = TRUE)
  cutoffs <- n7_read_sale_cutoffs(cutoff_connection, issues)
  # The left side must have a unique key too, or the merge multiplies rows.
  if (anyNA(fixtures$match_idx) || anyDuplicated(fixtures[c("issue", "match_idx")])) {
    stop("run_n7_experiment_baseline: fixtures need a unique non-missing ",
         "(issue, match_idx) key for the cutoff join")
  }
  n_before <- nrow(fixtures)
  fixtures <- merge(fixtures, cutoffs, by = c("issue", "match_idx"), all.x = TRUE,
                    sort = FALSE)
  if (nrow(fixtures) != n_before) {
    stop("run_n7_experiment_baseline: the cutoff join changed the row count")
  }
  fixtures <- fixtures[order(fixtures$match_id), , drop = FALSE]

  # ---- Calendar and availability, once per epoch -----------------------------
  fixtures$epoch_date <- n7_epoch_date(fixtures$kickoff_utc)
  snapshot_index <- n7_index_snapshots(snapshots)
  epochs <- sort(unique(fixtures$epoch_date))
  epoch_rows <- lapply(epochs, function(date) {
    list(issue = NA_character_, local_date = date, epoch_utc = n7_decision_epoch(date))
  })

  epoch_records <- list()
  priced_pool <- list()
  for (date in epochs) {
    epoch_utc <- n7_decision_epoch(date)
    scope <- fixtures[fixtures$epoch_date == date, , drop = FALSE]
    # One epoch may span several issues in the store; each issue is scored
    # separately so a period never mixes two issues' fixtures.
    for (issue in sort(unique(scope$issue))) {
      issue_fixtures <- scope[scope$issue == issue, , drop = FALSE]
      elig <- n7_eligible_fixtures(issue_fixtures, epoch_utc)
      priced <- n7_select_snapshots(snapshots, elig$eligible, epoch_utc,
                                    rows_by_fixture = snapshot_index)
      if (nrow(priced$priced)) {
        priced_pool[[length(priced_pool) + 1L]] <- priced$priced
      }
      epoch_records[[length(epoch_records) + 1L]] <- tibble::tibble(
        issue = issue, local_date = date, epoch_utc = epoch_utc,
        n_scope = nrow(issue_fixtures),
        n_eligible = nrow(elig$eligible),
        n_excluded_window = nrow(elig$excluded),
        n_priced = nrow(priced$priced),
        n_excluded_quote = nrow(priced$excluded))
    }
  }
  epoch_scope <- dplyr::bind_rows(epoch_records)
  cat(sprintf("[progress] %d issues, %d fixtures, %d snapshots, %d settlements, %d epochs\n",
              length(issues), nrow(fixtures), nrow(snapshots), nrow(settlement),
              nrow(epoch_scope)), file = stderr())

  # ---- Probability base, parallelised over independent chunks ----------------
  priced_all <- dplyr::bind_rows(priced_pool)
  if (!nrow(priced_all)) stop("driver: no decision-time-admissible priced fixture at all")
  probability_chunks <- if (args$workers > 1L && nrow(priced_all) > args$workers) {
    split(seq_len(nrow(priced_all)), cut(seq_len(nrow(priced_all)), args$workers))
  } else {
    list(seq_len(nrow(priced_all)))
  }
  computed <- parallel::mclapply(probability_chunks, function(rows) {
    n7_euro_probabilities(priced_all[rows, , drop = FALSE], fixtures, rho = args$rho)
  }, mc.cores = min(args$workers, length(probability_chunks)))
  cat(sprintf("[progress] priced rows %d across %d chunks\n", nrow(priced_all),
              length(probability_chunks)), file = stderr())
  probabilities <- dplyr::bind_rows(lapply(computed, function(x) x$probabilities))
  probability_excluded <- dplyr::bind_rows(lapply(computed, function(x) x$excluded))

  # ---- Period plans ----------------------------------------------------------
  # The plan loop lives in r/n7_experiment_replay.R so the cross-day budget,
  # under-investment and infeasibility boundaries are unit-testable with
  # engineering fixtures instead of only reachable through this script.
  structures <- n7_structural_definitions()
  structures <- structures[structures$structure %in% c("4x128", "8x64", "4x96_plus_4x32"), ]
  all_groups <- list(); all_tickets <- list(); all_settled <- list(); all_epochs <- list()

  for (s in seq_len(nrow(structures))) {
    structure <- structures$structure[s]
    group_tickets <- structures$group_tickets[[s]]
    for (issue in issues) {
      cat(sprintf("[progress] %s issue %s\n", structure, issue), file = stderr())
      issue_epochs <- epoch_scope[epoch_scope$issue == issue, , drop = FALSE]
      issue_epochs <- issue_epochs[order(issue_epochs$epoch_utc), , drop = FALSE]
      plan <- n7_run_period_plan(
        epoch_utc = issue_epochs$epoch_utc,
        probabilities = probabilities[probabilities$issue == issue, , drop = FALSE],
        settlement = settlement, group_tickets = group_tickets,
        max_reuse = args$max_reuse, max_overlap = args$max_overlap,
        seed = args$seed, issue = issue, structure = structure)
      all_groups[[length(all_groups) + 1L]] <- plan$groups
      all_tickets[[length(all_tickets) + 1L]] <- plan$tickets
      all_settled[[length(all_settled) + 1L]] <- plan$settled
      ledger <- plan$ledger
      ledger$local_date <- issue_epochs$local_date[match(ledger$epoch_utc,
                                                         issue_epochs$epoch_utc)]
      all_epochs[[length(all_epochs) + 1L]] <- ledger
    }
  }

  # Fall back to the first part's typed template when nothing was bought, so an
  # all-infeasible run still writes the contract's schemas instead of zero columns.
  nonempty <- function(parts) {
    keep <- vapply(parts, nrow, integer(1L)) > 0L
    if (!any(keep)) return(parts[[1L]])
    dplyr::bind_rows(parts[keep])
  }
  groups <- nonempty(all_groups)
  tickets <- nonempty(all_tickets)
  settled <- nonempty(all_settled)
  epoch_ledger <- nonempty(all_epochs)

  # ---- Metrics per structure -------------------------------------------------
  metrics <- dplyr::bind_rows(lapply(unique(settled$structure), function(structure) {
    subset <- settled[settled$structure == structure, , drop = FALSE]
    cbind(structure = structure, n7_experiment_metrics(subset))
  }))

  # ---- Freeze and write ------------------------------------------------------
  write.csv(epoch_scope, file.path(args$output, "epoch_scope.csv"), row.names = FALSE)
  write.csv(probability_excluded, file.path(args$output, "probability_excluded.csv"),
            row.names = FALSE)
  write.csv(epoch_ledger, file.path(args$output, "epoch_ledger.csv"), row.names = FALSE)
  write.csv(groups, file.path(args$output, "groups.csv"), row.names = FALSE)
  # The purchased tickets are part of the frozen baseline: without them the receipt
  # does not bind WHICH combinations were bought, and TopK or duplicate-purchase
  # claims cannot be checked independently.
  write.csv(tickets, file.path(args$output, "tickets.csv"), row.names = FALSE)
  write.csv(settled, file.path(args$output, "settled_groups.csv"), row.names = FALSE)
  write.csv(metrics, file.path(args$output, "metrics.csv"), row.names = FALSE)
  write.csv(probabilities, file.path(args$output, "probabilities.csv"), row.names = FALSE)

  receipt <- list(
    issue = 493, generated_at = n7_utc_iso(as.numeric(Sys.time()), "generated_at"),
    rho = args$rho, max_reuse = args$max_reuse, max_overlap = args$max_overlap,
    seed = as.integer(args$seed),
    # Declared, not assumed: a ticket is priced as the product of seven marginal
    # fixture distributions. Dixon-Coles models dependence WITHIN one match; it does
    # not establish independence BETWEEN fixtures.
    probability_model = N7_PROBABILITY_MODEL,
    kickoff_tz = N7_DECISION_TZ, decision_hour_local = N7_DECISION_HOUR,
    window_start_hours = N7_WINDOW_START_HOURS, window_end_hours = N7_WINDOW_END_HOURS,
    window_rule = "NEXT_LOCAL_CALENDAR_DAY_HALF_OPEN",
    # The cutoff table is no longer an admission gate; it is the schedule-anomaly
    # input. Its CONTENT still decides which fixtures are dropped, so the digest
    # is bound rather than only the file path (which is 51 GB and cannot be
    # hashed in a run).
    cutoff_db = args$cutoff_db, n_cutoffs = nrow(cutoffs),
    n_cutoff_unknown = sum(is.na(cutoffs$sale_cutoff_utc)),
    cutoff_digest = digest::digest(
      paste(cutoffs$issue, cutoffs$match_idx, cutoffs$sale_cutoff_local,
            collapse = "|"),
      algo = "sha256", serialize = FALSE),
    budget_cny = N7_PERIOD_BUDGET_CNY, unit_cny = N7_UNIT_CNY,
    payout_factor = N7_PAYOUT_FACTOR,
    issues = issues, n_fixtures = nrow(fixtures), n_snapshots = nrow(snapshots),
    n_settlement = nrow(settlement),
    source_identity = list(
      store = args$db,
      euro_odds = "500.com bjdc bet page pjoz (average European odds)",
      settlement = "500.com zqdc kaijiang",
      contract_mandated_source = "Nowscore",
      source_matches_contract = FALSE),
    implementation_hashes = n7_file_hashes(c(
      "r/n7_experiment_contract.R", "r/n7_experiment_replay.R",
      "r/n7_experiment_inputs.R", "r/dixon_coles_grid.R",
      "r/joint_basket_dc_fit.R", "r/joint_basket_settlement.R",
      "r/n7_fixture_portfolio.R", "scripts/run_n7_experiment_baseline.R")),
    input_hashes = n7_file_hashes(args$db))
  sealed <- n7_seal_artifact(list(receipt = receipt, metrics = metrics,
                                  groups = groups, tickets = tickets,
                                  settled = settled))
  receipt$seal <- sealed$seal
  writeLines(sealed$canonical_json, file.path(args$output, "artifact.json"))
  writeLines(jsonlite::toJSON(receipt, auto_unbox = TRUE, pretty = TRUE, digits = 17),
             file.path(args$output, "receipt.json"))
  write.csv(data.frame(file = names(receipt$implementation_hashes),
                       sha256 = unname(receipt$implementation_hashes)),
            file.path(args$output, "implementation_hashes.csv"), row.names = FALSE)

  cat("structure comparison\n")
  print(as.data.frame(metrics[, c("structure", "期数", "决策时点数", "组数", "票数",
                                  "总投入", "可结算投入", "待结算投入", "已知回款",
                                  "已结算净收益", "已结算净ROI", "回收倍数",
                                  "截至当前回款减累计投入", "最终净收益口径", "命中组数")]))
  cat("\nepoch reasons\n")
  print(as.data.frame(table(epoch_ledger$structure, epoch_ledger$reason)))
  cat("\nseal:", receipt$seal, "\n")
  invisible(NULL)
}

main()
