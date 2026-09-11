# Read-only frozen N7 attribution; no fitting or strategy changes.
args <- commandArgs(TRUE)
stopifnot(length(args)==2)
study <- args[1];out <- args[2]
if(dir.exists(out)) stop('New immutable output directory required')
source('r/fundamentals_pure_report.R')
source('r/fundamentals_missed_issues.R')
verified <- read_pure_baseline_report(study,FALSE)
receipt <- verified$receipt
paths <- names(receipt$source_hashes)
audit_path <- paths[grepl('settlement-audit.json$',paths)]
stopifnot(length(audit_path)==1)
audit <- tibble::as_tibble(jsonlite::read_json(audit_path,simplifyVector=TRUE)$rows)
plans <- list.files(file.path(study,'plans'),full.names=TRUE,pattern='json.gz$')
legs <- list()
for(path in plans) {
 z <- jsonlite::fromJSON(gzfile(path),simplifyVector=TRUE)$D2_U6_P5_BASE$plan
 legs[[path]] <- tibble::as_tibble(z$legs)
}
x <- missed_issue_diagnostics(dplyr::bind_rows(legs),audit)
reference <- verified$result$rows |> dplyr::filter(policy=='D2_U6_P5_BASE')
check <- dplyr::left_join(x$issues,reference,by='issue',relationship='one-to-one')
stopifnot(nrow(check)==48,all(check$winning_groups==check$hits))
dir.create(out,recursive=TRUE)
for(n in names(x)) readr::write_csv(x[[n]],file.path(out,paste0(n,'.csv')))
files <- c(plans,audit_path,file.path(study,c('results.json','plans-frozen.json')),
           'r/fundamentals_missed_issues.R','scripts/diagnose_missed_issues.R')
jsonlite::write_json(list(scope='EXPOSED_ATTRIBUTION_NOT_LEARNING',source=study,
 hashes=as.list(stats::setNames(vapply(files,digest::digest,character(1),file=TRUE,algo='sha256'),files))),
 file.path(out,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
print(x$issues |> dplyr::summarise(issues=dplyr::n(),missed=sum(whole_issue_missed),
  missed_one_away=sum(whole_issue_missed & nearest_misses==1),
  missed_two_plus=sum(whole_issue_missed & nearest_misses>=2)))
print(x$groups |> dplyr::inner_join(dplyr::filter(x$issues,whole_issue_missed) |> dplyr::select(issue),by='issue') |>
 dplyr::summarise(groups=dplyr::n(),single_error=sum(single_misses>0),double_error=sum(double_misses>0),
                 single_only=sum(single_misses>0 & double_misses==0),double_only=sum(double_misses>0 & single_misses==0)))
