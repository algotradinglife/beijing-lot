test_that("verification initializes both Python variables and reports installed paths", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "verification_environment.R"), local = TRUE)
  withr::local_envvar(c(RETICULATE_PYTHON = NA_character_))
  receipt <- verification_environment(root)
  expect_s3_class(receipt, "tbl_df")
  expect_equal(nrow(receipt), 1L)
  expect_identical(Sys.getenv("RETICULATE_PYTHON"), Sys.getenv("BEIDAN_TEST_PYTHON"))
  expect_identical(receipt$package, normalizePath(find.package("beidan")))
})

test_that("verification rejects configuration errors before running tests", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "verification_environment.R"), local = TRUE)
  withr::local_envvar(c(RETICULATE_PYTHON = "/wrong/python"))
  expect_error(verification_environment(root), "disagree")
  Sys.setenv(RETICULATE_PYTHON = Sys.getenv("BEIDAN_TEST_PYTHON"))
  withr::local_envvar(c(BEIDAN_HOT_ROOT = NA_character_))
  expect_error(verification_environment(root), "roots")
})

test_that("RETICULATE-only configuration is used before applying the default", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "verification_environment.R"), local = TRUE)
  withr::local_envvar(c(BEIDAN_TEST_PYTHON = NA_character_,
                        RETICULATE_PYTHON = "/configured/missing/python"))
  expect_error(verification_environment(root), "not executable.*configured/missing/python")
  Sys.setenv(RETICULATE_PYTHON = file.path(root, ".venv/bin/python"))
  receipt <- verification_environment(root)
  expect_identical(receipt$python, Sys.getenv("RETICULATE_PYTHON"))
  expect_identical(Sys.getenv("BEIDAN_TEST_PYTHON"), receipt$python)
})

test_that("verification rejects missing Python and shadowed package libraries", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "verification_environment.R"), local = TRUE)
  withr::local_envvar(c(BEIDAN_TEST_PYTHON = "/missing/python",
                        RETICULATE_PYTHON = "/missing/python"))
  expect_error(verification_environment(root), "not executable")
  Sys.setenv(BEIDAN_TEST_PYTHON = file.path(root, ".venv/bin/python"),
             RETICULATE_PYTHON = file.path(root, ".venv/bin/python"))
  withr::local_libpaths(.libPaths())
  empty <- withr::local_tempdir()
  withr::local_envvar(c(R_LIBS_USER = empty))
  expect_error(verification_environment(root), "intended installed")
  Sys.setenv(R_LIBS_USER = file.path(empty, "missing"))
  expect_error(verification_environment(root), "existing verification")
})

test_that("noninteractive R profile preserves an explicit library order", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  empty <- withr::local_tempdir()
  withr::local_envvar(c(R_LIBS_USER = empty, R_ENVIRON_USER = "/dev/null"))
  expression <- sprintf("source(%s); cat(.libPaths()[1L])",
    deparse(file.path(root, ".Rprofile")))
  actual <- system2(file.path(R.home("bin"), "Rscript"),
    c("--vanilla", "-e", shQuote(expression)), stdout = TRUE)
  expect_identical(actual, normalizePath(empty))
})

test_that("all historical diagnostic roots are bound and mismatches fail early", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root, "r", "verification_environment.R"), local = TRUE)
  bindings <- verification_repository_roots(root, character())
  expect_identical(bindings$FM17_RELEASE_ROOT, normalizePath(root))
  expect_identical(bindings$FM_CASE4_RATIO_ROOT, normalizePath(root))
  expect_true(all(unlist(bindings) == normalizePath(root)))
  expect_error(verification_repository_roots(root, c(FM17_RELEASE_ROOT="/other/checkout")),
    "repository root mismatch")
  expect_identical(verification_repository_roots(root, c(FM17_RELEASE_ROOT=root)), bindings)
  files <- list.files(file.path(root,"tests/testthat"),pattern="[.]R$",full.names=TRUE)
  text <- paste(readLines(files[[1L]],warn=FALSE),collapse="\n")
  for(file in files[-1L]) text <- paste(text,paste(readLines(file,warn=FALSE),collapse="\n"),sep="\n")
  calls <- regmatches(text,gregexpr("Sys[.]getenv\\(\\s*['\"][A-Z0-9_]*ROOT['\"]",text,perl=TRUE))[[1L]]
  variables <- unique(sub(".*['\"]([A-Z0-9_]*ROOT)['\"]$","\\1",calls,perl=TRUE))
  expect_setequal(setdiff(variables,"BEIDAN_PARQUET_ROOT"),intersect(variables,names(bindings)))
})
