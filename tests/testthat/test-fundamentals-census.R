source(file.path("..", "..", "r", "fundamentals_census.R"))

test_that("coverage includes unsuccessful documents in its denominator", {
  census <- list(
    responses = tibble::tibble(source = c("nowscore", "nowscore"), period = "historical",
      capture_state = c("HTTP_OK", "HTTP_FAILURE"), parse_state = c("PARSED", "NOT_PARSED"),
      evidence_class = "HISTORICAL_PROXY"),
    fields = tibble::tibble(source = "nowscore", period = "historical", field = "injuries",
      field_state = "PUBLISHED_NO_DATA"))
  result <- summarize_fundamentals_coverage(census)
  expect_equal(result$documents, 2L)
  expect_equal(result$fraction, 0.5)
  access <- summarize_fundamentals_access(census)
  expect_equal(sum(access$documents), 2L)
  expect_true("HTTP_FAILURE" %in% access$capture_state)
  census$fields$source <- "unknown"
  expect_error(summarize_fundamentals_coverage(census), "Missing coverage denominator")
})

test_that("immutable CSV input preserves identifiers, zero, null and UTC", {
  root <- tempfile("census-r-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE))
  panel <- tibble::tibble(issue = "001", slot = 1L, provider_id = "00023", status = "完场")
  tables <- list(panel = panel, denominator = panel,
    responses = dplyr::bind_rows(dplyr::mutate(panel, source = "nowscore", status = 200L),
      dplyr::mutate(panel, source = "titan", status = 200L)),
    identity = dplyr::mutate(panel, kickoff_utc = "2026-09-05T12:00:00+00:00"),
    fields = dplyr::mutate(panel, record_count = 0L),
    history = dplyr::mutate(panel, home_score = NA_integer_, away_score = 0L),
    findings = panel[0, ])
  hashes <- list()
  for (name in names(tables)) {
    filename <- paste0(name, ".csv")
    readr::write_csv(tables[[name]], file.path(root, filename), na = "")
    hashes[[filename]] <- digest::digest(file = file.path(root, filename), algo = "sha256", serialize = FALSE)
  }
  receipt <- list(schema = "bj407_diagnostic_census_v1", historical_learning = "NONE",
                  panel_rows = 1L, output_hashes = hashes)
  jsonlite::write_json(receipt, file.path(root, "receipt.json"), auto_unbox = TRUE)
  result <- read_fundamentals_census(root)
  expect_identical(result$panel$issue, "001")
  expect_identical(result$panel$provider_id, "00023")
  expect_identical(result$panel$status, "完场")
  expect_identical(result$responses$status, c(200L, 200L))
  expect_identical(result$fields$record_count, 0L)
  expect_true(is.na(result$history$home_score))
  expect_identical(result$history$away_score, 0L)
  expect_s3_class(result$identity$kickoff_utc, "POSIXct")
  expect_equal(format(result$identity$kickoff_utc, tz = "UTC"), "2026-09-05 12:00:00")
  expect_equal(nrow(result$findings), 0L)
  write("tampered", file.path(root, "fields.csv"))
  expect_error(read_fundamentals_census(root), "hash mismatch")
})

test_that("independent review binds original bytes without granting admission", {
  root <- tempfile("census-review-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE))
  bytes <- charToRaw("original official narrative")
  receipt <- list(url = "https://example.org/report", status = 200L,
                  body_base64 = jsonlite::base64_enc(bytes))
  jsonlite::write_json(receipt, file.path(root, "official.json"), auto_unbox = TRUE)
  review <- list(schema = "bj407_independent_audit_v1", revision = 1L,
    reviewer = "test reviewer", rationale = "test rationale", model_admission = FALSE,
    settlement_mutation = FALSE, issue = "001", slot = 1L, provider_id = "00023",
    disposition = "TIME_SEMANTICS_UNRESOLVED",
    independent_evidence = list(list(file = "official.json", url = receipt$url,
      sha256 = digest::digest(bytes, algo = "sha256", serialize = FALSE))))
  jsonlite::write_json(list(review), file.path(root, "independent-cases.v1.json"), auto_unbox = TRUE)
  result <- read_fundamentals_review(root)
  expect_identical(result$provider_id, "00023")
  expect_identical(result$disposition, "TIME_SEMANTICS_UNRESOLVED")
  receipt$body_base64 <- jsonlite::base64_enc(charToRaw("tampered"))
  jsonlite::write_json(receipt, file.path(root, "official.json"), auto_unbox = TRUE)
  expect_error(read_fundamentals_review(root), "receipt mismatch")
})
