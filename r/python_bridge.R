# Import a project module using an explicit interpreter; no scraping or DB writes.
project_python_module <- function(module, project_root, python) {
  stopifnot(length(module) == 1L, nzchar(module), dir.exists(project_root), file.exists(python))
  reticulate::use_python(file.path(normalizePath(dirname(python)), basename(python)), required = TRUE)
  root <- normalizePath(project_root)
  imported <- reticulate::import_from_path(module, path = root, convert = TRUE)
  if (!startsWith(normalizePath(imported$`__file__`), paste0(root, .Platform$file.sep))) {
    stop("Python module loaded outside requested project root; restart R in the correct project")
  }
  imported
}
