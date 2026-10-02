#' Initialize the bundled Python backend explicitly
#'
#' Python dependencies must already be installed in the selected interpreter.
#' Loading beidan alone never initializes Python. An already initialized different
#' interpreter or backend location is an error; no packages are installed here.
#' @param python Existing absolute path to the Python executable.
#' @return A backend handle containing the imported module and interpreter identity.
#' @export
python_backend <- function(python) {
  checkmate::assert_string(python, na.ok = FALSE, min.chars = 1)
  checkmate::assert_file_exists(python)
  python <- file.path(normalizePath(dirname(python), mustWork = TRUE), basename(python))
  if (reticulate::py_available(initialize = FALSE)) {
    active_path <- reticulate::py_config()$python
    active <- file.path(normalizePath(dirname(active_path), mustWork = TRUE), basename(active_path))
    if (!identical(active, python)) stop("Python already initialized with another interpreter")
  }
  reticulate::use_python(python, required = TRUE)
  active_path <- reticulate::py_config()$python
  active <- file.path(normalizePath(dirname(active_path), mustWork = TRUE), basename(active_path))
  if (!identical(active, python)) stop("Python initialized with another interpreter")
  root <- system.file("python", package = "beidan", mustWork = TRUE)
  module <- reticulate::import_from_path("beidan_backend", path = root, convert = FALSE)
  actual <- normalizePath(reticulate::py_to_r(module$`__file__`), mustWork = TRUE)
  expected <- normalizePath(file.path(root, "beidan_backend", "__init__.py"), mustWork = TRUE)
  if (!identical(actual, expected)) stop("Python backend was loaded from another package location")
  temporal <- reticulate::import("beidan_backend.temporal_learning", convert = FALSE)
  return(structure(list(module = temporal, python = python, root = root), class = "python_backend"))
}

#' Create a decision cutoff using the authoritative Python implementation
#'
#' No fitting, fetching or persistence occurs. The returned Python object can be
#' passed to the shared learning functions through the backend handle.
#' @param issue_id Nonempty character issue identifier; leading zeros are preserved.
#' @param cutoff_utc One nonmissing UTC POSIXct timestamp.
#' @param backend Handle returned by [python_backend()].
#' @return An immutable Python Cutoff object with decision-epoch identity.
#' @export
learning_cutoff <- function(issue_id, cutoff_utc, backend) {
  checkmate::assert_string(issue_id, na.ok = FALSE, min.chars = 1)
  if (!inherits(backend, "python_backend")) stop("backend must be an python_backend")
  if (!inherits(cutoff_utc, "POSIXct") || length(cutoff_utc) != 1L ||
      is.na(cutoff_utc) || !identical(attr(cutoff_utc, "tzone"), "UTC")) {
    stop("cutoff_utc must be one nonmissing UTC POSIXct timestamp")
  }
  instant <- format(cutoff_utc, "%Y-%m-%dT%H:%M:%OS6Z", tz = "UTC")
  return(backend$module$Cutoff$decision_epoch(issue_id, instant))
}

#' Convert a contracted R table for Python
#'
#' Only named columns carry identity; R vector names and pandas row indexes
#' are not part of these table contracts. Validation precedes conversion. Identifiers must already be character and
#' timestamps must satisfy the named schema; no implicit reparsing is performed.
#' @param data Tibble satisfying the named beidan table schema.
#' @param table Character schema name from match_table_schemas().
#' @param backend Explicit initialized handle from python_backend().
#' @return A Python pandas DataFrame. Missing values and typed empty columns remain explicit.
#' @export
python_table <- function(data, table, backend) {
  if (!inherits(backend, "python_backend")) stop("backend must be an python_backend")
  match_validate_table(data, table)
  result <- reticulate::r_to_py(as.data.frame(data), convert = FALSE)
  pandas <- reticulate::import("pandas", convert = FALSE)
  schema <- match_table_schemas()[[table]]
  # pandas nullable dtypes preserve R NA instead of integer sentinels or FALSE.
  for (column in names(schema$types)[schema$types %in% c("integer", "logical")]) {
    values <- lapply(data[[column]], function(value) if (is.na(value)) NULL else value)
    dtype <- if (schema$types[[column]] == "integer") "Int32" else "boolean"
    result$`__setitem__`(column, pandas$array(values, dtype = dtype))
  }
  for (column in names(schema$types)[schema$types == "POSIXct"]) {
    result$`__setitem__`(column, pandas$to_datetime(
      as.numeric(data[[column]]), unit = "s", utc = TRUE))
  }
  return(result)
}

#' Convert a Python table to a validated tibble
#'
#' Conversion errors and schema mismatches stop the call; they never become
#' empty tables or missing values. The Python object must be a pandas DataFrame.
#' @param data Python pandas DataFrame with the named schema.
#' @param table Character schema name from match_table_schemas().
#' @return A validated tibble, including typed empty tables.
#' @export
r_table <- function(data, table) {
  if (!inherits(data, "python.builtin.object")) stop("data must be a Python pandas DataFrame")
  pandas <- reticulate::import("pandas", convert = FALSE)
  builtins <- reticulate::import_builtins(convert = FALSE)
  if (!isTRUE(reticulate::py_to_r(builtins$isinstance(data, pandas$DataFrame)))) {
    stop("data must be a Python pandas DataFrame")
  }
  schema <- match_table_schemas()[[table]]
  if (is.null(schema)) stop("Unknown table schema")
  for (column in names(schema$types)[schema$types == "integer"]) {
    series <- data$`__getitem__`(column)
    if (!isTRUE(reticulate::py_to_r(pandas$api$types$is_integer_dtype(series$dtype)))) {
      stop("Python integer column has non-integer dtype: ", column)
    }
    present <- series$dropna()
    if (!isTRUE(reticulate::py_to_r(present$ge(-.Machine$integer.max)$all())) ||
        !isTRUE(reticulate::py_to_r(present$le(.Machine$integer.max)$all()))) {
      stop("Python integer column exceeds the R integer range: ", column)
    }
  }
  times <- names(schema$types)[schema$types == "POSIXct"]
  for (column in times) {
    zone <- data$`__getitem__`(column)$dt$tz
    if (is.null(reticulate::py_to_r(zone))) stop("Python timestamp must have a timezone: ", column)
  }
  # pandas 3 Arrow strings are not converted by every supported reticulate build.
  # Object dtype preserves values without stringifying invalid numeric IDs.
  strings <- names(schema$types)[schema$types == "character"]
  if (length(strings)) {
    types <- stats::setNames(as.list(rep("object", length(strings))), strings)
    data <- data$astype(types)
  }
  data <- data$copy()
  nullable <- names(schema$types)[schema$types %in% c("integer", "logical")]
  missing <- stats::setNames(vector("list", length(nullable)), nullable)
  for (column in nullable) {
    series <- data$`__getitem__`(column)
    missing[[column]] <- reticulate::py_to_r(series$isna()$to_numpy())
    if (schema$types[[column]] == "logical" &&
        !isTRUE(reticulate::py_to_r(pandas$api$types$is_bool_dtype(series$dtype)))) {
      stop("Python logical column has non-boolean dtype: ", column)
    }
    fill <- if (schema$types[[column]] == "integer") 0L else FALSE
    dtype <- if (schema$types[[column]] == "integer") "int32" else "bool"
    data$`__setitem__`(column, series$fillna(fill)$astype(dtype))
  }
  converted <- reticulate::py_to_r(data)
  result <- tibble::as_tibble(converted)
  for (column in nullable) result[[column]][missing[[column]]] <- NA
  attr(result, "pandas.index") <- NULL
  for (column in times) result[[column]] <- lubridate::with_tz(result[[column]], "UTC")
  match_validate_table(result, table)
  return(result)
}
