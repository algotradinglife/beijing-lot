args <- commandArgs(TRUE);stopifnot(length(args)==1L)
root <- normalizePath(args[1],mustWork=TRUE);setwd(root)
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
dll <- getLoadedDLLs()[['beidan']]
stopifnot(length(getDLLRegisteredRoutines(dll)$.Call)>0L)
pm <- matrix(rep(c(.6,.25,.15),2),nrow=2,byrow=TRUE)
u <- beidan:::ComponentUnionKernel(list(c(A=1L),c(B=1L)),c('A','B'),pm)
stopifnot(abs(u-.84)<1e-12,
 identical(beidan:::ComponentUnionKernelIdentity(),beidan:::.ParlayKernelSourceHash()))
print(u);print(dll[['path']]);print(beidan:::ComponentUnionKernelIdentity())
print(sessionInfo())
deps <- strsplit(utils::packageDescription('beidan')$Imports,',')[[1]]
deps <- trimws(sub('\\s*\\(.*','',deps))
print(tibble::tibble(package=deps,version=vapply(deps,function(p)as.character(utils::packageVersion(p)),character(1))))
print(system2(file.path(root,'.venv/bin/python'),'--version',stdout=TRUE))
