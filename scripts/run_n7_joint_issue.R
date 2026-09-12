# Thin offline entry point: bundle config output python. Run from repository root.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 4L, !file.exists(args[3]))
source("r/n7_sleeve_tables.R")
source("r/n7_joint_sleeves.R")
runtime <- jsonlite::fromJSON("config/n7_joint_runtime.json", simplifyVector = FALSE)
stopifnot(as.character(getRversion()) == runtime$R,
  all(vapply(names(runtime$r_packages), function(p)
    as.character(utils::packageVersion(p)) == runtime$r_packages[[p]], logical(1))))
bundle <- jsonlite::fromJSON(gzfile(args[1]), simplifyVector = FALSE)
config <- jsonlite::fromJSON(args[2], simplifyVector = FALSE)
result <- n7_joint_issue(bundle, bundle$cutoffs, config, args[4])
result$runtime <- runtime
jsonlite::write_json(result, args[3], auto_unbox = TRUE, digits = NA,
                     null = "null", na = "null", matrix = "rowmajor")
