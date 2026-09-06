# #408 executable QMD interface. Python performs acquisition replay and audit;
# R validates the frozen release and presents tidy analysis tables.

# Run the Python #408 pipeline through reticulate.
# bundle_dir: sealed #407 bundle containing raw_main/raw_regression and audits.
# output_dir: new immutable release directory; existing paths fail closed.
# generated_at_utc: timezone-aware generation timestamp.
# release_id: stable release identifier.
# python: explicit project interpreter selected before Python initialization.
# module_dir: explicit directory containing fundamentals_pipeline.py.
# Returns the converted Python receipt as an R list.
run_fundamentals_pipeline <- function(bundle_dir, output_dir, generated_at_utc, release_id, python, module_dir) {
  values <- list(bundle_dir, output_dir, generated_at_utc, release_id, python, module_dir)
  valid_text <- vapply(values, function(value) {
    is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)
  }, logical(1))
  if (!all(valid_text) || !dir.exists(bundle_dir) || !file.exists(python) ||
      !file.exists(file.path(module_dir, "fundamentals_pipeline.py"))) {
    stop("Declare an existing bundle_dir, module_dir, explicit Python interpreter and non-empty release parameters")
  }
  python_path <- file.path(normalizePath(dirname(python)), basename(python))
  environment_python <- Sys.getenv("RETICULATE_PYTHON", unset = "")
  if (nzchar(environment_python)) {
    environment_path <- file.path(normalizePath(dirname(environment_python), mustWork = FALSE), basename(environment_python))
    if (!identical(environment_path, python_path)) stop("RETICULATE_PYTHON conflicts with the explicit Python interpreter")
  }
  if (!reticulate::py_available(initialize = FALSE)) {
    reticulate::use_python(python_path, required = TRUE)
  }
  configured_python <- reticulate::py_config()$python
  configured <- file.path(normalizePath(dirname(configured_python)), basename(configured_python))
  if (!identical(configured, python_path)) stop("reticulate initialized with a different Python interpreter")
  module <- reticulate::import_from_path(
    "src.fundamentals_pipeline", path = dirname(normalizePath(module_dir)), convert = TRUE)
  module$run_pipeline(bundle_dir, output_dir,
    generated_at_utc = generated_at_utc, release_id = release_id)
}

# Validate and read a frozen #408 release into typed R tibbles.
# Missing strings remain NA, while identifiers retain leading zeros and numeric
# zero remains integer zero. Returns receipt plus five observational-unit tables.
read_fundamentals_pipeline_release <- function(output_dir) {
  receipt <- jsonlite::read_json(file.path(output_dir, "receipt.json"), simplifyVector = TRUE)
  if (!identical(receipt$schema, "bj408_fundamentals_audit_v1") ||
      !identical(receipt$historical_learning, "NONE")) stop("Unsupported #408 release contract")
  required <- paste0(c("canonical_identity", "discrepancy_queue", "adjudications", "facts", "quarantine"), ".csv")
  if (!all(required %in% names(receipt$output_hashes))) stop("Missing #408 output hashes")
  root <- normalizePath(output_dir)
  for (name in names(receipt$output_hashes)) {
    path <- normalizePath(file.path(root, name), mustWork = TRUE)
    if (!startsWith(path, paste0(root, .Platform$file.sep))) stop("Unsafe #408 output path")
    actual <- digest::digest(file = path, algo = "sha256", serialize = FALSE)
    if (!identical(actual, receipt$output_hashes[[name]])) stop("#408 output hash mismatch: ", name)
  }
  tables <- lapply(sub("\\.csv$", "", required), function(name) {
    table <- readr::read_csv(file.path(root, paste0(name, ".csv")),
      col_types = readr::cols(.default = readr::col_character()), na = "", show_col_types = FALSE)
    if (nrow(readr::problems(table))) stop("#408 CSV parsing failure: ", name)
    integer_columns <- intersect(c("slot", "revision", "source_count"), names(table))
    for (column in integer_columns) {
      parsed <- suppressWarnings(readr::parse_integer(table[[column]]))
      if (nrow(readr::problems(parsed))) stop("#408 integer parsing failure: ", name, ".", column)
      table[[column]] <- parsed
    }
    if ("reviewed_at_utc" %in% names(table)) {
      parsed <- suppressWarnings(readr::parse_datetime(table$reviewed_at_utc, locale = readr::locale(tz = "UTC")))
      if (any(is.na(parsed) & !is.na(table$reviewed_at_utc))) stop("#408 UTC parsing failure")
      table$reviewed_at_utc <- parsed
    }
    tibble::as_tibble(table)
  })
  names(tables) <- sub("\\.csv$", "", required)
  identity_key <- dplyr::count(tables$canonical_identity, scope, issue, slot, provider_id)
  if (any(identity_key$n != 1L)) stop("Duplicate canonical identity decision")
  quarantine_fixtures <- dplyr::filter(tables$canonical_identity, identity_status == "QUARANTINED")
  if (nrow(quarantine_fixtures)) {
    leaked <- dplyr::inner_join(tables$facts, quarantine_fixtures,
      by = c("scope", "issue", "slot", "provider_id"))
    if (nrow(leaked)) stop("Quarantined fixture leaked into facts")
  }
  c(list(receipt = receipt), tables)
}

# Return tidy release counts for the QMD overview.
summarize_fundamentals_pipeline <- function(release) {
  tibble::tibble(
    measure = c("identity decisions", "discrepancies", "adjudications", "facts", "quarantine rows"),
    rows = c(nrow(release$canonical_identity), nrow(release$discrepancy_queue),
             nrow(release$adjudications), nrow(release$facts), nrow(release$quarantine)))
}

# Extract independently captured evidence URLs from adjudication JSON.
fundamentals_evidence_links <- function(adjudications) {
  if (!nrow(adjudications)) {
    return(dplyr::mutate(adjudications, target_fields = character(), evidence_urls = character()))
  }
  targets <- lapply(adjudications$targets_json, function(value) {
    items <- jsonlite::fromJSON(value, simplifyVector = FALSE)
    paste(vapply(items, function(item) item$field, character(1)), collapse = " | ")
  })
  links <- lapply(adjudications$evidence_json, function(value) {
    evidence <- jsonlite::fromJSON(value, simplifyVector = FALSE)
    paste(vapply(evidence, function(item) item$url, character(1)), collapse = " | ")
  })
  dplyr::mutate(adjudications,
    target_fields = unlist(targets, use.names = FALSE),
    evidence_urls = unlist(links, use.names = FALSE))
}
