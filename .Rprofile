# Interactive convenience only; clean runs supply R_LIBS_USER explicitly.
local({
  project_lib <- file.path(getwd(), "r_lib")
  if (dir.exists(project_lib)) .libPaths(c(project_lib, .libPaths()))
})
