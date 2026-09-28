test_that("n7_probe_find_root locates the artifact directory", {
  root <- n7_probe_find_root()
  expect_true(dir.exists(file.path(root, "results", "data_collection",
                                   "n7_493_3in1_probe_v1")))
})

test_that("n7_probe_find_root fails closed when nothing matches", {
  expect_error(
    n7_probe_find_root(candidates = tempdir(), relative = "definitely/not/here"),
    "not found")
})

test_that("n7_probe_read_ledger returns a typed tibble and keeps unknowns NA", {
  path <- tempfile(fileext = ".jsonl")
  writeLines(c(
    '{"kind":"outcome","label":"a","http_status":200,"http_status_provenance":"recorded","duration_ms":10,"duration_ms_provenance":"recorded","hop":null,"hop_provenance":"missing","ended_at":"2026-01-01T00:00:00Z","ended_at_provenance":"observed_file_mtime"}',
    '{"kind":"outcome","label":"b","http_status":null,"http_status_provenance":"missing","duration_ms":null,"duration_ms_provenance":"missing","hop":null,"hop_provenance":"missing","ended_at":"2026-01-01T00:00:01Z","ended_at_provenance":"observed_file_mtime"}'
  ), path)
  out <- n7_probe_read_ledger(path)
  expect_s3_class(out, "tbl_df")
  expect_equal(nrow(out), 2L)
  expect_equal(out$status, c("200", NA_character_))
  expect_equal(out$duration_ms, c(10, NA_real_))
  expect_equal(out$hop_provenance, c("missing", "missing"))
})

test_that("n7_probe_read_ledger handles an empty ledger with a typed schema", {
  path <- tempfile(fileext = ".jsonl")
  writeLines(character(), path)
  out <- n7_probe_read_ledger(path)
  expect_s3_class(out, "tbl_df")
  expect_equal(nrow(out), 0L)
  expect_type(out$duration_ms, "double")
  expect_type(out$label, "character")
})

test_that("n7_probe_read_ledger stops when the ledger is absent", {
  expect_error(n7_probe_read_ledger(tempfile()), "ledger not found")
})

test_that("n7_probe_read_diagnostics requires assumption columns", {
  path <- tempfile(fileext = ".csv")
  utils::write.csv(data.frame(view = "v", rows_total = 1), path, row.names = FALSE)
  expect_error(n7_probe_read_diagnostics(path), "assumed timezone and year")
})

test_that("n7_probe_read_diagnostics returns a tibble with assumptions present", {
  path <- tempfile(fileext = ".csv")
  frame <- data.frame(
    view = "companyid=3", rows_total = 1,
    rows_strictly_before_epoch_ASSUMED_UTC.8_YEAR_2026 = 1,
    last_before_epoch_ASSUMED_UTC.8_YEAR_2026 = "2026-08-14 19:02",
    tz_status = "TZ_UNDECIDED_DIAGNOSTIC_ONLY",
    availability_evidence = "NOT_PROVEN", check.names = FALSE)
  utils::write.csv(frame, path, row.names = FALSE)
  out <- n7_probe_read_diagnostics(path)
  expect_s3_class(out, "tbl_df")
  expect_true(any(grepl("^last_before_epoch_ASSUMED_", names(out))))
  expect_equal(out$availability_evidence, "NOT_PROVEN")
})

test_that("n7_probe_read_impl_hashes returns real digests", {
  root <- n7_probe_find_root()
  out <- n7_probe_read_impl_hashes(root, "src/n7_493_probe.py")
  expect_equal(nrow(out), 1L)
  expect_match(out$sha256, "^[0-9a-f]{64}$")
})

test_that("n7_probe_read_impl_hashes marks a missing file NA", {
  root <- n7_probe_find_root()
  out <- n7_probe_read_impl_hashes(root, "src/definitely_missing.R")
  expect_true(is.na(out$sha256))
})

test_that("n7_probe_read_artifacts parses SHA256SUMS", {
  path <- tempfile()
  writeLines(c(paste0(strrep("a", 64), "  raw/x.html"),
               paste0(strrep("b", 64), "  diagnostics.csv")), path)
  out <- n7_probe_read_artifacts(path)
  expect_equal(out$file, c("raw/x.html", "diagnostics.csv"))
  expect_equal(out$sha256, c(strrep("a", 64), strrep("b", 64)))
})

test_that("n7_probe_compare_reviewed detects a changed file", {
  root <- n7_probe_find_root()
  reviewed <- tempfile(fileext = ".json")
  writeLines(jsonlite::toJSON(list(files = list(
    "src/n7_493_probe.py" = "0000000000000000000000000000000000000000000000000000000000000000"
  )), auto_unbox = TRUE), reviewed)
  out <- n7_probe_compare_reviewed(root, reviewed)
  expect_false(out$matches)
})

test_that("n7_probe_compare_reviewed confirms a matching file", {
  root <- n7_probe_find_root()
  current <- n7_probe_read_impl_hashes(root, "src/n7_493_probe.py")
  reviewed <- tempfile(fileext = ".json")
  writeLines(jsonlite::toJSON(list(files = list(
    "src/n7_493_probe.py" = current$sha256
  )), auto_unbox = TRUE), reviewed)
  out <- n7_probe_compare_reviewed(root, reviewed)
  expect_true(out$matches)
})

test_that("n7_probe_validate_artifacts verifies the delivered bytes", {
  root <- n7_probe_find_root()
  out <- n7_probe_validate_artifacts(
    root, "results/data_collection/n7_493_3in1_probe_v1/SHA256SUMS")
  expect_true(all(out$matches))
  expect_true(nrow(out) >= 8)
  expect_false(any(is.na(out$actual)))
})

test_that("n7_probe_validate_artifacts fails on a mutated artifact", {
  root <- n7_probe_find_root()
  tmp <- tempfile()
  dir.create(tmp)
  dir.create(file.path(tmp, "raw"))
  writeLines("original", file.path(tmp, "raw", "a.html"))
  digests <- system2("sha256sum", shQuote(file.path(tmp, "raw", "a.html")),
                     stdout = TRUE, stderr = FALSE)
  writeLines(paste0(strsplit(trimws(digests), "[[:space:]]+")[[1]][1], "  raw/a.html"),
             file.path(tmp, "SHA256SUMS"))
  expect_silent(n7_probe_validate_artifacts(tmp, "SHA256SUMS"))
  # Mutating the bytes must be detected, not merely displayed.
  writeLines("tampered", file.path(tmp, "raw", "a.html"))
  expect_error(n7_probe_validate_artifacts(tmp, "SHA256SUMS"), "artifact mismatch")
})

test_that("n7_probe_validate_artifacts fails on a missing artifact", {
  tmp <- tempfile()
  dir.create(tmp)
  writeLines(paste0(strrep("a", 64), "  raw/gone.html"), file.path(tmp, "SHA256SUMS"))
  expect_error(n7_probe_validate_artifacts(tmp, "SHA256SUMS"), "artifact mismatch")
})

test_that("n7_probe_compare_reviewed stops when the record is absent", {
  root <- n7_probe_find_root()
  expect_error(n7_probe_compare_reviewed(root, tempfile()),
               "reviewed revision not found")
})
