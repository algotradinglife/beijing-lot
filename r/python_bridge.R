# Import a project module through an explicitly selected interpreter; no I/O at import.
project_python_module <- function(module, project_root, python) {
  stopifnot(length(module) == 1L, nzchar(module), dir.exists(project_root), file.exists(python))
  reticulate::use_python(file.path(normalizePath(dirname(python)), basename(python)), required = TRUE)
  reticulate::import_from_path(module, path = normalizePath(project_root), convert = TRUE)
}
