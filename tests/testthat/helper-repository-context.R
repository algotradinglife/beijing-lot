# Repository test context.
#
# Derives the checkout root from the package DESCRIPTION instead of the
# caller's working directory, binds the repository-root environment variables
# the repository tests document, and selects the project interpreter
# explicitly. Bindings are released when the test run ends, so this helper
# must not be evaluated in a frame that outlives it.
local({
  criterion <- rprojroot::has_file(file.path("packages", "beidan", "DESCRIPTION"))
  root <- rprojroot::find_root(criterion, path = getwd())

  setup <- new.env(parent = globalenv())
  sys.source(file.path(root, "r", "verification_environment.R"), envir = setup)
  root_bindings <- setup$verification_repository_roots(root, Sys.getenv())

  interpreter <- Sys.getenv("BEIDAN_TEST_PYTHON")
  if (!nzchar(interpreter)) interpreter <- file.path(root, ".venv", "bin", "python")
  if (!file.exists(interpreter)) {
    stop("project interpreter not found: ", interpreter)
  }

  bindings <- c(
    root_bindings,
    list(RETICULATE_PYTHON = interpreter,
         BEIJING_LOT_VENV_PYTHON = interpreter,
         FUNDAMENTALS_PYTHON = interpreter))
  do.call(withr::local_envvar,
          c(bindings, list(.local_envir = testthat::teardown_env())))

  # Repository tests exercise the installed package; they must not compile or
  # load the source tree.
  library(beidan)

  # Initialize the bundled Python backend from the INSTALLED package before any
  # source client prepends the source backend to sys.path and imports
  # `beidan_backend`. Initializing first makes the installed module win the
  # import cache, so python_backend() keeps its interpreter and package-location
  # checks instead of refusing an already-contaminated process. The interpreter
  # is explicit and fails closed; a missing one is never silently replaced.
  beidan::python_backend(interpreter)

  # Prepare the existing sealed, network-free integration fixture before tests.
  # Explicit caller paths are never replaced; an invalid one fails immediately.
  bundle <- Sys.getenv("FUNDAMENTALS_PIPELINE_TEST_BUNDLE")
  if (!nzchar(bundle)) {
    bundle <- tempfile("fundamentals-pipeline-bundle-")
    log <- tempfile("fundamentals-pipeline-setup-", fileext = ".log")
    withr::defer(unlink(c(bundle, log), recursive = TRUE),
                 envir = testthat::teardown_env())
    status <- system2(interpreter,
      c(shQuote(file.path(root,"scripts/materialize_fundamentals_pipeline_fixture.py")),
        "--output-dir", shQuote(bundle)), stdout = log, stderr = log,
      env=paste0("PYTHONPATH=",shQuote(paste(c(file.path(find.package("beidan"),"python"),root),
                                            collapse=.Platform$path.sep))))
    if (status != 0L) stop("Offline fundamentals fixture setup failed: ",
      paste(readLines(log,warn=FALSE),collapse="\n"))
  }
  manifest <- file.path(bundle,"bundle-manifest.json")
  if (!dir.exists(bundle) || !file.exists(manifest) ||
      !file.exists(file.path(bundle,"bundle-manifest.sha256"))) {
    stop("Explicit fundamentals integration bundle is incomplete: ", bundle)
  }
  pipeline <- reticulate::import_from_path("src.fundamentals_pipeline",path=root,convert=TRUE)
  seal <- pipeline$validate_bundle(bundle)
  bundle <- seal$root
  withr::local_envvar(c(FUNDAMENTALS_PIPELINE_TEST_BUNDLE=bundle),
                     .local_envir=testthat::teardown_env())
})
