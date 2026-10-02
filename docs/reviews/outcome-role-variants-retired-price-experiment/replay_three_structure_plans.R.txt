# Verify frozen source/input identities before replaying the #543 delivery.
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=4L || !args[[1]] %in% c('verify','replay')) {
  stop('Usage: Rscript r/replay_three_structure_plans.R verify|replay RECEIPT_JSON INPUT_RDS OUTPUT_RDS')
}
receipt <- jsonlite::read_json(args[[2]],simplifyVector=TRUE)
stopifnot(length(receipt$code_hashes)>0L)
for (path in names(receipt$code_hashes)) {
  if (!file.exists(path) || !identical(digest::digest(file=path,algo='sha256'),receipt$code_hashes[[path]])) {
    stop('Frozen implementation mismatch: ',path)
  }
}
if (!identical(digest::digest(file=args[[3]],algo='sha256'),receipt$input_hash)) {
  stop('Frozen input mismatch')
}
if (args[[1]]=='replay') {
  status <- system2(file.path(R.home('bin'),'Rscript'),
    shQuote(c('r/build_three_structure_plans.R',args[[3]],args[[4]])))
  if (status!=0L) stop('Replay failed with exit code ',status)
} else cat('Frozen source and input identities verified\n')
