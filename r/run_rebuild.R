# Explicit one-issue rebuild. This command writes to the supplied data root.
# Rscript r/run_rebuild.R DATA_ROOT ISSUE CAPTURE_KEY RECEIVED_AT_UTC PROJECT_ROOT PYTHON
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 6L) stop("Required: DATA_ROOT ISSUE CAPTURE_KEY RECEIVED_AT_UTC PROJECT_ROOT PYTHON")
source(file.path(args[5], "r", "python_bridge.R"))
source(file.path(args[5], "r", "mapping_engine.R"))
result <- run_issue_mapping(args[2], args[1], args[3], args[4], args[5], args[6], rebuild = TRUE)
cat(jsonlite::toJSON(result, auto_unbox = TRUE, pretty = TRUE), "\n")
