# Issue #501 incremental QMD engineering MVP: R side of a synthetic
# fixture-level squared-error diagnostic.
#
# Scope is deliberately narrow. These functions do not learn from history,
# select models, predict, or size bets; they validate a small tabular contract,
# hand validated values to the Python `squared_errors` function, and aggregate
# the result. No function writes files or touches a database except `mvp_read`,
# which only reads the CSV path it is given.

# Columns and types required by the #501 MVP fixture/probability contract.
MVP_COLUMNS <- c("fixture_id", "league", "predicted", "observed")

# Validate the MVP table contract and return the input unchanged.
#
# Row meaning: one row per fixture with a predicted home-win-style probability
# and an observed 0/1 label (NA for a not-yet-known label).
# Columns: fixture_id character (unique, nonempty, leading zeros preserved),
# league character (nonempty, nonmissing), predicted double in [0, 1],
# observed double exactly 0 or 1 or NA_real_.
# Units: probabilities are dimensionless shares in [0, 1].
# Missing values: only `observed` may be NA; an all-missing or partly-missing
# label column is valid and must stay distinguishable from a zero error.
# Errors: malformed input (wrong class, missing/extra columns, wrong column
# type) and invalid values (duplicate/empty IDs, NaN/Inf, out-of-range
# probabilities, non-binary labels) stop with a descriptive error.
# Side effects: none.
# Empty input: a correctly typed zero-row tibble is accepted and returned.
mvp_validate <- function(x) {
  if (!tibble::is_tibble(x)) stop("mvp_validate: x must be a tibble")
  if (!identical(names(x), MVP_COLUMNS)) {
    stop("mvp_validate: columns must be exactly fixture_id, league, predicted, observed")
  }
  if (any(vapply(x, is.object, logical(1))) ||
      any(vapply(x, function(column) !is.null(dim(column)), logical(1)))) {
    stop("mvp_validate: columns must be plain vectors without classes or dimensions")
  }
  if (!is.character(x$fixture_id)) stop("mvp_validate: fixture_id must be character")
  if (!is.character(x$league)) stop("mvp_validate: league must be character")
  if (!is.double(x$predicted)) stop("mvp_validate: predicted must be double")
  if (!is.double(x$observed)) stop("mvp_validate: observed must be double")

  if (anyNA(x$fixture_id)) stop("mvp_validate: fixture_id must not be missing")
  if (any(!nzchar(x$fixture_id))) stop("mvp_validate: fixture_id must be nonempty")
  if (anyDuplicated(x$fixture_id)) stop("mvp_validate: fixture_id must be unique")

  if (anyNA(x$league)) stop("mvp_validate: league must not be missing")
  if (any(!nzchar(x$league))) stop("mvp_validate: league must be nonempty")

  if (any(is.nan(x$predicted))) stop("mvp_validate: predicted must not be NaN")
  if (anyNA(x$predicted)) stop("mvp_validate: predicted must not be missing")
  if (any(!is.finite(x$predicted))) stop("mvp_validate: predicted must be finite")
  if (any(x$predicted < 0 | x$predicted > 1)) {
    stop("mvp_validate: predicted must be within [0, 1]")
  }

  observed_known <- !is.na(x$observed)
  if (any(is.nan(x$observed))) stop("mvp_validate: observed must not be NaN")
  if (any(observed_known & !is.finite(x$observed))) stop("mvp_validate: observed must be finite")
  if (any(observed_known & !(x$observed %in% c(0, 1)))) {
    stop("mvp_validate: observed must be 0, 1, or NA")
  }
  x
}

# Read an MVP CSV with explicit column types and validate it.
#
# Inputs: `path` is a single existing CSV path.
# Returns: a validated tibble with the MVP schema (see `mvp_validate`).
# Missing values: only the literal token `NA` is missing. Empty fields are not
# accepted as missing; in a text column a blank is the empty string (rejected as
# nonempty by `mvp_validate`) and in a numeric column a blank is a parse problem
# that stops the read. A malformed field is therefore never silently turned into
# a missing value.
# Errors: a missing file, any readr parse problem (reported with row/column and
# the actual token), or a contract violation stops.
# Side effects: reads the file only.
mvp_read <- function(path) {
  if (!is.character(path) || length(path) != 1L || is.na(path) || !nzchar(path)) {
    stop("mvp_read: path must be one nonempty string")
  }
  if (!file.exists(path)) stop("mvp_read: file does not exist: ", path)
  x <- readr::read_csv(
    path,
    col_types = readr::cols(
      fixture_id = readr::col_character(),
      league = readr::col_character(),
      predicted = readr::col_double(),
      observed = readr::col_double()
    ),
    na = "NA",
    progress = FALSE
  )
  # readr records malformed input in `problems()` instead of failing; promote
  # every problem to a fatal error so a parse failure cannot masquerade as NA.
  problems <- readr::problems(x)
  if (nrow(problems)) {
    detail <- paste0(
      "row ", problems$row, ", column ", problems$col,
      " (", problems$expected, "), got ", encodeString(problems$actual, quote = '"')
    )
    stop("mvp_read: CSV parse problems: ", paste(detail, collapse = "; "))
  }
  mvp_validate(x)
}

# Score validated fixtures with the Python `squared_errors` implementation.
#
# Inputs: `x` is a validated MVP tibble (validated here as a boundary check);
# `python` is the explicit interpreter path; `project_root` is the project root
# holding `src/`; `source_files` is the explicit list of existing dependency
# files that the bridge needs (the Python module and the R bridge helper).
# Returns: a validated tibble with fixture_id character, league character, and
# squared_error double (NA when the label is missing). Row order follows `x`.
# Missing values: NA labels are converted to Python None intentionally so a
# missing label yields NA, never a zero error. The returned missing pattern must
# match the observed NA pattern exactly; a mismatch stops.
# Errors: bad interpreter/project paths, missing source files, a Python result
# whose records, IDs, row count, field set, missing pattern, or score types and
# values disagree with the input stop. Scores are never coerced from strings.
# Side effects: imports the Python module; no scraping or database writes.
mvp_errors <- function(x, python, project_root, source_files) {
  x <- mvp_validate(x)
  if (!is.character(python) || length(python) != 1L || is.na(python) || !file.exists(python)) {
    stop("mvp_errors: python must be one existing interpreter path")
  }
  if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root) ||
      !dir.exists(project_root)) {
    stop("mvp_errors: project_root must be one existing directory")
  }
  if (!is.character(source_files) || !length(source_files) || anyNA(source_files) ||
      !all(nzchar(source_files))) {
    stop("mvp_errors: source_files must be nonempty existing file paths")
  }
  missing_sources <- source_files[!file.exists(source_files)]
  if (length(missing_sources)) {
    stop("mvp_errors: missing source files: ", paste(missing_sources, collapse = ", "))
  }
  # Callers source r/python_bridge.R (see snapshots.R); the import is a visible
  # top-level dependency, not hidden inside this function.
  if (!exists("project_python_module", mode = "function")) {
    stop("mvp_errors: source r/python_bridge.R before calling")
  }

  # NA -> None keeps a missing label missing across the language boundary.
  observed <- lapply(x$observed, function(value) if (is.na(value)) NULL else value)
  module <- project_python_module("src.qmd_incremental_mvp", project_root, python)
  result <- module$squared_errors(
    as.list(x$fixture_id),
    as.list(x$predicted),
    observed
  )

  if (length(result) != nrow(x)) {
    stop("mvp_errors: Python returned ", length(result), " rows for ", nrow(x), " inputs")
  }

  # Each record must expose exactly the two contracted fields; a missing or
  # extra field is a broken result contract, not something to coerce around.
  is_record <- vapply(result, is.list, logical(1))
  if (!all(is_record)) {
    stop("mvp_errors: Python rows must be records with fixture_id and squared_error")
  }
  record_fields <- lapply(result, names)
  bad_fields <- which(!vapply(record_fields, function(fields) {
    identical(fields, c("fixture_id", "squared_error"))
  }, logical(1)))
  if (length(bad_fields)) {
    stop(
      "mvp_errors: Python row ", bad_fields[[1L]], " fields must be exactly ",
      "fixture_id and squared_error, got ",
      paste(record_fields[[bad_fields[[1L]]]], collapse = ", ")
    )
  }

  result_ids <- vapply(result, function(row) row$fixture_id, character(1))
  if (!identical(result_ids, x$fixture_id)) {
    stop("mvp_errors: Python fixture_ids do not match the input order")
  }
  # The label contract requires the record to be missing exactly when the
  # input label is NA: a missing input with a returned score, or a known input
  # with a returned NULL, both break the contract.
  result_missing <- vapply(result, function(row) is.null(row$squared_error), logical(1))
  if (!identical(result_missing, is.na(x$observed))) {
    stop("mvp_errors: Python missing-value pattern does not match the observed NA pattern")
  }

  scores <- vapply(result, function(row) {
    if (is.null(row$squared_error)) {
      return(NA_real_)
    }
    value <- row$squared_error
    # Reject string/logical/list scores rather than coercing them to numbers.
    if (!is.double(value) || is.object(value) || !is.null(dim(value)) || length(value) != 1L) {
      stop(
        "mvp_errors: squared_error must be a single number (double) or NULL, got ",
        class(value)[[1L]]
      )
    }
    value
  }, numeric(1))
  known <- !is.na(scores)
  if (any(is.nan(scores))) stop("mvp_errors: squared_error must not be NaN")
  if (!identical(is.na(scores), is.na(x$observed))) {
    stop("mvp_errors: numeric missing score cannot replace a known label")
  }
  if (any(known & !is.finite(scores))) stop("mvp_errors: squared_error must be finite")
  if (any(known & (scores < 0 | scores > 1))) {
    stop("mvp_errors: squared_error must be within [0, 1]")
  }

  out <- tibble::tibble(
    fixture_id = x$fixture_id,
    league = x$league,
    squared_error = scores
  )
  out
}

# Aggregate validated squared errors per league.
#
# Inputs: `errors` is a validated error tibble (fixture_id character, league
# character, squared_error double in [0, 1] or NA).
# Returns: one row per league, sorted by league, with n_total integer,
# n_scored integer, n_missing integer, and mean_error double.
# Missing values: `mean_error` averages only scored rows; a league with no
# scored rows gets NA_real_ and never a fabricated zero.
# Errors: schema/type violations, duplicate IDs, empty leagues, NaN, or
# out-of-range scores stop.
# Side effects: none. Empty input: returns a typed zero-row tibble.
mvp_summary <- function(errors) {
  expected <- c("fixture_id", "league", "squared_error")
  if (!tibble::is_tibble(errors) || !identical(names(errors), expected)) {
    stop("mvp_summary: errors must be a tibble with fixture_id, league, squared_error")
  }
  if (any(vapply(errors, is.object, logical(1))) ||
      any(vapply(errors, function(column) !is.null(dim(column)), logical(1)))) {
    stop("mvp_summary: columns must be plain vectors without classes or dimensions")
  }
  if (!is.character(errors$fixture_id)) stop("mvp_summary: fixture_id must be character")
  if (!is.character(errors$league)) stop("mvp_summary: league must be character")
  if (!is.double(errors$squared_error)) stop("mvp_summary: squared_error must be double")
  if (anyNA(errors$fixture_id)) stop("mvp_summary: fixture_id must not be missing")
  if (any(!nzchar(errors$fixture_id))) stop("mvp_summary: fixture_id must be nonempty")
  if (anyDuplicated(errors$fixture_id)) stop("mvp_summary: fixture_id must be unique")
  if (anyNA(errors$league)) stop("mvp_summary: league must not be missing")
  if (any(!nzchar(errors$league))) stop("mvp_summary: league must be nonempty")
  if (any(is.nan(errors$squared_error))) stop("mvp_summary: squared_error must not be NaN")
  known <- !is.na(errors$squared_error)
  if (any(known & !is.finite(errors$squared_error))) {
    stop("mvp_summary: squared_error must be finite")
  }
  if (any(known & (errors$squared_error < 0 | errors$squared_error > 1))) {
    stop("mvp_summary: squared_error must be within [0, 1]")
  }

  summary <- errors |>
    dplyr::group_by(league) |>
    dplyr::summarise(
      n_total = dplyr::n(),
      n_scored = sum(!is.na(squared_error)),
      n_missing = sum(is.na(squared_error)),
      mean_error = mean(squared_error, na.rm = TRUE),
      .groups = "drop"
    ) |>
    dplyr::mutate(
      n_total = as.integer(n_total),
      n_scored = as.integer(n_scored),
      n_missing = as.integer(n_missing),
      mean_error = as.numeric(mean_error)
    )
  # Deterministic C-locale byte order; `arrange` would depend on the session
  # collation, which is hidden mutable session state.
  summary <- summary[order(summary$league, method = "radix"), , drop = FALSE]
  # mean() over an all-missing group is NaN; the contract requires NA_real_ so a
  # missing league stays missing rather than becoming an arithmetic artifact.
  summary$mean_error[is.nan(summary$mean_error)] <- NA_real_

  if (!nrow(summary)) {
    return(tibble::tibble(
      league = character(0),
      n_total = integer(0),
      n_scored = integer(0),
      n_missing = integer(0),
      mean_error = double(0)
    ))
  }
  summary
}
