library(testthat)

ledger_repo_root <- function() {
  rprojroot::find_root(rprojroot::has_file("config/data_collection_plan.json"))
}

write_ledger_file <- function(path, text) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  writeLines(text, path)
  path
}

# A deterministic fixture: one collector whose code exists inside the fixture
# repository and whose store is a real fixture file.
write_ledger_fixture <- function(folder) {
  repo <- file.path(folder, "repo")
  dir.create(file.path(repo, "scripts"), recursive = TRUE, showWarnings = FALSE)
  write_ledger_file(file.path(repo, "scripts/demo_scrape.py"), "# fixture")
  write_ledger_file(file.path(repo, "data/demo.sqlite"), "fixture")
  plan <- list(
    schema_version = "data_collection_plan_v1",
    updated_at = "2026-10-01",
    collectors = list(list(
      collector_id = "demo", label = "demo", importance = "critical", enabled = TRUE,
      owner_process = "demo_refresh", source = "example.com",
      code_entry = "scripts/demo_scrape.py", database = "data/demo.sqlite",
      tables = list("demo"), schedule_interval_sec = 900,
      stale_after_sec = 1200, coverage_check = "matches_sp")))
  write_ledger_file(file.path(repo, "config/data_collection_plan.json"),
    jsonlite::toJSON(plan, auto_unbox = TRUE))
  repo
}

test_that("collection_ledger_rows returns a typed empty tibble for every type", {
  source(file.path(ledger_repo_root(), "r/collection_ledger.R"))
  columns <- c(a = "character", b = "logical", c = "integer", d = "numeric", e = "POSIXct")
  empty <- collection_ledger_rows(NULL, columns)
  expect_identical(nrow(empty), 0L)
  expect_identical(names(empty), c("a", "b", "c", "d", "e"))
  expect_type(empty$a, "character")
  expect_type(empty$b, "logical")
  expect_type(empty$c, "integer")
  expect_type(empty$d, "double")
  expect_s3_class(empty$e, "POSIXct")
})

test_that("collection_ledger_rows validates scalar types and joins multi-value text", {
  source(file.path(ledger_repo_root(), "r/collection_ledger.R"))
  rows <- collection_ledger_rows(
    list(list(id = "a", flag = TRUE, count = 3L, tags = c("x", "y"), when = "2026-10-04T00:00:00")),
    c(id = "character", flag = "logical", count = "integer", tags = "character", when = "POSIXct"))
  expect_identical(rows$flag, TRUE)
  expect_identical(rows$count, 3L)
  expect_identical(rows$tags, "x; y")
  expect_s3_class(rows$when, "POSIXct")
  expect_identical(format(rows$when, "%Y-%m-%d", tz = "UTC"), "2026-10-04")
})

test_that("collection_ledger_rows rejects incompatible source types", {
  source(file.path(ledger_repo_root(), "r/collection_ledger.R"))
  expect_error(collection_ledger_rows(list(list(n = "3")), c(n = "integer")), "integer")
  expect_error(collection_ledger_rows(list(list(n = 1.5)), c(n = "integer")), "integer")
  expect_error(collection_ledger_rows(list(list(x = TRUE)), c(x = "numeric")), "numeric")
  expect_error(collection_ledger_rows(list(list(id = 42)), c(id = "character")), "character")
  expect_error(collection_ledger_rows(list(list(f = "yes")), c(f = "logical")), "logical")
  # Numeric double -> integer is accepted only when exact.
  expect_identical(collection_ledger_rows(list(list(n = 3.0)), c(n = "integer"))$n, 3L)
})

test_that("collection_ledger_time honors timezone offsets and rejects malformed input", {
  source(file.path(ledger_repo_root(), "r/collection_ledger.R"))
  instant <- collection_ledger_time("2026-10-04T08:00:00+08:00")
  expect_identical(format(instant, "%Y-%m-%dT%H:%M:%S", tz = "UTC"), "2026-10-04T00:00:00")
  expect_identical(format(collection_ledger_time("2026-10-04T00:00:00Z"), "%H:%M", tz = "UTC"), "00:00")
  expect_true(is.na(collection_ledger_time(NA_character_)))
  expect_error(collection_ledger_time("not-a-time"), "unparseable")
  expect_error(collection_ledger_time("2026-10-04T00:00:00+08:00junk"), "unparseable")
})

test_that("collection_ledger_contract declares every table with typed columns", {
  source(file.path(ledger_repo_root(), "r/collection_ledger.R"))
  contract <- collection_ledger_contract()
  expect_true(all(c("collectors", "units", "findings", "stores", "retirements",
    "summary", "plan", "inputs") %in% names(contract)))
  for (table in contract) {
    expect_true(is.character(table) && length(table) >= 2L)
    expect_false(is.null(names(table)))
    expect_true(all(nzchar(names(table))))
    expect_true(all(table %in% c("character", "logical", "integer", "numeric", "POSIXct")))
  }
})

test_that("collection_ledger_run is deterministic on fixture inputs", {
  skip_if_not_installed("reticulate")
  project_root <- ledger_repo_root()
  python <- file.path(project_root, ".venv/bin/python")
  skip_if_not(file.exists(python), "project interpreter not present")
  source(file.path(project_root, "r/python_bridge.R"))
  source(file.path(project_root, "r/collection_ledger.R"))

  folder <- withr::local_tempdir()
  repo <- write_ledger_fixture(folder)
  host <- file.path(folder, "host-units")
  dir.create(host, recursive = TRUE, showWarnings = FALSE)
  service <- write_ledger_file(file.path(host, "beidanlot-demo.service"),
    paste0("[Service]\nWorkingDirectory=", repo, "\nExecStart=/venv/python scripts/demo_scrape.py\n"))
  link <- file.path(host, "default.target.wants/beidanlot-demo.service")
  dir.create(dirname(link), recursive = TRUE, showWarnings = FALSE)
  file.symlink(service, link)

  report <- collection_ledger_run(
    project_root = project_root, python = python,
    plan_path = file.path(repo, "config/data_collection_plan.json"),
    unit_dirs = host, registry_dir = NA, external_data_root = NA,
    generated_at = "2026-10-04T00:00:00+00:00", repo_root = repo)
  expect_identical(report$schema, "beijing_lot_collection_ledger_v1")
  expect_identical(report$generated_at, "2026-10-04T00:00:00+00:00")
  expect_identical(nrow(report$collectors), 1L)
  expect_identical(report$collectors$id, "demo")
  expect_identical(report$collectors$state, "running")
  expect_type(report$collectors$enabled_in_plan, "logical")
  expect_true(report$collectors$enabled_in_plan)
  expect_true(tibble::is_tibble(report$summary))
  expect_identical(nrow(report$summary), 12L)
  expect_true(all(c("collectors", "inputs_unavailable", "errors", "warnings") %in% report$summary$metric))
  expect_true(tibble::is_tibble(report$findings))
  expect_true(all(c("severity", "code", "subject", "message") %in% names(report$findings)))
  # External inputs explicitly disabled must surface as unavailable inputs.
  expect_true(any(report$inputs$name == "registry_dir" & !report$inputs$available))
  expect_s3_class(report$retirements$removed_at_utc, "POSIXct")
  # Nested store state must be extracted onto the collector row.
  expect_identical(report$collectors$store_state, "running")
  # The repository-unit inventory is a separate, typed table.
  expect_true(tibble::is_tibble(report$repo_units))
  expect_true(all(c("id", "unit_kind", "description", "code_paths") %in% names(report$repo_units)))
  # Input evidence digests bind the classification to the actual inputs.
  expect_true(tibble::is_tibble(report$evidence))
  expect_true(all(c("plan", "host_units") %in% report$evidence$input))
  expect_true(all(nzchar(report$evidence$digest[report$evidence$input %in% c("plan", "host_units")])))
})

test_that("collection_ledger_text prints the operator view", {
  source(file.path(ledger_repo_root(), "r/collection_ledger.R"))
  report <- list(render_text = function() "collection ledger test-view")
  expect_output(collection_ledger_text(report), "collection ledger test-view")
})

test_that("collection ledger Python module defaults are importable", {
  project_root <- ledger_repo_root()
  python <- file.path(project_root, ".venv/bin/python")
  skip_if_not(file.exists(python), "project interpreter not present")
  skip_if_not_installed("reticulate")
  source(file.path(project_root, "r/python_bridge.R"))
  reticulate::use_python(file.path(normalizePath(dirname(python)), basename(python)), required = TRUE)
  reticulate::py_run_string(paste0("import sys\nif ", deparse(file.path(project_root, "src")),
    " not in sys.path: sys.path.insert(0, ", deparse(file.path(project_root, "src")), ")"))
  module <- project_python_module("collection_ledger", file.path(project_root, "src"), python)
  expect_identical(as.character(reticulate::py_to_r(module$DEFAULT_HOST_UNIT_DIRS[[1]])), "~/.config/systemd/user")
  expect_identical(as.character(reticulate::py_to_r(module$DEFAULT_REPO_UNIT_RELATIVE)), "ops/systemd/user")
  expect_true(is.numeric(reticulate::py_to_r(module$DEFAULT_STORE_STALE_DAYS)))
})
