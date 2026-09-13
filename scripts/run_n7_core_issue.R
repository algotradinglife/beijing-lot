# Offline, prediction-only entry: frozen bundle, explicit config, new output, Python.
args<-commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==4L,!file.exists(args[3]))
for(path in c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
              'r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_core_plan.R',
              'r/n7_core_issue.R'))source(path)
runtime<-jsonlite::fromJSON('config/n7_joint_runtime.json',simplifyVector=FALSE)
stopifnot(as.character(getRversion())==runtime$R,
 all(vapply(names(runtime$r_packages),function(p)
   as.character(utils::packageVersion(p))==runtime$r_packages[[p]],logical(1))))
bundle<-jsonlite::fromJSON(gzfile(args[1]),simplifyVector=FALSE)
config<-jsonlite::fromJSON(args[2],simplifyVector=FALSE)
result<-n7_core_issue(bundle,bundle$cutoffs,config,args[4])
result$runtime<-runtime
jsonlite::write_json(result,args[3],auto_unbox=TRUE,digits=NA,null='null',na='null',matrix='rowmajor')
