# Interactive convenience only; clean runs supply R_LIBS_USER explicitly.
local({
  project_lib <- file.path(getwd(), "r_lib")
  if (dir.exists(project_lib)) .libPaths(c(project_lib, .libPaths()))
})

# Prefer Posit Package Manager Linux binaries over CRAN source builds.
# P3M keys binaries by distribution codename and R minor version; this host is
# Ubuntu 26.04 "resolute" on R 4.6. Without this, pak/install.packages compile
# from source (arrow takes many minutes). Update the codename if the host
# distribution changes (`lsb_release -cs`).
options(repos = c(CRAN = "https://packagemanager.posit.co/cran/__linux__/resolute/latest"))
