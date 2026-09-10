# Run from project root; args: frozen study directory, SQLite path, project Python.
# Reads the database through the authoritative R API; writes derived JSON only.
args <- commandArgs(TRUE)
if (length(args) != 3L) stop('Usage: Rscript scripts/settle_fundamentals_n7_baseline.R STUDY SQLITE PYTHON')
for (p in c('python_bridge','nowscore_query','fundamentals_returns','fundamentals_n7_baseline')) source(paste0('r/',p,'.R'))
x <- settle_n7_baseline_study(args[1],args[2],args[3],getwd())
jsonlite::write_json(x,file.path(args[1],'settlement.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null')
training <- jsonlite::read_json('data/derived/fundamentals_417/cv-thirtytwo-test-sixteen-v1/contract.json')$training_issues
summary <- n7_baseline_summary(x$results,unlist(training),getwd())
jsonlite::write_json(summary,file.path(args[1],'summary.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null')
print(summary$summary,width=Inf)
