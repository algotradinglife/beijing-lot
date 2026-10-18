arguments <- commandArgs(trailingOnly = TRUE)
if (!length(arguments)) {
  requested_phases <- c("package", "repository")
} else if (length(arguments) == 1L && arguments %in% c("--phase=package", "--phase=repository")) {
  requested_phases <- sub("--phase=", "", arguments, fixed = TRUE)
} else {
  stop("Use no arguments, --phase=package or --phase=repository")
}
source(file.path("r", "verification_environment.R"))
runtime <- verification_environment(getwd())
cat("Verification environment (validated before test discovery):\n")
print(runtime, width = Inf)
library(testthat)
library(beidan)

# Standard entry point: `Rscript tests/testthat.R` from the repository root.
#
# Both phases exercise the normally installed package (never a source compile)
# and both run even when one fails, so a single invocation yields complete
# evidence. The exit status is non-zero when a phase errored or any test failed
# or errored. Raising the reporter's failure cap collects the full inventory
# instead of stopping at the first failures.

testthat::set_max_fails(Inf)

root <- rprojroot::find_root(
  rprojroot::has_file(file.path("packages", "beidan", "DESCRIPTION")),
  path = getwd())

# Python and installed-package identity were validated before loading testthat.

phases <- list(
  package = file.path(root, "packages", "beidan", "tests", "testthat"),
  repository = file.path(root, "tests", "testthat"))
phases <- phases[requested_phases]

summaries <- list()
phase_errors <- list()
for (label in names(phases)) {
  cat("\n===== ", label, " tests (installed package) =====\n", sep = "")
  results <- tryCatch(
    testthat::test_dir(phases[[label]], package = "beidan", reporter = "summary",
      load_package = "installed", stop_on_failure = FALSE),
    error = function(e) {
      phase_errors[[label]] <<- conditionMessage(e)
      NULL
    })
  if (is.null(results)) {
    cat("phase '", label, "' errored before producing results: ",
        phase_errors[[label]], "\n", sep = "")
    next
  }
  frame <- as.data.frame(results)
  frame <- frame[, !vapply(frame, is.list, logical(1)), drop = FALSE]
  summaries[[label]] <- tibble::as_tibble(frame[intersect(
    c("file", "context", "test", "nb", "failed", "error", "warning", "skipped", "passed"),
    names(frame))])
  print(summaries[[label]])
}

for (label in names(summaries)) {
  frame <- summaries[[label]]
  totals <- c(tests = nrow(frame), passed = sum(frame$passed), failed = sum(frame$failed),
              errors = sum(frame$error), warnings = sum(frame$warning),
              skipped = sum(frame$skipped))
  cat("\n", label, ": ", paste(names(totals), unname(totals), sep = "=", collapse = " "),
      "\n", sep = "")
}
for (label in names(phase_errors)) {
  cat("\n", label, ": phase error: ", phase_errors[[label]], "\n", sep = "")
}

failures <- sum(vapply(summaries, function(f) sum(f$failed) + sum(f$error), numeric(1)))
if (failures > 0L || length(phase_errors) > 0L) {
  message("test entry failed: ", failures, " failing or errored test blocks, ",
          length(phase_errors), " phase error(s)")
  quit(status = 1L, save = "no")
}
