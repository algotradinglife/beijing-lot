#!/usr/bin/env Rscript
# Fresh-process prediction-only replay; labels are neither loaded nor required.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==2,!file.exists(args[2]))
library(dplyr);source('r/n7_sweet_region.R')
freeze <- jsonlite::fromJSON(file.path(args[1],'plans-frozen.json'),simplifyVector=FALSE)
for(name in names(freeze$files))stopifnot(digest::digest(file=file.path(args[1],name),algo='sha256')==freeze$files[[name]])
all <- readr::read_csv(file.path(args[1],'prediction-points.csv'),show_col_types=FALSE,
  col_types=readr::cols(issue='c',sleeve_id='c'))
funded <- readr::read_csv(file.path(args[1],'frozen-plan-groups.csv'),show_col_types=FALSE,
  col_types=readr::cols(issue='c',sleeve_id='c'))
policies <- bind_rows(freeze$config$policies);n <- 0L
for(issue in names(freeze$metadata)) {
  points <- all |> filter(.data$issue==.env$issue) |>
    select(sleeve_id,target,depth,stake,coverage,expected_gross)
  cuts <- freeze$metadata[[issue]]$cutoffs
  attr(points,'cutoffs') <- cuts
  sets <- lapply(freeze$metadata[[issue]]$fixture_sets,unlist)
  for(i in seq_len(nrow(policies))) {
    p <- policies[i,]
    plan <- n7_sweet_allocate(points,sets,cuts,cuts,p$target,p$cap_cny,1024,2,p$reuse,p$overlap)
    expected <- funded |> filter(.data$issue==.env$issue,arm==p$arm)
    stopifnot(setequal(plan$ids,expected$sleeve_id),plan$stake==sum(expected$stake))
    n <- n+1L
  }
}
stopifnot(n==5400)
jsonlite::write_json(list(status='PASS',plans=n,labels_loaded=FALSE,
  freeze_sha256=digest::digest(file=file.path(args[1],'plans-frozen.json'),algo='sha256'),
  implementation_sha256=digest::digest(file='r/n7_sweet_region.R',algo='sha256')),
  args[2],auto_unbox=TRUE,pretty=TRUE)
message('PASS: ',n,' fresh prediction-only allocations')
