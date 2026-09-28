# Input readers for the joint-probability basket reconciliation.
#
# Every reader is explicit about its source root, validates the data contract at
# the boundary, and fails closed on anything unexpected. Bundles are verified
# against the catalogue hash before use. No function scrapes, writes, imputes or
# admits a fixture on the basis of an outcome.

jb_sha256_file <- function(path) {
  if (!file.exists(path)) stop("jb_sha256_file: missing file ", path)
  digest::digest(file = path, algo = "sha256")
}

# Catalogue: one row per issue with the bundle path and its sha256.
jb_read_catalog <- function(source_root) {
  path <- file.path(source_root, "catalog.json")
  if (!file.exists(path)) stop("jb_read_catalog: missing ", path)
  raw <- jsonlite::fromJSON(path, simplifyDataFrame = TRUE)
  if (!all(c("issues") %in% names(raw))) stop("jb_read_catalog: catalogue has no $issues")
  x <- tibble::as_tibble(raw$issues)
  need <- c("issue", "cohort", "path", "sha256")
  if (!all(need %in% names(x))) stop("jb_read_catalog: catalogue columns must include ",
                                     paste(need, collapse = ", "))
  x <- x[, need]
  if (anyDuplicated(x$issue)) stop("jb_read_catalog: duplicate issue identity")
  if (any(!nzchar(x$issue)) || any(!nzchar(x$sha256))) stop("jb_read_catalog: blank issue or sha256")
  if (any(!file.exists(x$path))) {
    stop("jb_read_catalog: missing bundle file(s): ",
         paste(utils::head(x$path[!file.exists(x$path)], 3), collapse = ", "))
  }
  x <- dplyr::arrange(x, .data$issue)
  attr(x, "historical_admission") <- isTRUE(raw$historical_admission)
  x
}

jb_read_receipt <- function(source_root) {
  path <- file.path(source_root, "receipt.json")
  if (!file.exists(path)) stop("jb_read_receipt: missing ", path)
  jsonlite::fromJSON(path, simplifyVector = FALSE)
}

# Verify every catalogue bundle hash. Returns the count verified.
jb_verify_bundle_hashes <- function(catalog, expected_n = NULL) {
  actual <- vapply(catalog$path, jb_sha256_file, character(1))
  bad <- which(actual != catalog$sha256)
  if (length(bad)) {
    stop("jb_verify_bundle_hashes: hash mismatch for issue(s) ",
         paste(utils::head(catalog$issue[bad], 3), collapse = ", "))
  }
  if (!is.null(expected_n) && nrow(catalog) != expected_n) {
    stop("jb_verify_bundle_hashes: expected ", expected_n, " issues, found ", nrow(catalog))
  }
  nrow(catalog)
}

# Settlement labels with the derived direction. Ids stay character so that
# leading zeros survive.
jb_read_labels <- function(source_root) {
  path <- file.path(source_root, "labels.json")
  if (!file.exists(path)) stop("jb_read_labels: missing ", path)
  x <- tibble::as_tibble(jsonlite::fromJSON(path, simplifyDataFrame = TRUE))
  need <- c("issue", "slot", "provider_id", "handicap", "actual_home", "actual_away", "result_state")
  if (!all(need %in% names(x))) stop("jb_read_labels: labels columns must include ",
                                     paste(need, collapse = ", "))
  x <- dplyr::mutate(x,
    issue = as.character(.data$issue),
    slot = as.integer(.data$slot),
    provider_id = as.character(.data$provider_id),
    outcome = jb_outcome_index(.data$actual_home, .data$actual_away, .data$handicap))
  key <- c("issue", "slot", "provider_id")
  if (anyDuplicated(x[key])) stop("jb_read_labels: duplicate settled fixture identity")
  if (any(x$result_state != "完场")) {
    stop("jb_read_labels: non-final settlement rows present: ",
         paste(unique(x$result_state[!x$result_state == "完场"]), collapse = ", "))
  }
  x
}

# One frozen issue bundle, hash-checked against the catalogue.
jb_read_bundle <- function(path, sha256) {
  if (jb_sha256_file(path) != sha256) stop("jb_read_bundle: bundle hash mismatch for ", path)
  b <- jsonlite::fromJSON(gzfile(path), simplifyDataFrame = TRUE)
  if (!"expanded_pool" %in% names(b)) stop("jb_read_bundle: bundle has no expanded_pool")
  fx <- tibble::as_tibble(b$expanded_pool$fixtures)
  need <- c("slot", "provider_id", "handicap", "p_W", "p_D", "p_L")
  if (!all(need %in% names(fx))) stop("jb_read_bundle: fixtures columns must include ",
                                      paste(need, collapse = ", "))
  if (anyDuplicated(fx$slot)) stop("jb_read_bundle: duplicate fixture slot")
  pv <- as.matrix(fx[, c("p_W", "p_D", "p_L"), drop = FALSE])
  if (anyNA(pv) || any(pv < 0) || any(abs(rowSums(pv) - 1) > 1e-8)) {
    stop("jb_read_bundle: frozen probabilities are not a valid distribution")
  }
  list(
    issue = as.character(b$issue),
    fixtures = fx,
    pv = pv,
    historical_admission = isTRUE(b$historical_admission),
    seal = as.character(b$seal),
    mode = if ("mode" %in% names(b$expanded_pool)) as.character(b$expanded_pool$mode) else NA_character_,
    cutoffs = b$cutoffs
  )
}

# Align one issue's frozen fixtures to its settled outcomes. Fails closed on any
# fixture that has no settlement.
jb_issue_design <- function(bundle, labels) {
  lb <- dplyr::filter(labels, .data$issue == bundle$issue)
  if (!nrow(lb)) stop("jb_issue_design: no settlement rows for issue ", bundle$issue)
  fx <- bundle$fixtures
  idx <- match(paste(fx$slot, fx$provider_id), paste(lb$slot, lb$provider_id))
  if (anyNA(idx)) {
    stop("jb_issue_design: unsettled fixture(s) in issue ", bundle$issue, ": ",
         paste(utils::head(fx$slot[is.na(idx)], 3), collapse = ", "))
  }
  if (any(fx$handicap != lb$handicap[idx])) {
    stop("jb_issue_design: handicap disagreement for issue ", bundle$issue)
  }
  list(issue = bundle$issue, pv = bundle$pv, outcomes = lb$outcome[idx])
}
