library(testthat)

# A deterministic, offline fixture: the same on-disk layout the NAS uses, so the
# reader contract is tested without needing the mount.
parquet_fixture <- function() {
  # A plain tempdir, not withr::local_tempdir(): the fixture must outlive this
  # helper's frame so the calling test can read from it.
  root <- tempfile("parquet-demo-")
  dir.create(root, recursive = TRUE)
  version_dir <- file.path(root, "datasets", "demo", "versions", "v1")
  dir.create(file.path(version_dir, "tables", "obs"), recursive = TRUE, showWarnings = FALSE)

  obs_part <- function(ids, issues, slots, plays, years) {
    arrow::arrow_table(
      observation_id = arrow::Array$create(ids, type = arrow::int64()),
      issue = arrow::Array$create(issues),
      slot = arrow::Array$create(slots, type = arrow::int16()),
      play = arrow::Array$create(plays),
      issue_year = arrow::Array$create(years, type = arrow::int16())
    )
  }
  obs_2026 <- obs_part(c(1, 2), c("26011", "26011"), c(1L, 2L), c("spf", "jq"), c(2026L, 2026L))
  obs_2009 <- obs_part(3, "090918", 3L, "bf", 2009L)
  small <- arrow::arrow_table(
    batch_id = arrow::Array$create(c("b1", "b2")),
    row_count = arrow::Array$create(c(10, 20), type = arrow::int32())
  )
  arrow::write_parquet(obs_2026, file.path(version_dir, "tables", "obs", "part-issue-year=2026.parquet"))
  arrow::write_parquet(obs_2009, file.path(version_dir, "tables", "obs", "part-issue-year=2009.parquet"))
  arrow::write_parquet(small, file.path(version_dir, "tables", "small.parquet"))

  describe <- function(path) list(
    name = basename(path),
    sha256 = digest::digest(file = path, algo = "sha256"),
    bytes = unname(file.size(path))
  )
  manifest <- list(
    schema = "beijing_lot_parquet_dataset_v1",
    dataset = "demo",
    version = "v1",
    partition_by = "issue_year",
    row_counts = list(obs = 3L, small = 2L),
    tables = list(
      obs = list(kind = "partitioned", rows = 3L, partitions = 2L, files = list(
        describe(file.path(version_dir, "tables", "obs", "part-issue-year=2009.parquet")),
        describe(file.path(version_dir, "tables", "obs", "part-issue-year=2026.parquet"))
      )),
      small = list(kind = "whole", rows = 2L, files = list(
        describe(file.path(version_dir, "tables", "small.parquet"))
      ))
    )
  )
  dir.create(file.path(root, "registry"), showWarnings = FALSE)
  writeLines(jsonlite::toJSON(manifest, auto_unbox = TRUE, pretty = TRUE),
             file.path(version_dir, "manifest.json"))
  registry <- list(schema = "beijing_lot_parquet_dataset_v1", dataset = "demo",
                   version = "v1", root = version_dir, partitions = 2L, files = 3L)
  writeLines(jsonlite::toJSON(registry, auto_unbox = TRUE),
             file.path(root, "registry", "demo-parquet-current.json"))
  root
}

test_that("parquet_root fails closed when the root is unavailable", {
  expect_error(parquet_root(file.path(tempdir(), "does-not-exist-xyz")),
               "not available")
  root <- withr::local_tempdir()
  expect_identical(parquet_root(root), normalizePath(root, mustWork = TRUE))
})

test_that("registry and manifest are read from the persistent root", {
  root <- parquet_fixture()
  reg <- dataset_registry("demo", root = root)
  expect_identical(reg$version, "v1")
  man <- dataset_manifest("demo", root = root)
  expect_identical(man$version, "v1")
  expect_setequal(dataset_tables("demo", root = root), c("obs", "small"))
  expect_error(dataset_registry("nope", root = root), "no registry for dataset")
})

test_that("dataset_contract maps Arrow types to the declared R types", {
  root <- parquet_fixture()
  contract <- dataset_contract("demo", "obs", root = root)
  expect_identical(contract[["observation_id"]], "double")   # int64 -> double
  expect_identical(contract[["slot"]], "integer")            # int16 -> integer
  expect_identical(contract[["issue"]], "character")         # string -> character
  expect_identical(contract[["issue_year"]], "integer")
})

test_that("read_dataset reads a partition and honours the declared types", {
  root <- parquet_fixture()
  d <- read_dataset("demo", "obs", root = root, issue_year = 2026)
  expect_s3_class(d, "tbl_df")
  expect_identical(nrow(d), 2L)
  expect_type(d$observation_id, "double")
  expect_type(d$slot, "integer")
  expect_type(d$issue, "character")
  expect_identical(sort(d$issue), c("26011", "26011"))
})

test_that("read_dataset reads a whole non-partitioned table and all partitions", {
  root <- parquet_fixture()
  expect_identical(nrow(read_dataset("demo", "small", root = root)), 2L)
  expect_identical(nrow(read_dataset("demo", "obs", root = root)), 3L)
})

test_that("read_dataset refuses an invalid partition or table selection", {
  root <- parquet_fixture()
  expect_error(read_dataset("demo", "obs", root = root, issue_year = 2020),
               "partition issue_year=2020 is not published")
  expect_error(read_dataset("demo", "small", root = root, issue_year = 2026),
               "not partitioned")
  expect_error(read_dataset("demo", "missing", root = root), "not in the version manifest")
  expect_error(read_dataset("demo", "obs", root = root, columns = c("nope")),
               "unknown column")
})

test_that("read_dataset verifies files against the manifest and detects tampering", {
  root <- parquet_fixture()
  version_dir <- file.path(root, "datasets", "demo", "versions", "v1")
  target <- file.path(version_dir, "tables", "small.parquet")
  expect_identical(nrow(read_dataset("demo", "small", root = root, verify = TRUE)), 2L)

  # Rewrite the file with different bytes: size changes, content hash changes.
  arrow::write_parquet(
    arrow::arrow_table(batch_id = arrow::Array$create("tampered")),
    target)
  expect_error(read_dataset("demo", "small", root = root, verify = TRUE), "sha256 mismatch")
})

test_that("read_dataset fails when a published file is missing", {
  root <- parquet_fixture()
  unlink(file.path(root, "datasets", "demo", "versions", "v1", "tables", "small.parquet"))
  expect_error(read_dataset("demo", "small", root = root), "published file")
})

test_that("missing root and missing version fail closed", {
  root <- parquet_fixture()
  expect_error(dataset_manifest("demo", version = "v9", root = root), "not published")
  expect_error(read_dataset("demo", "obs", root = file.path(tempdir(), "gone")), "not available")
})

test_that("dataset_query aggregates across partitions", {
  skip_if_not_installed("duckdb")
  root <- parquet_fixture()
  out <- dataset_query("demo", "SELECT issue_year, count(*) AS n FROM obs GROUP BY issue_year ORDER BY issue_year",
                       "obs", root = root)
  expect_s3_class(out, "tbl_df")
  expect_identical(out$issue_year, c(2009L, 2026L))
  expect_identical(out$n, c(1, 2))
})

test_that("real NAS dataset reads consistently when available", {
  root <- "/mnt/nas/Data/beijing-lot"
  skip_if_not(dir.exists(root), "NAS persistent root not mounted")
  skip_if_not(file.exists(file.path(root, "registry", "settlement-parquet-current.json")),
              "settlement parquet registry not published")
  manifest <- dataset_manifest("settlement", root = root)
  d <- read_dataset("settlement", "option_sp", root = root, issue_year = 2026)
  expect_s3_class(d, "tbl_df")
  expect_identical(names(d), c("observation_id", "option", "raw_sp", "sp", "cell_id", "issue_year"))
  expect_type(d$sp, "double")
  expect_true(nrow(d) > 0)
  # the year partition must be internally consistent with its own key
  expect_true(all(d$issue_year == 2026L))
  # the whole table reconciles with the manifest row count
  expect_identical(as.integer(manifest$row_counts$option_sp),
                   as.integer(nrow(read_dataset("settlement", "option_sp", root = root))))
})
