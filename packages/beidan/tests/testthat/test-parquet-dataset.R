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
  # A derived artifact registered in the catalog, not in the version manifest.
  derived_dir <- file.path(version_dir, "derived")
  dir.create(derived_dir, recursive = TRUE, showWarnings = FALSE)
  labels <- arrow::arrow_table(
    issue = arrow::Array$create(c("26011", "26011")),
    slot = arrow::Array$create(c(1L, 2L), type = arrow::int16()),
    handicap = arrow::Array$create(c(0L, -1L), type = arrow::int64()),
    handicap_source = arrow::Array$create(c("cross_source", "archive"))
  )
  derived_path <- file.path(derived_dir, "labels.parquet")
  arrow::write_parquet(labels, derived_path)

  dir.create(file.path(root, "registry"), showWarnings = FALSE)
  writeLines(jsonlite::toJSON(manifest, auto_unbox = TRUE, pretty = TRUE),
             file.path(version_dir, "manifest.json"))
  registry <- list(schema = "beijing_lot_parquet_dataset_v1", dataset = "demo",
                   version = "v1", root = version_dir, partitions = 2L, files = 3L)
  writeLines(jsonlite::toJSON(registry, auto_unbox = TRUE),
             file.path(root, "registry", "demo-parquet-current.json"))
  catalog <- list(
    schema = "beijing_lot_catalog_v1",
    datasets = list(demo = list(
      kind = "dataset", format = "parquet", version = "v1",
      location = "frozen:datasets/demo", tables = 2L, rows = 5L,
      derived = list(labels = list(
        format = "parquet", rows = 2L,
        location = paste0("frozen:datasets/demo/versions/v1/derived/labels.parquet"),
        sha256 = digest::digest(file = derived_path, algo = "sha256")
      ))
    ))
  )
  writeLines(jsonlite::toJSON(catalog, auto_unbox = TRUE, pretty = TRUE),
             file.path(root, "registry", "catalog.json"))
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
  expect_error(dataset_registry("nope", root = root), "no registry or pointer for dataset")
})

test_that("the dataset's own current.json pointer takes precedence", {
  root <- parquet_fixture()
  # registry snapshot says v1; the dataset pointer names a different version
  pointer <- file.path(root, "datasets", "demo", "current.json")
  dir.create(dirname(pointer), recursive = TRUE, showWarnings = FALSE)
  writeLines(jsonlite::toJSON(list(schema = "beijing_lot_version_v1",
    label_version = "v2"), auto_unbox = TRUE), pointer)
  reg <- dataset_registry("demo", root = root)
  expect_identical(reg$label_version, "v2")
  expect_true(grepl("datasets/demo/current.json", reg$path, fixed = TRUE))
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
  expect_error(read_dataset("demo", "missing", root = root), "neither a base table")
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

test_that("derived artifacts are listed from the catalog, base tables from the manifest", {
  root <- parquet_fixture()
  expect_setequal(dataset_tables("demo", root = root), c("obs", "small"))
  expect_identical(dataset_derived_tables("demo", root = root), "labels")
  # a dataset with no catalog entry yields an empty, not an error
  expect_identical(dataset_derived_tables("absent", root = root), character(0))
})

test_that("read_dataset reads a catalog-registered derived artifact", {
  root <- parquet_fixture()
  d <- read_dataset("demo", "labels", root = root)
  expect_s3_class(d, "tbl_df")
  expect_identical(nrow(d), 2L)
  expect_identical(names(d), c("issue", "slot", "handicap", "handicap_source"))
  expect_type(d$issue, "character")
  expect_type(d$slot, "integer")       # int16 -> integer
  expect_type(d$handicap, "double")    # int64 -> double
  expect_identical(attr(d, "kind"), "derived")
  expect_identical(attr(d, "dataset"), "demo")
  expect_identical(attr(d, "version"), "v1")
})

test_that("read_dataset supports projection on a derived artifact", {
  root <- parquet_fixture()
  d <- read_dataset("demo", "labels", root = root, columns = c("issue", "handicap"))
  expect_identical(names(d), c("issue", "handicap"))
  expect_error(read_dataset("demo", "labels", root = root, columns = "nope"),
               "unknown column")
})

test_that("read_dataset verifies a derived artifact against the catalog sha256", {
  root <- parquet_fixture()
  expect_identical(nrow(read_dataset("demo", "labels", root = root, verify = TRUE)), 2L)
  # rewrite with different content; the catalog hash no longer matches
  target <- file.path(root, "datasets", "demo", "versions", "v1", "derived", "labels.parquet")
  arrow::write_parquet(
    arrow::arrow_table(issue = arrow::Array$create(c("26011", "26011", "26011"))), target)
  expect_error(read_dataset("demo", "labels", root = root, verify = TRUE),
               "sha256 mismatch|row count")
})

test_that("read_dataset fails closed for derived misuse", {
  root <- parquet_fixture()
  # issue_year is a base-partition concept only
  expect_error(read_dataset("demo", "labels", root = root, issue_year = 2026),
               "not partitioned")
  # a derived artifact is registered in the catalog, not in the version manifest
  expect_null(dataset_manifest("demo", root = root)$tables$labels)
  expect_identical(dataset_derived_tables("demo", root = root), "labels")
  # unknown names are neither base tables nor registered derived artifacts
  expect_error(read_dataset("demo", "ghost", root = root),
               "neither a base table")
})

test_that("dataset_query can aggregate a derived artifact", {
  skip_if_not_installed("duckdb")
  root <- parquet_fixture()
  out <- dataset_query("demo",
    "SELECT handicap_source, count(*) AS n FROM labels GROUP BY 1 ORDER BY 1",
    "labels", root = root)
  expect_identical(nrow(out), 2L)
  expect_identical(sum(out$n), 2)
})

test_that("read_dataset follows a versioned derived pointer", {
  root <- parquet_fixture()
  version_dir <- file.path(root, "datasets", "demo", "versions", "v1")
  derived_dir <- file.path(version_dir, "derived")

  # Replace the flat artifact with a versioned layout + current pointer.
  unlink(file.path(derived_dir, "labels.parquet"))
  for (label in c("2026-10-06", "2026-10-07")) {
    dir.create(file.path(derived_dir, "labels", "versions", label),
               recursive = TRUE, showWarnings = FALSE)
    arrow::write_parquet(
      arrow::arrow_table(issue = arrow::Array$create(rep("26011", if (label == "2026-10-06") 2L else 3L)),
                         handicap = arrow::Array$create(1L)),
      file.path(derived_dir, "labels", "versions", label, "labels.parquet"))
  }
  newest <- file.path(derived_dir, "labels", "versions", "2026-10-07", "labels.parquet")
  writeLines(jsonlite::toJSON(list(
    schema = "beijing_lot_version_v1", label_version = "2026-10-07",
    artifact = list(path = newest, rows = 3L,
                    sha256 = digest::digest(file = newest, algo = "sha256"))), auto_unbox = TRUE),
    file.path(derived_dir, "labels", "current.json"))

  catalog <- jsonlite::fromJSON(file.path(root, "registry", "catalog.json"), simplifyVector = FALSE)
  catalog$datasets$demo$derived$labels <- list(
    format = "parquet",
    location = "frozen:datasets/demo/versions/v1/derived/labels/current.json")
  writeLines(jsonlite::toJSON(catalog, auto_unbox = TRUE, pretty = TRUE),
             file.path(root, "registry", "catalog.json"))

  d <- read_dataset("demo", "labels", root = root)
  expect_identical(nrow(d), 3L)                       # the newest version
  expect_identical(attr(d, "label_version"), "2026-10-07")
  expect_identical(attr(d, "kind"), "derived")
})

test_that("a versioned derived pointer fails closed on a missing artifact", {
  root <- parquet_fixture()
  derived_dir <- file.path(root, "datasets", "demo", "versions", "v1", "derived")
  dir.create(file.path(derived_dir, "labels", "versions", "2026-10-06"),
             recursive = TRUE, showWarnings = FALSE)
  writeLines(jsonlite::toJSON(list(
    label_version = "2026-10-06",
    artifact = list(path = file.path(derived_dir, "labels", "versions", "2026-10-06", "gone.parquet"),
                    rows = 1L, sha256 = "00")), auto_unbox = TRUE),
    file.path(derived_dir, "labels", "current.json"))
  catalog <- jsonlite::fromJSON(file.path(root, "registry", "catalog.json"), simplifyVector = FALSE)
  catalog$datasets$demo$derived$labels <- list(
    format = "parquet",
    location = "frozen:datasets/demo/versions/v1/derived/labels/current.json")
  writeLines(jsonlite::toJSON(catalog, auto_unbox = TRUE),
             file.path(root, "registry", "catalog.json"))
  expect_error(read_dataset("demo", "labels", root = root), "current artifact is missing")
})

test_that("a base table rejects a play argument", {
  root <- parquet_fixture()
  expect_error(read_dataset("demo", "obs", root = root, play = "spf"),
               "base table 'obs' is not partitioned by play")
})

test_that("read_dataset reads a single play partition and matches the full table", {
  root <- parquet_fixture()
  derived_dir <- file.path(root, "datasets", "demo", "versions", "v1", "derived")
  labels_dir <- file.path(derived_dir, "labels")
  dir.create(file.path(labels_dir, "versions", "v1", "by_play"),
             recursive = TRUE, showWarnings = FALSE)

  full_df <- data.frame(
    issue = c("26011", "26011", "26012", "26012"),
    play = c("spf", "jq", "spf", "jq"),
    option = c("胜", "3球", "平", "1球"),
    stringsAsFactors = FALSE)
  full_path <- file.path(labels_dir, "versions", "v1", "labels.parquet")
  arrow::write_parquet(full_df, full_path)

  parts <- list()
  for (pl in c("spf", "jq")) {
    # a shard drops the partition key column and holds only that play's rows
    part_df <- full_df[full_df$play == pl, setdiff(names(full_df), "play"), drop = FALSE]
    p <- file.path(labels_dir, "versions", "v1", "by_play", sprintf("play=%s.parquet", pl))
    arrow::write_parquet(part_df, p)
    parts[[pl]] <- list(file = basename(p), rows = nrow(part_df),
                        sha256 = digest::digest(file = p, algo = "sha256"))
  }
  writeLines(jsonlite::toJSON(list(
    label_version = "v1",
    artifact = list(path = full_path, rows = 4L,
                    sha256 = digest::digest(file = full_path, algo = "sha256")),
    partition = list(key = "play", directory = "by_play", parts = parts)),
    auto_unbox = TRUE), file.path(labels_dir, "current.json"))

  catalog <- jsonlite::fromJSON(file.path(root, "registry", "catalog.json"), simplifyVector = FALSE)
  catalog$datasets$demo$derived$labels <- list(
    format = "parquet",
    location = "frozen:datasets/demo/versions/v1/derived/labels/current.json")
  writeLines(jsonlite::toJSON(catalog, auto_unbox = TRUE, pretty = TRUE),
             file.path(root, "registry", "catalog.json"))

  a <- read_dataset("demo", "labels", root = root, play = "spf")
  expect_identical(attr(a, "partition"), "play")
  expect_identical(nrow(a), 2L)
  # the shard omits the partition key itself
  expect_false("play" %in% names(a))
  expect_identical(a$issue, c("26011", "26012"))

  whole <- read_dataset("demo", "labels", root = root)
  expect_identical(nrow(whole), 4L)
  expect_identical(dplyr::filter(whole, play == "spf")$issue, a$issue)

  expect_error(read_dataset("demo", "labels", root = root, play = "nope"),
               "no partition for play")
})
