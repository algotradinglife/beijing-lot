library(tibble)
library(dplyr)
library(purrr)

`%||%` <- function(x, y) if (is.null(x)) y else x

# Read-only: no scraping, no writes, no network. Requires r/python_bridge.R.

# Declared column contract for each ledger table. Every column is scalar-typed;
# multi-value fields are explicitly flattened to ";"-joined strings.
collection_ledger_contract <- function() {
  list(
    collectors = c(id = "character", label = "character", state = "character",
      importance = "character", owner_process = "character", source = "character",
      code_entry = "character", enabled_in_plan = "logical", code_exists = "logical",
      store_state = "character", units = "character", foreign_units = "character"),
    units = c(id = "character", unit_kind = "character", state = "character",
      description = "character", unit_dir = "character", scheduled = "logical",
      enabled_by = "character", scheduled_by_timer = "character",
      dangling_wants = "character", in_repo_units = "logical",
      missing_code = "character", unsupported_specifiers = "character"),
    repo_units = c(id = "character", unit_kind = "character", description = "character",
      code_paths = "character"),
    findings = c(severity = "character", code = "character", subject = "character",
      message = "character"),
    stores = c(id = "character", kind = "character", state = "character",
      path = "character", registry = "character", key = "character",
      exists = "logical", entries = "integer", bytes = "numeric",
      mtime_utc = "POSIXct"),
    retirements = c(source = "character", archive = "character",
      archive_sha256 = "character", removed_at_utc = "POSIXct", registry = "character"),
    summary = c(metric = "character", value = "integer"),
    plan = c(path = "character", schema_version = "character",
      updated_at = "character", age_days = "numeric"),
    inputs = c(name = "character", path = "character", available = "logical"),
    evidence = c(input = "character", path = "character", kind = "character",
      digest = "character")
  )
}

collection_ledger_init <- function(type) {
  switch(type,
    character = character(),
    logical = logical(),
    integer = integer(),
    numeric = numeric(),
    POSIXct = as.POSIXct(character(), tz = "UTC"))
}

collection_ledger_na <- function(type) {
  switch(type,
    character = NA_character_,
    logical = NA,
    integer = NA_integer_,
    numeric = NA_real_,
    POSIXct = as.POSIXct(NA_character_, tz = "UTC"))
}

# Strictly parse one ISO-8601 instant, honoring any timezone offset, and
# normalize to UTC. Rejects malformed or partial strings.
collection_ledger_time <- function(value) {
  if (is.null(value) || length(value) == 0L) return(collection_ledger_na("POSIXct"))
  if (!is.character(value) || length(value) != 1L) {
    stop("collection_ledger: timestamp must be one ISO-8601 character string")
  }
  if (is.na(value) || !nzchar(value)) return(collection_ledger_na("POSIXct"))
  if (!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:?[0-9]{2})?$", value)) {
    stop("collection_ledger: unparseable timestamp ", value)
  }
  normalized <- value
  if (grepl("Z$", normalized)) normalized <- sub("Z$", "+0000", normalized)
  else if (grepl("[+-][0-9]{2}:[0-9]{2}$", normalized)) normalized <- sub("([+-][0-9]{2}):([0-9]{2})$", "\\1\\2", normalized)
  else normalized <- paste0(normalized, "+0000")
  parsed <- as.POSIXct(normalized, format = "%Y-%m-%dT%H:%M:%OS%z", tz = "UTC")
  if (is.na(parsed)) stop("collection_ledger: unparseable timestamp ", value)
  parsed
}

# Convert a scalar field to its declared type, rejecting incompatible values.
collection_ledger_scalar <- function(value, type, column) {
  if (is.null(value) || length(value) == 0L) return(collection_ledger_na(type))
  if (type == "character") {
    if (!is.character(value)) stop("collection_ledger: column '", column, "' expected character")
    if (length(value) == 1L) return(value)
    return(paste(value, collapse = "; "))
  }
  if (type == "POSIXct") return(collection_ledger_time(value))
  if (length(value) != 1L) {
    stop("collection_ledger: column '", column, "' (", type, ") received a non-scalar value")
  }
  switch(type,
    logical = {
      if (!is.logical(value)) stop("collection_ledger: column '", column, "' expected logical")
      value
    },
    integer = {
      if (is.na(value)) return(NA_integer_)
      if (is.integer(value)) return(value)
      if (is.double(value) && value == as.integer(value)) return(as.integer(value))
      stop("collection_ledger: column '", column, "' expected an integer")
    },
    numeric = {
      if (is.na(value)) return(NA_real_)
      if (is.double(value) || is.integer(value)) return(as.numeric(value))
      stop("collection_ledger: column '", column, "' expected numeric")
    },
    stop("collection_ledger: unsupported type ", type))
}

# Build typed rows from a list of named lists, validating every declared column.
collection_ledger_rows <- function(items, columns) {
  stopifnot(is.character(columns), !is.null(names(columns)), all(nzchar(names(columns))))
  stopifnot(all(columns %in% c("character", "logical", "integer", "numeric", "POSIXct")))
  empty <- tibble::as_tibble(
    stats::setNames(lapply(columns, collection_ledger_init), names(columns)))
  if (is.null(items) || length(items) == 0L) return(empty)
  rows <- lapply(items, function(item) {
    values <- lapply(names(columns), function(name) {
      collection_ledger_scalar(item[[name]], columns[[name]], name)
    })
    tibble::as_tibble(stats::setNames(values, names(columns)))
  })
  dplyr::bind_rows(rows)
}

# Run the Python master ledger and validate it at the R boundary. ``NULL``
# registry/external defaults resolve to the Python module's declared defaults;
# pass NA or "" to disable an external input explicitly.
collection_ledger_run <- function(project_root, python, plan_path,
                                  unit_dirs = NULL, registry_dir = NULL,
                                  external_data_root = NULL, generated_at = NULL,
                                  repo_root = NULL) {
  stopifnot(dir.exists(project_root), file.exists(python), file.exists(plan_path))
  project_root <- normalizePath(project_root)
  # ``repo_root`` is the tree the plan's code paths are resolved against.
  if (is.null(repo_root)) repo_root <- project_root
  repo_root <- normalizePath(repo_root)
  src_root <- file.path(project_root, "src")
  stopifnot(dir.exists(src_root))
  # Bind reticulate to the project interpreter before touching sys.path.
  reticulate::use_python(file.path(normalizePath(dirname(python)), basename(python)), required = TRUE)
  reticulate::py_run_string(paste0(
    "import sys\n",
    "if ", deparse(src_root), " not in sys.path: sys.path.insert(0, ", deparse(src_root), ")"))
  module <- project_python_module("collection_ledger", src_root, python)

  # Host unit directories only; repository definitions are inventoried separately
  # by the Python module and must never be passed as host evidence.
  if (is.null(unit_dirs)) unit_dirs <- as.list(module$DEFAULT_HOST_UNIT_DIRS)
  registry_arg <- if (is.null(registry_dir)) module$DEFAULT_EXTERNAL_REGISTRY
    else if (identical(registry_dir, NA) || identical(registry_dir, "")) NULL else registry_dir
  external_arg <- if (is.null(external_data_root)) module$DEFAULT_EXTERNAL_DATA_ROOT
    else if (identical(external_data_root, NA) || identical(external_data_root, "")) NULL else external_data_root

  ledger <- module$build_ledger(
    plan_path = normalizePath(plan_path),
    repo_root = repo_root,
    unit_dirs = as.list(unit_dirs),
    registry_dir = registry_arg,
    external_data_root = external_arg,
    generated_at = generated_at)
  contract <- collection_ledger_contract()
  if (!identical(ledger$schema, "beijing_lot_collection_ledger_v1")) {
    stop("unexpected ledger schema: ", ledger$schema)
  }

  objects <- ledger$objects
  # Python collector objects nest store evidence under ``store``; flatten the
  # nested state so the declared ``store_state`` column is populated.
  collector_rows <- lapply(objects$collectors, function(item) {
    store <- item$store
    list(id = item$id, label = item$label, state = item$state, importance = item$importance,
      owner_process = item$owner_process, source = item$source, code_entry = item$code_entry,
      enabled_in_plan = item$enabled_in_plan, code_exists = item$code_exists,
      store_state = if (is.null(store)) NA_character_ else store$state,
      units = item$units, foreign_units = item$foreign_units)
  })
  collectors <- collection_ledger_rows(collector_rows, contract$collectors)
  units <- collection_ledger_rows(objects$units, contract$units)
  repo_units <- collection_ledger_rows(objects$repo_units, contract$repo_units)
  findings <- collection_ledger_rows(ledger$findings, contract$findings)
  stores <- collection_ledger_rows(objects$stores, contract$stores)
  retirements <- collection_ledger_rows(objects$retirements, contract$retirements)

  summary_metrics <- c("collectors", "collectors_running", "units", "units_running",
    "units_not_in_repo", "stores", "external_registries", "retirements",
    "findings", "errors", "warnings", "inputs_unavailable")
  summary <- collection_ledger_rows(
    lapply(summary_metrics, function(name) list(metric = name, value = ledger$summary[[name]])),
    contract$summary)

  plan <- collection_ledger_rows(list(list(
    path = ledger$plan$path, schema_version = ledger$plan$schema_version,
    updated_at = ledger$plan$updated_at, age_days = ledger$plan$age_days)), contract$plan)

  input_names <- names(ledger$inputs)
  inputs <- collection_ledger_rows(
    lapply(input_names, function(name) {
      info <- ledger$inputs[[name]]
      if (is.list(info) && "available" %in% names(info)) {
        list(name = name,
          path = if (is.null(info$path)) NA_character_ else as.character(info$path),
          available = isTRUE(info$available))
      } else if (is.list(info)) {
        paths <- vapply(info, function(x) if (is.null(x$path)) NA_character_ else as.character(x$path), character(1))
        available <- vapply(info, function(x) isTRUE(x$available), logical(1))
        list(name = name, path = paste(paths, collapse = "; "), available = all(available))
      } else {
        list(name = name, path = as.character(info), available = NA)
      }
    }), contract$inputs)

  # Evidence binding is computed by the authoritative Python ledger so both the
  # R table and the JSON report share one bounded observation manifest.
  evidence <- collection_ledger_rows(ledger$evidence, contract$evidence)

  list(
    schema = ledger$schema,
    generated_at = ledger$generated_at,
    states = as.character(unlist(ledger$states)),
    summary = summary,
    plan = plan,
    inputs = inputs,
    evidence = evidence,
    collectors = collectors,
    units = units,
    repo_units = repo_units,
    findings = findings,
    stores = stores,
    retirements = retirements,
    render_text = function() module$render_text(ledger))
}

# Print the operator-facing text view produced by the same ledger object.
collection_ledger_text <- function(report) cat(report$render_text(), sep = "\n")
