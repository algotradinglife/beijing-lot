# Explicit environment setup only: Rscript --vanilla r/bootstrap.R
project_lib <- file.path(getwd(), "r_lib")
dir.create(project_lib, showWarnings = FALSE)
.libPaths(c(project_lib, .libPaths()))
if (!requireNamespace("renv", quietly = TRUE)) {
  install.packages("renv", repos = "https://cloud.r-project.org", lib = project_lib)
}
renv::restore(project = getwd(), library = project_lib, lockfile = "renv.lock", prompt = FALSE)
