# From repository root: STUDY SQLITE PYTHON. Read-only DB; derived JSON output.
args <- commandArgs(TRUE)
if(length(args)!=3L) stop('Usage: STUDY SQLITE PYTHON')
for(p in c('python_bridge','nowscore_query','fundamentals_returns','fundamentals_n7_baseline','fundamentals_n7_selection')) source(paste0('r/',p,'.R'))
receipt <- n7_selection_r_receipt(getwd())
x <- settle_n7_baseline_study(args[1],args[2],args[3],getwd(),
                             settlement_module='src.fundamentals_n7_selection',settlement_function='settle_n7_selection')
stopifnot(identical(receipt,n7_selection_r_receipt(getwd())))
x$selection_r_implementation <- receipt
x$contract_sha256 <- digest::digest(file=file.path(args[1],'contract.json'),algo='sha256')
jsonlite::write_json(x,file.path(args[1],'settlement.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null')
y <- n7_selection_report(args[1],getwd())
jsonlite::write_json(y,file.path(args[1],'summary.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null')
print(y$summary,width=Inf)
