testthat::test_that("alpha client is reproducible and does not replace formal FM", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  outputs <- list()
  for (i in 1:2) {
    out <- tempfile("fm18-smoke-"); log <- tempfile()
    status <- system2("/opt/R/4.6.1/bin/Rscript", shQuote(c(file.path(root, "r/fm18_alpha_smoke.R"), root, out)),
      env = paste0("R_LIBS=", shQuote(paste(.libPaths(), collapse = ":"))), stdout = log, stderr = log)
    testthat::expect_equal(status, 0L, info = paste(readLines(log), collapse = "\n"))
    outputs[[i]] <- readRDS(file.path(out, "smoke.rds"))
    r <- jsonlite::fromJSON(file.path(out, "receipt.json"))
    testthat::expect_equal(r$formal_model, "FM-1.7.0")
    testthat::expect_false(r$labels_opened_by_client)
    testthat::expect_equal(r$output_sha256, digest::digest(file = file.path(out, "smoke.rds"), algo = "sha256"))
  }
  testthat::expect_identical(outputs[[1]], outputs[[2]])
  for (x in outputs[[1]]) {
    testthat::expect_equal(sum(x$grid$probability), 1, tolerance = 1e-12)
    testthat::expect_equal(sum(x$margins$probability), 1, tolerance = 1e-12)
    testthat::expect_equal(x$margins$probability[x$margins$margin == -x$projection_handicap],
      x$probabilities$probability[x$probabilities$outcome == "D"], tolerance = 1e-12)
    testthat::expect_equal(x$receipt$model_id, "FM-1.8.0-alpha.1")
  }
})
