#' Estimate venue goal means from explicit long and recent distributions
#' @param history Tibble of fixture history with source match identities and scores.
#' @param fixture Named list with fixture/issue/provider and home/away team IDs.
#' @param target_native_ids Character vector of the complete target roster IDs.
#' @param cutoff Shared temporal_learning Cutoff object; required, never inferred.
#' @param source_hashes Named source SHA256 list.
#' @param repository_root Explicit repository path containing the project interpreter.
#' @param policy List: integer recent_n/minimum_matches, numeric alpha/minimum_ess.
#' @return List with parameter/rate tibbles, empirical components and shared receipts.
#' @details Historical diagnostic only. Empty/malformed/sparse history fails.
#' No fetching, persistence, market fitting or implicit environment selection.
estimate_recent_venue_goals <- function(history, fixture, target_native_ids,
                                       cutoff, source_hashes, repository_root, policy) {
  if (!tibble::is_tibble(history) || !nrow(history) || !is.list(fixture) ||
      !is.character(target_native_ids) || !is.list(source_hashes) ||
      !is.list(policy) || !inherits(cutoff, "python.builtin.object")) {
    stop("Explicit typed history, fixture, policy and shared cutoff required")
  }
  root <- normalizePath(repository_root, mustWork = TRUE)
  reticulate::use_python(file.path(root, ".venv/bin/python"), required = TRUE)
  sys <- reticulate::import("sys", convert = FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(sys$prefix)),
                 normalizePath(file.path(root, ".venv")))) stop("Project Python required")
  sys$path$insert(0L, file.path(root, "packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.recent_venue_goals", convert = FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(backend$`__file__`)),
                 file.path(root, "packages/beidan/inst/python/beidan_backend/recent_venue_goals.py"))) {
    stop("Backend path differs")
  }
  rows <- jsonlite::fromJSON(jsonlite::toJSON(history, dataframe = "rows",
    auto_unbox = TRUE, na = "null"), simplifyVector = FALSE)
  value <- reticulate::py_to_r(backend$estimate_recent_venue_goals(rows, fixture,
    as.list(target_native_ids), cutoff, source_hashes, root, policy))
  value$parameters <- tibble::as_tibble(value$parameters)
  value$rates <- dplyr::bind_rows(value$rates)
  stopifnot(nrow(value$parameters) == 1L, nrow(value$rates) == 2L,
            all(is.finite(unlist(value$parameters))), !anyNA(value$rates))
  value
}
