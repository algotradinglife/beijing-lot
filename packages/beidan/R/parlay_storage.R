#' Validate a saved decision's identity and ledgers
#' @param result Result returned by [parlay_build_plan()].
#' @return Invisibly TRUE; malformed identities or inconsistent ledgers error.
#' @details No I/O. The result retains probabilities and support for later diagnosis.
parlay_check_saved_result <- function(result) {
  checkmate::assert_list(result)
  for (name in c("plan", "cutoff", "history", "funded", "probabilities", "built", "ranked")) {
    if (is.null(result[[name]])) stop("result is missing ", name)
  }
  match_check_character_id(result$plan$issue_id, "issue_id")
  checkmate::assert_posixct(result$plan$epoch_utc, len = 1L, any.missing = FALSE)
  if (!is.finite(as.numeric(result$plan$epoch_utc))) stop("invalid decision time")
  if (!identical(result$cutoff$issue_id, result$plan$issue_id) ||
      !identical(as.numeric(result$cutoff$cutoff_utc), as.numeric(result$plan$epoch_utc))) {
    stop("result decision identity mismatch")
  }
  match_validate_table(result$plan$purchases, "purchases")
  if (!identical(result$plan$purchases, result$funded$purchases)) {
    stop("result purchase ledger mismatch")
  }
  history <- parlay_validate_prior_state(result$history)$purchases
  purchases <- result$plan$purchases
  if (anyNA(purchases$issue_id) || any(purchases$issue_id != result$plan$issue_id) ||
      anyNA(purchases$epoch_at) || any(purchases$epoch_at != result$plan$epoch_utc)) {
    stop("purchase decision identity mismatch")
  }
  if (anyNA(history$issue_id) || any(history$issue_id != result$plan$issue_id) ||
      anyNA(history$epoch_at) || any(history$epoch_at > result$plan$epoch_utc)) {
    stop("history decision identity or chronology mismatch")
  }
  current <- history[history$epoch_at == result$plan$epoch_utc, , drop = FALSE]
  pick <- match(purchases$ticket_id, current$ticket_id)
  if (nrow(current) != nrow(purchases) || anyNA(pick) ||
      !identical(current[pick, , drop = FALSE], purchases)) {
    stop("history does not reconcile current purchases")
  }
  funded <- result$plan$funded
  if (!is.data.frame(funded) || anyDuplicated(funded$ticket_id) ||
      !all(c("ticket_id", "candidate_id", "group_id") %in% names(funded))) {
    stop("invalid settlement funded ledger")
  }
  pick <- match(purchases$ticket_id, funded$ticket_id)
  keys <- c("ticket_id", "candidate_id", "group_id")
  if (nrow(funded) != nrow(purchases) || anyNA(pick) ||
      !identical(funded[pick, keys, drop = FALSE], purchases[, keys, drop = FALSE])) {
    stop("settlement funded ledger mismatch")
  }
  for (group in unique(purchases$group_id)) {
    ids <- result$plan$group_legs$fixture_id[result$plan$group_legs$group_id == group]
    if (!setequal(ids, result$history$fixture_sets[[group]])) {
      stop("history fixture set mismatch")
    }
  }
  invisible(TRUE)
}

#' Save a decision result without overwriting a previous decision
#' @param result Result from [parlay_build_plan()], including its frozen plan and history.
#' @param path Explicit destination RDS path. Parent directory must already exist.
#' @param recorded_at Explicit POSIXct recording time. Must not precede the decision
#'   or exceed the current clock. Beijing timezone is accepted without changing the instant.
#' @return Invisibly the destination path. Existing files always cause an error.
#' @details Writes a result and integrity receipt through a temporary file in the
#'   destination directory, then publishes with an exclusive hard link. Unsupported
#'   filesystems fail without overwriting. No network or betting action occurs.
#'   This records an artifact; it does not certify when upstream data became available.
#' @export
parlay_save_result <- function(result, path, recorded_at) {
  parlay_check_saved_result(result)
  checkmate::assert_string(path, min.chars = 1L)
  checkmate::assert_posixct(recorded_at, len = 1L, any.missing = FALSE)
  if (!is.finite(as.numeric(recorded_at)) || recorded_at < result$plan$epoch_utc ||
      recorded_at > Sys.time()) stop("recorded_at must be after decision and not in future")
  if (!dir.exists(dirname(path))) stop("destination directory does not exist")
  if (file.exists(path)) stop("saved decision already exists; refusing overwrite")
  envelope <- list(result = result, receipt = list(
    issue_id = result$plan$issue_id, decision_at = result$plan$epoch_utc,
    recorded_at = lubridate::with_tz(recorded_at, "Asia/Shanghai"),
    result_hash = rlang::hash(result)))
  temporary <- tempfile(".decision-", tmpdir = dirname(path))
  on.exit(unlink(temporary), add = TRUE)
  saveRDS(envelope, temporary, version = 3)
  if (!file.link(temporary, path)) stop("cannot publish decision without overwriting")
  invisible(path)
}

#' Read the original decision for settlement and later allocations
#' @param path Explicit path written by [parlay_save_result()].
#' @param issue_id Expected issue identifier, preserving leading zeros.
#' @param decision_at Expected POSIXct decision time; any explicit timezone is accepted.
#' @return Original result, including plan, history and diagnosis inputs.
#' @details Reads local RDS only. Corruption, hash mismatch or wrong issue/time error.
#'   It never rebuilds a plan from current quotes. No network or writes occur.
#' @export
parlay_read_result <- function(path, issue_id, decision_at) {
  checkmate::assert_file_exists(path)
  match_check_character_id(issue_id, "issue_id")
  checkmate::assert_posixct(decision_at, len = 1L, any.missing = FALSE)
  envelope <- readRDS(path)
  if (!is.list(envelope) || !is.list(envelope$receipt) ||
      !identical(envelope$receipt$result_hash, rlang::hash(envelope$result))) {
    stop("saved result integrity mismatch")
  }
  parlay_check_saved_result(envelope$result)
  receipt <- envelope$receipt
  if (!identical(receipt$issue_id, issue_id) ||
      !identical(receipt$issue_id, envelope$result$plan$issue_id) ||
      !identical(as.numeric(receipt$decision_at), as.numeric(decision_at)) ||
      !identical(as.numeric(receipt$decision_at), as.numeric(envelope$result$plan$epoch_utc))) {
    stop("saved result issue or decision mismatch")
  }
  envelope$result
}
