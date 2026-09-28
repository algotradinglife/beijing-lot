# Environment setup only: shared user library, no project-local package copies.
# pak itself must already be provisioned by the machine/CI environment.
shared_library <- Sys.getenv("R_LIBS_USER")
stopifnot(nzchar(shared_library), requireNamespace("pak", quietly = TRUE), requireNamespace("jsonlite", quietly = TRUE))
dir.create(shared_library, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(shared_library, .Library))
versions <- unlist(jsonlite::read_json("config/qmd_incremental_mvp/packages.json"), use.names = TRUE)
pak::pkg_install(paste0(names(versions), "@", versions), lib = shared_library, ask = FALSE)
actual <- vapply(names(versions), function(p) as.character(utils::packageVersion(p)), character(1))
# package_version normalizes CRAN hyphens and printed dots (e.g. 0.2-20).
stopifnot(all(package_version(actual) == package_version(versions)))
