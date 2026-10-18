# Explicit setup for repository verification. No installation or network access.
# root: repository directory; returns a one-row runtime receipt tibble.
# Missing roots, conflicting interpreters and a shadowed package fail before tests.
verification_environment <- function(root) {
  root <- normalizePath(root, mustWork = TRUE)
  verification_repository_roots(root, Sys.getenv())
  python <- Sys.getenv("BEIDAN_TEST_PYTHON")
  other <- Sys.getenv("RETICULATE_PYTHON")
  if (!nzchar(python)) python <- other
  if (!nzchar(python)) python <- file.path(root, ".venv", "bin", "python")
  if (nzchar(other) && !identical(other, python)) {
    stop("BEIDAN_TEST_PYTHON and RETICULATE_PYTHON disagree", call. = FALSE)
  }
  if (!file.exists(python) || file.access(python, 1L) != 0L) {
    stop("Project Python is missing or not executable: ", python, call. = FALSE)
  }
  # Preserve the venv path: resolving its symlink selects the system interpreter.
  Sys.setenv(BEIDAN_TEST_PYTHON = python, RETICULATE_PYTHON = python)
  roots <- Sys.getenv(c("BEIDAN_HOT_ROOT", "BEIDAN_PARQUET_ROOT"))
  if (any(!nzchar(roots)) || any(!dir.exists(roots))) {
    stop("Data roots must be configured and mounted before verification", call. = FALSE)
  }
  libs <- strsplit(Sys.getenv("R_LIBS_USER"), .Platform$path.sep, fixed = TRUE)[[1L]]
  if (!length(libs) || any(!nzchar(libs)) || any(!dir.exists(libs))) {
    stop("R_LIBS_USER must explicitly list existing verification/dependency libraries",
         call. = FALSE)
  }
  .libPaths(c(libs, .libPaths()))
  package <- find.package("beidan", quiet = TRUE)
  expected <- file.path(libs[[1L]], "beidan")
  if (!length(package) || !dir.exists(expected) ||
      normalizePath(package) != normalizePath(expected)) {
    stop("First R_LIBS_USER library must contain the intended installed beidan package",
         call. = FALSE)
  }
  for (dependency in c("testthat", "tibble", "rprojroot", "jsonlite")) {
    if (!requireNamespace(dependency, quietly = TRUE)) {
      stop("Missing verification dependency: ", dependency, call. = FALSE)
    }
  }
  beidan::python_backend(python)
  tibble::tibble(python = python, package = normalizePath(package),
    hot_root = unname(roots[[1L]]), parquet_root = unname(roots[[2L]]),
    r_version = as.character(getRversion()))
}

# Explicit aliases used by repository diagnostic tests. Returns bindings without
# mutating the environment; a supplied different checkout is rejected up front.
verification_repository_roots <- function(root, environ) {
  root <- normalizePath(root, mustWork = TRUE)
  variables <- c("BEIDAN_REPOSITORY_ROOT", "BEIDAN_REPO_ROOT",
    "OVERLAP6_REPOSITORY_ROOT", "OVERLAP6_TRIPLE433_REPOSITORY_ROOT",
    "OVERLAP6_VARIANTS_REPOSITORY_ROOT", "OVERLAP6_WINDOW_REPOSITORY_ROOT",
    "TRIPLE433_REPOSITORY_ROOT", "UNCOVERED_RANKS_REPOSITORY_ROOT",
    "BEIDAN_SCENARIO_ROOT", "FM16_BACKTEST_ROOT", "FM17_BACKTEST_ROOT",
    "FM17_DIAG_ROOT", "FM17_MARKET_ROOT", "FM17_OPPONENT_ROOT", "FM17_RELEASE_ROOT",
    "FM_CASE4_ADJUST_ROOT", "FM_CASE4_AH_ROOT", "FM_CASE4_RATIO_ROOT",
    "FM_CASE4_TAIL_ROOT", "FM_LINE_REVIEW_ROOT", "FM_MARGIN_TOP3_ROOT",
    "FM_NATIVE_TEST_ROOT", "FM_TAILR_POLICY_ROOT")
  supplied <- environ[intersect(names(environ), variables)]
  supplied <- supplied[!is.na(supplied) & nzchar(supplied)]
  if (length(supplied) && any(normalizePath(supplied, mustWork = FALSE) != root)) {
    stop("repository root mismatch in verification environment", call. = FALSE)
  }
  stats::setNames(as.list(rep(root, length(variables))), variables)
}
