# Import a project module through an explicitly selected interpreter; no I/O at import.
project_python_module <- function(module, project_root, python, convert = TRUE) {
  stopifnot(length(module) == 1L, nzchar(module), dir.exists(project_root), file.exists(python))
  if (!is.logical(convert) || length(convert)!=1L || is.na(convert)) stop('Explicit conversion flag required')
  interpreter <- file.path(normalizePath(dirname(python)), basename(python))
  configured_env <- Sys.getenv('RETICULATE_PYTHON',unset='')
  if (nzchar(configured_env) && !identical(file.path(normalizePath(dirname(configured_env)),basename(configured_env)),interpreter)) stop('RETICULATE_PYTHON conflicts with explicit interpreter')
  if (!reticulate::py_available(initialize=FALSE)) reticulate::use_python(interpreter,required=TRUE)
  configured <- reticulate::py_config()$python
  if (!identical(file.path(normalizePath(dirname(configured)),basename(configured)),interpreter)) stop('reticulate initialized with a different interpreter')
  reticulate::import_from_path(module, path = normalizePath(project_root), convert = convert)
}
