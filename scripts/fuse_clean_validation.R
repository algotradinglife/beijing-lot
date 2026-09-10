# Fixed50/50 expert fusion -> model/market factors, no target labels.
args <- commandArgs(TRUE)
if(length(args)!=2) stop('Supply study and project Python')
study <- args[1];python <- args[2]
path <- file.path(study,'factors.json')
if(file.exists(path)) stop('Immutable factors already exist')
modules <- c('python_bridge','probability_exploration','fundamentals_score_shape','fundamentals_score_diagnostic',
 'fundamentals_signal_rate_projection','fundamentals_ev_returns')
for(m in modules) source(paste0('r/',m,'.R'))
receipt <- jsonlite::read_json(file.path(study,'signals/receipt.json'))
for(p in names(receipt$files)) stopifnot(identical(digest::digest(file=p,algo='sha256'),receipt$files[[p]]))
prepared <- jsonlite::read_json(file.path(study,'prepared.json'))
all <- list()
for(issue in prepared$receipt$contract$issues) {
 x <- jsonlite::read_json(file.path(study,'projected',paste0(issue,'.json')),simplifyVector=TRUE)
 signals <- jsonlite::read_json(file.path(study,'signals',paste0(issue,'.json')),simplifyVector=TRUE)
 stopifnot(identical(signals$projected_sha256,digest::digest(file=file.path(study,'projected',paste0(issue,'.json')),algo='sha256')))
 if (!length(signals$rows)) next
 sig <- tibble::as_tibble(signals$rows) |> dplyr::mutate(issue=issue_code)
 stopifnot(all(sig$expert_version_raw=='0.1.0'),all(sig$expert_version_calibrated=='1.1.0'),all(sig$draw_weight==.5))
 predictions <- dplyr::transmute(sig,issue,slot,provider_id,draw_probability=draw_target_probability)
 adjusted <- signal_rate_score_choices(x$control,predictions,sig,x$cutoffs,.5)
 factors <- ev_candidate_factors(adjusted,x$market,python,getwd())
 all[[issue]] <- dplyr::select(factors,issue,slot,provider_id,home,away,handicap,p_W,p_D,p_L,q_W,q_D,q_L)
 cat('FUSED',issue,nrow(factors),'\n');flush.console()
}
code <- c(paste0('r/',modules,'.R'),'scripts/fuse_clean_validation.R')
jsonlite::write_json(list(rows=dplyr::bind_rows(all),cutoffs=prepared$receipt$cutoffs,contract=prepared$receipt$contract,
 source_hashes=list(prepared=digest::digest(file=file.path(study,'prepared.json'),algo='sha256'),
 projected=digest::digest(file=file.path(study,'projected/receipt.json'),algo='sha256'),
 signals=digest::digest(file=file.path(study,'signals/receipt.json'),algo='sha256')),
 implementation=as.list(stats::setNames(vapply(code,digest::digest,character(1),file=TRUE,algo='sha256'),code))),
 path,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
